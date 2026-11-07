"""모델 로딩과 사진 읽기를 담당합니다. FastAPI·Ray와 분리해 단위 시험이 가능하게 둡니다.

마운트된 모델 버전(MLflow 모델 폴더) 안에서 검출 가중치 det.pt와 인식 가중치 rec.pt를 찾아 읽는다.
학습(Python 3.12)과 서빙(3.11)의 버전 차이로 pickle 복원이 어긋나지 않게, MLflow pyfunc 객체 대신
가중치(state_dict)만 읽고 이 템플릿에 함께 넣은 추론 코드(src/ocr_core)로 모델을 다시 만든다.
"""

import logging
import sys
import time
from pathlib import Path

logger = logging.getLogger(__name__)
CORE = Path(__file__).resolve().parent / "ocr_core"


class InputError(ValueError):
    """호출 측이 고쳐야 하는 요청 오류(HTTP 4xx)."""


def _one(root: Path, name: str) -> str:
    hits = sorted(p for p in root.rglob(name) if p.is_file())
    if len(hits) != 1:
        raise FileNotFoundError(f"모델 폴더에서 {name}이 정확히 1개여야 합니다(찾은 파일: {[str(h) for h in hits]})")
    return str(hits[0])


def load_reader(model_dir: str, model_meta: dict, threads: int):
    """마운트된 모델에서 가중치 2개를 찾아 PackageOCR을 만든다. 실패하면 예외를 그대로 올린다."""
    import torch

    t0 = time.time()
    logger.info("[load_model] 시작 %s", model_dir)
    try:
        torch.set_num_threads(threads)
        if str(CORE) not in sys.path:
            sys.path.insert(0, str(CORE))
        from pipeline import PackageOCR

        root = Path(model_dir)
        reader = PackageOCR(_one(root, "det.pt"), _one(root, "rec.pt"), device="cpu")
    except Exception:
        logger.exception("[load_model] 실패 (%.1fs)", time.time() - t0)
        raise
    meta = {**model_meta, "charset": len(reader.charset), "device": "cpu", "threads": threads}
    logger.info("[load_model] 완료 (%.1fs) 글자표 %d종", time.time() - t0, len(reader.charset))
    return reader, meta


JPEG, PNG, WEBP = b"\xff\xd8", b"\x89PNG", b"RIFF"


def check_image(data: bytes, max_mb: int) -> None:
    if not data:
        raise InputError("사진 파일이 비어 있습니다.")
    if len(data) > max_mb * 1024 * 1024:
        raise InputError(f"사진은 {max_mb}MB까지 받습니다.")
    if not data.startswith((JPEG, PNG, WEBP)):
        raise InputError("JPEG·PNG·WebP 사진만 받습니다.")
