# serving/7팀_package_ocr — 화장품 포장 사진 OCR 서빙 (v0.5.0, AIStream 템플릿 버전 3으로 게시·배포)

시드(새 서빙 템플릿 개발 환경)에 이 파일들을 덮어쓴다. Dockerfile·deployment.yaml·src/model_inputs.py는 시드 것을 그대로 둔다.

| 파일 | 내용 |
|---|---|
| main.py | click 옵션(--max_mb 8, --threads 4, --max_concurrency 1)만 최상위 import |
| template-inout.yaml | 입력 model(MLFLOW_MODEL, /app/volume/models/model), 출력 serving(SERVING, http) |
| pyproject.toml | torch·torchvision CPU 판(download.pytorch.org/whl/cpu), mlflow==3.13.0, protobuf<7, python-multipart, rapidfuzz(사전 해독 후보 찾기) |
| src/predictor.py | 모델 폴더에서 det.pt·rec.pt를 하나씩 찾아 state_dict로 복원(Python 3.12 학습 ↔ 3.11 서빙 pickle 차이 회피), 사전 단어(ocr_core/lexicon_words.txt.gz)가 있으면 사전 제한 해독을 켬(OCR_LEXICON=0이면 끔), health에 lexicon_words |
| src/app.py | POST /predict(multipart file) → 단어·줄·전체 글자·전성분, GET /health |
| src/serving_runtime.py | load_model_input("model") → ray.init → serve.start(port 8000) → serve.run |
| src/ocr_core/ | ocr/의 추론 코드 사본(pipeline·train_det·train_ocr·tarstore·lexicon) |
| src/ocr_core/lexicon_words.txt.gz | 식약처 화장품 원료성분 사전(공공데이터)에서 뽑은 성분명 단어 56,563개(모델 업로드가 .csv를 받지 않아 템플릿에 넣음) |

검증(2026-11-07, axgpu, Python 3.12 venv): 가짜 MODEL_INPUTS_JSON(FROM_VERSION, mountPath=시험 모델) → /health 200, /predict 사진 → JSON, 사진 아닌 파일 → 415.
v0.5.0(2026-11-08): AIStream 빌드 성공(00:38, 9분)·게시 → 워크플로 재실행으로 서빙 반영(00:47, health lexicon_words 56407).
실서빙 실측(학습에 없던 제품 사진 12장): 실패 0, 정밀도 96.4%·재현율 95.7%, 중간 3.3초. 변경 이력은 modified_version.md
