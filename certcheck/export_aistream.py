"""synth 데이터셋을 AIStream 표 분류 학습용 CSV로 변환.

실행: python -m certcheck.export_aistream out/private/ml/certcheck_train_v1.csv out/public/aistream
- 열 이름·정답 값을 영문(ASCII)으로 바꾼다: 통과 가능=PASS, 조건부=COND, 불가=FAIL, 해당 없음=NOT_APPLICABLE
  ('NA'는 pandas가 결측값으로 읽으므로 쓰지 않는다)
- 규칙 엔진 판정(rule_on_noisy)은 원-핫 특징으로 넣는다(추론 때도 얻을 수 있는 값)
- 추론 때 알 수 없는 값(sample, noise_level)은 뺀다
- 같은 합성 제품의 행이 학습·평가에 나뉘지 않도록 제품 단위로 8:2 분할한다
"""
from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path

from . import STATUS_COND, STATUS_FAIL, STATUS_NA, STATUS_PASS
from .data import DATA

LABELS = {STATUS_PASS: "PASS", STATUS_COND: "COND", STATUS_FAIL: "FAIL", STATUS_NA: "NOT_APPLICABLE"}
DROP = {"sample", "cert_id", "noise_level", "label", "rule_on_noisy"}
COLUMNS_FILE = DATA / "ml" / "feature_columns.json"


def is_test(sample: str) -> bool:
    return int(hashlib.sha1(sample.encode()).hexdigest(), 16) % 5 == 0


def convert(src: Path, out_dir: Path) -> dict:
    rows = list(csv.DictReader(src.open(encoding="utf-8-sig")))
    feats = [k for k in rows[0] if k not in DROP]
    rule_cols = [f"rule_{v}" for v in LABELS.values()]
    header = feats + rule_cols + ["label"]
    out_dir.mkdir(parents=True, exist_ok=True)
    counts = {"train": 0, "test": 0}
    with (out_dir / "train.csv").open("w", newline="", encoding="utf-8") as ftr, \
            (out_dir / "test.csv").open("w", newline="", encoding="utf-8") as fte:
        wtr, wte = csv.writer(ftr), csv.writer(fte)
        wtr.writerow(header)
        wte.writerow(header)
        for r in rows:
            rule = LABELS[r["rule_on_noisy"]]
            line = [r[k] for k in feats] + [int(c == f"rule_{rule}") for c in rule_cols] + [LABELS[r["label"]]]
            split = "test" if is_test(r["sample"]) else "train"
            (wte if split == "test" else wtr).writerow(line)
            counts[split] += 1
    meta = {"source": src.name, "rows": counts, "n_features": len(header) - 1, "target": "label",
            "label_map": {v: k for k, v in LABELS.items()}, "split": "합성 제품 단위 sha1 % 5 == 0 → test"}
    (out_dir / "dataset_info.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    cols = json.dumps(header[:-1], ensure_ascii=False, indent=0)
    (out_dir / "feature_columns.json").write_text(cols, encoding="utf-8")
    COLUMNS_FILE.parent.mkdir(parents=True, exist_ok=True)
    COLUMNS_FILE.write_text(cols, encoding="utf-8")  # 앱이 AIStream 모델을 부를 때 같은 열 순서를 쓴다
    return meta


if __name__ == "__main__":
    print(json.dumps(convert(Path(sys.argv[1]), Path(sys.argv[2])), ensure_ascii=False, indent=2))
