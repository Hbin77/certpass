# AIStream 학습·서빙 진행 기록 (7팀 CertPass)

정식 학습은 AIStream에서 한다. AIStream 카탈로그에 표 데이터용 템플릿이 없어 자체 템플릿을 만든다.

| 시각(KST) | 단계 | 내용 | 상태 |
|---|---|---|---|
| 2026-11-07 15:05 | SSH 접속 | AIStream 개발 환경 SSH 키 등록, 접속 설정은 PC 기본 ssh 설정을 건드리지 않는 별도 파일 사용 | 완료 |
| 2026-11-07 15:10 | 학습 템플릿 작성 | ml/7팀_certpass_rf v1: train.py 단일 Step, 입력 train_dataset·test_dataset(CSV)·base_model(FRESH 허용), 출력 trained_model(mlflow.sklearn RF). 사본: `aistream_templates/ml_certpass_rf/` | 완료 |
| 2026-11-07 15:10 | 개발 환경 검증 | 표본 3,000/1,500행으로 학습·평가·MLflow(sqlite) 기록, 모델 1개·재로딩, click만 설치된 환경 --help 통과 | 통과 |
| 2026-11-07 15:11 | 변경사항 저장 | Commit 72dadc6da46d (Revision 1446120a-…) | 완료 |
| 2026-11-07 15:12 | 빌드 요청 | 출력 버전 1v1 | 진행 중 |
| 2026-11-07 15:30 | 학습 템플릿 게시 | ml/7팀_certpass_rf 1v1 빌드 성공·게시(PUBLISHED) | 완료 |
| 2026-11-07 15:37 | 서빙 템플릿 생성 | serving/7팀_certpass_rf 버전 1, 개발 세션 certpass-serve-dev(4 CPU·8 GiB) RUNNING | 완료 |
| 2026-11-07 15:55 | 서빙 템플릿 작성 | 시드(SSD 예제)를 RF 서빙으로 교체: POST /predict(dataframe_split·instances → label·proba_*), GET /health·/info, replica 초기화 때 mlflow.sklearn 1회 로드. Dockerfile·deployment.yaml 변경 없음. 사본: `aistream_templates/serving_certpass_rf/`, 명세 requirements.md, 이력 modified_version.md v0.1.0 | 완료 |
| 2026-11-07 15:55 | 개발 환경 검증 | click 전용 --help, Python 3.11 pytest 13건, 96열 시험 모델로 Ray Serve 실행(health·두 형식·422 4종·3,000행 6건 동시), 앱 parse_predictions 해석. protobuf 7.36에서 Ray Serve 배포 실패 → protobuf<7 고정 | 통과 |

| 2026-11-07 15:52 | 서빙 변경사항 저장·빌드 요청 | Commit 7d9b96de3de3 | 완료 |
| 2026-11-07 16:00 | 서빙 빌드 | 소스 추출·검증 → 이미지 빌드·push → 검증 후 결과 저장 모두 통과. 출력 버전 TPV-6738c9b5, Step SERVING(TPS-06930c93), 파라미터 max_rows 5000·n_jobs 2·max_concurrency 2 | 성공 |

| 2026-11-07 16:20 | 워크플로 종료(kill) → 재구성 | 이전 워크스페이스(해커톤 교육, 계정 eduhack21)의 실행이 종료됨. 운영진 안내로 팀 워크스페이스 "AX 해커톤 7팀"(계정 axhack21)에서 학습·서빙 템플릿을 다시 만들기로 함. 새 계정에 SSH 키 등록(지문 SHA256:ZSxouK…J6R24 일치), 데이터셋은 새로 업로드 필요 | 진행 |
| 2026-11-07 16:31 | 두 템플릿 재작성 | 학습 7팀_certpass_rf(개발 세션 certpass-rf-dev2), 서빙 serving/7팀_certpass_rf(certpass-serve-dev2)에 v0.1.0과 같은 코드 업로드(v0.1.1 이력). 시드 Dockerfile·job.yaml·deployment.yaml 해시가 이전과 같아 보호 파일 변경 없음 | 완료 |
| 2026-11-07 16:36 | 개발 환경 검증 | 학습: click 전용 --help, 표본 3,000/1,500행 FRESH 학습·MLflow 기록·모델 1개 재로딩. 서빙: pytest 13건, Ray Serve 실행 시험. 교차 확인: 학습 조합(3.12·numpy 2.5.4)으로 만든 모델을 서빙 조합(3.11·numpy 2.4.6)에서 로드·예측 성공 | 통과 |

| 2026-11-07 16:48 | 학습 템플릿 빌드(팀 워크스페이스) | 7팀_certpass_rf 버전 1, 소스 Commit 759a15ff967e, 빌드 성공 후 자동 PUBLISHED | 완료 |
| 2026-11-07 17:04 | 서빙 템플릿 빌드(팀 워크스페이스) | serving/7팀_certpass_rf 버전 1, Commit 7e6fbee7ab49, 16:36 요청 → 빌드 대기 → 17:04 성공, 출력 버전 TPV-fc7341e4, 자동 PUBLISHED | 완료 |

학습·배포 방식(16:05 사용자 결정): 학습은 팀 B200(axgpu)과 AIStream 둘 다 허용. OCR 같은 큰 모델은 B200에서 학습하고 추론 배포는 AIStream 서빙으로 한다. RF는 만든 AIStream 학습 템플릿을 그대로 쓴다.

## 남은 순서
1. ~~서빙 템플릿 게시~~ · ~~데이터셋 업로드~~ · ~~워크플로 실행~~ · ~~calibrate·경보 기준~~ · ~~대회 서버 연결~~ (17:56 모두 완료, 아래 "RF 워크플로 실행" 표)
2. 발표 근거 캡처: 워크플로 실행 화면, 학습 로그 상세(`[load_dataset]`·`[evaluate]` 줄) 또는 MLflow 실험 260 지표 화면
3. 발표 직전: 서빙은 60분 무호출 시 자동 일시정지 → 시연 전에 `/health` 한 번 호출하거나 화면에서 켜 두기

## 딥러닝: 화장품 포장 글자 인식(OCR) — 2026-11-07 시작 (A안: 사용자 선택)
| 시각(KST) | 단계 | 내용 | 상태 |
|---|---|---|---|
| 15:32 | 데이터 | AI Hub 633 검증 원천 VS1(30GB) jinusubuntu로 다운로드 시작. 라벨 VL1: 화장품 사진 10,152장·단어 약 146만 개·글자 1,291종 | 진행 중 |
| 15:35 | 전송 경로 | axgpu는 AI Hub 접속 불가(시간 초과). 제한 키 방식은 jinusubuntu 홈 폴더 공유 권한 때문에 sshd가 거부 → 키 줄 즉시 삭제. 방화벽 임시 허용 방식은 사용자 승인 대기 | 대기 |
| 15:45 | 학습 코드 | `ocr/crop_633.py`(단어 자르기, 사진 단위 9:1 분할), `ocr/train_ocr.py`(CNN+Transformer 인코더+CTC, 19.5M 파라미터, bf16). B200(MIG 45GB)에서 가짜 데이터로 수렴 확인(단어 정확도 100%) | 통과 |
- 학습은 B200(axgpu, DevStream 대회 서버)에서 하고, 결과 모델은 AIStream 모델 새 버전으로 등록할 계획(사용자 지시: "gpu는 b200서버 있잖아")
| 16:30 | 데이터 준비 | VS1 32GB 다운로드 완료 → 화장품 사진 10,152장에서 단어 158만 개 자름(학습 141만·평가 16.6만, 사진 단위 분할·겹침 0), 검출용 1280px 사진 10,152장 | 완료 |
| 16:50 | 전송 | jinusubuntu → axgpu 임시 HTTP(무작위 경로, ufw axgpu IP만 허용) 10개 파일 크기 대조 OK → 서버 종료·ufw 규칙 삭제·차단 확인 | 완료 |
| 16:56 | 사고 | 검출 시험이 axgpu 메모리 16GB 초과 → 서버 재시작(웹 일시 중단, 즉시 재기동). 대책: tar 지연 읽기, guard.sh(여유 3GB 미만 시 학습 중지), uint8 전달·prefetch 1(/dev/shm 64MB) | 조치 |
| 17:14 | 기준선 | EasyOCR(공개 범용, ko+en) 평가 5,000단어: 단어 59.0%, 글자 오류율 17.7%, 성분명 27.6% | 완료 |
| 17:15 | 버그 수정 | 평가 시 CTC 풀기가 채움 영역까지 읽던 버그(단어 4.5%로 보였음) → 단어별 길이까지만 풀도록 수정(pipeline.py도) | 수정 |
| 17:16 | 1회차 결과 | 같은 5,000단어: 단어 92.6%, 글자 오류율 3.5%, 성분명 93.0%. 학습에 없던 제품 사진만(3,130단어): 92.5%·3.7%·91.3% | 확인 |
| 17:19 | 재학습 | 동시 평가로 /dev/shm 부족 → 학습 중단 → 작업자 5·prefetch 1로 3회차 재학습(rec2) | 진행 중 |
| 17:25 | 앱 연결 | /api/ocr(사진 8MiB·형식 검사·식약처 표준명 exact/fuzzy/unknown), 화면 '포장 사진으로 전성분 채우기'(브라우저에서 긴 변 2400px로 줄여 전송), 테스트 6개 추가(전체 54 통과) | 완료 |
| 17:28 | MLflow 묶기 | package_mlflow.py: 검출·인식 가중치+추론 코드를 pyfunc 1개(87MB)로. CPU 환경에서 불러오기·사진 읽기 동작 확인 | 완료 |

## RF 워크플로 실행 (팀 워크스페이스, ax-45 세션 기록)
| 시각(KST) | 단계 | 내용 | 상태 |
|---|---|---|---|
| 2026-11-07 17:28 | 워크플로 #1 | 7팀_certpass_rf(학습) → serving/7팀_certpass_rf. 학습 17:28~17:29(42초) 완료, MLflow 실험 260 run 55fb4729…, 등록 모델 버전 RMV-f4290176. 워크플로 비용 0.73크레딧 | 학습 완료 |
| 2026-11-07 17:30 | 서빙 SV-(RF 서빙) | 서비스 URL <RF 서빙 URL(서버 설정 deploy/server.env)> (맥·대회 서버에서 응답 없음). 운영 상태 "실패": 컨테이너가 메모리 부족으로 종료(OOM). 원인: 서빙 노드 자원을 1C1GB로 설정한 실수(사용자 확인). 로컬 실측으로 Ray Serve 전체 약 2.5~3GB 추정 → 4C8GB로 다시 띄우기로 함 | 실패 → 재시도 |
| 2026-11-07 17:25 (로컬 측정) | 자원 산정 | 학습 템플릿 코드 전체 데이터: 최대 메모리 0.82GB, 약 12 CPU초, 모델 40MB. 서빙(맥): 대시보드 0.7GB·빈 작업자 0.62GB(8개)·드라이버 0.78GB·replica 0.38GB·컨트롤러+프록시 0.37GB | 참고 |
| 2026-11-07 17:3x | 서빙 재시도 v2 | workflow-WFTR-db7d2772(v2), 서빙 노드 2C4GB → 다시 OOM. 의심 원인: 개발 세션 `nproc`이 96(컨테이너 할당과 무관하게 서버 전체 CPU)이라 Ray가 빈 작업자를 CPU 수만큼 띄움 [미확인: 서빙 컨테이너 안에서 직접 확인 못 함] | 실패 |
| 2026-11-07 17:45 | 서빙 v3 정상 | workflow-WFTR-093bfdf9(v3), SVV-06813…, 운영 상태 "정상"·승인 완료. 서빙 노드 자원 설정은 [미확인](사용자 화면). 맥·대회 서버 둘 다 `/health`·`/info`·`/docs` 200(약 0.19초). health: 등록 모델 model-c16f88b2 버전 3, 특징 96개, 학습·서빙 sklearn 1.7.2 일치. 서빙 누적 7.76크레딧(17:45) | 완료 |
| 2026-11-07 17:47 | 실측(calibrate_aistream) | 평가셋 13,303행(합성 제품 단위 분할, 학습 50,297행과 겹침 없음)을 서빙 `/predict`로 직접 호출(500행씩, 요청 지연 중앙 0.80초·최대 1.75초, 전체 21초). 4종 정확도 **모델 0.9854 / 규칙만 0.9831**. 오분류는 대부분 불가→조건부(모델 179건, 규칙 208건). 결과 `out/aistream_calib/calib_SV-(RF 서빙)_v3.json`, 확률 `proba_SV-(RF 서빙)_v3.json` | 완료 |
| 2026-11-07 17:50 | 경보 기준 확정 | 규칙이 불가가 아니라고 한 11,353건 중 실제 불가 210건 대상. 기준별(재현율/정밀도/경고 수/오경보율): 0.1 0.724/0.226/672/4.67%, 0.15 0.600/0.329/383/2.31%, **0.175 0.571/0.396/303/1.64%**, 0.2 0.476/0.422/237/1.23%, 0.3 0.300/0.624/101/0.34%, 0.5 0.133/1.000/28/0%. **0.175 채택**(F1 0.468·F2 0.525 모두 최대). 참고: 로컬 이진 분류기(기준 0.85)는 0.343/0.434 | 확정 |
| 2026-11-07 17:56 | 대회 서버 연결 | axgpu 기존 코드 백업(`/data/certcheck_backup/certcheck_code_before_aistream_0848.tgz`, UTC 08:48) → 맥 최신 코드(커밋 435b9b9 + `deploy/run_server.sh` 변경, 시험 54 통과) push → 재시작. run_server.sh 기본값: `AISTREAM_URL=…/SV-(RF 서빙)/predict`, `AISTREAM_FORMAT=mlflow`, `AISTREAM_FAIL_THRESHOLD=0.175`(빈 값 넘기면 끔). 공개 URL `/api/health` `ml_model:true`. 데모 D3: 판정 56건 중 53건에 AI 판정(회사 인증 3건 제외), 숨은 불가 경보 1건(KR_FUNCTIONAL_REPORT, 규칙 통과 가능, 불가 확률 0.182) | 완료 |

## RF 재학습 (운영진 데이터 검토 반영, ax-45)
| 시각(KST) | 단계 | 내용 | 상태 |
|---|---|---|---|
| 2026-11-07 19:20 | 판단 | 운영진 검토로 중국 IECIC·2015 규범, 대만 TFDA 목록이 '사용 불가'(ax-fd가 표에서 삭제, 식약처 API 15111772로 대체). 기존 합성 데이터는 일반 성분 후보를 **IECIC 목록에서 뽑았고** `f_n_not_in_inventory` 특징도 IECIC 기반 → 지금 AIStream 데이터셋·모델이 사용 불가 자료로 만들어진 상태. **재학습 필요** | 결정 |
| 2026-11-07 19:24 | 생성기 수정 | `certcheck/synth.py`: 일반 성분 후보를 식약처 원료성분사전(15111774, DATA_SOURCES '가능')에서 어느 관할 금지·제한 목록에도 없는 INCI 18,475개로 교체(`safe_pool`). 시험 61 통과 | 완료 |
| 2026-11-07 19:25 | 데이터 v6 | `out/private/ml/certcheck_train_v5.csv`(제품 1,200, seed 7, 기준일 2026-11-07) → `out/public/aistream_v5/`(학습 50,297·평가 13,303행, 열 96개 = 서빙 중 모델과 같음). 평가 정답 분포 COND 9,932·FAIL 2,310·NA 801·PASS 260, 숨은 불가 312건, IECIC 특징 0. 업로드용 사본 `~/Downloads/7팀_certpass_train_v6.csv`·`7팀_certpass_test_v6.csv` | 완료 |
| 2026-11-07 19:26 | 영향 확인 | 지금 서빙 모델(옛 데이터 학습)을 새 평가셋에: 정확도 모델 0.9787 / 규칙 0.9754, 기준 0.2에서 재현율 0.609·정밀도 0.662. 성능은 유지되지만 학습 자료 문제로 교체. 맥 가능성 확인(발표 수치 아님): 새 데이터 학습 시 정확도 0.9833 / 규칙 0.9754 | 참고 |
| 다음 | AIStream | 데이터셋 7팀_certpass_train·test에 v6 새 버전 업로드 → 기존 워크플로 재실행(새 데이터셋 버전 선택) → 서빙 새 버전 → calibrate_aistream(`out/public/aistream_v5`) → 기준값을 deploy/server.env(맥·axgpu)에 반영 | 대기 |

## 포장 OCR 서빙 (워크스페이스 'AX 해커톤 7팀')
| 시각(KST) | 단계 | 내용 | 상태 |
|---|---|---|---|
| 18:05 | 개발 세션 | serving/7팀_package_ocr(TP-7d2f1b98) 세션 ocr-serve-dev(4C8GB)에 서빙 코드 반영. Python 3.11 uv sync(torch 2.15 CPU·Ray 2.55.1·mlflow 3.13.0·protobuf 6.33.6), 시험 모델로 /health 200·/predict JSON·사진 아닌 파일 415 확인 | 통과 |
| 19:05 | 변경사항 저장 | Commit 9fecda4a5cec '포장 OCR 서빙 작성' | 완료 |
| 19:27 | 빌드·게시 | 빌드 성공(의존성 설치 1,066초), PUBLISHED | 완료 |
| — | 모델 등록 | 7팀_package_ocr 새 버전(MLflow pyfunc zip 80.7MB: det.pt·rec.pt·추론 코드) | 대기 |

## 팀 서버 경로 정리 (운영진 안내 2026-11-07 19:18)
- `cp -a /home/ubuntu/. /data/` 실행(캐시 8,755,523,427바이트 원본·사본 일치). 이 명령이 /data 권한을 홈 권한(drwxr-x---)으로 덮어써 2775로 되돌림
- 캐시 경로: `/data/env_cache.sh`(사본 `deploy/env_cache.sh`)로 uv·pip·torch·huggingface·CUDA 캐시를 /data/.cache 아래로. ~/.bashrc·~/.profile·/data/.bashrc에서 읽음(서버 재시작 시 /home이 지워지므로 /data/.bashrc 포함)
