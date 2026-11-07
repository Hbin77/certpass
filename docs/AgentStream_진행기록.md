# AgentStream LLM + RAG 진행 기록

목적: 규칙 엔진 판정마다 "왜 이 등급인지" 설명과 근거 인용을 붙인다. 판정 등급은 규칙 엔진이 정본이며 LLM은 등급을 바꾸지 않는다. 화면에 "참고용 설명, 공식 인증 아님"을 표시한다.

- 플랫폼: AgentStream https://agentopen.jntp-ax.or.kr (계정 axhack21, 워크스페이스 "AX 해커톤 7팀" — 사용자 확인 2026-11-07)
- 모델: LLM qwen3.5-122b, 임베딩 bge-m3
- 담당 세션: ax-3b (ax-45에게서 넘겨받음)

## 구성

| 부분 | 파일 | 내용 |
|---|---|---|
| 지식베이스 문서 | `certcheck/kb_export.py` → `out/agentstream_kb/*.md` | 인증 카드 56장 → 카드당 문서 1개 + 공통 판정기준 1개(57개, 약 400KB). 공개 링크만 싣고 로컬 원문 경로·원문 인용·엔진 태그 제외. data/private 미사용 |
| 호출부 | `certcheck/llm_client.py` | 환경변수 AGENTSTREAM_URL·AGENTSTREAM_KEY가 있을 때만 켬. 근거 목록(번호·제목·링크)은 서버가 엔진 판정·카드에서 직접 만들고, LLM은 그 번호로 인용. 같은 판정은 캐시(256건). 실패하면 ok=false와 짧은 오류 문자열 |
| API | `certcheck/app.py` | POST /api/explain(판정 요청 + cert_id, 서버가 판정을 다시 계산), GET /api/explain-demo/{제품}/{인증}, /api/health에 llm_model |
| 시험 | `tests/test_llm_client.py` | 미설정·응답 형식 5종·가짜 서버 호출·캐시·Key 미노출·404 |

## 기록

| 시각(KST) | 단계 | 내용 | 상태 |
|---|---|---|---|
| 2026-11-07 18:5x | 인수 | ax-45에게서 작업 넘겨받음. 기존 AIStream 호출부(ml_client.py) 패턴 확인 | 완료 |
| 2026-11-07 19:0x | 지식베이스 문서 | kb_export.py로 문서 57개 생성 | 완료 |
| 2026-11-07 19:04 | 호출부·API·시험 | llm_client.py, /api/explain, 시험 추가 — 전체 61개 통과. 실제 API 형식은 [미확인] → Key 발급 뒤 curl로 확인해 맞출 것 | 완료(형식 확인 전) |
| 2026-11-07 19:0x | AgentStream 화면 | 사용자 로그인·메뉴 확인 중 | 진행 중 |
