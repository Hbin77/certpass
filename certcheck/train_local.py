"""로컬 가능성 확인(정식 학습은 AIStream). AIStream에 올리는 것과 같은 train.csv·test.csv·열로만 잰다.

실행: python -m certcheck.train_local out/public/aistream [--out 결과.json]
- 특징 = feature_columns.json의 92열(추론 때도 얻는 값만, noise_level 같은 합성 메타데이터 없음)
- 기준선 = 규칙 엔진 판정(rule_* 원-핫)
- 숨은 불가 탐지 = 규칙이 불가라고 하지 않은 건 중에서 실제 불가를 확률로 잡는 이진 모델(임계값별 재현율·정밀도)
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report, f1_score

RULE_COLS = ["rule_PASS", "rule_COND", "rule_FAIL", "rule_NOT_APPLICABLE"]


def load(path: Path, cols: list[str]) -> tuple[list[list[float]], list[str], list[str]]:
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    X = [[float(r[c] or 0) for c in cols] for r in rows]
    y = [r["label"] for r in rows]
    rule = [next((c[5:] for c in RULE_COLS if r[c] == "1"), "NOT_APPLICABLE") for r in rows]
    return X, y, rule


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("folder", type=Path, help="export_aistream 출력 폴더(train.csv, test.csv, feature_columns.json)")
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args()
    cols = json.loads((a.folder / "feature_columns.json").read_text(encoding="utf-8"))
    Xtr, ytr, rtr = load(a.folder / "train.csv", cols)
    Xte, yte, rte = load(a.folder / "test.csv", cols)
    clf = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.08, random_state=0).fit(Xtr, ytr)
    pred = list(clf.predict(Xte))
    res = {
        "n_train": len(ytr), "n_test": len(yte), "n_features": len(cols), "label_dist_test": Counter(yte),
        "rule_acc": round(accuracy_score(yte, rte), 4), "ml_acc": round(accuracy_score(yte, pred), 4),
        "rule_macroF1": round(f1_score(yte, rte, average="macro"), 4), "ml_macroF1": round(f1_score(yte, pred, average="macro"), 4),
    }
    cand_tr = [i for i, r in enumerate(rtr) if r != "FAIL"]
    cand_te = [i for i, r in enumerate(rte) if r != "FAIL"]
    det = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.06, random_state=0, class_weight="balanced")
    det.fit([Xtr[i] for i in cand_tr], [int(ytr[i] == "FAIL") for i in cand_tr])
    prob = det.predict_proba([Xte[i] for i in cand_te])[:, 1]
    hidden = [int(yte[i] == "FAIL") for i in cand_te]
    n_hidden, n_clean = sum(hidden), len(hidden) - sum(hidden)
    sweep = []
    for thr in (0.3, 0.5, 0.7, 0.85, 0.95):
        flag = [int(p >= thr) for p in prob]
        tp = sum(f and h for f, h in zip(flag, hidden))
        fp = sum(f and not h for f, h in zip(flag, hidden))
        sweep.append({"thr": thr, "숨은불가_재현율": round(tp / n_hidden, 3) if n_hidden else None,
                      "경고_정밀도": round(tp / (tp + fp), 3) if tp + fp else None, "경고수": tp + fp,
                      "규칙통과건_오경보율": round(fp / max(1, n_clean), 4)})
    sim = cols.index("r_max_sim_banned") if "r_max_sim_banned" in cols else None
    if sim is not None:  # 기준선2: 금지 목록과 이름이 0.9 이상 비슷하면 경고
        flag = [int(Xte[i][sim] >= 0.9) for i in cand_te]
        tp = sum(f and h for f, h in zip(flag, hidden))
        fp = sum(f and not h for f, h in zip(flag, hidden))
        res["baseline_sim0.9_recall"] = round(tp / n_hidden, 3) if n_hidden else None
        res["baseline_sim0.9_precision"] = round(tp / (tp + fp), 3) if tp + fp else None
    res["hidden_fail_in_test"] = n_hidden
    res["hidden_fail_detector_binary"] = sweep
    # AIStream에서 실제로 쓸 방식: 4종 분류 랜덤포레스트 하나의 '불가 확률'로 경보
    rf = RandomForestClassifier(n_estimators=300, min_samples_leaf=2, n_jobs=-1, random_state=0).fit(Xtr, ytr)
    fi = list(rf.classes_).index("FAIL")
    p_fail = rf.predict_proba([Xte[i] for i in cand_te])[:, fi]
    rf_pred = list(rf.predict(Xte))
    res["rf4_acc"] = round(accuracy_score(yte, rf_pred), 4)
    res["rf4_macroF1"] = round(f1_score(yte, rf_pred, average="macro"), 4)
    alert = []
    for thr in (0.1, 0.2, 0.3, 0.5):
        flag = [int(q >= thr) for q in p_fail]
        tp = sum(f and h for f, h in zip(flag, hidden))
        fp = sum(f and not h for f, h in zip(flag, hidden))
        alert.append({"thr": thr, "숨은불가_재현율": round(tp / n_hidden, 3) if n_hidden else None,
                      "경고_정밀도": round(tp / (tp + fp), 3) if tp + fp else None, "경고수": tp + fp,
                      "규칙통과건_오경보율": round(fp / max(1, n_clean), 4)})
    res["alert_from_rf4"] = alert
    print(json.dumps(res, ensure_ascii=False, indent=1))
    print("\n[규칙만, 지저분한 입력]\n", classification_report(yte, rte, zero_division=0))
    print("[ML 단독(참고)]\n", classification_report(yte, pred, zero_division=0))
    if a.out:
        a.out.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
