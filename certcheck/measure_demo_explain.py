"""데모 제품 하나의 AI 설명을 실제 화면 경로(/api/explain-demo)로 한 번씩 만들며 검색 정확도를 잰다(만든 설명은 저장돼 다시 쓰임).

실행: .venv/bin/python -m certcheck.measure_demo_explain D5 [--url 공개주소]
- 이미 저장된 행은 cache_only로 건너뛰고(토큰 0), 저장 안 된 행만 11초 간격으로 부른다(방문자별 분당 6건 안쪽)
- 지표: precision = 이 인증 카드 조각 수 / 조회 조각 수(rag_target / (rag_target + rag_other)), hit = 이 카드 조각이 1건 이상
- 모델 한도(LLM_RATE_LIMITED)가 두 번 이어지면 멈춘다(토큰 낭비 방지). 결과: out/measure_explain_{제품}.json
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

URL = "https://devopen-gpu.jntp-ax.or.kr/i/FBi4CwFvT4Pe38Xd"


def get(url: str) -> dict:
    return json.loads(urllib.request.urlopen(url, timeout=180).read())


def main(pid: str, url: str = URL) -> dict:
    ids = [c["id"] for c in get(f"{url}/api/certs") if c.get("kind") != "company_certification"]
    rows, limited = [], 0
    for cid in ids:
        d = get(f"{url}/api/explain-demo/{pid}/{cid}?cache_only=1")
        if d.get("enabled") is False:
            continue
        if d.get("cached"):
            rows.append({"cert": cid, "new": False, **{k: d.get(k) for k in ("rag_target", "rag_other", "unsupported", "bad_refs")}})
            continue
        t = time.monotonic()
        d = get(f"{url}/api/explain-demo/{pid}/{cid}")
        row = {"cert": cid, "new": True, "ok": bool(d.get("ok")), "sec": round(time.monotonic() - t, 1),
               **{k: d.get(k) for k in ("rag_target", "rag_other", "unsupported", "bad_refs", "error")}}
        rows.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
        limited = limited + 1 if "LLM_RATE_LIMITED" in str(d.get("error")) else 0
        if limited >= 2:
            print("모델 한도가 두 번 이어져 멈춤", flush=True)
            break
        time.sleep(11)
    m = [r for r in rows if r.get("rag_target") is not None and (r["rag_target"] + (r.get("rag_other") or 0)) > 0]
    summ = {"product": pid, "rows": len(rows), "new_calls": sum(r["new"] for r in rows),
            "new_ok": sum(r.get("ok", False) for r in rows if r["new"]),
            "hit": round(sum(r["rag_target"] > 0 for r in m) / len(m), 3) if m else None,
            "precision": round(sum(r["rag_target"] / (r["rag_target"] + r["rag_other"]) for r in m) / len(m), 3) if m else None,
            "with_unsupported": sum(bool(r.get("unsupported")) for r in rows),
            "mean_sec_new": round(sum(r["sec"] for r in rows if r["new"]) / max(1, sum(r["new"] for r in rows)), 1)}
    Path("out").mkdir(exist_ok=True)
    Path(f"out/measure_explain_{pid}.json").write_text(json.dumps({"summary": summ, "rows": rows}, ensure_ascii=False, indent=1),
                                                       encoding="utf-8")
    return summ


if __name__ == "__main__":
    a = sys.argv[1:]
    url = a[a.index("--url") + 1] if "--url" in a else URL
    print(json.dumps(main(a[0] if a else "D5", url), ensure_ascii=False))
