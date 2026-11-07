"""성분명 정규화와 매칭.

- INCI 표기 차이(대소문자, 괄호 속 일반명, 하이픈/공백, 'Water'↔'Aqua')를 흡수한다.
- CAS는 숫자-숫자-숫자 형식만 골라 비교한다.
"""
from __future__ import annotations

import re
import unicodedata

CAS_RE = re.compile(r"^\d{2,7}-\d{2}-\d$")

# 같은 성분의 대표적 이표기(INCI 국가별 차이 포함)
SYNONYMS = {
    "water": "aqua",
    "aqua/water": "aqua",
    "water/aqua": "aqua",
    "eau": "aqua",
    "fragrance": "parfum",
    "perfume": "parfum",
    "parfum/fragrance": "parfum",
    "fragrance/parfum": "parfum",
    "pinene": "pinene",
    "alpha-pinene": "pinene",
    "beta-pinene": "pinene",
    "alpha-terpinene": "terpinene",
    "terpinene": "terpinene",
    "glycerine": "glycerin",
    "1,2-hexanediol": "1,2-hexanediol",
}


def split_cas(value: str | None) -> list[str]:
    if not value:
        return []
    parts = re.split(r"[;,/\s]+", str(value))
    return [p.strip() for p in parts if CAS_RE.match(p.strip())]


def norm_inci(name: str | None) -> str:
    """INCI를 비교용 키로 바꾼다. 괄호 속 일반명은 제거하되 식물명 본체는 유지한다."""
    if not name:
        return ""
    s = unicodedata.normalize("NFKC", str(name)).lower().strip()
    s = s.replace("’", "'").replace("–", "-").replace("—", "-")
    s = re.sub(r"\((?:[^()]*)\)", " ", s)          # (Orange), (Shea) 같은 일반명 제거
    s = re.sub(r"[\"'®™*]", "", s)
    s = re.sub(r"\s*/\s*", "/", s)
    s = re.sub(r"\s*-\s*", "-", s)
    s = re.sub(r"\s+", " ", s).strip(" .,")
    return SYNONYMS.get(s, s)
