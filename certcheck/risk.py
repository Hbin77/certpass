"""ML 보정용 위험 특징: 규칙 엔진이 '정확히 일치'로만 판정하며 놓치는 위험을 수치로 만든다.

- 각 성분 표기와 관할별 금지·제한 목록 사이의 최대 유사도(rapidfuzz)
- 정확 일치하지 않았지만 금지 목록과 매우 비슷한(0.85 이상) 성분 수
- 함량 미상 성분 비율, CAS 누락 비율
"""
from __future__ import annotations

import csv
import re
from functools import lru_cache

from rapidfuzz import fuzz, process

from .classify import parse_pcts
from .data import DATA, RegIndex
from .normalize import norm_inci, split_cas


@lru_cache(maxsize=None)
def _names(reg_id: int, juris: str, list_type: str) -> tuple[str, ...]:
    reg = _REG[reg_id]
    names = {k for (j, k), rows in reg.by_key.items() if j == juris and any(r.list_type == list_type for r in rows)}
    return tuple(sorted(n for n in names if len(n) > 3))


_REG: dict[int, RegIndex] = {}
HANGUL = re.compile(r"[가-힣]")
CMR = {"H340", "H341", "H350", "H351", "H360", "H361", "H362"}
SENSITIZER = {"H317", "H334"}


@lru_cache(maxsize=1)
def _country_bans() -> dict[str, int]:
    """식약처 화장품 규제정보 요약: 성분 키 → 금지 국가 수."""
    path = DATA / "kr" / "식약처_국가별규제요약.csv"
    out: dict[str, int] = {}
    if path.exists():
        with path.open(encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                n = len([c for c in re.split(r"[,;]", row.get("banned_in") or "") if c.strip()])
                k = norm_inci(row.get("inci"))
                if k:
                    out[k] = max(out.get(k, 0), n)
    return out


@lru_cache(maxsize=1)
def _ghs_by_cas() -> dict[str, set[str]]:
    """AI Hub 71916 생활화학제품 주성분 건강유해성에서 모은 CAS → GHS 유해·위험 문구 코드."""
    path = DATA / "aihub" / "71916_ghs_by_cas.csv"
    out: dict[str, set[str]] = {}
    if path.exists():
        with path.open(encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                out[row["cas"]] = {c for c in (row.get("ghs_codes") or "").split(";") if c}
    return out


def product_risk(p: dict) -> dict:
    """관할과 무관한 제품 단위 위험 특징."""
    ings = [i for i in p.get("ingredients", []) if i.get("inci")]
    n = max(len(ings), 1)
    bans = _country_bans()
    ghs = _ghs_by_cas()
    ban_counts = [bans.get(norm_inci(i["inci"]), 0) for i in ings]
    codes = [set().union(*[ghs.get(c, set()) for c in split_cas(i.get("cas"))]) if split_cas(i.get("cas")) else set() for i in ings]
    return {
        "n_banned_elsewhere": sum(1 for b in ban_counts if b > 0),
        "max_ban_countries": max(ban_counts, default=0),
        "n_ghs_health": sum(1 for c in codes if any(x.startswith("H3") for x in c)),
        "n_ghs_sensitizer": sum(1 for c in codes if c & SENSITIZER),
        "n_ghs_cmr": sum(1 for c in codes if c & CMR),
        "frac_kr_unmatched": round(sum(1 for i in ings if HANGUL.search(i["inci"])) / n, 3),
    }


def risk_features(p: dict, reg: RegIndex, juris: str) -> dict:
    _REG[id(reg)] = reg
    banned = _names(id(reg), juris, "banned")
    restricted = _names(id(reg), juris, "restricted")
    ings = [i for i in p.get("ingredients", []) if i.get("inci")]
    n = max(len(ings), 1)
    max_b = max_r = 0.0
    near_b = near_r = 0
    unk_limits: list[float] = []  # 함량 미상인 제한 성분의 한도(낮을수록 실제 함량이 한도를 넘을 여지가 큼)
    for ing in ings:
        k = norm_inci(ing["inci"])
        if not k:
            continue
        exact = reg.lookup(juris, ing["inci"], split_cas(ing.get("cas")))
        if exact:
            if ing.get("pct") is None:
                lims = [x for r, _ in exact if r.list_type == "restricted" for x in parse_pcts(r.max_conc)]
                if lims:
                    unk_limits.append(min(lims))
            continue
        if banned:
            _, s, _ = process.extractOne(k, banned, scorer=fuzz.ratio)
            max_b = max(max_b, s / 100)
            near_b += int(s >= 85)
        if restricted:
            _, s, _ = process.extractOne(k, restricted, scorer=fuzz.ratio)
            max_r = max(max_r, s / 100)
            near_r += int(s >= 85)
    return {
        **product_risk(p),
        "max_sim_banned": round(max_b, 3), "n_near_banned": near_b,
        "max_sim_restricted": round(max_r, 3), "n_near_restricted": near_r,
        "frac_pct_missing": round(sum(1 for i in ings if i.get("pct") is None) / n, 3),
        "frac_cas_missing": round(sum(1 for i in ings if not split_cas(i.get("cas"))) / n, 3),
        "n_pct_unknown_limited": len(unk_limits),
        "min_limit_pct_unknown": round(min(unk_limits), 4) if unk_limits else 0.0,
    }
