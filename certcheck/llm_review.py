"""AI 검토 의견(AgentStream LLM+RAG, 판정 설명과 별개).

규칙 엔진이 불가로 확정하지 않았고 AIStream 모델도 경보하지 않은 판정 중 '확정하지 못한' 것(함량 미상, 오기 의심 등)을
검토 전용 챗봇에 보내 '불가 가능성 높음 / 낮음 / 판단 불가'와 필요한 정보·근거를 받는다.
- 등급은 바꾸지 않는다(규칙 엔진이 정본). 화면에는 'AI 검토 의견, 확인 필요'로 따로 표시한다.
- 입력에 없는 사실(함량·CAS·시험 결과)은 추측하지 않고 '판단 불가'로 답하게 한다.
- 환경변수 AGENTSTREAM_REVIEW_CHATBOT_ID(검토 챗봇 UUID)가 없으면 끈다. Key는 판정 설명과 같은 AGENTSTREAM_API_KEY.
"""
from __future__ import annotations

import os
import re

from . import llm_client

LEVELS = ("불가 가능성 높음", "불가 가능성 낮음", "판단 불가")
# 검토를 보낼 만한 판정: 규칙이 확정하지 못한 사유가 있을 때만(모든 판정을 보내면 느리고 헛경보만 는다)
UNSURE = ("ING_RESTRICTED_PCT_UNKNOWN", "ING_BANNED_SUSPECT", "ING_BANNED_CONDITIONAL", "ING_BANNED_WITH_EXCEPTION",
          "ING_RESTRICTED_SCOPE_CHECK", "ING_SCOPE_MISMATCH", "ING_PEROXIDE", "ING_CYCLOMETHICONE_MIX")
MAX_INGREDIENTS = 40
NOTICE = "AI 검토 의견입니다. 규칙 엔진 판정(등급)을 바꾸지 않으며, 공식 인증·심사가 아닙니다. 표시된 정보로 직접 확인하세요."


def enabled() -> bool:
    return bool(os.environ.get("AGENTSTREAM_API_KEY", "").strip() and os.environ.get("AGENTSTREAM_REVIEW_CHATBOT_ID", "").strip())


def needs_review(v: dict) -> bool:
    """불가로 확정되지 않았고, 확정하지 못한 성분 사유가 있는 판정만 검토 대상."""
    if v.get("status") == "불가" or v.get("kind") == "company_certification":
        return False
    return any(f.get("code") in UNSURE for f in v.get("findings") or [])


def _ing_line(i: dict) -> str:
    pct = i.get("pct")
    cas = i.get("cas")
    return f"- {str(i.get('inci') or i.get('kr') or '')[:80]}" + (f" / 함량 {pct}%" if isinstance(pct, (int, float)) else " / 함량 없음") \
        + (f" / CAS {str(cas)[:30]}" if cas else "")


def build_prompt(v: dict, card: dict, product: dict, ml: dict | None = None, near: list | None = None) -> str:
    """검토 요청문. 줄 머리에 대괄호를 쓰지 않는다(AgentStream이 표로 읽어 실패). 확률은 둘째 자리."""
    unsure = [f for f in v.get("findings") or [] if f.get("code") in UNSURE or f.get("level") == "fail"][:12]
    reasons = "\n".join("- " + llm_client.KW.sub("", f.get("message", ""))[:220] for f in unsure) or "- 없음"
    ings = product.get("ingredients") or []
    ing_text = "\n".join(_ing_line(i) for i in ings[:MAX_INGREDIENTS]) + (f"\n- 외 {len(ings) - MAX_INGREDIENTS}종" if len(ings) > MAX_INGREDIENTS else "")
    ml_text = f"불가 확률 {ml['fail_proba']:.2f} (경보 기준 미만)" if ml and ml.get("fail_proba") is not None else "결과 없음"
    near_text = "; ".join(f"'{n['input'][:60]}' — {'금지' if n['list_type'] == 'banned' else '제한'} 성분 '{n['listed'][:60]}'와 유사도 {n['similarity']:.2f}"
                          for n in near or []) or "없음"
    return f"""아래 판정을 검토하세요. 규칙 엔진은 이 판정을 불가로 확정하지 못했고, AI 모델도 경보하지 않았습니다.
지식베이스에서 '{card.get('id')}' 인증 요건 카드(꼬리표 {str(card.get('id') or '').replace('_', '')})를 찾아, 이 제품이 실제로는 불가일 가능성을 판단하세요.

규칙:
1. 첫 줄은 반드시 '판단: 불가 가능성 높음', '판단: 불가 가능성 낮음', '판단: 판단 불가' 중 하나입니다.
2. 입력에 없는 함량·CAS·시험 결과를 추측하지 마세요. 판단에 꼭 필요한 정보가 없으면 '판단 불가'로 하고 무엇이 필요한지 쓰세요.
3. 성분 이름이 금지·제한 성분과 비슷하면 오기 가능성을 이유에 쓰세요.
4. 지식베이스에서 찾은 카드 내용만 근거로 쓰고, 없으면 '판단 불가'로 하세요.
5. 형식(한국어, 6줄 이내):
판단: ...
이유: (2문장 이내)
필요한 정보: (없으면 없음)
근거: (카드 꼬리표와 절 제목)

인증: {card.get('name_ko')} ({card.get('id')}, 관할 {card.get('jurisdiction')})
제품: 유형 {product.get('product_type') or '-'} / 사용 {product.get('application') or '-'} / 함량 정보 {product.get('formula_known') or '-'}
규칙 판정: {v.get('status')}
확정하지 못한 사유:
{reasons}
AI 모델(AIStream): {ml_text}
이름이 비슷한 규제 성분: {near_text}
전성분(표시 순서):
{ing_text}
"""


def parse(text: str) -> dict:
    """첫 '판단:' 줄에서 단계를 읽는다. 형식을 지키지 않으면 '판단 불가'로 본다(추측을 경보로 올리지 않음)."""
    lines = [x.strip() for x in str(text or "").splitlines() if x.strip()]
    level = "판단 불가"
    for x in lines:
        m = re.match(r"^\**\s*판단\s*[:：]\s*(.+)$", x)
        if m:
            level = next((lv for lv in LEVELS if lv.replace(" ", "") in m.group(1).replace(" ", "")), "판단 불가")
            break
    field = {k: next((re.sub(rf"^\**\s*{k}\s*[:：]\s*", "", x) for x in lines if re.match(rf"^\**\s*{k}\s*[:：]", x)), "")
             for k in ("이유", "필요한 정보", "근거")}
    return {"level": level, "reason": field["이유"][:300], "needed": field["필요한 정보"][:200], "basis": field["근거"][:200]}


def review(v: dict, card: dict, product: dict, ml: dict | None = None, near: list | None = None) -> dict:
    base = {"cert_id": v.get("cert_id"), "status": v.get("status"), "notice": NOTICE}
    if not enabled():
        return {**base, "enabled": False, "reason": "AI 검토 챗봇 미연결"}
    if not needs_review(v):
        return {**base, "enabled": True, "ok": True, "skipped": True, "reason": "검토 대상 아님(확정 판정)"}
    try:
        ans = llm_client.call(build_prompt(v, card, product, ml, near), float(os.environ.get("AGENTSTREAM_TIMEOUT", "60")),
                              f"{card.get('id')} AI 검토", bot=os.environ["AGENTSTREAM_REVIEW_CHATBOT_ID"])
        if not ans.get("text"):
            raise ValueError("빈 응답")
    except Exception as e:  # 검토가 실패해도 판정 화면은 그대로
        return {**base, "enabled": True, "ok": False, "error": f"{type(e).__name__}: {e}"[:200]}
    return {**base, "enabled": True, "ok": True, **parse(ans["text"]), "text": ans["text"][:1500],
            "rag_sources": ans.get("rag_sources") or []}
