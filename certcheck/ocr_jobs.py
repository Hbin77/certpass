"""OCR 접수 → 결과 조회(공개 주소 프록시가 60초에 연결을 끊으므로, 오래 걸리는 OCR은 요청 하나로 기다리지 않는다).

- 화면은 POST /api/ocr?mode=job 으로 접수 번호를 받고, GET /api/ocr/jobs/{번호}를 1~2초마다 부른다
- 작업자 수(OCR_JOB_WORKERS)만큼만 동시에 OCR 서빙을 부른다. 서빙(4 CPU)은 한 번에 한 장씩 읽으므로 많이 보내도 빨라지지 않는다
- 대기열 상한(OCR_JOB_QUEUE)을 넘으면 429. 결과는 OCR_JOB_TTL초 뒤 지운다(사진은 처리 직후 버리고 결과만 잠시 둔다)
- 접수 번호는 추측할 수 없는 난수(uuid4)라 다른 사람의 결과를 볼 수 없다
"""
from __future__ import annotations

import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Callable


class Busy(RuntimeError):
    """대기열이 가득 참(429)."""


class JobError(RuntimeError):
    """작업 실패. status·detail은 동기 경로와 같은 HTTP 오류로 화면에 보낸다."""

    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status, self.detail = status, detail


class Jobs:
    def __init__(self, workers: int | None = None, max_queue: int | None = None, ttl: float | None = None):
        self.workers = workers or int(os.environ.get("OCR_JOB_WORKERS", "2"))
        self.max_queue = max_queue or int(os.environ.get("OCR_JOB_QUEUE", "12"))
        self.ttl = ttl or float(os.environ.get("OCR_JOB_TTL", "600"))
        self._pool = ThreadPoolExecutor(max_workers=self.workers, thread_name_prefix="ocr-job")
        self._lock = threading.Lock()
        self._jobs: dict[str, dict] = {}
        self._order: list[str] = []  # 접수 순서(대기 순번 계산용)

    def _sweep(self) -> None:
        now = time.monotonic()
        for jid in [j for j, v in self._jobs.items() if v.get("done_at") and now - v["done_at"] > self.ttl]:
            self._jobs.pop(jid, None)
            if jid in self._order:
                self._order.remove(jid)

    def submit(self, fn: Callable[[], dict]) -> dict:
        with self._lock:
            self._sweep()
            waiting = sum(1 for v in self._jobs.values() if v["status"] in ("queued", "running"))
            if waiting >= self.max_queue:
                raise Busy("대기열이 가득 찼습니다")
            jid = uuid.uuid4().hex
            self._jobs[jid] = {"status": "queued", "created": time.monotonic()}
            self._order.append(jid)
        self._pool.submit(self._run, jid, fn)
        return self.get(jid)

    def _run(self, jid: str, fn: Callable[[], dict]) -> None:
        with self._lock:
            job = self._jobs.get(jid)
            if job is None:
                return
            job.update(status="running", started=time.monotonic())
        try:
            result, err = fn(), None
        except JobError as e:
            result, err = None, {"status": e.status, "detail": e.detail}
        except Exception as e:  # 예상 못 한 오류도 화면이 끝없이 기다리지 않게 실패로 남긴다
            result, err = None, {"status": 500, "detail": f"OCR 처리 중 오류가 났습니다({type(e).__name__})."}
        with self._lock:
            job = self._jobs.get(jid)
            if job is not None:
                job.update(status="error" if err else "done", result=result, error=err, done_at=time.monotonic())

    def get(self, jid: str) -> dict | None:
        with self._lock:
            job = self._jobs.get(jid)
            if job is None:
                return None
            ahead = 0
            if job["status"] == "queued":
                ahead = sum(1 for j in self._order[: self._order.index(jid)]
                            if self._jobs.get(j, {}).get("status") in ("queued", "running"))
            out = {"job": jid, "status": job["status"], "ahead": ahead,  # 앞에서 대기·처리 중인 접수 수
                   "waited_sec": round(time.monotonic() - job["created"], 1)}
            if job["status"] == "done":
                out["result"] = job["result"]
            elif job["status"] == "error":
                out["error"] = job["error"]
            return out
