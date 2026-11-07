# AgentStream AI 검토 에이전트 설정 (판정 설명과 별개)

규칙 엔진이 불가로 확정하지 못했고 AIStream 모델도 경보하지 않은 판정(함량 미상, 금지 성분 오기 의심 등)을 검토해 '불가 가능성 높음 / 낮음 / 판단 불가'로 답하는 전용 에이전트입니다. 판정 설명 챗봇(7팀_CertPass_판정설명)과 지시문·캐시가 섞이지 않게 따로 만듭니다. 코드: `certcheck/llm_review.py`, 측정: `certcheck/eval_llm_review.py`.

## 1. RAG 에이전트 만들기
- 이름: `7팀_CertPass_AI검토`
- 종류: RAG
- 지식베이스: `7팀_CertPass_인증요건_v2` (판정 설명과 같은 것)
- use_rerank: 켬, 검색 갯수: 6
- 역할·답변 원칙(아래를 그대로 붙여 넣기):

```
당신은 CertPass 'AI 검토' 도우미입니다. 규칙 엔진이 확정하지 못한 화장품 수출 인증 판정에서, 지식베이스의 인증 요건 카드를 근거로 '실제로는 불가일 가능성'만 검토합니다.
원칙
1. 등급을 정하거나 바꾸지 않습니다. 첫 줄은 반드시 '판단: 불가 가능성 높음', '판단: 불가 가능성 낮음', '판단: 판단 불가' 중 하나입니다.
2. 입력에 없는 사실(성분 함량, CAS 번호, 시험 결과, 보유 서류)을 추측하지 않습니다. 판단에 꼭 필요한 정보가 없으면 '판단 불가'로 하고 '필요한 정보:'에 무엇이 있어야 하는지 씁니다.
3. 근거는 지식베이스에서 찾은 해당 인증 카드(줄 머리 꼬리표가 인증 id에서 밑줄을 뺀 것, 예: EUCPNP)의 내용만 씁니다. 근거를 찾지 못하면 '판단 불가'입니다.
4. 입력 성분 이름이 금지·제한 성분과 거의 같으면 오기 가능성을 이유에 씁니다.
5. 형식은 아래 네 줄입니다. 줄 머리에 대괄호를 쓰지 않습니다. 한국어로 씁니다.
판단: ...
이유: (2문장 이내)
필요한 정보: (없으면 없음)
근거: (카드 꼬리표와 절 제목)
```

## 2. 챗봇 만들기
- 이름: `7팀_CertPass_AI검토`, 공개
- LLM: `7팀_qwen3.5-122b`
- RAG 에이전트: `7팀_CertPass_AI검토` 1개
- 장애 대응: 켬(판정 설명 챗봇과 같게), 원본 이미지 근거: 끔, 가드레일 없음
- 프롬프트: 기본 보안 지침 + 위 역할·답변 원칙

## 3. API 권한
- 계정관리 → API 연동 → 기존 Key에 이 챗봇의 CHAT_INVOKE 권한을 매핑 → 저장
- 챗봇 UUID('ID 복사')를 맥 `~/.certpass_agentstream.env`에 한 줄 추가(저장소에는 적지 않음):
  `AGENTSTREAM_REVIEW_CHATBOT_ID=<UUID>`
- 서버(axgpu)는 측정 결과를 보고 화면에 붙이기로 정하면 `.env.agentstream`에 같은 줄을 넣는다.

## 4. 측정 (맥)
```
.venv/bin/python -m certcheck.eval_llm_review make out/llm_review/cases.jsonl --n 40   # 이미 만들어 둠
set -a; . ~/.certpass_agentstream.env; set +a
.venv/bin/python -m certcheck.eval_llm_review run out/llm_review/cases.jsonl out/llm_review/results.jsonl
.venv/bin/python -m certcheck.eval_llm_review score out/llm_review/cases.jsonl out/llm_review/results.jsonl
```
- 판정 설명 warm과 같은 모델 한도를 쓰므로 warm이 끝난 뒤 돌린다.
- 화면에 붙이는 기준: '불가 가능성 높음'의 재현율이 의미 있고(숨은 불가를 실제로 더 잡음), 실제 비율로 환산한 정밀도가 무작위(약 2.8%)보다 확실히 높을 때. 아니면 붙이지 않고 결과만 발표 근거로 쓴다.
