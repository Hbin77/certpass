"""AIStream에 서빙한 판정 모델을 평가셋(test.csv)으로 직접 불러 성능을 재고, 숨은 불가 경보 기준값을 고른다.

실행: AISTREAM_URL=<서빙 주소> python -m certcheck.calibrate_aistream out/public/aistream [--out 결과.json]
- 4종 판정 정확도: 모델 vs 규칙만(rule_* 원-핫)
- 숨은 불가 경보: 규칙이 불가가 아니라고 한 건 중 모델의 불가 확률이 기준 이상인 것 → 재현율·정밀도·오경보율
- 확률을 안 주는 모델이면 '모델이 불가라고 한 것'만으로 한 점을 잰다
"""
from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path

from .ml_client import call_model

RULE_COLS = ["rule_PASS", "rule_COND", "rule_FAIL", "rule_NOT_APPLICABLE"]


def call(url: str, cols: list[str], rows: list[list], classes: list[str], fmt: str, timeout: float) -> list[dict]:
    return call_model(url, cols, rows, classes, fmt, timeout)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("folder", type=Path)
    ap.add_argument("--batch", type=int, default=500)
    ap.add_argument("--limit", type=int, default=0, help="앞에서 N행만(0=전부)")
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args()
    url = os.environ["AISTREAM_URL"]
    classes = os.environ.get("AISTREAM_CLASSES", "COND,FAIL,NOT_APPLICABLE,PASS").split(",")
    fmt = os.environ.get("AISTREAM_FORMAT", "mlflow")
    cols = json.loads((a.folder / "feature_columns.json").read_text(encoding="utf-8"))
    rows = list(csv.DictReader((a.folder / "test.csv").open(encoding="utf-8")))
    if a.limit:
        rows = rows[: a.limit]
    X = [[float(r[c] or 0) for c in cols] for r in rows]
    y = [r["label"] for r in rows]
    rule = [next((c[5:] for c in RULE_COLS if r[c] == "1"), "NOT_APPLICABLE") for r in rows]
    preds: list[dict] = []
    for i in range(0, len(X), a.batch):
        preds += call(url, cols, X[i:i + a.batch], classes, fmt, float(os.environ.get("AISTREAM_TIMEOUT", "60")))
    labels = [p["label"] for p in preds]
    res = {"n_test": len(y), "rule_acc": round(sum(r == t for r, t in zip(rule, y)) / len(y), 4),
           "model_acc": round(sum(m == t for m, t in zip(labels, y)) / len(y), 4)}
    cand = [i for i, r in enumerate(rule) if r != "FAIL"]
    hidden = [int(y[i] == "FAIL") for i in cand]
    nh, nc = sum(hidden), len(hidden) - sum(hidden)
    res["hidden_fail_in_test"] = nh
    has_proba = all(preds[i]["proba"] for i in cand)
    points = (0.1, 0.2, 0.3, 0.5, 0.7, 0.85) if has_proba else (None,)
    sweep = []
    for thr in points:
        flag = [(preds[i]["proba"]["FAIL"] >= thr) if thr is not None else preds[i]["label"] == "FAIL" for i in cand]
        tp = sum(f and h for f, h in zip(flag, hidden))
        fp = sum(f and not h for f, h in zip(flag, hidden))
        sweep.append({"thr": thr, "숨은불가_재현율": round(tp / nh, 3) if nh else None,
                      "경고_정밀도": round(tp / (tp + fp), 3) if tp + fp else None, "경고수": tp + fp,
                      "규칙통과건_오경보율": round(fp / max(1, nc), 4)})
    res["hidden_fail_alert"] = sweep
    print(json.dumps(res, ensure_ascii=False, indent=1))
    if a.out:
        a.out.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
