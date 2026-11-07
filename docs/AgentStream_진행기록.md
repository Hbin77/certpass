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
| 2026-11-07 21:34 | RAG 평가 1차 | eval_agentstream_rag(카드 56장 × D3, 동시 2) → 53건 중 47건 turn.failed **LLM_RATE_LIMITED**('모델 공급자의 순간 요청 한도 초과'). 여러 팀이 같은 모델을 쓰는 것으로 보임 | 원인 확인 |
| 2026-11-07 21:4x | 한도 대응 | 동시 1, 한도 초과일 때만 3초 뒤 1회 재시도, 평가는 하나씩 2초 간격 | 완료 |
| 2026-11-07 21:48 | RAG 평가(고치기 전, 꼬리표 안내 없음) | 53건 중 오류 6(연결 끊김·시간 초과·한도). 나머지 47건: hit@5 100%, top1 83%, precision@5 71%(5건 중 약 1.4건이 다른 카드 조각) | 측정 |
| 2026-11-07 21:5x | RAG 보완 | ① 지식베이스가 밑줄을 지워 저장한 꼬리표(EU_CPNP→EUCPNP)로 찾게 프롬프트 4-1 ② 성분 농도·경고·부작용은 판정 사유에 있는 것만(4-2) ③ 화면 출처는 이 카드 조각만 '파일: 절' 묶음, 다른 카드는 개수만 ④ 설명 속 날짜·비율이 판정 사유·조회 문서에 없으면 '원문 확인 필요' 표시 ⑤ 절 제목이 잘린 꼬리표(EUEC…)도 앞부분 일치로 인정 | 완료 |
| 2026-11-07 22:0x | 코드 리뷰(code-reviewer) | HIGH 1(슬롯 1개 60초 대기 → 공개 URL에서 분당 20건이면 서버 스레드풀 고갈), MEDIUM 3(캐시 전 ML 호출·키 불안정 / 대기 후 제한 시간 / 전역 상한·데모 캐시 밀려남), LOW 6 → 모두 수정: 슬롯 대기 최대 3건·15초 후 즉시 거절, 제한 시간은 슬롯 뒤부터, 캐시 적중 시 ML 생략, 방문자별 분당 6, 데모 설명 고정·파일 저장(사용자 처방은 메모리만), 리다이렉트 거부, 바이트 단위 스트림 제한, 화면 요청 90초, 긴 id 404, 규정 번호를 날짜로 오인하지 않음. 캐시 키에 AIStream 모델 주소·기준값 포함(ax-45 지적). 시험 86개 | 완료 |
| 2026-11-07 22:0x | 커밋·배포 | 0092867·da4ad49 push. axgpu에 llm_client.py·app.py·web/app.js·styles.css 단일 전송(md5 일치) → run_server.sh. 공개 URL D5/EU_CPNP: 'AI 경보:' 줄(Dibutyl Phthlate 오기) 포함, 출처 이 카드 4건 묶음·다른 카드 1건 제외, 두 번째 요청 캐시 적중, out/explain_cache.json 저장 | 완료 |
| 2026-11-07 21:56 | RAG 평가(고친 후, 꼬리표 안내 있음) | 고치기 전·후 모두 성공한 42장 기준 재채점: hit@5 100%→100%, **top1 85.7%→97.6%, precision@5 70.4%→81.9%** | 측정 |
| 2026-11-07 22:1x | RAG 평가(최종 코드) | 53건 중 오류 7(모두 LLM_RATE_LIMITED). 46건: hit@5 100%, top1 95.7%, precision@5 82.0%, 평균 6.1초. 남은 18%는 조각에 꼬리표가 없는 경우 22건 | 측정 |
| 2026-11-07 22:2x | 원인 | AgentStream이 절 경계와 상관없이 일정 길이로 조각을 자름('# 기간·비용·유' 같은 잘린 제목, 앞 카드 끝과 뒤 카드 시작이 한 조각). 본문 꼬리표는 밑줄이 남기도 함([KR_CFS_EXPORT …) | 확인 |
| 2026-11-07 22:2x | 지식베이스 문서 개선 | kb_export: 모든 줄 머리에 [EUCPNP] 꼬리표(밑줄 없는 모양), 긴 메모는 문장마다 나눔, 파일당 38KB 이하로 자동 분할(12개 + 판정기준). 서버는 본문의 밑줄 꼬리표도 읽음. 캐시 키에 AGENTSTREAM_KB_VERSION 포함(다시 올리면 숫자를 올려 새로 생성). 시험 91개 | 완료(재업로드 대기) |

## 남은 점

- 지식베이스 재업로드: out/agentstream_kb_재업로드/ 12개로 기존 카드 파일 9개를 바꾸고(판정기준 파일은 그대로), .env.agentstream에 AGENTSTREAM_KB_VERSION=2 → 웹 재시작 → eval_agentstream_rag로 다시 측정.
- 데모 설명 미리 만들기: axgpu에서 deploy/warm_explain.sh D3 D5 D1 D2 D4(11초 간격). 데모 설명은 out/explain_cache.json에 남아 웹을 다시 켜도 바로 뜬다.
- 모델 순간 요청 한도(LLM_RATE_LIMITED)는 여러 팀이 같이 쓰는 한도로 보여, 발표 중 새 설명은 실패할 수 있다 → 시연 행은 미리 만들어 둔다.
- 키는 2026-11-07 20:45 발급본. 스크린샷으로 대화에 찍힌 첫 Key가 있었다면 대회 뒤 재발급해 폐기 권장.
