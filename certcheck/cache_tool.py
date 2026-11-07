"""저장된 AI 설명(out/explain_cache.json)에서 데모 판정 몇 개만 지우거나(drop) 근거 목록에 없는 '(근거 n)'을 원문에서 지운다(strip).

실행(웹 서버를 멈춘 상태에서, 서버와 같은 환경변수로): .venv/bin/python -m certcheck.cache_tool drop|strip D3/RSPO D5/CA_CNF …
- drop: 프롬프트를 고친 뒤 그 판정만 다시 만들 때
- strip: 다시 만들지 않고(토큰 0) 저장된 설명 본문의 잘못된 근거 번호만 지운다(화면에서 지우던 것을 저장본에도 반영)
- 웹 서버는 저장할 때 메모리 캐시로 파일을 덮어쓰므로 서버를 멈추고 고친 뒤 다시 켠다(deploy/run_server.sh)
"""
from __future__ import annotations

import json
import sys

from . import llm_client as L
from .app import demo_products, resources, run_demo
from .schemas import Product


def _entries(items: list[str]):
    cards = {c["id"]: c for c in resources()[0]}
    prods = {p["id"]: p for p in demo_products()["products"]}
    for it in items:
        pid, cid = it.split("/", 1)
        pd = Product(**{k: v for k, v in prods[pid].items() if k in Product.model_fields}).model_dump()
        v = next(x for x in run_demo(pid)["verdicts"] if x["cert_id"] == cid)
        srcs = L.sources_for(v, cards[cid])
        yield L.cache_keys(v, cards[cid], pd, srcs), len(srcs)


def run(cmd: str, items: list[str]) -> int:
    data = json.loads(open(L.CACHE_FILE, encoding="utf-8").read())
    n = 0
    for keys, n_src in _entries(items):
        for k in keys:
            if k not in data:
                continue
            if cmd == "drop":
                data.pop(k)
                n += 1
            elif L.bad_refs(data[k]["text"], n_src):
                data[k]["text"] = L.strip_bad_refs(data[k]["text"], n_src)
                n += 1
    with open(L.CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    return n


if __name__ == "__main__":
    if len(sys.argv) < 3 or sys.argv[1] not in ("drop", "strip"):
        sys.exit("사용: python -m certcheck.cache_tool drop|strip 제품/인증 …")
    print(f"{'지움' if sys.argv[1] == 'drop' else '근거 번호 고침'} {run(sys.argv[1], sys.argv[2:])}건")
