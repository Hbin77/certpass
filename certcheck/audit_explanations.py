"""저장된 AI 판정 설명을 토큰 없이 점검한다(explain-demo?cache_only=1 — 저장본이 없으면 모델을 부르지 않음).

실행: .venv/bin/python -m certcheck.audit_explanations [제품…=D3 D5] [--url 공개주소]
- 설명 문장의 영문 용어·약어, 숫자, 따옴표 속 말, 서류·절차 이름이 판정 사유·근거 목록·인증 카드·제품 성분 어디에도 없으면 '확인 필요'
- 근거 목록에 없는 '(근거 n)' 인용, 근거에 없는 날짜·비율도 센다
- 결과: out/explanation_audit.json (설명 원문은 싣지 않고 걸린 말만)
"""
from __future__ import annotations

import json
import sys
import urllib.request
from collections import Counter
from pathlib import Path

from . import llm_client as L
from .app import demo_products, resources, run_demo
from .kb_export import card_doc
from .schemas import Product

URL = "https://devopen-gpu.jntp-ax.or.kr/i/FBi4CwFvT4Pe38Xd"


def main(pids: list[str], url: str = URL) -> dict:
    cards = {c["id"]: c for c in resources()[0]}
    prods = {p["id"]: p for p in demo_products()["products"]}
    rows, terms = [], Counter()
    for pid in pids:
        pd = Product(**{k: v for k, v in prods[pid].items() if k in Product.model_fields}).model_dump()
        for v in run_demo(pid)["verdicts"]:
            card = cards.get(v["cert_id"])
            if not card or card.get("kind") == "company_certification":
                continue
            d = json.loads(urllib.request.urlopen(f"{url}/api/explain-demo/{pid}/{v['cert_id']}?cache_only=1", timeout=30).read())
            if not d.get("cached"):
                continue
            srcs = L.sources_for(v, card)
            ing = " ".join(f"{i.get('inci') or ''} {i.get('name_kr') or ''}" for i in pd.get("ingredients") or [])
            corpus = "\n".join([L._key_prompt(v, card, pd, srcs, d.get("ai_alert")), card_doc(card), ing])
            un = L.unsupported_terms(d["text"], corpus)
            terms.update(un)
            rows.append({"product": pid, "cert": v["cert_id"], "unsupported": un,
                         "bad_refs": d.get("bad_refs") or [],  # 서버가 지우기 전 원문으로 센 값(받은 text는 이미 지운 뒤라 다시 세면 늘 0)
                         "unverified_facts": L.unverified_facts(d["text"], corpus)})
    n = len(rows)
    summ = {"explanations": n,
            "clean": sum(not (r["unsupported"] or r["bad_refs"] or r["unverified_facts"]) for r in rows),
            "with_unsupported": sum(bool(r["unsupported"]) for r in rows),
            "with_bad_refs": sum(bool(r["bad_refs"]) for r in rows),
            "with_unverified_facts": sum(bool(r["unverified_facts"]) for r in rows),
            "top_terms": terms.most_common(20)}
    Path("out").mkdir(exist_ok=True)
    Path("out/explanation_audit.json").write_text(json.dumps({"summary": summ, "rows": rows}, ensure_ascii=False, indent=1),
                                                  encoding="utf-8")
    return summ


if __name__ == "__main__":
    args = sys.argv[1:]
    url = args[args.index("--url") + 1] if "--url" in args else URL
    pids = [a for a in args if a != "--url" and a != url] or ["D3", "D5"]
    print(json.dumps(main(pids, url), ensure_ascii=False, indent=1))
