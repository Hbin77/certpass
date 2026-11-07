"""FastAPI 라우트와 Ray Serve Deployment입니다.

- 모델은 replica가 시작할 때(__init__) 한 번 읽고 이후 요청은 메모리의 모델을 재사용한다.
  읽기에 실패하면 예외가 올라가 replica가 준비되지 않는다(health도 응답하지 않음).
- 사진 읽기는 CPU를 오래 쓰므로 스레드로 넘겨 이벤트 루프(health 응답)를 막지 않고,
  세마포어로 replica당 동시 처리 수를 제한한다(초과 요청은 순서대로 대기).
"""

import asyncio
import logging
import os
import time

from fastapi import FastAPI, File, HTTPException, UploadFile
from ray import serve

from src.predictor import InputError, check_image, load_reader

logger = logging.getLogger(__name__)

app = FastAPI(title="7팀 화장품 포장 사진 OCR 서빙", root_path=os.getenv("SERVING_ROOT_PATH", "").rstrip("/"))


@serve.deployment
@serve.ingress(app)
class ServingModel:
    def __init__(self, model_dir: str, model_meta: dict, max_mb: int, threads: int, max_concurrency: int):
        logging.basicConfig(level=logging.INFO)
        self.reader, self.meta = load_reader(model_dir, model_meta, threads)
        self.max_mb = max_mb
        self._slots = asyncio.Semaphore(max_concurrency)

    @app.post("/predict")
    async def predict(self, file: UploadFile = File(...)):
        """사진 한 장(multipart 필드 file) → 단어(위치·글자·확신도), 줄, 전체 글자, 전성분 목록."""
        t0 = time.time()
        data = await file.read()
        try:
            check_image(data, self.max_mb)
        except InputError as exc:
            raise HTTPException(status_code=415 if "JPEG" in str(exc) else 413 if "MB" in str(exc) else 422,
                                detail=str(exc)) from exc
        async with self._slots:
            try:
                res = await asyncio.to_thread(self.reader.read, data)
            except Exception as exc:
                logger.exception("[predict] 실패 (%.2fs) bytes=%d", time.time() - t0, len(data))
                raise HTTPException(status_code=500, detail="사진을 읽는 중 오류가 났습니다. 서버 로그를 확인해 주세요.") from exc
        logger.info("[predict] 완료 (%.2fs) 단어 %d 줄 %d 성분 %d", time.time() - t0, len(res["words"]), len(res["lines"]),
                    len(res["ingredients"]))
        return {**res, "model": self.meta, "elapsed_sec": round(time.time() - t0, 2)}

    @app.get("/health")
    async def health_check(self):
        # 이 메서드에 도달했다면 __init__에서 모델 로드가 끝난 상태다.
        return {"status": "ok", "model": self.meta}
