"""학습한 검출·인식 가중치를 MLflow pyfunc 모델 하나로 묶는다(AIStream 모델 등록·서빙용).

실행(axgpu, mlflow==3.13.0 환경): python package_mlflow.py --det runs/det1/best.pt --rec runs/rec2/best.pt --out mlflow_model
- 모델 하나 안에 가중치 2개(artifacts)와 추론 코드(code_paths: pipeline·train_det·train_ocr·tarstore)를 함께 넣는다
- 서빙: m = mlflow.pyfunc.load_model(mountPath); m.unwrap_python_model().read(사진 바이트) → 글자·줄·전성분
- pyfunc predict 규약도 지원: DataFrame 열 image_b64(사진 base64) → 행마다 JSON 문자열
"""
from __future__ import annotations

import argparse
import shutil
import tempfile
from pathlib import Path

import mlflow.pyfunc

HERE = Path(__file__).resolve().parent
CODE = [HERE / f for f in ("pipeline.py", "train_det.py", "train_ocr.py", "tarstore.py")]


class PackageOCRModel(mlflow.pyfunc.PythonModel):
    def load_context(self, context):
        from pipeline import PackageOCR  # code_paths로 함께 실린 모듈

        self.ocr = PackageOCR(context.artifacts["det"], context.artifacts["rec"])

    def read(self, data: bytes) -> dict:
        return self.ocr.read(data)

    def predict(self, context, model_input, params=None):
        import base64
        import json

        return [json.dumps(self.ocr.read(base64.b64decode(b)), ensure_ascii=False) for b in model_input["image_b64"]]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--det", required=True)
    ap.add_argument("--rec", required=True)
    ap.add_argument("--out", default="mlflow_model")
    a = ap.parse_args()
    out = Path(a.out)
    if out.exists():
        shutil.rmtree(out)
    # 서빙은 모델 폴더에서 det.pt·rec.pt라는 이름으로 찾는다 → 이름을 고정해 넣는다
    stage = Path(tempfile.mkdtemp())
    shutil.copy(a.det, stage / "det.pt")
    shutil.copy(a.rec, stage / "rec.pt")
    mlflow.pyfunc.save_model(
        str(out), python_model=PackageOCRModel(), artifacts={"det": str(stage / "det.pt"), "rec": str(stage / "rec.pt")},
        code_paths=[str(p) for p in CODE],
        pip_requirements=["torch", "torchvision", "numpy", "pillow", "scipy", "mlflow==3.13.0"])
    shutil.rmtree(stage)
    print(f"saved {out} ({sum(f.stat().st_size for f in out.rglob('*') if f.is_file()) / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
