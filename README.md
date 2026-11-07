# CertPass — 화장품 수출 인증, 통과까지 남은 것

2026 전남광주 기업 AX 혁신챌린지 7팀 (트랙 B · 바이오/화장품 · ㈜지너스인터내셔널). 코드 패키지 이름은 `certcheck`.

화장품의 전성분(또는 **포장 사진**)과 제품 정보를 넣으면 국내외 인증·등록 56종 각각을
**통과 가능 / 조건부 / 불가 / 해당 없음**으로 판정하고, 근거 조항·해야 할 일·서류 초안을 만든다.

- 불가: 재처방해야만 통과 · 조건부: 재처방 없이 서류·현지 책임자·문구·시험·원료 증빙으로 통과 · 통과 가능: 지금 상태로 통과 · 해당 없음: 적용 대상 아님
- 모든 판정은 예비 판정이다. 최종 판단은 인증기관과 자격 있는 안전성 평가자가 한다.
- 시연: https://devopen-gpu.jntp-ax.or.kr/i/FBi4CwFvT4Pe38Xd/ (대회 서버)

## 동작 구조

```
포장 사진 ──▶ [딥러닝 OCR] 글자 위치 찾기(ResNet18-FPN) + 글자 읽기(CNN-Transformer-CTC) ──▶ 전성분 글자
                                    └ AIStream 서빙(serving/7팀_package_ocr, 배포 진행 중)
전성분 글자 ──▶ 성분명 표준화(식약처 원료성분 사전, 쉼표 누락·줄바꿈 보정) ──▶ 표준 INCI
표준 INCI + 제품 정보 ──▶ [규칙 엔진] 인증 카드 56종 × 성분 규제표(10개 관할) ──▶ 4종 판정·근거·할 일
판정 결과 ──▶ [ML] 랜덤포레스트 '숨은 불가' 경보(입력 오류로 규칙이 놓친 불가) ── AIStream 서빙(7팀_certpass_rf)
판정 결과 ──▶ 서류 초안(docx·xlsx), [LLM] AgentStream 근거 설명
```

## 폴더 구조

| 경로 | 내용 |
|---|---|
| `certcheck/` | 판정 엔진과 API. `classify.py`(판정 규칙), `data.py`(데이터 적재), `normalize.py`·`names.py`(성분명 정규화), `app.py`(FastAPI), `schemas.py`(입력 검증·상한), `docs_gen.py`·`routes_docs.py`(서류 초안) |
| `certcheck/` (ML·연동) | `synth.py`(합성 학습 데이터), `export_aistream.py`(AIStream 업로드용 변환), `ml_client.py`(RF 서빙 호출), `calibrate_aistream.py`(경보 기준 실측), `ocr_client.py`(OCR 서빙 호출·성분명 맞추기), `llm_client.py`(AgentStream), `mfds_api.py`(식약처 API 수집) |
| `ocr/` | 포장 OCR 딥러닝: `crop_633.py`·`resize_633.py`(학습 데이터 만들기), `train_ocr.py`(인식), `train_det.py`(검출), `pipeline.py`(사진 → 전성분), `e2e_eval.py`·`baseline_easyocr.py`(평가), `package_mlflow.py`(AIStream 등록용 묶기), `guard.sh`(메모리 감시) |
| `aistream_templates/` | AIStream 템플릿 사본: `ml_certpass_rf`(RF 학습), `serving_certpass_rf`(RF 서빙), `serving_package_ocr`(OCR 서빙) |
| `data/certs/` | 인증 요건 카드 56종(YAML, 규약은 `data/certs/README.md`) |
| `data/regs/` | 성분 규제표: EU·일본 원문 가공(`성분규제_통합표*.csv`), 식약처 API 8개 관할(`성분규제_식약처API.csv`) |
| `data/kr/` | 식약처 원료성분 사전·국가별 규제 요약, 관세청 수출 실적 |
| `data/ingredients/` · `data/public/` · `data/ml/` | 성분 속성표 · 공개 데모 제품(함량은 가상값) · 모델 입력 열 순서 |
| `web/` | 화면(정적 HTML·JS·CSS, API와 같은 서버). 디자인 토큰은 `design-system/MASTER.md` |
| `deploy/` | 대회 서버 배포(`push_axgpu.sh`, `run_server.sh`, 서버 전용 설정 `server.env.example`), 백업(`backup_axgpu_to_jinus.sh`), AIStream SSH 설정 |
| `docs/` | 진행 기록(`AIStream_진행기록.md`, `AgentStream_진행기록.md`), OCR 평가 결과(`ocr_results/`), **데이터 출처와 이용 조건(`DATA_SOURCES.md`)** |
| `tests/` | pytest 61개(판정 규칙·API 입력 상한·ML/OCR/LLM 연동) |

## 실행

```bash
uv venv .venv && uv pip install --python .venv/bin/python -r requirements-dev.txt
.venv/bin/uvicorn certcheck.app:app --port 8501      # http://localhost:8501
.venv/bin/python -m pytest -q tests
```

서버 설정(환경변수, 대회 서버는 `deploy/server.env`): `AISTREAM_URL`·`AISTREAM_FORMAT`·`AISTREAM_FAIL_THRESHOLD`(RF 경보),
`CERTCHECK_OCR_URL`(포장 사진 OCR), `AGENTSTREAM_*`(LLM). 없으면 해당 기능만 꺼지고 규칙 판정은 그대로 된다.

대회 서버는 프록시가 경로 접두사(`/i/<토큰>`)를 그대로 넘기므로 `CERTCHECK_BASE=/i/<토큰>`과 `certcheck.app:asgi`(접두사 마운트)로 띄운다.
```bash
deploy/push_axgpu.sh                                         # 중계 서버가 큰 전송을 끊어 12KB 조각으로 전송
ssh axgpu "cd /data/certcheck && bash deploy/run_server.sh"
```

## 모델과 평가 (모두 학습에 쓰지 않은 데이터로 측정)

**포장 사진 OCR (딥러닝, B200에서 학습 → AIStream 서빙)** — 상세는 `docs/ocr_results/README.md`
| 단계 | 7팀 모델 | 비교: EasyOCR(공개 범용) |
|---|---|---|
| 글자 위치 찾기, 평가 사진 1,054장 | F1 0.946 | — |
| 단어 읽기, 같은 5,000단어 | 단어 93.5% · 성분명 95.6% | 단어 59.0% · 성분명 27.6% |
| 사진 → 전성분, 학습에 없던 제품 150장 | 정밀도 98.2% · 재현율 90.3% (F1 0.94) | F1 0.35 |

**숨은 불가 경보 (랜덤포레스트, AIStream 학습·서빙)** — 상세는 `docs/AIStream_진행기록.md`
- 평가셋 13,303행: 4종 판정 정확도 모델 98.5% / 규칙만 98.3%
- 경보 기준 0.175: 규칙이 놓친 불가의 57% 탐지, 경보 정밀도 40%, 오경보율 1.6%

## 데이터

출처·이용 조건·운영진 검토 결과는 [`docs/DATA_SOURCES.md`](docs/DATA_SOURCES.md).
- 식약처 공공데이터 API(이용허락범위 제한 없음), EU CosIng(CC BY 4.0), 일본 후생노동성 화장품기준을 판정용으로 가공해 쓴다.
- AI Hub 데이터(의약품·화장품 패키징 OCR, 생활화학제품 주성분 건강유해성)는 약관에 따라 저장소에 넣지 않는다.
  이 OCR 모델은 과학기술정보통신부의 재원으로 한국지능정보사회진흥원의 지원을 받아 구축된 '의약품, 화장품 패키징 OCR 데이터'를 활용하여 학습했습니다(https://aihub.or.kr).
- 운영진 검토에서 이용 불가로 분류된 자료(중국 IECIC·안전기술규범 2015, 대만 TFDA 목록, COSMOS 등)는 원문을 넣지 않고 식약처 API 등으로 대체했다.
- 자사 실데이터(배합비·서류 원본)는 `data/private/`에만 두며 저장소에 올리지 않는다.
