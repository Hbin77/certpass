"""학습 실행 코드입니다. train.py의 main()에서 import합니다.

7팀 CertPass: 제품×인증 한 행마다 특징 96열과 정답 label(PASS·COND·FAIL·NOT_APPLICABLE)이 있는 CSV로
랜덤포레스트를 학습합니다. 평가용 CSV로 4종 판정 정확도와 '숨은 불가' 경보 성능을 재고 MLflow에 기록합니다.

계약(template-inout.yaml):
- train_dataset, test_dataset: 데이터셋 파일이 각 path에 읽기 전용으로 마운트된다. 입력은 읽기만 한다.
- base_model: 등록 모델 대상 식별용(MNIST 방식). FRESH면 새로 학습, FROM_VERSION이어도 새로 학습한다(이전 버전을 이어 학습하지 않음).
- trained_model: Run에 log_model로 남긴 모델 하나가 등록 모델 버전이 된다. Registry 등록은 플랫폼이 한다.
"""

import json
import os
import tempfile
import time
from pathlib import Path

# 서비스 마운트 경로(template-inout.yaml의 path와 같아야 함)
TRAIN_DIR = "/app/volume/train"
TEST_DIR = "/app/volume/test"

LABEL = "label"
# 예전 내보내기 파일은 '해당 없음'을 NA로 적었다. pandas가 NA를 결측으로 읽지 않도록 na_filter=False로 읽고 이름을 맞춘다.
LEGACY_RENAME = {"NA": "NOT_APPLICABLE"}
RULE_COLS = ["rule_PASS", "rule_COND", "rule_FAIL", "rule_NOT_APPLICABLE"]


def _log(step: str, state: str, t0: float | None = None, extra: str = "") -> None:
    took = f" ({time.time() - t0:.1f}s)" if t0 is not None else ""
    print(f"[{step}] {state}{took} {extra}".rstrip(), flush=True)


def find_csv(mount: str) -> Path:
    """마운트 위치에서 CSV 파일 하나를 찾는다. 파일이면 그대로, 폴더면 안의 .csv/.csv.gz가 정확히 하나여야 한다."""
    p = Path(mount)
    if p.is_file():
        return p
    if not p.is_dir():
        raise FileNotFoundError(f"데이터셋 마운트가 없습니다: {mount}")
    files = sorted(f for f in p.rglob("*") if f.is_file() and f.name.lower().endswith((".csv", ".csv.gz")))
    if len(files) != 1:
        raise FileNotFoundError(f"{mount}에서 CSV가 정확히 1개여야 합니다(찾은 파일: {[str(f) for f in files]})")
    return files[0]


def load_table(path: Path):
    import pandas as pd

    df = pd.read_csv(path, na_filter=False)  # .csv.gz도 확장자로 자동 해제
    if LABEL not in df.columns:
        raise ValueError(f"{path}에 정답 열 '{LABEL}'이 없습니다.")
    df = df.rename(columns={"rule_NA": "rule_NOT_APPLICABLE"})
    df[LABEL] = df[LABEL].astype(str).replace(LEGACY_RENAME)
    feats = [c for c in df.columns if c != LABEL]
    df[feats] = df[feats].apply(pd.to_numeric, errors="raise")
    return df


def alert_table(p_fail, y, rule) -> list[dict]:
    """숨은 불가 경보: 규칙이 불가가 아니라고 한 행 중 모델의 불가 확률이 기준 이상인 것을 경보로 본다."""
    cand = rule != "FAIL"
    hidden = (y == "FAIL") & cand
    n_hidden, n_clean = int(hidden.sum()), int((cand & ~hidden).sum())
    rows = []
    for thr in (0.1, 0.2, 0.3, 0.5):
        flag = (p_fail >= thr) & cand
        tp, fp = int((flag & hidden).sum()), int((flag & ~hidden).sum())
        rows.append({"thr": thr, "hidden_fail_recall": round(tp / max(1, n_hidden), 4),
                     "alert_precision": round(tp / max(1, tp + fp), 4), "alerts": tp + fp,
                     "false_alarm_rate": round(fp / max(1, n_clean), 5)})
    return rows


def run_training(n_estimators: int, min_samples_leaf: int, max_depth: int | None, random_state: int,
                 train_dir: str = TRAIN_DIR, test_dir: str = TEST_DIR) -> dict:
    import mlflow
    import mlflow.sklearn
    from mlflow.models import infer_signature
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score

    from src.model_inputs import load_model_input

    print("#Start training#", flush=True)

    # 등록 모델 대상 확인(MNIST 방식). 학습은 항상 새 모델로 한다.
    model_input = load_model_input("base_model", allow_fresh=True)
    _log("model_input", "확인", extra=f"mode={model_input['mode']}")

    experiment_name = os.getenv("EXPERIMENT_NAME")
    run_name = os.getenv("RUN_NAME")
    if not experiment_name or not run_name:
        raise RuntimeError("EXPERIMENT_NAME과 RUN_NAME 환경 변수가 필요합니다.")

    t0 = time.time()
    _log("load_dataset", "시작")
    train_path, test_path = find_csv(train_dir), find_csv(test_dir)
    tr, te = load_table(train_path), load_table(test_path)
    cols = [c for c in tr.columns if c != LABEL]
    missing = [c for c in cols if c not in te.columns]
    if missing:
        raise ValueError(f"평가용 데이터에 학습 특징 열이 없습니다: {missing[:5]}")
    _log("load_dataset", "완료", t0, f"train={len(tr)}행 test={len(te)}행 특징={len(cols)}열 "
         f"파일={train_path.name},{test_path.name}")

    mlflow.set_experiment(experiment_name)
    with mlflow.start_run(run_name=run_name) as run:
        _log("mlflow_run", "연결", extra=f"run_id={run.info.run_id}")
        params = {"model": "RandomForestClassifier", "n_estimators": n_estimators,
                  "min_samples_leaf": min_samples_leaf, "max_depth": max_depth or "none",
                  "random_state": random_state, "n_features": len(cols),
                  "rows_train": len(tr), "rows_test": len(te), "base_model_mode": model_input["mode"]}
        mlflow.log_params(params)

        t0 = time.time()
        _log("train", "시작")
        clf = RandomForestClassifier(n_estimators=n_estimators, min_samples_leaf=min_samples_leaf,
                                     max_depth=max_depth, n_jobs=-1, random_state=random_state)
        clf.fit(tr[cols], tr[LABEL])
        _log("train", "완료", t0, f"classes={list(clf.classes_)}")

        t0 = time.time()
        _log("evaluate", "시작")
        proba = clf.predict_proba(te[cols])
        pred = clf.classes_[proba.argmax(axis=1)]
        y = te[LABEL].to_numpy()
        metrics = {"acc": accuracy_score(y, pred), "macro_f1": f1_score(y, pred, average="macro")}
        alert = []
        if all(c in te.columns for c in RULE_COLS) and "FAIL" in clf.classes_:
            # 규칙 판정(rule_* 원-핫)만 쓴 기준선과 비교
            rule = te[RULE_COLS].idxmax(axis=1).str.replace("rule_", "", regex=False).to_numpy()
            metrics["rule_acc"] = accuracy_score(y, rule)
            metrics["rule_macro_f1"] = f1_score(y, rule, average="macro")
            metrics["hidden_fail_in_test"] = int(((y == "FAIL") & (rule != "FAIL")).sum())
            alert = alert_table(proba[:, list(clf.classes_).index("FAIL")], y, rule)
            for row in alert:
                t = str(row["thr"]).replace(".", "_")
                metrics[f"alert_recall_thr{t}"] = row["hidden_fail_recall"]
                metrics[f"alert_precision_thr{t}"] = row["alert_precision"]
                metrics[f"alert_false_alarm_thr{t}"] = row["false_alarm_rate"]
        metrics = {k: round(float(v), 5) for k, v in metrics.items()}
        mlflow.log_metrics(metrics)
        report = classification_report(y, pred, zero_division=0)
        labels = list(clf.classes_)
        cm = confusion_matrix(y, pred, labels=labels).tolist()
        _log("evaluate", "완료", t0, json.dumps(metrics, ensure_ascii=False))
        print(report, flush=True)

        # 보조 자료는 임시 폴더에 쓰고 artifact로 올린다(입력 마운트에는 쓰지 않음).
        t0 = time.time()
        _log("save_model", "시작")
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "metrics.json").write_text(json.dumps({**metrics, "alert": alert}, ensure_ascii=False, indent=1), encoding="utf-8")
            (d / "feature_columns.json").write_text(json.dumps(cols), encoding="utf-8")
            (d / "confusion_matrix.json").write_text(json.dumps({"labels": labels, "matrix": cm}), encoding="utf-8")
            (d / "classification_report.txt").write_text(report, encoding="utf-8")
            for f in d.iterdir():
                mlflow.log_artifact(str(f))
        sample = te[cols].head(5)
        # 서빙에서 predict_proba를 쓰도록 sklearn flavor로 모델 하나만 기록한다(registered_model_name 없음: 등록은 플랫폼 담당).
        mlflow.sklearn.log_model(clf, name="model", input_example=sample,
                                 signature=infer_signature(sample, clf.predict(sample)))
        _log("save_model", "완료", t0)

    print("#Finish training#", flush=True)
    return metrics
