"""시연 직전 점검: 공개 주소에서 판정·AI 경보·서류·저장된 AI 설명·OCR(사진·PDF)을 한 번씩 불러 본다.

AIStream 서빙은 요청이 없으면 60분 뒤 자동 일시 정지되므로, 시연 10분 전쯤 실행해 OCR 서빙을 깨운다(첫 사진이 늦거나 실패하지 않게).
실행: python3 deploy/demo_check.py [사진.jpg ...] [전성분표.pdf ...]   (파일을 안 주면 OCR은 건너뛴다)
- 표준 라이브러리만 쓴다. 사진은 그대로 보낸다(화면은 긴 변 2400px로 줄여 보낸다)
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request

BASE = "https://devopen-gpu.jntp-ax.or.kr/i/FBi4CwFvT4Pe38Xd"
CTYPE = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp", ".pdf": "application/pdf"}


def call(path: str, data: bytes | None = None, ctype: str | None = None, timeout: float = 60) -> tuple[float, dict | bytes]:
    req = urllib.request.Request(BASE + path, data=data, headers={"Content-Type": ctype} if ctype else {})
    t = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read()
        kind = r.headers.get("Content-Type", "")
    return time.time() - t, json.loads(body) if "json" in kind else body


def ocr(path: str) -> str:
    ext = path[path.rfind("."):].lower()
    data = open(path, "rb").read()
    t = time.time()
    _, job = call("/api/ocr?mode=job", data, CTYPE[ext])
    while job["status"] in ("queued", "running"):
        if time.time() - t > 180:
            return "시간 초과(180초)"
        time.sleep(1)
        _, job = call(f"/api/ocr/jobs/{job['job']}")
    if job["status"] == "error":
        return f"실패 {job['error']}"
    c = job["result"]["counts"]
    return f"{time.time() - t:.1f}초 · 정확 일치 {c['exact']}종 · 비슷한 이름 {c['fuzzy']} · 확인 필요 {c['unknown']}"


def main() -> None:
    ok = True
    checks = [
        ("웹 상태", lambda: (lambda r: f"{r[0]:.1f}초 · RF {r[1]['ml_model']} · OCR {r[1]['ocr_model']} · LLM {r[1]['llm_model']}")(call("/api/health"))),
        ("판정+AI 경보(데모 D3)", lambda: (lambda r: f"{r[0]:.1f}초 · 판정 {len(r[1]['verdicts'])}건")(call("/api/evaluate-demo/D3"))),
        ("저장된 AI 설명(D3 첫 판정)", lambda: (lambda v: (lambda r: f"{r[0]:.2f}초 · 저장본 {r[1].get('cached')}")(
            call(f"/api/explain-demo/D3/{v}?cache_only=1")))(call("/api/evaluate-demo/D3")[1]["verdicts"][0]["cert_id"])),
    ] + [(f"OCR {p.rsplit('/', 1)[-1]}", lambda p=p: ocr(p)) for p in sys.argv[1:]]
    for name, fn in checks:
        try:
            print(f"[통과] {name}: {fn()}", flush=True)
        except Exception as e:
            ok = False
            print(f"[실패] {name}: {type(e).__name__}: {e}", flush=True)
    print("모두 통과" if ok else "실패 항목이 있습니다. 위 내용을 확인하세요.")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
