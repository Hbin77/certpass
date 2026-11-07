"""한글 성분명 ↔ 영문 INCI (식약처 화장품 원료성분정보, data.go.kr 15111774).

API(판정 요청)와 학습 데이터 생성(synth)이 같은 변환을 쓰도록 한곳에 둔다.
"""
from __future__ import annotations

import re
from functools import lru_cache

from .data import kr_key, load_kr_dict
from .normalize import norm_inci

HANGUL = re.compile(r"[가-힣]")
SOURCE = "식약처 화장품 원료성분정보(data.go.kr 15111774)"


@lru_cache(maxsize=1)
def kr_dict() -> dict[str, dict]:
    return load_kr_dict()


@lru_cache(maxsize=1)
def inci_to_kr() -> dict[str, str]:
    """영문 INCI 키 → 한글 표준명(합성 데이터에서 '한글로 적은 입력'을 만들 때 쓴다)."""
    out: dict[str, str] = {}
    for hit in kr_dict().values():
        out.setdefault(norm_inci(hit["inci"]), hit["kr_name"])
    return out


_CHO = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
_JUNG = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"
_JONG = " ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ"


def jamo(s: str) -> str:
    """한글 음절을 자모로 분해('셀' → 'ㅅㅔㄹ'). 자모 단위 편집거리는 음절 단위보다 OCR·오타 한 획 차이를 작게 본다
    (노강호 외 2010 「음소의 분류 체계를 이용한 한글 편집거리 알고리즘」, 박승현 외 2017 「한글 편집거리 알고리즘을 이용한 한국어 철자오류 교정방법」)."""
    out = []
    for ch in s:
        c = ord(ch) - 0xAC00
        if 0 <= c < 11172:
            out += [_CHO[c // 588], _JUNG[(c % 588) // 28], _JONG[c % 28].strip()]
        else:
            out.append(ch)
    return "".join(out)


@lru_cache(maxsize=1)
def _jamo_index() -> tuple[list[str], list[str]]:
    keys = list(kr_dict())
    return keys, [jamo(k) for k in keys]


@lru_cache(maxsize=20000)
def kr_fuzzy(name: str, threshold: float = 0.88) -> dict | None:
    """사전에 정확히 없는 한글 성분명을 가장 가까운 식약처 표준명에 맞춘다(OCR 오독·오타·글자 잘림).
    - 자모 단위 유사도 threshold 이상, 또는 표준명의 앞부분이 잘린 꼴(3글자 이상, 2글자 이내로 잘림)
    - 결과는 '의심 후보'다. 판정 엔진은 이 후보로 등급을 확정하지 않고 '확인 필요'로만 쓴다."""
    from rapidfuzz import fuzz, process
    k = kr_key(name)
    if not k or k in kr_dict() or len(k) < 3:
        return None
    keys, jk = _jamo_index()
    hit, score, idx = process.extractOne(jamo(k), jk, scorer=fuzz.ratio)
    best = {"kr_name": kr_dict()[keys[idx]]["kr_name"], "inci": kr_dict()[keys[idx]]["inci"], "similarity": round(score / 100, 2), "how": "자모 유사"}
    if score / 100 >= threshold:
        return best
    pref = [x for x in keys if x.startswith(k) and 0 < len(x) - len(k) <= 2]
    if len(pref) == 1:
        h = kr_dict()[pref[0]]
        return {"kr_name": h["kr_name"], "inci": h["inci"], "similarity": round(len(k) / len(pref[0]), 2), "how": "앞부분 일치(잘림)"}
    return None


def convert_korean_names(ingredients: list[dict]) -> dict:
    """한글로 적은 성분명을 영문 INCI로 바꾼다(제자리 수정). 못 찾은 이름은 그대로 두고 목록으로 알린다."""
    converted, unmatched = [], []
    for ing in ingredients:
        name = ing.get("inci") or ""
        if not HANGUL.search(name):
            continue
        hit = kr_dict().get(kr_key(name))
        if hit:
            ing["kr"] = ing.get("kr") or name
            ing["inci"] = hit["inci"]
            ing["cas"] = ing.get("cas") or hit["cas"]
            converted.append({"kr": name, "inci": hit["inci"]})
        else:
            unmatched.append(name)
    return {"converted": converted, "unmatched": unmatched, "source": SOURCE}
