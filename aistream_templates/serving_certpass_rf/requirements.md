# CertPass 인증 판정 서빙 — 요구사항과 API 명세

- 문서 갱신: 2026-11-07 15:55 (KST)
- 기준 코드 버전: `modified_version.md` v0.1.0
- 템플릿: `serving/7팀_certpass_rf` 버전 1 (시드: SSD 이미지 검출 예제 → 표 데이터 분류 서빙으로 교체)
- MLflow 모델 버전: 워크플로에서 연결하는 등록 모델 버전(플랫폼 주입, 이 문서에 고정하지 않음)

## 1. 요구사항 (구현 전 정리)

| 구분 | 내용 | 근거 |
| --- | --- | --- |
| 목적 | 학습 템플릿 `ml/7팀_certpass_rf`가 등록한 랜덤포레스트 모델로, 제품×인증 한 행마다 4종 판정과 클래스별 확률을 돌려준다 | 사용자 결정(정식 학습·서빙은 AIStream) |
| 모델 | MLflow sklearn flavor `RandomForestClassifier` 1개, `name="model"`로 기록, 특징 열 이름(`feature_names_in_`) 포함 | 학습 템플릿 `src/train_runtime.py` |
| 입력 | 특징 96열(엔진 특징 `f_*`, 위험 특징 `r_*`, 인증 원-핫 `cert_*`, 규칙 판정 원-핫 `rule_*`), 숫자 | 학습 데이터 `feature_columns.json` |
| 출력 | `label`(COND·FAIL·NOT_APPLICABLE·PASS) + `proba_<클래스>` | 호출 측 `certcheck/ml_client.py`의 `parse_predictions` |
| 호출 측 | CertPass 앱(대회 서버)이 판정 화면마다 호출, `calibrate_aistream`이 평가셋 13,303행을 500행씩 호출 | `certcheck/calibrate_aistream.py` |
| 유지할 계약 | Ray Serve + FastAPI 구조, `load_model_input("model")`, `SERVING_ROOT_PATH`, 포트 8000, `/health`, Dockerfile·deployment.yaml 변경 없음 | `AGENTS.md`, 공통 작업 계약 |
| 확인된 사실 | 서빙 이미지는 Python 3.11(Dockerfile), 학습 이미지는 Python 3.12 | 각 Dockerfile |
| 추정 | 학습 이미지의 scikit-learn은 같은 범위(>=1.5,<1.8)의 최신 1.7.2. 서빙 시작 시 모델에 기록된 버전과 비교해 다르면 경고 | 개발 환경 설치 결과 |

## 2. 엔드포인트

외부 주소는 플랫폼이 붙이는 prefix + 아래 경로입니다. 앱은 `POST {서빙 주소}/predict`를 `AISTREAM_URL`로 씁니다.

| Method | 경로 | 용도 | 요청 형식 | 성공 응답 |
| --- | --- | --- | --- | --- |
| POST | `/predict` | 판정 추론 | `application/json` | 200, `PredictResponse` |
| GET | `/health` | 모델 준비 확인 | 없음 | 200, 상태·클래스·모델 버전 |
| GET | `/info` | 특징 열 순서·제한값 조회 | 없음 | 200 |

인증: 템플릿 코드에는 없음(플랫폼 게이트웨이 정책은 미확인).

## 3. 요청 필드와 검증

`dataframe_split`과 `instances` 중 **하나만** 보냅니다.

| 필드 | 타입 | 필수 | 설명·제약 |
| --- | --- | --- | --- |
| `dataframe_split.columns` | 문자열 배열 | 둘 중 하나 | 특징 열 이름. 중복 불가. 모델 특징 96열을 모두 포함해야 함. 모르는 열은 무시하고 `ignored_columns`로 알려 줌 |
| `dataframe_split.data` | 숫자 배열의 배열 | 〃 | 행마다 `columns`와 같은 개수·순서 |
| `instances` | 객체 배열 | 〃 | `{열 이름: 값}` 행 목록 |

- 행 수: 1 이상 `--max_rows`(기본 5,000) 이하
- 값: 숫자만, 빈칸·NaN·무한대 불가
- 열 순서: 서버가 모델 학습 순서로 다시 맞춤. 예전 이름 `rule_NA`는 `rule_NOT_APPLICABLE`로 읽음(학습 템플릿과 같은 규칙)

## 4. 요청 예시 (열·값 축약)

```json
{"dataframe_split": {"columns": ["f_n_ingredients", "r_max_sim_banned", "cert_EU_CPNP", "rule_COND"], "data": [[18, 0.42, 1, 1]]}}
```

실제 요청은 96열 전부를 보내야 합니다. 열 목록은 `GET /info`의 `features`로 받을 수 있습니다.

## 5. 성공 응답

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `predictions[]` | 객체 배열 | 요청 행 순서 그대로. 각 행 `label`, `proba_COND`, `proba_FAIL`, `proba_NOT_APPLICABLE`, `proba_PASS`(소수 6자리) |
| `classes` | 문자열 배열 | 확률 순서(모델 `classes_`) |
| `model` | 객체 | `registered_model`, `model_version`(플랫폼 주입값), `n_features`, `sklearn`, `sklearn_trained` |
| `ignored_columns` | 문자열 배열 | 모델이 쓰지 않아 무시한 열 |

```json
{"predictions": [{"label": "PASS", "proba_COND": 0.250429, "proba_FAIL": 0.256, "proba_NOT_APPLICABLE": 0.235, "proba_PASS": 0.258571}],
 "classes": ["COND", "FAIL", "NOT_APPLICABLE", "PASS"],
 "model": {"registered_model": "smoke-model", "model_version": "1", "n_features": 96, "sklearn": "1.7.2", "sklearn_trained": "1.7.2"},
 "ignored_columns": []}
```

위 값은 개발 환경 시험 모델(무작위 데이터)의 출력이며 실제 판정 결과가 아닙니다.

## 6. 동시 요청

- 단위: Ray Serve replica 하나(Deployment 기본값, replica 수는 템플릿에서 바꾸지 않음)
- 추론은 `asyncio.to_thread`로 이벤트 루프 밖에서 실행해 `/health`가 막히지 않습니다.
- replica당 동시 계산은 `--max_concurrency`(기본 2)까지, 넘는 요청은 순서대로 기다립니다(거절하지 않음).
- 랜덤포레스트 내부 스레드는 `--n_jobs`(기본 2). 학습 때 저장된 `n_jobs=-1`을 시작 시 바꿉니다(결과는 같고 CPU 사용만 줄어듦).
- 작업 ID·폴링 방식은 없습니다(동기 응답).

## 7. 오류 응답

| HTTP | 조건 | 응답 | 호출 측 처리 |
| --- | --- | --- | --- |
| 422 | 두 형식을 함께 보내거나 하나도 안 보냄, 숫자가 아닌 값(FastAPI 검증) | `{"detail": [...]}` | 요청 형식 수정 |
| 422 | 특징 열 누락, 값 개수 불일치, 빈 요청, 행 수 초과, NaN·무한대, 중복 열 | `{"detail": "<이유>"}` | 열·값 수정, 큰 요청은 나눠 보내기 |
| 500 | 추론 중 예외 | `{"detail": "추론 중 오류가 났습니다..."}` | 서버 로그 확인 |
| 연결 실패 | 모델 로딩 실패로 replica가 뜨지 않음, 60분 무호출 뒤 일시정지 | 응답 없음 | 서빙 로그 확인, 첫 호출은 깨우는 시간을 기다림 |

## 8. 파일 역할

| 파일 | 역할 | 주요 함수·클래스 |
| --- | --- | --- |
| `main.py` | 진입점, Click 옵션(`--max_rows`, `--n_jobs`, `--max_concurrency`) | `main()` |
| `src/serving_runtime.py` | 모델 입력 해석 → Ray·Serve 시작 → Deployment 실행 | `run_serving()` |
| `src/model_inputs.py` | 플랫폼 `MODEL_INPUTS_JSON` 해석(시드 원본 그대로, FROM_VERSION만 허용) | `load_model_input()` |
| `src/app.py` | FastAPI 라우트, Ray Serve Deployment | `ServingModel` |
| `src/predictor.py` | 모델 로딩, 입력 검증, 추론 | `load_predictor()`, `Predictor` |
| `src/dto.py` | 요청·응답 스키마 | `PredictRequest`, `PredictResponse` |
| `tests/test_predictor.py` | 로딩·검증·추론 계약 시험(가짜 데이터 모델) | — |

## 9. 모델 로딩과 생명주기

| 시점 | 함수 | 처리 | 실패 시 |
| --- | --- | --- | --- |
| 프로세스 시작 | `run_serving` → `load_model_input("model")` | 플랫폼 주입 `mountPath`, 등록 모델 이름·버전 읽기 | 예외, 서버 안 뜸 |
| replica 초기화 | `ServingModel.__init__` → `load_predictor` | `mlflow.sklearn.load_model(mountPath)` 1회, 특징·클래스 확인, `n_jobs` 조정, sklearn 버전 비교 | 예외, replica 준비 안 됨(health 응답 없음) |
| 요청 | `predict` | 메모리의 모델 재사용, 요청마다 다시 읽지 않음 | 422 또는 500 |
| 재시작·replica 추가 | 위 초기화 반복 | replica마다 모델 1벌 | — |

## 10. 실행 설정

| 항목 | 값 | 상태 |
| --- | --- | --- |
| 모델 입력 포트 | `model`, `MLFLOW_MODEL`, `/app/volume/models/model`, `mlflow` | `template-inout.yaml` |
| 출력 포트 | `serving`, `SERVING`, `http` | 〃 |
| 컨테이너 포트 | 8000(deployment.yaml) ↔ `serve.start(port=8000)` | 일치 |
| 실행 명령 | `uv run --active --no-sync python main.py`(deployment.yaml, 변경 없음) | 일치 |
| 의존성 | `mlflow==3.13.0`, `scikit-learn>=1.5,<1.8`, `numpy>=2,<3`, `protobuf>=3.20.3,<7`, `ray[serve]`, `fastapi<0.112`, `pandas`, `click` | 개발 환경 설치: mlflow 3.13.0, sklearn 1.7.2, numpy 2.4.6, ray 2.55.1, protobuf 6.33.6 |
| GPU | 쓰지 않음 | — |

## 11. 검증 상태 (2026-11-07 개발 환경 `certpass-serve-dev`)

| 항목 | 방법 | 결과 |
| --- | --- | --- |
| 경량 진입점 | click만 설치한 격리 환경에서 `python main.py --help` | 통과 |
| 단위 시험 | Python 3.11 + 선언 의존성, `pytest tests` 13건 | 통과 |
| 서버 실행 | 96열 시험 모델 + 시험용 `MODEL_INPUTS_JSON` + `SERVING_ROOT_PATH`로 `python main.py` 실행 | 통과(health 200, 10초 안) |
| API 계약 | `dataframe_split`·`instances` 200, 잘못된 요청 4종 422 | 통과 |
| 동시 요청 | 3,000행 요청 6건 동시 | 통과(모두 200) |
| 호출 측 호환 | 응답을 `certcheck/ml_client.parse_predictions`로 해석 | 통과 |
| protobuf 7 문제 | Ray Serve 2.55 + protobuf 7.36에서 배포 실패 → `<7`로 고정 후 통과 | 해결 |
| 이미지 빌드·플랫폼 서빙·실제 학습 모델 추론 | — | 미검증(빌드 후 워크플로에서 확인) |
