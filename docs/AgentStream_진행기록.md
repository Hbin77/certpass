# AgentStream LLM + RAG 진행 기록

목적: 규칙 엔진 판정마다 "왜 이 등급인지" 설명과 근거 인용을 붙인다. 판정 등급은 규칙 엔진이 정본이며 LLM은 등급을 바꾸지 않는다. 화면에 "참고용 설명, 공식 인증 아님"을 표시한다.

- 플랫폼: AgentStream https://agentopen.jntp-ax.or.kr (계정 axhack21, 워크스페이스 "AX 해커톤 7팀" — 사용자 확인 2026-11-07)
- 모델: LLM qwen3.5-122b, 임베딩 bge-m3
- 담당 세션: ax-3b (ax-45에게서 넘겨받음)

## 구성

| 부분 | 파일 | 내용 |
|---|---|---|
| 지식베이스 문서 | `certcheck/kb_export.py` → `out/agentstream_kb/*.md` | 인증 카드 56장 → 카드당 문서 1개 + 공통 판정기준 1개(57개, 약 400KB). 공개 링크만 싣고 로컬 원문 경로·원문 인용·엔진 태그 제외. data/private 미사용 |
| 호출부 | `certcheck/llm_client.py` | 환경변수 AGENTSTREAM_API_KEY·AGENTSTREAM_CHATBOT_ID가 있을 때만 켬(AGENTSTREAM_BASE_URL 기본 https://api-gateway.jntp-ax.or.kr/agentstream). 설명마다 새 세션 → 메시지 → NDJSON 스트림 해석. 근거 목록(번호·제목·링크)은 서버가 엔진 판정·카드에서 직접 만들고, LLM은 그 번호로 인용. 같은 판정은 캐시(256건). 실패하면 ok=false와 짧은 오류 문자열 |
| API | `certcheck/app.py` | POST /api/explain(판정 요청 + cert_id, 서버가 판정을 다시 계산), GET /api/explain-demo/{제품}/{인증}, /api/health에 llm_model |
| 시험 | `tests/test_llm_client.py` | 미설정·NDJSON 이벤트(중복 event_id·thinking 블록·replace·turn.failed·끊김)·가짜 서버(세션→메시지 경로·X-API-Key)·캐시·Key 미노출·404 |

## API 형식 (AgentStream 사용 가이드 /docs 'Codex용 연동 가이드' 본문, 2026-11-07 19:3x 확인)

| 단계 | 요청 | 응답 |
|---|---|---|
| 상태 | GET {BASE}/open/v1/chatbots/{chatbot_id}/health | 200, status(healthy/unhealthy/unknown)·message·checked_at |
| 세션 | POST {BASE}/open/v1/chatbots/{chatbot_id}/sessions, 본문 {"query": 첫 질문} | 201, 최상위 session_id (세션 생성만으로 답변은 안 나옴) |
| 질문 | POST {BASE}/open/v1/chat-sessions/{session_id}/messages, 본문 {"message": 질문} | 200 application/x-ndjson. assistant.delta의 content(배열이면 text 블록만), assistant.replace, turn.completed=정상 종료, turn.failed(category TOKEN_LIMIT/LLM/RAG/SERVER), references[type=rag]=문서 출처 |

- 인증: 헤더 X-API-Key. BASE = https://api-gateway.jntp-ax.or.kr/agentstream (화면 표시값). 일반 /api/* 는 Key로 못 씀.
- 오류: 401 Key, 403 챗봇 비공개·다른 조직·CHAT_INVOKE 권한 없음, 404 ID, 503 동시 처리 한도. 실패한 POST는 자동 재전송하지 않는다.
- 지식베이스 파일 형식: .md .txt .pdf .docx .hwp .hwpx .csv (화면 코드에서 확인)
- 실제 Key로 curl 확인은 [미확인] — Key 발급 뒤 진행

## 기록

| 시각(KST) | 단계 | 내용 | 상태 |
|---|---|---|---|
| 2026-11-07 18:5x | 인수 | ax-45에게서 작업 넘겨받음. 기존 AIStream 호출부(ml_client.py) 패턴 확인 | 완료 |
| 2026-11-07 19:0x | 지식베이스 문서 | kb_export.py로 문서 57개 생성 | 완료 |
| 2026-11-07 19:04 | 호출부·API·시험 | llm_client.py, /api/explain, 시험 추가 — 전체 61개 통과. 실제 API 형식은 [미확인] → Key 발급 뒤 curl로 확인해 맞출 것 | 완료(형식 확인 전) |
| 2026-11-07 19:29 | AgentStream 로그인 | axhack21 로그인, 사용 가이드 화면 확인 | 완료 |
| 2026-11-07 19:3x | API 형식 반영 | 가이드 본문대로 llm_client.py를 세션→메시지→NDJSON으로 바꿈, 시험 62개 통과. kb_export 공통 문서를 운영진 데이터 검토(중국·대만 원문 목록 → 식약처 API) 결과에 맞춤 | 완료 |
| 2026-11-07 19:43 | 모델 등록 | 모델 종류 'JNTP 모델'로 7팀_qwen3.5-122b(LLM, 멀티모달 표시)·7팀_bge-m3(Embedding) 등록, 둘 다 정상(초록) | 완료 |
| 2026-11-07 19:45 | 지식베이스 생성 | 7팀_CertPass_인증요건(문서 RAG, LLM 7팀_qwen3.5-122b, 임베딩 7팀_bge-m3) | 완료 |
| 2026-11-07 19:49 | 업로드 실패 | 카드 56장 합본 1파일(285KB)이 '문서 분석' 단계 DATAPROCESSOREXCEPTION(자동 재시도 1회 후 실패). 판정기준 2KB 파일은 정상 → 파일 크기 원인으로 판단 | 해결 |
| 2026-11-07 19:55 | 지식베이스 적재 | kb_export 묶음을 지역·종류별 9개(23~39KB)+판정기준 1개로 나눠 업로드 → 처리 시작 → 파싱 결과 승인, 10개 모두 '적재 완료'(282.4KB) | 완료 |
| 2026-11-07 20:00 | RAG 에이전트 | 7팀_CertPass_RAG(종류 RAG, 지식베이스 7팀_CertPass_인증요건, use_rerank 켬, 검색 갯수 6, 역할·답변 원칙 작성) | 완료 |
| 2026-11-07 20:05 | 챗봇 | 7팀_CertPass_판정설명(공개, 7팀_qwen3.5-122b, 장애 대응 ON — 화면 설명상 OFF일 때 20초 차단, RAG 에이전트 1개, 원본 이미지 근거 OFF, 가드레일 없음, 기본 보안 지침 + CertPass 역할·답변 원칙 프롬프트) | 완료 |
| 2026-11-07 20:06 | 챗봇 화면 시험 | "EU 화장품 신고(CPNP)에 필요한 서류는?" → 약 30초 안에 답, 조회 근거 청크 5개(CertPass_카드01_유럽_영국_유라시아.md, EU_CPNP 카드 '필요 서류' 절). 답 내용이 카드와 일치 | 완료 |
| 2026-11-07 20:08 | API 권한·Key | 챗봇 UUID 확인(공개 저장소에는 적지 않음, .env.agentstream에만), CHAT_INVOKE 권한 매핑 저장. **Key 발급 버튼 없음 — 화면 문구 '조직 대표만 발급·재발급', axhack21 역할 member** → 조직 대표 권한 또는 운영진 발급 필요 | 막힘(사용자 확인 중) |
| 2026-11-07 20:1x | 연동 가이드 반영 | 'Codex용 챗봇 연동 가이드' 대조: 단계별 로그(단계·HTTP·Content-Type·경과 초, Key·원문 없음), tool.failed 처리, 401/403/404/422/429/503 안내, HTML 응답 거부, health(), 동시 호출 2개 제한, 실패 POST 자동 재전송 없음, deploy/agentstream.env.example(빈 값)·README 실행법, run_server.sh가 .env.agentstream을 읽음. 시험 65개 통과 | 완료 |
| 2026-11-07 20:1x | 화면 | 판정 행 상세 맨 아래 'AI 판정 설명'(행을 펼칠 때 POST api/explain, 생성 중·완료·실패+다시 불러오기·근거 목록·참고용 표시, 미설정이면 칸 없음). 로컬 대역(가짜 AgentStream, NDJSON 조각 전송)으로 데스크톱·모바일 390px 확인: 콘솔 오류 0, 가로 스크롤 없음, 버튼·펼침 44px. /design-audit: CRITICAL 0, 본문 14→16px·제목 굵기 700→600(MASTER) 수정 | 완료(대역 시험) |
| 2026-11-07 20:45 | API Key | 조직 대표 권한으로 Key 발급. 맥 ~/.certpass_agentstream.env(600)에 클립보드로 저장(화면 출력 없음) | 완료 |
| 2026-11-07 21:18 | 실제 호출 1차 | health healthy(LLM·bge-m3), 세션 201, 메시지 200 x-ndjson. 그런데 turn.failed **INPUT '분석할 표가 여러 개입니다'** — 프롬프트 줄 머리의 `[1]`·`[불가 사유]`를 JSON 표로 읽음 | 원인 확인 |
| 2026-11-07 21:20 | 프롬프트 수정 | 대괄호를 빼고 '근거 1:'·'(근거 1)'·'불가 사유:'로 바꿈(시험으로 고정). 재호출 성공 7.7초. RAG 출처는 tool.completed의 artifact.documents[].reference·evidence.section_title에 옴 → 파싱 추가, EU_CPNP 실호출 rag 5건 | 완료 |
| 2026-11-07 21:2x | 배포 | axgpu /data/certcheck/.env.agentstream(600, 143B) → push_axgpu.sh(293조각) → run_server.sh. health `llm_model:true`(ml_model·ocr_model도 true) | 완료 |
| 2026-11-07 21:2x | 공개 URL 확인 | curl /api/explain-demo/D3/EU_ECOLABEL_RINSEOFF: ok, 등급 '불가' 유지, 5.8초, RAG 5건. 브라우저(공개 URL, D3 → 중국 특수화장품 행 펼침): 설명·지식베이스 문서·근거 목록 표시 6.5초, 콘솔 오류 0 | 완료 |
| 2026-11-07 21:3x | 기획서 | 6절 표 LLM 행, 확인 현황 'AgentStream 연동', 구조도, 체크리스트, 예상 질문 답 갱신 | 완료 |

## 남은 점

- 설명은 서버 메모리 캐시(256건)라 웹 서버를 재시작하면 처음 여는 행마다 다시 6~8초 걸린다. 발표 직전에 데모 행을 한 번씩 열어 두면 즉시 뜬다.
- 키는 2026-11-07 20:45 발급본. 스크린샷으로 대화에 찍힌 첫 Key가 있었다면 대회 뒤 재발급해 폐기 권장.
