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


def run_serving(max_mb: int, threads: int, max_concurrency: int) -> None:
    t0 = time.time()
    logger.info("[model_input] 시작")
    spec = load_model_input("model")  # 기본 인자가 base_model이라 포트명을 꼭 넘긴다
    model_meta = {"registered_model": spec["mlflowRegisteredModelName"], "model_version": spec["mlflowModelVersion"]}
    logger.info("[model_input] 완료 (%.1fs) model_version=%s", time.time() - t0, model_meta["model_version"])
    try:
        t0 = time.time()
        logger.info("[serve] 시작")
        ray.init()
        serve.start(http_options={"host": "0.0.0.0", "port": 8000})
        app = ServingModel.bind(spec["mountPath"], model_meta, max_mb, threads, max_concurrency)
        logger.info("[serve] 준비 완료 (%.1fs), 요청 대기", time.time() - t0)
        serve.run(app, blocking=True)
    except Exception:
        logger.exception("[serve] 실패")
        raise
