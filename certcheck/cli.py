"""실행: python -m certcheck.cli [--products 경로] [--certs 폴더] [--reg 통합표] [--date 2026-11-07] [--out 폴더]"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import date
from pathlib import Path

from .classify import evaluate_all
from .data import DATA, ROOT, load_attributes, load_cards, load_products, load_reg_index
from .report import write_all


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--products", type=Path, default=DATA / "private" / "products" / "products.json")
    ap.add_argument("--certs", type=Path, default=DATA / "certs")
    ap.add_argument("--reg", type=Path, default=None)
    ap.add_argument("--attrs", type=Path, default=DATA / "ingredients" / "ingredient_attributes.csv")
    ap.add_argument("--date", type=lambda s: date.fromisoformat(s), default=date.today())
    ap.add_argument("--out", type=Path, default=ROOT / "out" / "private")
    a = ap.parse_args()

    products = load_products(a.products)
    cards = load_cards(a.certs)
    reg = load_reg_index(a.reg)
    attrs = load_attributes(a.attrs)
    print(f"제품 {len(products.get('products', []))}개 · 인증 카드 {len(cards)}장 · 성분규제 관할 {sorted(reg.jurisdictions) or '없음'} · 성분속성 {len(attrs)}개 · 판정일 {a.date}")
    verdicts = evaluate_all(cards, products, reg, attrs, a.date)
    paths = write_all(verdicts, a.out)
    by = Counter((v.product_id, v.status) for v in verdicts)
    for pid in sorted({v.product_id for v in verdicts}):
        print(pid, {s: n for (p, s), n in by.items() if p == pid})
    for k, p in paths.items():
        print(f"{k}: {p}")


if __name__ == "__main__":
    main()
