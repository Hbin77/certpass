# serving/7팀_package_ocr — 화장품 포장 사진 OCR 서빙 (작성본)

시드(새 서빙 템플릿 개발 환경)에 이 파일들을 덮어쓴다. Dockerfile·deployment.yaml·src/model_inputs.py는 시드 것을 그대로 둔다.

| 파일 | 내용 |
|---|---|
| main.py | click 옵션(--max_mb 8, --threads 4, --max_concurrency 1)만 최상위 import |
| template-inout.yaml | 입력 model(MLFLOW_MODEL, /app/volume/models/model), 출력 serving(SERVING, http) |
| pyproject.toml | torch·torchvision CPU 판(download.pytorch.org/whl/cpu), mlflow==3.13.0, protobuf<7, python-multipart |
| src/predictor.py | 모델 폴더에서 det.pt·rec.pt를 하나씩 찾아 state_dict로 복원(Python 3.12 학습 ↔ 3.11 서빙 pickle 차이 회피) |
| src/app.py | POST /predict(multipart file) → 단어·줄·전체 글자·전성분, GET /health |
| src/serving_runtime.py | load_model_input("model") → ray.init → serve.start(port 8000) → serve.run |
| src/ocr_core/ | ocr/의 추론 코드 사본(pipeline·train_det·train_ocr·tarstore) |

검증(2026-11-07, axgpu, Python 3.12 venv): 가짜 MODEL_INPUTS_JSON(FROM_VERSION, mountPath=시험 모델) → /health 200, /predict 사진 → JSON, 사진 아닌 파일 → 415.
미검증: AIStream 이미지 빌드(Python 3.11), 플랫폼 배포.
