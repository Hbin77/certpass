"""AI 검토 의견(llm_review) 측정: 정답이 있는 합성 사례로 '규칙·ML이 놓친 불가'를 LLM이 더 잡는지 잰다.

1) make  : 합성 제품(학습에 안 쓴 seed) → 지저분한 입력의 규칙 판정·AIStream 확률, 깨끗한 제품의 규칙 판정(정답)
           → 검토 대상(needs_review) 중 ML이 경보하지 않은 판정에서 숨은 불가 N건 + 정상 N건 추출
2) run   : 검토 챗봇 호출(순서대로, 이어서 하기 지원) → 결과 JSONL
3) score : 단계별 재현율·헛경보율, 실제 비율(숨은 불가 비율)로 환산한 정밀도

실행(맥):
  AISTREAM_URL=.../predict .venv/bin/python -m certcheck.eval_llm_review make out/llm_review/cases.jsonl --n 40
  set -a; . ~/.certpass_agentstream.env; set +a; AGENTSTREAM_REVIEW_CHATBOT_ID=... \
    .venv/bin/python -m certcheck.eval_llm_review run out/llm_review/cases.jsonl out/llm_review/results.jsonl
  .venv/bin/python -m certcheck.eval_llm_review score out/llm_review/cases.jsonl out/llm_review/results.jsonl
"""
from __future__ import annotations

import argparse
import json
import os
import random
import time
from datetime import date
from pathlib import Path

from . import STATUS_FAIL, ml_client
from .classify import PROXY, evaluate
from .data import DATA, load_attributes, load_cards, load_reg_index
from .llm_review import build_prompt, needs_review, parse
from .risk import near_matches
from .synth import make_products, noisy


def make(out: Path, n: int, n_normal: int, products: int, seed: int) -> None:
    reg, attrs = load_reg_index(), load_attributes()
    cards = [c for c in load_cards() if c.get("kind") != "company_certification"]
    by_id = {c["id"]: c for c in cards}
    doc = json.loads((DATA / "public" / "products" / "demo_products.json").read_text(encoding="utf-8"))
    base = [p for p in doc["products"] if p.get("ingredients")]
    rng = random.Random(seed + 1)
    thr = float(os.environ.get("AISTREAM_FAIL_THRESHOLD", "0.25"))
    hidden, normal = [], []
    for p in make_products(base, reg, products, seed):
        q = noisy(p, rng, rng.choice([0.5, 1.0, 1.5]))
        dirty = [evaluate(c, q, {}, reg, attrs, date(2026, 11, 7)) for c in cards]
        ml = ml_client.predict(dirty, by_id, q, reg)
        if not ml.get("ok"):
            raise SystemExit(f"AIStream 호출 실패: {ml.get('error') or ml.get('reason')}")
        for v in dirty:
            d = v.to_dict()
            d.pop("features", None)
            r = (ml.get("results") or {}).get(v.cert_id) or {}
            if not needs_review(d) or (r.get("fail_proba") or 0) >= thr:
                continue
            label = evaluate(by_id[v.cert_id], p, {}, reg, attrs, date(2026, 11, 7)).status
            rules = (by_id[v.cert_id].get("ingredient_rules") or "none").upper()
            case = {"pid": p["id"], "cert_id": v.cert_id, "label": label, "verdict": d, "product": q,
                    "ml": {"fail_proba": r.get("fail_proba")}, "near": near_matches(q, reg, PROXY.get(rules, rules))}
            (hidden if label == STATUS_FAIL else normal).append(case)
    rng.shuffle(hidden)
    rng.shuffle(normal)
    pool = len(hidden) + len(normal)
    cases = hidden[:n] + normal[:n_normal]
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for c in cases:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    meta = {"products": products, "seed": seed, "review_pool": pool, "hidden_in_pool": len(hidden),
            "hidden_rate": round(len(hidden) / max(1, pool), 4), "sampled_hidden": min(n, len(hidden)), "sampled_normal": min(n_normal, len(normal))}
    out.with_suffix(".meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(meta, ensure_ascii=False))


def run(cases_path: Path, out: Path, gap: float) -> None:
    from . import llm_client
    bot = os.environ["AGENTSTREAM_REVIEW_CHATBOT_ID"]
    cards = {c["id"]: c for c in load_cards()}
    done = set()
    if out.exists():
        done = {(r["pid"], r["cert_id"]) for r in map(json.loads, out.read_text(encoding="utf-8").splitlines()) if r.get("ok")}
    with out.open("a", encoding="utf-8") as f:
        for line in cases_path.read_text(encoding="utf-8").splitlines():
            c = json.loads(line)
            if (c["pid"], c["cert_id"]) in done:
                continue
            t = time.time()
            try:
                ans = llm_client.call(build_prompt(c["verdict"], cards[c["cert_id"]], c["product"], c["ml"], c["near"]), 60,
                                      f"{c['cert_id']} AI 검토 측정", bot=bot)
                r = {"ok": True, **parse(ans["text"]), "text": ans["text"][:1500], "rag": len(ans.get("rag_sources") or [])}
            except Exception as e:
                r = {"ok": False, "error": f"{type(e).__name__}: {e}"[:200]}
            r.update(pid=c["pid"], cert_id=c["cert_id"], label=c["label"], sec=round(time.time() - t, 1))
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
            f.flush()
            print(r["cert_id"], r.get("level") or r.get("error"), r["sec"], flush=True)
            time.sleep(gap)


def score(cases_path: Path, results: Path) -> None:
    meta = json.loads(cases_path.with_suffix(".meta.json").read_text(encoding="utf-8"))
    rs = [r for r in map(json.loads, results.read_text(encoding="utf-8").splitlines()) if r.get("ok")]
    hid = [r for r in rs if r["label"] == STATUS_FAIL]
    nor = [r for r in rs if r["label"] != STATUS_FAIL]
    out = {"answered": len(rs), "hidden": len(hid), "normal": len(nor), "hidden_rate_in_pool": meta["hidden_rate"]}
    for lv in ("불가 가능성 높음", "불가 가능성 낮음", "판단 불가"):
        out[lv] = {"숨은불가": sum(r["level"] == lv for r in hid), "정상": sum(r["level"] == lv for r in nor)}
    rec = out["불가 가능성 높음"]["숨은불가"] / max(1, len(hid))
    fpr = out["불가 가능성 높음"]["정상"] / max(1, len(nor))
    base = meta["hidden_rate"]
    out["재현율(숨은불가 중 '높음')"] = round(rec, 3)
    out["헛경보율(정상 중 '높음')"] = round(fpr, 3)
    out["실제 비율 환산 정밀도"] = round(rec * base / max(1e-9, rec * base + fpr * (1 - base)), 3) if rec or fpr else None
    out["판단 불가 비율"] = round(sum(r["level"] == "판단 불가" for r in rs) / max(1, len(rs)), 3)
    out["평균 초"] = round(sum(r["sec"] for r in rs) / max(1, len(rs)), 1)
    print(json.dumps(out, ensure_ascii=False, indent=1))
    results.with_suffix(".score.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    m = sp.add_parser("make")
    m.add_argument("out", type=Path)
    m.add_argument("--n", type=int, default=80, help="숨은 불가 표본 수")
    m.add_argument("--n-normal", type=int, default=200, help="정상 표본 수(정밀도 하한을 말하려면 200 이상)")
    m.add_argument("--products", type=int, default=400)
    m.add_argument("--seed", type=int, default=2026)
    r = sp.add_parser("run")
    r.add_argument("cases", type=Path)
    r.add_argument("out", type=Path)
    r.add_argument("--gap", type=float, default=12.0, help="호출 간격(초), 판정 설명과 모델 한도를 나눠 씀")
    s = sp.add_parser("score")
    s.add_argument("cases", type=Path)
    s.add_argument("results", type=Path)
    a = ap.parse_args()
    if a.cmd == "make":
        make(a.out, a.n, a.n_normal, a.products, a.seed)
    elif a.cmd == "run":
        run(a.cases, a.out, a.gap)
    else:
        score(a.cases, a.results)


if __name__ == "__main__":
    main()
