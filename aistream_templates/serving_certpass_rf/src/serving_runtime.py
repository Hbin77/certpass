"""서빙 실행 코드입니다. main.py의 main()에서 import합니다.

시작 순서: 플랫폼 모델 입력 해석(MODEL_INPUTS_JSON) → Ray·Serve 시작 → Deployment(replica) 초기화 때 모델 로드 → 요청 대기.
모델 입력·로딩 실패는 예외로 올려 서버가 뜨지 않게 합니다(더미 모델이나 다른 경로로 대체하지 않음).
"""

import logging
import time

import ray
from ray import serve

from src.app import ServingModel
from src.model_inputs import load_model_input

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_serving(max_rows: int, n_jobs: int, max_concurrency: int) -> None:
    t0 = time.time()
    logger.info("[model_input] 시작")
    # 플랫폼이 MLFLOW_MODEL 포트(model)에 마운트한 모델 버전 정보를 기존 함수로 읽습니다.
    spec = load_model_input("model")
    model_dir = spec["mountPath"]
    # 응답·health에 어떤 등록 모델 버전으로 판정했는지 남기기 위한 정보(플랫폼 주입값 그대로 사용)
    model_meta = {
        "registered_model": spec["mlflowRegisteredModelName"],
        "model_version": spec["mlflowModelVersion"],
    }
    logger.info("[model_input] 완료 (%.1fs) model_version=%s", time.time() - t0, model_meta["model_version"])

    try:
        t0 = time.time()
        logger.info("[serve] 시작")
        ray.init()
        serve.start(http_options={"host": "0.0.0.0", "port": 8000})
        app = ServingModel.bind(model_dir, model_meta, max_rows, n_jobs, max_concurrency)
        logger.info("[serve] 준비 완료 (%.1fs), 요청 대기", time.time() - t0)
        serve.run(app, blocking=True)
    except Exception:
        logger.exception("[serve] 실패")
        raise
