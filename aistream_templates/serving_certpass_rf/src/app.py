"""FastAPI 라우트와 Ray Serve Deployment입니다.

- 모델은 replica가 시작할 때(__init__) 한 번 읽고, 이후 요청은 메모리의 모델을 재사용한다.
  읽기에 실패하면 예외가 올라가 replica가 준비되지 않는다(health도 응답하지 않음).
- 추론은 CPU를 오래 쓰므로 스레드로 넘겨 이벤트 루프(health 응답)를 막지 않고,
  세마포어로 replica당 동시 계산 수를 제한한다(초과 요청은 순서대로 대기).
"""

import asyncio
import logging
import os
import time

from fastapi import FastAPI, HTTPException
from ray import serve

from src.dto import PredictRequest, PredictResponse
from src.predictor import InputError, load_predictor

logger = logging.getLogger(__name__)

app = FastAPI(
    title="CertPass 인증 판정 서빙(랜덤포레스트)",
    root_path=os.getenv("SERVING_ROOT_PATH", "").rstrip("/"),
)


@serve.deployment
@serve.ingress(app)
class ServingModel:
    def __init__(self, model_dir: str, model_meta: dict, max_rows: int, n_jobs: int, max_concurrency: int):
        logging.basicConfig(level=logging.INFO)
        self.predictor = load_predictor(model_dir, model_meta, n_jobs)
        self.max_rows = max_rows
        self.max_concurrency = max_concurrency
        self._slots = asyncio.Semaphore(max_concurrency)

    @app.post("/predict", response_model=PredictResponse)
    async def predict(self, body: PredictRequest):
        t0 = time.time()
        try:
            if body.dataframe_split is not None:
                X, ignored = self.predictor.frame_from_split(body.dataframe_split.columns, body.dataframe_split.data, self.max_rows)
            else:
                X, ignored = self.predictor.frame_from_records(body.instances, self.max_rows)
        except InputError as exc:
            logger.info("[predict] 입력 오류: %s", exc)
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        async with self._slots:
            try:
                preds = await asyncio.to_thread(self.predictor.predict, X)
            except Exception as exc:
                logger.exception("[predict] 추론 실패 (%.2fs) rows=%d", time.time() - t0, len(X))
                raise HTTPException(status_code=500, detail="추론 중 오류가 났습니다. 서버 로그를 확인해 주세요.") from exc
        logger.info("[predict] 완료 (%.2fs) rows=%d ignored=%d", time.time() - t0, len(preds), len(ignored))
        return {"predictions": preds, "classes": self.predictor.classes, "model": self.predictor.meta,
                "ignored_columns": ignored}

    @app.get("/health")
    async def health_check(self):
        # 이 메서드에 도달했다면 __init__에서 모델 로드가 끝난 상태다.
        return {"status": "ok", "classes": self.predictor.classes, "model": self.predictor.meta}

    @app.get("/info")
    async def info(self):
        """호출 측이 열 순서를 맞출 수 있게 모델 특징 열과 제한값을 알려 준다."""
        return {"features": self.predictor.features, "classes": self.predictor.classes, "model": self.predictor.meta,
                "max_rows": self.max_rows, "max_concurrency": self.max_concurrency}
