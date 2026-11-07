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
