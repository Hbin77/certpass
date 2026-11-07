"""포장 사진 OCR: AIStream에 서빙한 7팀 포장 OCR 모델(글자 위치 찾기 + 글자 읽기)을 부르고, 읽은 성분명을 표준명에 맞춘다.

환경변수 (서버 설정으로만 받음)
- CERTCHECK_OCR_URL: OCR 서빙의 /predict 전체 주소. 없으면 사진 입력 기능을 끈다(503)
- CERTCHECK_OCR_TIMEOUT: 초(기본 40). 공개 주소 프록시가 60초에 끊으므로 그보다 짧게. 늦은 응답은 다시 보내지 않는다
성분명 맞추기: OCR이 읽은 글자를 식약처 원료성분 사전(한글↔INCI)의 표준 한글명과 비교한다.
정확히 같으면 exact, 글자 유사도 88 이상이면 fuzzy(사용자 확인 필요), 아니면 unknown.
"""
from __future__ import annotations

import json
import os
import re
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
    hit = kr_dict().get(kr_key(raw))
    if hit:
        return {"raw": raw, "kr": hit["kr_name"], "inci": hit["inci"], "match": "exact", "score": 100}
    names, by_name = _kr_names()
    best = process.extractOne(raw, names, scorer=fuzz.ratio, score_cutoff=FUZZY_CUTOFF) if len(raw) >= 3 else None
    if best:
        h = by_name[best[0]]
        return {"raw": raw, "kr": h["kr_name"], "inci": h["inci"], "match": "fuzzy", "score": round(best[1])}
    return {"raw": raw, "kr": None, "inci": None, "match": "unknown", "score": 0}


def segment(chunk: str, max_span: int = 6) -> list[str]:
    """쉼표가 빠져 붙은 덩어리('세테아릴알코올 잔탄검')를 띄어쓰기 단위로 나눠 사전 이름이 가장 많이 맞는 조합으로 쪼갠다.
    줄바꿈으로 잘린 이름('다이프로필렌글 라이콜')은 이어 붙여 찾고, 사전에 없는 조각은 이웃끼리 다시 붙여 하나로 남긴다.
    (ocr/e2e_eval.py의 segment와 같은 규칙 — 평가 수치와 서비스 동작을 맞춘다)"""
    keys = kr_dict()
    toks = [t for t in (JUNK.sub("", x) for x in chunk.split()) if t][:60]
    n = len(toks)
    best = [(0, -1, False)] + [(-1, -1, False)] * n  # (맞은 개수, 이전 위치, 이번 조각이 사전 이름인가)
    for i in range(1, n + 1):
        for j in range(max(0, i - max_span), i):
            hit = kr_key("".join(toks[j:i])) in keys
            score = best[j][0] + (1 if hit else 0)
            if (hit or i - j == 1) and (score > best[i][0] or (score == best[i][0] and best[i][1] < 0)):
                best[i] = (score, j, hit)
    pieces, i = [], n
    while i > 0:
        _, j, hit = best[i]
        pieces.append(("".join(toks[j:i]) if hit else " ".join(toks[j:i]), hit))
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


def match_all(raw_items: list[str]) -> list[dict]:
    """OCR 전성분 덩어리 목록 → 표준명 맞추기 결과(쪼개기 포함, 같은 성분은 한 번만)."""
    out, seen = [], set()
    for raw in raw_items:
        clean = JUNK.sub("", raw)
        m = match_name(clean) if clean else None
        parts = [m] if m and m["match"] == "exact" else [match_name(p) for p in segment(raw)]
        for p in parts:
            key = p["kr"] or p["raw"]
            if key not in seen:
                seen.add(key)
                out.append(p)
    return out


def read_package(image: bytes, content_type: str) -> dict:
    """사진 → OCR 서빙 → 전성분 목록과 표준명 맞추기 결과."""
    res = call_ocr(image, content_type)
    items = match_all(res.get("ingredients") or [])
    lines = res.get("lines") or []
    return {
        "ingredients": items,
        "found_section": bool(res.get("ingredients")),
        "text": res.get("text", ""),
        "lines": [{"text": l.get("text", ""), "conf": l.get("conf")} for l in lines][:400],
        "words": len(res.get("words") or []),
        "model": res.get("model"),
        "counts": {k: sum(i["match"] == k for i in items) for k in ("exact", "fuzzy", "unknown")},
    }
