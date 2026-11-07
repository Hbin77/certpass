"""저장된 AI 설명(out/explain_cache.json)에서 데모 판정 몇 개만 지운다 — 프롬프트를 고친 뒤 그 판정만 다시 만들 때.

실행(웹 서버를 멈춘 상태에서, 서버와 같은 환경변수로): .venv/bin/python -m certcheck.cache_tool drop D3/RSPO D5/CA_CNF …
- 웹 서버는 저장할 때 메모리 캐시로 파일을 덮어쓰므로 서버를 멈추고 지운 뒤 다시 켠다(deploy/run_server.sh)
"""
from __future__ import annotations

import json
import sys

from . import llm_client as L
from .app import demo_products, resources, run_demo
from .schemas import Product


def drop(items: list[str]) -> int:
    cards = {c["id"]: c for c in resources()[0]}
    prods = {p["id"]: p for p in demo_products()["products"]}
    data = json.loads(open(L.CACHE_FILE, encoding="utf-8").read())
    n = 0
    for it in items:
        pid, cid = it.split("/", 1)
        pd = Product(**{k: v for k, v in prods[pid].items() if k in Product.model_fields}).model_dump()
        v = next(x for x in run_demo(pid)["verdicts"] if x["cert_id"] == cid)
        for k in L.cache_keys(v, cards[cid], pd, L.sources_for(v, cards[cid])):
            if data.pop(k, None) is not None:
                n += 1
    with open(L.CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    return n


if __name__ == "__main__":
    if len(sys.argv) < 3 or sys.argv[1] != "drop":
        sys.exit("사용: python -m certcheck.cache_tool drop 제품/인증 …")
    print(f"지움 {drop(sys.argv[2:])}건")
