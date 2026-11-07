"""모델 로딩·입력 검증·추론 계약 시험(작은 가짜 데이터로 만든 실제 sklearn 모델 사용, 플랫폼·Ray 없이)."""

import json

import numpy as np
import pandas as pd
import pytest

from src.model_inputs import load_model_input
from src.predictor import InputError, load_predictor

FEATURES = ["f_a", "f_b", "rule_PASS", "rule_COND", "rule_FAIL", "rule_NOT_APPLICABLE"]
CLASSES = ["COND", "FAIL", "NOT_APPLICABLE", "PASS"]


@pytest.fixture(scope="module")
def model_dir(tmp_path_factory):
    import mlflow.sklearn
    from sklearn.ensemble import RandomForestClassifier

    rng = np.random.default_rng(0)
    X = pd.DataFrame(rng.random((80, len(FEATURES))), columns=FEATURES)
    y = np.array(CLASSES * 20)
    clf = RandomForestClassifier(n_estimators=5, n_jobs=-1, random_state=0).fit(X, y)
    path = tmp_path_factory.mktemp("m") / "model"
    mlflow.sklearn.save_model(clf, str(path))
    return str(path)


@pytest.fixture(scope="module")
def pred(model_dir):
    return load_predictor(model_dir, {"registered_model": "test", "model_version": "1"}, n_jobs=1)


def test_load_sets_features_classes_and_limits_threads(pred):
    assert pred.features == FEATURES
    assert pred.classes == CLASSES
    assert pred.model.n_jobs == 1
    assert pred.meta["n_features"] == len(FEATURES)


def test_split_predicts_label_and_proba(pred):
    X, ignored = pred.frame_from_split(FEATURES + ["extra"], [[0.1] * 7, [0.9] * 7], max_rows=10)
    out = pred.predict(X)
    assert ignored == ["extra"] and len(out) == 2
    for row in out:
        assert row["label"] in CLASSES
        assert set(row) == {"label"} | {f"proba_{c}" for c in CLASSES}
        assert abs(sum(row[f"proba_{c}"] for c in CLASSES) - 1) < 1e-5


def test_column_order_and_legacy_name(pred):
    cols = list(reversed(FEATURES))
    cols[cols.index("rule_NOT_APPLICABLE")] = "rule_NA"
    X, _ = pred.frame_from_split(cols, [[0.5] * 6], max_rows=10)
    assert list(X.columns) == FEATURES


def test_records_path(pred):
    X, _ = pred.frame_from_records([{c: 0.3 for c in FEATURES}], max_rows=10)
    assert pred.predict(X)[0]["label"] in CLASSES


@pytest.mark.parametrize("cols,data,max_rows", [
    (FEATURES[:-1], [[0.1] * 5], 10),            # 특징 열 누락
    (FEATURES, [[0.1] * 5], 10),                 # 값 개수 불일치
    (FEATURES, [], 10),                          # 빈 요청
    (FEATURES, [[0.1] * 6] * 3, 2),              # 행 수 초과
    (FEATURES, [[float("nan")] * 6], 10),        # NaN
    (FEATURES + ["f_a"], [[0.1] * 7], 10),       # 중복 열
])
def test_bad_inputs_raise_input_error(pred, cols, data, max_rows):
    with pytest.raises(InputError):
        pred.frame_from_split(cols, data, max_rows)


def test_records_missing_value_raises(pred):
    rows = [{c: 0.3 for c in FEATURES}, {c: 0.3 for c in FEATURES[:-1]}]
    with pytest.raises(InputError):
        pred.frame_from_records(rows, max_rows=10)


def test_load_failure_propagates(tmp_path):
    with pytest.raises(Exception):
        load_predictor(str(tmp_path / "없음"), {}, n_jobs=1)


def test_serving_model_input_rejects_fresh():
    raw = json.dumps({"schemaVersion": 1, "inputs": {"model": {"mode": "FRESH", "registeredModelId": "x"}}})
    with pytest.raises(ValueError):
        load_model_input("model", raw_value=raw)
