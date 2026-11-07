"""AI Hub 633(의약품·화장품 패키징 OCR) 글자 목록으로 '실제 포장에 인쇄된 한글 성분명'과 OCR 변형 표기를 만든다.

실행: python -m certcheck.aihub_prep data/aihub/633_ocr_kr_tokens.csv
- 입력: 화장품 포장 사진 OCR 정답 글자와 빈도(팀 서버에서 VL1 라벨로 집계, AI Hub 이용약관상 원본·파생 표는 저장소에 올리지 않음)
- 출력: data/aihub/633_kr_variants.json  {한글 표준명: [포장 OCR에서 나온 비슷한 변형 표기, ...]}
         data/aihub/633_coverage.json    식약처 원료성분 사전이 포장 글자를 얼마나 맞히는지
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

from rapidfuzz import fuzz, process

from .data import DATA, kr_key
from .names import kr_dict


def main(tokens_csv: Path) -> None:
    rows = [(r["token"], int(r["count"])) for r in csv.DictReader(tokens_csv.open(encoding="utf-8-sig"))]
    keys = kr_dict()
    names = sorted({h["kr_name"] for h in keys.values()})
    exact = [(t, n) for t, n in rows if kr_key(t) in keys]
    unknown = [(t, n) for t, n in rows if kr_key(t) not in keys and len(t) >= 3]
    variants: dict[str, list[str]] = {}
    for tok, n in unknown[:20000]:  # 빈도 높은 글자부터: 사전에 없는데 사전 이름과 매우 비슷하면 OCR 변형·이표기로 본다
        hit = process.extractOne(tok, names, scorer=fuzz.ratio, score_cutoff=88)
        if hit:
            variants.setdefault(hit[0], []).append(tok)
    out = DATA / "aihub"
    (out / "633_kr_variants.json").write_text(json.dumps(variants, ensure_ascii=False, indent=0), encoding="utf-8")
    total = sum(n for _, n in rows)
    cov = {"tokens": len(rows), "token_occurrences": total,
           "dict_exact_tokens": len(exact), "dict_exact_occurrences": sum(n for _, n in exact),
           "near_miss_tokens": sum(len(v) for v in variants.values()), "names_with_variants": len(variants),
           "note": "포장 글자 중 식약처 원료성분 사전과 정확히 일치하는 글자 수, 사전 이름과 88% 이상 비슷하지만 다른 글자(OCR 변형·이표기) 수"}
    (out / "633_coverage.json").write_text(json.dumps(cov, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(cov, ensure_ascii=False))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
