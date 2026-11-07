"""모델 로딩·입력 검증·추론을 담당합니다. FastAPI·Ray와 분리해 단위 시험이 가능하게 둡니다.

입력 한 행 = 제품 × 인증 한 건의 특징(학습 템플릿 ml/7팀_certpass_rf와 같은 열).
출력 한 행 = 판정 label(PASS·COND·FAIL·NOT_APPLICABLE)과 클래스별 확률 proba_<클래스>.
"""

import logging
import time
from dataclasses import dataclass

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# 학습 템플릿과 같은 규칙: 예전 내보내기 파일은 '해당 없음'을 NA로 적었으므로 열·라벨 이름을 맞춘다.
LEGACY_COLUMNS = {"rule_NA": "rule_NOT_APPLICABLE"}
LEGACY_LABELS = {"NA": "NOT_APPLICABLE"}


class InputError(ValueError):
    """호출 측이 고쳐야 하는 요청 오류(HTTP 422로 돌려준다)."""


@dataclass
class Predictor:
    model: object
    features: list
    classes: list
    meta: dict

    def frame_from_split(self, columns: list, data: list, max_rows: int):
        """{"columns": [...], "data": [[...], ...]} 형식 → 모델 입력 표."""
        _check_rows(len(data), max_rows)
        if len(set(columns)) != len(columns):
            raise InputError("columns에 같은 열 이름이 두 번 이상 있습니다.")
        bad = next((i for i, row in enumerate(data) if len(row) != len(columns)), None)
        if bad is not None:
            raise InputError(f"data[{bad}]의 값 개수({len(data[bad])})가 columns 개수({len(columns)})와 다릅니다.")
        return self._finalize(pd.DataFrame(data, columns=columns))

    def frame_from_records(self, records: list, max_rows: int):
        """[{열: 값}, ...] 형식 → 모델 입력 표."""
        _check_rows(len(records), max_rows)
        return self._finalize(pd.DataFrame.from_records(records))

    def _finalize(self, df: pd.DataFrame):
        df = df.rename(columns=LEGACY_COLUMNS)
        missing = [c for c in self.features if c not in df.columns]
        if missing:
            raise InputError(f"모델 특징 열 {len(missing)}개가 없습니다: {missing[:10]}")
        known = set(self.features)
        ignored = [c for c in df.columns if c not in known]
        try:
            X = df[self.features].astype(float)
        except (TypeError, ValueError) as exc:
            raise InputError("특징 값은 모두 숫자여야 합니다.") from exc
        if not np.isfinite(X.to_numpy()).all():
            raise InputError("비어 있거나 NaN·무한대인 특징 값이 있습니다.")
        return X, ignored

    def predict(self, X: pd.DataFrame) -> list:
        proba = self.model.predict_proba(X)
        best = proba.argmax(axis=1)
        out = []
        for i, row in enumerate(proba):
            item = {"label": self.classes[int(best[i])]}
            item.update({f"proba_{c}": round(float(p), 6) for c, p in zip(self.classes, row)})
            out.append(item)
        return out


def _check_rows(n: int, max_rows: int) -> None:
    if n == 0:
        raise InputError("판정할 행이 없습니다.")
    if n > max_rows:
        raise InputError(f"한 번에 {max_rows}행까지 받습니다(요청 {n}행). 나눠서 보내 주세요.")


def load_predictor(model_dir: str, model_meta: dict, n_jobs: int) -> Predictor:
    """마운트된 MLflow sklearn 모델을 한 번 읽어 Predictor로 만든다. 실패하면 예외를 그대로 올린다."""
    import mlflow.sklearn
    import sklearn
    from mlflow.models import Model

    t0 = time.time()
    logger.info("[load_model] 시작")
    try:
        model = mlflow.sklearn.load_model(model_dir)
        if not hasattr(model, "predict_proba"):
            raise TypeError("모델에 predict_proba가 없습니다(분류 확률을 낼 수 없음).")
        features = [str(c) for c in getattr(model, "feature_names_in_", [])]
        if not features:
            raise ValueError("모델에 학습 특징 열 이름(feature_names_in_)이 없습니다.")
        classes = [LEGACY_LABELS.get(str(c), str(c)) for c in model.classes_]
        # 학습 때 n_jobs=-1(모든 CPU)로 저장돼 있다. 컨테이너에서 호스트 CPU 수만큼 스레드를 만들지 않도록 줄인다(결과는 같음).
        if hasattr(model, "n_jobs"):
            model.n_jobs = n_jobs
        # 학습 이미지와 서빙 이미지의 scikit-learn 버전이 다르면 트리 복원이 어긋날 수 있어 경고를 남긴다.
        recorded = (Model.load(model_dir).flavors.get("sklearn") or {}).get("sklearn_version")
        if recorded and recorded != sklearn.__version__:
            logger.warning("[load_model] 학습 sklearn %s ≠ 서빙 sklearn %s", recorded, sklearn.__version__)
    except Exception:
        logger.exception("[load_model] 실패 (%.1fs)", time.time() - t0)
        raise
    meta = {**model_meta, "n_features": len(features), "sklearn": sklearn.__version__, "sklearn_trained": recorded or "미확인"}
    logger.info("[load_model] 완료 (%.1fs) classes=%s features=%d", time.time() - t0, classes, len(features))
    return Predictor(model=model, features=features, classes=classes, meta=meta)
