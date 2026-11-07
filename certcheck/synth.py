"""ML 학습용 합성 데이터 생성.

1) 실제 제품(P1~P3)과 공식 목록 성분으로 합성 제품을 만든다(금지·제한·실리콘 성분 주입, 표방·서류·현지책임자 무작위).
2) 같은 제품의 '지저분한 입력' 판본을 만든다(OCR식 오탈자, CAS·함량 누락).
3) 정답 = 깨끗한 제품에 규칙 엔진을 돌린 등급, 특징 = 지저분한 판본에서 계산한 특징 + 위험 특징.
   → 모델은 '입력이 불완전할 때 실제 등급'을 추정하도록 학습한다. 기준선은 지저분한 입력에 규칙만 돌린 등급.
"""
from __future__ import annotations

import copy
import csv
import json
import random
import re
from datetime import date
from functools import lru_cache
from pathlib import Path

from .classify import PROXY, evaluate
from .names import convert_korean_names, inci_to_kr, kr_dict
from .normalize import norm_inci
from .data import DATA, RegIndex
from .risk import risk_features

_GROUPED = re.compile(r"[|;]|(?<!\d),(?!\d)|,\s")
OCR_SWAPS = [("l", "1"), ("o", "0"), ("rn", "m"), ("m", "rn"), ("i", "l"), ("e", "c"), ("-", ""), (" ", "")]
CLAIM_POOL = ["whitening", "anti_wrinkle", "moisturizing", "natural_origin_ingredients", "cleansing"]
DOC_POOL = ["formula_composition_with_percent", "finished_product_test_report", "label_kr", "msds_kr_en",
            "stability_test", "challenge_test", "pif_draft", "cpsr_signed", "ifra_allergen_statement"]


def typo(s: str, rng: random.Random) -> str:
    if len(s) < 5:
        return s
    r = rng.random()
    if r < 0.4:
        a, b = rng.choice(OCR_SWAPS)
        if a in s.lower():
            i = s.lower().index(a)
            return s[:i] + b + s[i + len(a):]
    if r < 0.7:
        i = rng.randrange(1, len(s) - 1)
        return s[:i] + s[i + 1:]
    i = rng.randrange(1, len(s) - 2)
    return s[:i] + s[i + 1] + s[i] + s[i + 2:]


def pool(reg: RegIndex, juris: str, list_type: str) -> list[tuple[str, list[str], str]]:
    seen, out = set(), []
    for (j, k), rows in reg.by_key.items():
        if j != juris:
            continue
        if _GROUPED.search(k):  # 여러 성분이 묶인 전체 표기 키는 건너뛰고 토큰 키만 쓴다
            continue
        for r in rows:
            if r.list_type == list_type and k not in seen and 4 < len(k) < 60:
                seen.add(k)
                out.append((k, r.cas if len(r.cas) == 1 else [], r.max_conc))
    return out


def safe_pool(reg: RegIndex) -> list[tuple[str, list[str], str]]:
    """일반 성분 후보: 식약처 원료성분사전(15111774)에서 어느 관할의 금지·제한 목록에도 없는 INCI.
    (예전에는 중국 IECIC를 썼으나 운영진 데이터 검토에서 사용 불가 → 제외)"""
    listed = {k for (_, k), rows in reg.by_key.items() if any(r.list_type in ("banned", "restricted") for r in rows)}
    seen, out = set(), []
    for hit in sorted(kr_dict().values(), key=lambda h: h["inci"] or ""):
        name = (hit.get("inci") or "").strip()
        k = norm_inci(name)
        if not (4 < len(k) < 60) or k in listed or k in seen or _GROUPED.search(name):
            continue
        seen.add(k)
        cas = [c for c in re.split(r"[;,/\s]+", hit.get("cas") or "") if c]
        out.append((name, cas if len(cas) == 1 else [], ""))
    return out


def make_products(base: list[dict], reg: RegIndex, n: int, seed: int = 7) -> list[dict]:
    rng = random.Random(seed)
    jur = sorted(j for j in reg.jurisdictions if j != "GLOBAL")
    banned = {j: pool(reg, j, "banned") for j in jur}
    restricted = {j: pool(reg, j, "restricted") for j in jur}
    safe = safe_pool(reg)
    out = []
    for i in range(n):
        p = copy.deepcopy(rng.choice(base))
        p["id"] = f"S{i:05d}"
        p["name_kr"] = f"합성제품{i:05d}"
        # 성분 일부 교체·추가
        ings = p["ingredients"]
        for _ in range(rng.randint(0, 6)):
            name, cas, _ = rng.choice(safe)
            ings.insert(rng.randrange(len(ings) + 1), {"kr": "", "inci": name.title(), "cas": ";".join(cas), "pct": round(rng.uniform(0.01, 3), 3)})
        if rng.random() < 0.25:
            j = rng.choice(jur)
            if banned[j]:
                name, cas, _ = rng.choice(banned[j])
                ings.insert(rng.randrange(len(ings) + 1), {"kr": "", "inci": name, "cas": ";".join(cas), "pct": round(rng.uniform(0.01, 2), 3)})
        if rng.random() < 0.35:
            j = rng.choice(jur)
            if restricted[j]:
                name, cas, mx = rng.choice(restricted[j])
                ings.insert(rng.randrange(len(ings) + 1), {"kr": "", "inci": name, "cas": ";".join(cas), "pct": round(rng.uniform(0.01, 5), 3)})
        if rng.random() < 0.2:
            ings.append({"kr": "", "inci": rng.choice(["Cyclopentasiloxane", "Cyclohexasiloxane", "Cyclotetrasiloxane"]), "pct": round(rng.uniform(0.05, 3), 2)})
        p["application"] = rng.choice(["leave_on", "rinse_off"])
        p["claims"] = rng.sample(CLAIM_POOL, rng.randint(0, 3))
        p["functional_kr"] = [c for c in p["claims"] if c in ("whitening", "anti_wrinkle")]
        p["documents"] = rng.sample(DOC_POOL, rng.randint(0, len(DOC_POOL)))
        # 실제 전성분 표시처럼 1% 초과 성분은 함량 많은 순으로 먼저, 1% 이하는 그 뒤(넣은 순서 유지)
        high = sorted((i for i in ings if (i.get("pct") or 0) > 1), key=lambda i: -i["pct"])
        ings[:] = high + [i for i in ings if not (i.get("pct") or 0) > 1]
        p["formula_known"] = rng.choice(["full_with_concentration", "full_with_concentration", "ingredients_only_no_concentration"])
        if p["formula_known"] != "full_with_concentration":
            for ing in ings:
                ing["pct"] = None
        out.append(p)
    return out


@lru_cache(maxsize=1)
def _ocr_variants() -> dict[str, list[str]]:
    path = DATA / "aihub" / "633_kr_variants.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def noisy(p: dict, rng: random.Random, level: float) -> dict:
    """실제 입력에서 생기는 오류를 흉내 낸다: 영문 오탈자, CAS·함량 누락, 한글 성분명 입력과 포장 OCR 변형 표기.
    한글 입력은 서비스와 같은 변환(식약처 원료성분 사전)을 거치고, 사전에 없는 변형은 한글로 남는다."""
    q = copy.deepcopy(p)
    to_kr = inci_to_kr()
    variants = _ocr_variants()
    for ing in q["ingredients"]:
        kr = to_kr.get(norm_inci(ing.get("inci")))
        if kr and rng.random() < 0.15 * level:
            name = kr
            if rng.random() < 0.4:
                name = rng.choice(variants[kr]) if variants.get(kr) else (kr[: max(2, len(kr) - 2)] if len(kr) > 4 else kr)
            ing["inci"], ing["cas"] = name, None
        elif rng.random() < 0.12 * level and ing.get("inci"):
            ing["inci"] = typo(ing["inci"], rng)
        if rng.random() < 0.5 * level:
            ing["cas"] = None
        if rng.random() < 0.3 * level:
            ing["pct"] = None
    convert_korean_names(q["ingredients"])
    return q


def build_dataset(cards: list[dict], base: list[dict], company: dict, reg: RegIndex, attrs: dict, n: int, out: Path,
                  eval_date: date | None = None, seed: int = 7) -> Path:
    rng = random.Random(seed + 1)
    prods = make_products(base, reg, n, seed)
    cards = [c for c in cards if c.get("kind") != "company_certification"]
    cert_ids = sorted(c["id"] for c in cards)
    rows = []
    for p in prods:
        level = rng.choice([0.0, 0.5, 1.0, 1.5])
        q = noisy(p, rng, level)
        risk_cache: dict[str, dict] = {}
        for c in cards:
            clean = evaluate(c, p, company, reg, attrs, eval_date)
            dirty = evaluate(c, q, company, reg, attrs, eval_date)
            juris = PROXY.get((c.get("ingredient_rules") or "none").upper(), (c.get("ingredient_rules") or "none").upper())
            if juris not in risk_cache:
                risk_cache[juris] = risk_features(q, reg, juris)
            rf = risk_cache[juris]
            row = {"sample": p["id"], "cert_id": c["id"], "noise_level": level, "label": clean.status, "rule_on_noisy": dirty.status}
            row.update({f"f_{k}": v for k, v in (dirty.features or {}).items()})
            row.update({f"r_{k}": v for k, v in rf.items()})
            row.update({f"cert_{cid}": int(cid == c["id"]) for cid in cert_ids})
            rows.append(row)
    out.parent.mkdir(parents=True, exist_ok=True)
    keys = sorted({k for r in rows for k in r}, key=lambda k: (k not in ("sample", "cert_id", "noise_level", "label", "rule_on_noisy"), k))
    with out.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=keys, restval=0)
        w.writeheader()
        w.writerows(rows)
    return out


def main() -> None:
    """실행: python -m certcheck.synth --n 600 --out out/private/ml/dataset.csv (기본 바탕 = 마스킹된 데모 제품)"""
    import argparse
    import json

    from .data import DATA, load_attributes, load_cards, load_reg_index

    ap = argparse.ArgumentParser()
    ap.add_argument("--base", type=Path, default=DATA / "public" / "products" / "demo_products.json")
    ap.add_argument("--certs", type=Path, default=DATA / "certs")
    ap.add_argument("--n", type=int, default=600)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--date", type=lambda x: date.fromisoformat(x), default=date.today())
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    doc = json.loads(a.base.read_text(encoding="utf-8"))
    base = [p for p in doc["products"] if p.get("ingredients")]
    out = build_dataset(load_cards(a.certs), base, doc.get("company", {}), load_reg_index(), load_attributes(), a.n, a.out,
                        a.date, a.seed)
    print(out)


if __name__ == "__main__":
    main()
