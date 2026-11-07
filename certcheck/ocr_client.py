"""포장 사진 OCR: AIStream에 서빙한 7팀 포장 OCR 모델(글자 위치 찾기 + 글자 읽기)을 부르고, 읽은 성분명을 표준명에 맞춘다.

환경변수 (서버 설정으로만 받음)
- CERTCHECK_OCR_URL: OCR 서빙의 /predict 전체 주소. 없으면 사진 입력 기능을 끈다(503)
- CERTCHECK_OCR_TIMEOUT: 초(기본 40). 공개 주소 프록시가 60초에 끊으므로 그보다 짧게. 늦은 응답은 다시 보내지 않는다
성분명 맞추기: OCR이 읽은 글자를 식약처 원료성분 사전(한글↔INCI)의 표준 한글명과 비교한다.
정확히 같으면 exact, 글자 유사도 88 이상이면 fuzzy(사용자 확인 필요), 아니면 unknown.
"""
from __future__ import annotations

import json
import math
import os
import re
import statistics
import time
import urllib.error
import urllib.request
import uuid
from functools import lru_cache

from rapidfuzz import fuzz, process

from .data import kr_key
from .names import kr_dict

FUZZY_CUTOFF = 88
JUNK = re.compile(r"^[^0-9A-Za-z가-힣(]+|[^0-9A-Za-z가-힣)\]]+$")  # 목록 기호·괄호 조각 같은 앞뒤 잡문자
LETTER = re.compile(r"[A-Za-z가-힣]")


def enabled() -> bool:
    return bool(os.environ.get("CERTCHECK_OCR_URL"))


def _multipart(field: str, filename: str, content_type: str, data: bytes) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    head = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{field}\"; filename=\"{filename}\"\r\n"
            f"Content-Type: {content_type}\r\n\r\n").encode()
    return head + data + f"\r\n--{boundary}--\r\n".encode(), f"multipart/form-data; boundary={boundary}"


RETRY_STATUS = (500, 502, 503, 504)
RETRY_WAIT = (3.0, 6.0)  # 서빙 replica가 다시 뜨는 동안(수 초) 기다렸다 다시 보낸다


def call_ocr(image: bytes, content_type: str) -> dict:
    """OCR 서빙 호출. 서빙이 잠깐 내려가 500·502·503·504를 주면 최대 2번 다시 보낸다(사진 문제 4xx는 바로 실패)."""
    body, ctype = _multipart("file", "package.jpg", content_type, image)
    timeout = float(os.environ.get("CERTCHECK_OCR_TIMEOUT", "40"))
    for attempt in range(len(RETRY_WAIT) + 1):
        req = urllib.request.Request(os.environ["CERTCHECK_OCR_URL"], data=body, headers={"Content-Type": ctype}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code not in RETRY_STATUS or attempt == len(RETRY_WAIT):
                raise
        except TimeoutError:
            raise  # 응답이 늦으면 다시 보내지 않는다(공개 주소 프록시가 60초에 끊으므로 화면이 먼저 끊기지 않게)
        except urllib.error.URLError as e:
            if isinstance(e.reason, TimeoutError) or attempt == len(RETRY_WAIT):
                raise
        time.sleep(RETRY_WAIT[attempt])
    raise RuntimeError("unreachable")


@lru_cache(maxsize=1)
def _kr_names() -> tuple[list[str], dict[str, dict]]:
    by_name: dict[str, dict] = {}
    for hit in kr_dict().values():
        by_name.setdefault(hit["kr_name"], hit)
    return list(by_name), by_name


def match_name(raw: str) -> dict:
    """OCR이 읽은 성분명 하나를 표준명에 맞춘다."""
    hit = lookup(raw)
    if hit:
        return {"raw": raw, "kr": hit["kr_name"], "inci": hit["inci"], "match": "exact", "score": 100}
    names, by_name = _kr_names()
    best = process.extractOne(raw, names, scorer=fuzz.ratio, score_cutoff=FUZZY_CUTOFF) if len(raw) >= 3 else None
    if best:
        h = by_name[best[0]]
        return {"raw": raw, "kr": h["kr_name"], "inci": h["inci"], "match": "fuzzy", "score": round(best[1])}
    return {"raw": raw, "kr": None, "inci": None, "match": "unknown", "score": 0}


INCI_KEY = re.compile(r"[^a-z0-9]")


def inci_key(name: str) -> str:
    """영문 INCI 대조 키: 소문자·영숫자만(띄어쓰기·괄호·쉼표·하이픈 무시)."""
    return INCI_KEY.sub("", (name or "").lower())


@lru_cache(maxsize=1)
def _inci_index() -> dict[str, dict]:
    """영문 INCI → 사전 항목(식약처 원료성분 사전의 영문명). 짧은 키(4글자 미만)는 오탐이 많아 뺀다."""
    out: dict[str, dict] = {}
    for hit in kr_dict().values():
        k = inci_key(hit.get("inci"))
        if len(k) >= 4:
            out.setdefault(k, hit)
    return out


def lookup(text: str) -> dict | None:
    """한글 표준명·이명 또는 영문 INCI로 사전 항목을 찾는다(정확 일치)."""
    return kr_dict().get(kr_key(text)) or _inci_index().get(inci_key(text))


def segment(chunk: str, max_span: int = 6, prefer_long: bool = False) -> list[str]:
    """쉼표가 빠져 붙은 덩어리('세테아릴알코올 잔탄검')를 띄어쓰기 단위로 나눠 사전 이름이 가장 많이 맞는 조합으로 쪼갠다.
    줄바꿈으로 잘린 이름('다이프로필렌글 라이콜')은 이어 붙여 찾고, 사전에 없는 조각은 이웃끼리 다시 붙여 하나로 남긴다.
    (ocr/e2e_eval.py의 segment와 같은 규칙 — 평가 수치와 서비스 동작을 맞춘다)
    prefer_long: 맞은 이름 개수 대신 사전 이름으로 덮은 낱말 수를 최대로 하고, 같으면 조각 수가 적은 쪽을 고른다.
    표 형식 문서에서 '마그네슘 알루미늄실리케이트'가 '마그네슘'+'알루미늄실리케이트'로 쪼개지지 않게 한다(scan_lines용)."""
    toks = [t for t in (JUNK.sub("", x) for x in chunk.split()) if t][:400]
    n = len(toks)
    zero, none = ((0, 0) if prefer_long else 0), ((-1, 0) if prefer_long else -1)
    best = [(zero, -1, False)] + [(none, -1, False)] * n  # (점수, 이전 위치, 이번 조각이 사전 이름인가)
    for i in range(1, n + 1):
        for j in range(max(0, i - max_span), i):
            hit = lookup(" ".join(toks[j:i])) is not None or kr_key("".join(toks[j:i])) in kr_dict()
            if prefer_long:
                score = (best[j][0][0] + (i - j if hit else 0), best[j][0][1] - (1 if hit else 0))
            else:
                score = best[j][0] + (1 if hit else 0)
            if (hit or i - j == 1) and (score > best[i][0] or (score == best[i][0] and best[i][1] < 0)):
                best[i] = (score, j, hit)
    pieces, i = [], n
    while i > 0:
        _, j, hit = best[i]
        joined = " ".join(toks[j:i])
        pieces.append(((joined if _inci_index().get(inci_key(joined)) else "".join(toks[j:i])) if hit else joined, hit))
        i = j
    out, buf = [], []
    for text, hit in reversed(pieces):
        if hit:
            if buf:
                out.append(" ".join(buf))
                buf = []
            out.append(text)
        else:
            buf.append(text)
    if buf:
        out.append(" ".join(buf))
    return [x for x in out if len(x) >= 2 and LETTER.search(x)]


def rejoin_digit_commas(raw_items: list[str], text: str) -> list[str]:
    """서빙은 전성분을 쉼표로 자르므로 '1,2-헥산다이올'이 '2-헥산다이올'로 남는다(앞 '1'은 버려짐).
    원문 줄에 '숫자,' + 그 조각이 있으면 숫자를 되붙인다."""
    flat = re.sub(r"\s+", "", text or "")
    out = []
    for raw in raw_items:
        r = raw.strip()
        if re.match(r"\d", r):
            m = re.search(r"((?:\d+,)+)" + re.escape(re.sub(r"\s+", "", r)), flat)
            if m:
                r = m.group(1) + re.sub(r"\s+", "", r)
        out.append(r)
    return out


def match_all(raw_items: list[str], text: str = "") -> list[dict]:
    """OCR 전성분 덩어리 목록 → 표준명 맞추기 결과(쪼개기 포함, 같은 성분은 한 번만). text는 숫자 쉼표를 되붙일 원문."""
    out, seen = [], set()
    for raw in rejoin_digit_commas(raw_items, text) if text else raw_items:
        clean = JUNK.sub("", raw)
        m = match_name(clean) if clean else None
        parts = [m] if m and m["match"] == "exact" else [match_name(p) for p in segment(raw)]
        for p in parts:
            key = p["kr"] or p["raw"]
            if key not in seen:
                seen.add(key)
                out.append(p)
    return out


MIN_SCAN = 3  # 줄 단위 대조는 정확히 맞은 성분이 이 개수 이상일 때만 쓴다(앞면 광고 문구 한두 단어로 목록을 만들지 않게)


# 줄 단위 대조에서 버리는 사전 이름: 제품명('…크림')이나 잘린 복합 성분명('마그네슘 알루미늄실리케이트'의 앞 조각)에서
# 홀로 잡히는 일반 낱말. '전성분' 구역 안에서는 그대로 쓴다
SCAN_SKIP = {"크림", "글라이콜", "마그네슘", "알루미늄"}


def scan_lines(lines: list[str]) -> list[dict]:
    """표 형식 문서(위탁사 전성분표 등)용: 모든 줄을 사전과 대조해 정확히 맞는 성분명만 모은다.
    한 줄에 성분명·CAS·기능이 섞여 있어도 사전 이름 조각만 골라낸다(맞지 않는 조각은 버림 — 오탐 방지)."""
    out, seen = [], set()
    for line in lines:
        for piece in segment(line, prefer_long=True):
            hit = lookup(piece)
            if hit and hit["kr_name"] not in seen and hit["kr_name"] not in SCAN_SKIP:
                seen.add(hit["kr_name"])
                out.append({"raw": piece, "kr": hit["kr_name"], "inci": hit["inci"], "match": "exact", "score": 100})
    return out


def choose(section_items: list[dict], lines: list[str]) -> tuple[list[dict], str]:
    """전성분 구역 추출과 줄 단위 사전 대조 중 하나를 고른다.
    줄 단위 대조는 문서 전체(광고 문구 포함)를 보므로 구역을 제대로 찾았으면 구역 쪽이 낫다.
    줄 단위 대조로 정확히 맞은 성분이 구역의 2배 이상이면 구역을 잘못 찾았다고(제목·표 머리) 보고 바꾼다.
    구역 결과에 '사전에 없는 조각'이 정확 일치보다 많으면(표의 CAS 번호·기능·원료 상품명이 섞인 경우) 줄 단위 대조가
    그 수의 80% 이상을 찾을 때 바꾼다(확인할 잡조각 수십 개보다 깨끗한 목록이 낫다)."""
    exact = sum(i["match"] == "exact" for i in section_items)
    unknown = sum(i["match"] == "unknown" for i in section_items)
    scanned = scan_lines(lines)
    if len(scanned) >= MIN_SCAN and (len(scanned) >= 2 * exact or (unknown > exact and 5 * len(scanned) >= 4 * exact)):
        return scanned, "lines"
    return section_items, "section"


def estimate_skew(words: list[dict], min_pairs: int = 10) -> float | None:
    """글자 상자로 사진 기울기(도)를 잰다. 같은 줄에서 바로 오른쪽에 있는 비슷한 높이의 단어 쌍마다
    중심을 잇는 선의 각도를 재고 중앙값을 쓴다. 화면 좌표(아래가 +)라 오른쪽으로 갈수록 올라가면 음수.
    서빙의 상자는 축 정렬이라 실제보다 조금 작게 나온다(4° → 약 3.8°). 쌍이 적으면 None."""
    boxes = [w["box"] for w in words[:600] if len(w.get("box") or []) == 4
             and w["box"][2] > w["box"][0] and w["box"][3] > w["box"][1]]
    angles = []
    for a in boxes:
        ha, cya, cxa = a[3] - a[1], (a[1] + a[3]) / 2, (a[0] + a[2]) / 2
        best = None
        for b in boxes:
            if b is a:
                continue
            hb = b[3] - b[1]
            h = min(ha, hb)
            gap = b[0] - a[2]
            if max(ha, hb) > 2 * h or not -0.3 * h <= gap <= 2.5 * h or abs((b[1] + b[3]) / 2 - cya) > 0.7 * h:
                continue
            if best is None or gap < best[0]:
                best = (gap, b)
        if best:
            b = best[1]
            dx = (b[0] + b[2]) / 2 - cxa
            if dx > 0:
                angles.append(math.degrees(math.atan2((b[1] + b[3]) / 2 - cya, dx)))
    return round(statistics.median(angles), 2) if len(angles) >= min_pairs else None


# 흐린 사진 기준은 모델마다 확신도 분포가 달라 서버 설정으로 둔다(모델을 바꿀 때 같이 바꾼다)
# rec2(기존): 0.8·0.4 / rec4(망가뜨리기 증강): 0.9·0.4 — 학습에 없던 제품 사진 150장×3상태 실측에서
# 재현율 0.6 미만 사진 52장 중 39장을 잡고, 0.8 이상 사진 365장 중 6장(1.6%)만 잘못 알린다
LOW_CONF = float(os.environ.get("CERTCHECK_OCR_LOW_CONF", "0.8"))  # 단어 확신도가 이보다 낮으면 '흐릿한 단어'
BLURRY_SHARE = float(os.environ.get("CERTCHECK_OCR_BLURRY_SHARE", "0.4"))  # 흐릿한 단어 비율이 이 이상이면 알린다


def photo_quality(words: list[dict]) -> dict:
    """글자가 작거나 흐리게 찍힌 사진 판별. 실측(자사 서류·AI Hub 사진을 해상도·JPEG 화질별로): 잘 읽힌 사진은
    확신 0.8 미만 단어가 17% 이하, 결과가 무너진 사진은 60% 이상(긴 변 1000px·JPEG 40, 700px 등)."""
    confs = [float(w.get("conf") or 0) for w in words if w.get("text")]
    heights = sorted(w["box"][3] - w["box"][1] for w in words if len(w.get("box") or []) == 4)
    share = round(sum(c < LOW_CONF for c in confs) / len(confs), 2) if confs else None
    return {"low_conf_share": share, "text_px": heights[len(heights) // 2] if heights else None,
            "blurry": bool(len(confs) >= 30 and share is not None and share >= BLURRY_SHARE)}


def read_package(image: bytes, content_type: str) -> dict:
    """사진 → OCR 서빙 → 전성분 목록과 표준명 맞추기 결과."""
    res = call_ocr(image, content_type)
    lines = res.get("lines") or []
    texts = [ln.get("text", "") for ln in lines]
    items, method = choose(match_all(res.get("ingredients") or [], "\n".join(texts)), texts)
    return {
        "ingredients": items,
        "found_section": bool(items),
        "method": method,  # section: '전성분' 표기 구역, lines: 문서 전체 줄을 사전과 대조(표 형식 문서)
        "text": res.get("text", ""),
        "lines": [{"text": ln.get("text", ""), "conf": ln.get("conf")} for ln in lines][:400],
        "words": len(res.get("words") or []),
        "skew": estimate_skew(res.get("words") or []),
        "quality": photo_quality(res.get("words") or []),  # 화면이 1° 이상이면 반대로 돌려 한 번 더 읽는다
        "model": res.get("model"),
        "counts": {k: sum(i["match"] == k for i in items) for k in ("exact", "fuzzy", "unknown")},
    }
