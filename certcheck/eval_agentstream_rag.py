"""AgentStream RAG 검색 정확도를 실제 챗봇 API로 잰다(인증 카드 56장 × 데모 제품 1개).

실행: set -a; . ./.env.agentstream; set +a; .venv/bin/python -m certcheck.eval_agentstream_rag [이름=run] [제품=D3] [hint=1]
- hint=0이면 꼬리표 안내(프롬프트 4-1) 없이 보낸다(고치기 전과 비교용).
- 모델 순간 요청 한도(LLM_RATE_LIMITED)가 낮아 한 번에 하나씩, 호출 사이 2초 쉬고, 한도 초과면 5초 뒤 한 번 더.
- 카드마다 설명 프롬프트(llm_client.build_prompt)를 보내고, 응답의 RAG 결과(tool.completed artifact.documents)가
  그 카드의 조각인지 본다. 카드 꼬리표는 문서 제목의 [EUCPNP …] 부분(지식베이스 변환 때 밑줄이 빠짐).
- 지표: hit@5(상위 5건에 맞는 카드 조각이 1건 이상), top1(1위가 맞는 카드), precision@5(5건 중 맞는 카드 비율).
- 결과는 out/agentstream_rag_eval_{이름}.json. Key·프롬프트 원문은 저장하지 않는다.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

from . import llm_client as L

TAG = L.TAG_IN


def tag_of(card_id: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", card_id.upper())


def doc_tag(d: dict) -> str | None:
    for s in (d.get("document") or "", (d.get("evidence") or {}).get("section_title") or ""):
        m = TAG.search(s)
        if m:
            return L.kb_tag(m.group(1))
    return None


def one(card: dict, v: dict, product: dict, hint: bool = True, retry: bool = True) -> dict:
    prompt = L.build_prompt(v, card, product, L.sources_for(v, card), kb_hint=hint)
    bot = os.environ["AGENTSTREAM_CHATBOT_ID"].strip()
    t = time.monotonic()
    try:
        with L._step("sessions", f"{L._base()}/chatbots/{bot}/sessions", {"query": f"{card['id']} 검색 평가"}, 30) as r:
            sid = json.loads(r.read())["session_id"]
        tags, done = [], False
        with L._step("messages", f"{L._base()}/chat-sessions/{sid}/messages", {"message": prompt}, 120) as r:
            for line in r:
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                if e.get("event") == "turn.failed":
                    raise (L.RateLimited if e.get("code") == "LLM_RATE_LIMITED" else ValueError)(
                        f"turn.failed {e.get('category')} {e.get('code')}")
                done = done or e.get("event") == "turn.completed"
                art = e.get("artifact") if isinstance(e.get("artifact"), dict) else {}
                tags += [doc_tag(d) for d in art.get("documents") or [] if isinstance(d, dict)]
        if not done:
            raise ValueError("turn.completed 없음")
    except L.RateLimited as e:  # 스트림을 닫은 뒤(with 밖에서) 한 번만 다시
        if retry:
            time.sleep(5)
            return one(card, v, product, hint, retry=False)
        return {"card": card["id"], "error": f"RateLimited: {e}"[:120], "sec": round(time.monotonic() - t, 1)}
    except Exception as e:
        return {"card": card["id"], "error": f"{type(e).__name__}: {e}"[:120], "sec": round(time.monotonic() - t, 1)}
    want = tag_of(card["id"])
    top = tags[:5]
    ok = [L.tag_match(x, want) for x in top]
    return {"card": card["id"], "want": want, "tags": top, "hit": any(ok), "top1": bool(ok) and ok[0],
            "precision": round(sum(ok) / len(top), 2) if top else 0.0, "n_docs": len(tags),
            "sec": round(time.monotonic() - t, 1)}


def main(name: str, pid: str, hint: bool = True) -> dict:
    from .app import EvalRequest, demo_products, resources, run as run_eval
    from .schemas import Product

    data = demo_products()
    p = next(x for x in data["products"] if x["id"] == pid)
    product = Product(**{k: v for k, v in p.items() if k in Product.model_fields})
    res = run_eval(EvalRequest(product=product, company=data["company"]))
    cards = {c["id"]: c for c in resources()[0]}
    vs = [v for v in res["verdicts"] if v["cert_id"] in cards and cards[v["cert_id"]].get("kind") != "company_certification"]
    pd = product.model_dump()
    rows = []
    for v in vs:
        rows.append(one(cards[v["cert_id"]], v, pd, hint))
        time.sleep(2)
    ok = [r for r in rows if "error" not in r]
    summ = {"name": name, "product": pid, "kb_hint": hint, "n": len(rows), "errors": len(rows) - len(ok),
            "hit@5": round(sum(r["hit"] for r in ok) / len(ok), 3) if ok else None,
            "top1": round(sum(r["top1"] for r in ok) / len(ok), 3) if ok else None,
            "precision@5": round(sum(r["precision"] for r in ok) / len(ok), 3) if ok else None,
            "no_docs": sum(r["n_docs"] == 0 for r in ok),
            "mean_sec": round(sum(r["sec"] for r in ok) / len(ok), 1) if ok else None}
    out = Path("out") / f"agentstream_rag_eval_{name}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"summary": summ, "rows": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
    return summ


if __name__ == "__main__":
    a = sys.argv[1:]
    print(json.dumps(main(a[0] if a else "run", a[1] if len(a) > 1 else "D3", (a[2] if len(a) > 2 else "1") != "0"),
                     ensure_ascii=False))
