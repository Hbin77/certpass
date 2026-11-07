"""AIStream 워크스페이스에서 실행하는 학습 코드(판정 모델 랜덤포레스트).

실행(워크스페이스 터미널 또는 노트북 셀):
    python aistream_train.py --train <train.csv 경로> --test <test.csv 경로> [--out 결과폴더]

- 정답 열 label(PASS·COND·FAIL·NA), 입력은 나머지 열 전부(96열, 열 순서는 CSV 그대로)
- 평가: 4종 정확도·매크로 F1, 규칙 판정(rule_*) 대비, 숨은 불가(규칙이 불가가 아니라고 한 실제 불가) 경보 재현율·정밀도
- MLflow가 있으면 파라미터·지표·모델을 기록하고 모델 레지스트리 '7팀_certpass_rf'에 등록한다.
  서빙 응답은 행마다 label과 proba_COND·proba_FAIL·proba_NA·proba_PASS(확률)를 돌려준다.
- MLflow가 없으면 결과 폴더에 model.pkl·metrics.json만 남긴다(모델 화면의 '새 버전 생성'으로 올릴 수 있음).
"""
from __future__ import annotations

import argparse
import json
import pickle
from pathlib import Path

import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report, f1_score

RULES = ["rule_PASS", "rule_COND", "rule_FAIL", "rule_NOT_APPLICABLE"]


class CertPassModel:
    """MLflow pyfunc 래퍼: 등급과 등급별 확률을 함께 돌려준다."""

    def __init__(self, clf, columns):
        self.clf, self.columns = clf, list(columns)

    def predict(self, context, model_input, params=None):  # MLflow pyfunc 규약
        X = model_input[self.columns] if isinstance(model_input, pd.DataFrame) else pd.DataFrame(model_input, columns=self.columns)
        proba = self.clf.predict_proba(X)
        out = pd.DataFrame(proba, columns=[f"proba_{c}" for c in self.clf.classes_])
        out.insert(0, "label", self.clf.classes_[proba.argmax(axis=1)])
        return out


def alert_table(p_fail, y, rule):
    cand = rule != "FAIL"
    hidden = (y == "FAIL") & cand
    rows = []
    for thr in (0.1, 0.2, 0.3, 0.5):
        flag = (p_fail >= thr) & cand
        tp, fp = int((flag & hidden).sum()), int((flag & ~hidden).sum())
        rows.append({"thr": thr, "hidden_fail_recall": round(tp / max(1, int(hidden.sum())), 3),
                     "alert_precision": round(tp / max(1, tp + fp), 3), "alerts": tp + fp,
                     "false_alarm_rate": round(fp / max(1, int((cand & ~hidden).sum())), 4)})
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", required=True)
    ap.add_argument("--test", required=True)
    ap.add_argument("--out", default="certpass_out")
    ap.add_argument("--trees", type=int, default=300)
    ap.add_argument("--min-leaf", type=int, default=2)
    a = ap.parse_args()
    tr, te = pd.read_csv(a.train), pd.read_csv(a.test)
    cols = [c for c in tr.columns if c != "label"]
    clf = RandomForestClassifier(n_estimators=a.trees, min_samples_leaf=a.min_leaf, n_jobs=-1, random_state=0)
    clf.fit(tr[cols], tr["label"])
    proba = clf.predict_proba(te[cols])
    pred = clf.classes_[proba.argmax(axis=1)]
    rule = te[RULES].idxmax(axis=1).str.replace("rule_", "", regex=False)
    p_fail = proba[:, list(clf.classes_).index("FAIL")]
    metrics = {
        "rows_train": len(tr), "rows_test": len(te), "n_features": len(cols),
        "acc": round(accuracy_score(te["label"], pred), 4), "macro_f1": round(f1_score(te["label"], pred, average="macro"), 4),
        "rule_acc": round(accuracy_score(te["label"], rule), 4), "rule_macro_f1": round(f1_score(te["label"], rule, average="macro"), 4),
        "hidden_fail_in_test": int(((te["label"] == "FAIL") & (rule != "FAIL")).sum()),
        "alert": alert_table(p_fail, te["label"].to_numpy(), rule.to_numpy()),
    }
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "feature_columns.json").write_text(json.dumps(cols), encoding="utf-8")
    with (out / "model.pkl").open("wb") as f:
        pickle.dump(clf, f)
    print(json.dumps(metrics, ensure_ascii=False, indent=1))
    print(classification_report(te["label"], pred, zero_division=0))
    try:
        import mlflow
        import mlflow.pyfunc
        from mlflow.models import infer_signature
    except ImportError:
        print("MLflow 없음 — certpass_out/model.pkl을 모델 화면의 '새 버전 생성'으로 올리세요.")
        return

    class Wrapped(mlflow.pyfunc.PythonModel):
        def __init__(self, inner):
            self.inner = inner

        def predict(self, context, model_input, params=None):
            return self.inner.predict(context, model_input, params)

    wrapped = Wrapped(CertPassModel(clf, cols))
    sample = te[cols].head(5)
    with mlflow.start_run(run_name="7팀_certpass_rf"):
        mlflow.log_params({"model": "RandomForestClassifier", "n_estimators": a.trees, "min_samples_leaf": a.min_leaf,
                           "n_features": len(cols), "rows_train": len(tr)})
        mlflow.log_metrics({k: v for k, v in metrics.items() if isinstance(v, (int, float))})
        for row in metrics["alert"]:
            mlflow.log_metrics({f"alert_recall_thr{row['thr']}": row["hidden_fail_recall"],
                                f"alert_precision_thr{row['thr']}": row["alert_precision"]})
        mlflow.log_artifact(str(out / "metrics.json"))
        mlflow.log_artifact(str(out / "feature_columns.json"))
        mlflow.pyfunc.log_model("model", python_model=wrapped, input_example=sample,
                                signature=infer_signature(sample, wrapped.predict(None, sample)),
                                registered_model_name="7팀_certpass_rf")
    print("MLflow 기록·등록 완료: 모델 레지스트리 '7팀_certpass_rf'")


if __name__ == "__main__":
    main()
