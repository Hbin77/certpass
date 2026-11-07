"""공개 API의 입력 검증·크기 상한·보안 헤더 회귀 테스트(ASGI 직접 호출, httpx 불필요)."""
import asyncio
import io
import json
import re
import time
import zipfile

import pytest

from certcheck.app import MAX_BODY_BYTES, app
from certcheck.data import DATA
from certcheck.docs_gen import MAX_ALLERGEN_NOTES, _net, _prep_verdict

DEMO = json.loads((DATA / "public/products/demo_products.json").read_text(encoding="utf-8"))
P3 = next(p for p in DEMO["products"] if p["id"] == "D3")


def call(method: str, path: str, body=None, chunks: list[bytes] | None = None):
    """(상태, 헤더, 본문). chunks를 주면 Content-Length 없이 조각으로 보낸다(chunked 전송)."""
    payload = json.dumps(body).encode() if body is not None else b""
    parts = chunks if chunks is not None else [payload]
    messages, sent = [], 0

    async def receive():
        nonlocal sent
        if sent >= len(parts):
            return {"type": "http.disconnect"}
        sent += 1
        return {"type": "http.request", "body": parts[sent - 1], "more_body": sent < len(parts)}

    async def send(message):
        messages.append(message)

    headers = [(b"host", b"test"), (b"content-type", b"application/json")]
    if chunks is None:
        headers.append((b"content-length", str(len(payload)).encode()))
    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": method, "scheme": "http",
             "path": path, "raw_path": path.encode(), "root_path": "", "query_string": b"", "headers": headers,
             "client": ("127.0.0.1", 1), "server": ("test", 80)}
    asyncio.run(app(scope, receive, send))
    start = next(m for m in messages if m["type"] == "http.response.start")
    return (start["status"], {k.decode().lower(): v.decode() for k, v in start["headers"]},
            b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body"))


@pytest.mark.parametrize("company", [{"local_entities": "EU"}, {"documents": 7}, {"company_certs": {"venture": [1]}},
                                     {"role_kr": 5}, {"financial": [1]}])
def test_bad_company_is_422_not_500(company):
    assert call("POST", "/api/evaluate", {"product": P3, "company": company})[0] == 422


def test_demo_and_real_company_shapes_pass():
    real = {"name": "회사", "role_kr": "화장품책임판매업자", "own_manufacturing": False, "location": "전남",
            "export_history": ["2025 일본"], "company_certs": {"venture": "valid", "innobiz": "none"}, "local_entities": {},
            "financial": {"capital_impairment": "partial", "fiscal_year": 2025, "_source": "x"}, "annual_production_krw": "10억"}
    for company in (DEMO["company"], real):
        assert call("POST", "/api/evaluate", {"product": P3, "company": company})[0] == 200


def test_bad_manufacturer_and_too_many_ingredients_are_422():
    assert call("POST", "/api/evaluate", {"product": {**P3, "manufacturer": {"certs": [1]}}})[0] == 422
    ings = [{"inci": f"Ing {i}"} for i in range(501)]
    assert call("POST", "/api/evaluate", {"product": {**P3, "ingredients": ings}})[0] == 422


def test_body_over_limit_is_413():
    big = {"product": P3, "pad": "x" * MAX_BODY_BYTES}
    assert call("POST", "/api/evaluate", big)[0] == 413
    raw = json.dumps(big).encode()
    assert call("POST", "/api/evaluate", chunks=[raw[i:i + 65536] for i in range(0, len(raw), 65536)])[0] == 413


def test_long_message_is_rejected_and_regexes_stay_linear():
    v = {"cert_id": "X", "findings": [{"level": "fail", "code": "X", "message": "1" * 30000}]}
    t = time.perf_counter()
    assert call("POST", "/api/docs/gap_checklist", {"product": P3, "verdicts": [v]})[0] == 422
    assert time.perf_counter() - t < 3
    t = time.perf_counter()  # 지금은 수 ms. 예전 정규식은 2만 자 숫자열 하나에 10초 넘게 걸렸다(느린 CI 여유로 3초)
    for s in ("1" * 20000, " " * 20000 + "x", "[kw:" * 5000):
        _prep_verdict({"findings": [{"message": s, "evidence": s, "action": s}]}, {1.0})
        _net(s)
    assert time.perf_counter() - t < 3


def test_api_docs_closed_and_security_headers():
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert call("GET", path)[0] == 404
    status, headers, _ = call("GET", "/api/health")
    assert status == 200
    assert headers["x-content-type-options"] == "nosniff" and headers["referrer-policy"] == "same-origin"


def test_unknown_cert_ids():
    cid = json.loads(call("GET", "/api/certs")[2])[0]["id"]
    status, _, body = call("POST", "/api/evaluate", {"product": P3, "cert_ids": [cid, "NOPE"]})
    d = json.loads(body)
    assert status == 200 and d["unknown_cert_ids"] == ["NOPE"] and [v["cert_id"] for v in d["verdicts"]] == [cid]
    assert call("POST", "/api/evaluate", {"product": P3, "cert_ids": ["NOPE"]})[0] == 422


def test_lone_surrogate_input_is_not_500():
    s = "\ud800"  # json.dumps가 "\ud800" 이스케이프로 보낸다
    for path, body in (("/api/evaluate", {"product": {**P3, "name_kr": s}}),
                       ("/api/evaluate", {"product": {**P3, "name_kr": s + "x" * 400}}),
                       ("/api/evaluate", {"product": P3, "cert_ids": [s]}),
                       ("/api/docs/gap_checklist", {"product": P3, "verdicts": [{"cert_id": "X", "findings": [{"message": s}]}]})):
        status, _, out = call("POST", path, body)
        assert status in (200, 422)
        json.loads(out)


def test_allergen_footnotes_are_bounded():
    incis = [f"a{i}" for i in range(100)]
    rules = [{"level": "info", "code": "ALLERGEN_LABEL_RULE", "message": " ".join(incis), "evidence": f"ev{k}"} for k in range(100)]
    t = time.perf_counter()
    status, _, out = call("POST", "/api/docs/inci_list", {"product": {**P3, "ingredients": [{"inci": x} for x in incis]},
                                                          "verdicts": [{"cert_id": "EU_X", "jurisdiction": "EU", "findings": rules}]})
    assert status == 200 and time.perf_counter() - t < 3
    xml = zipfile.ZipFile(io.BytesIO(out)).read("word/footnotes.xml").decode()
    # 예전에는 성분 100 × 근거 100 = 1만 개. 지금은 성분당 근거 MAX_ALLERGEN_NOTES개 + '생략' 1개
    assert len(re.findall(r'<w:footnote w:id="[1-9]\d*"', xml)) <= len(incis) * (MAX_ALLERGEN_NOTES + 1) + 10


def test_newline_bomb_in_paragraph_text_is_fast():
    fs = [{"level": "cond", "code": "LABEL_LOCAL", "message": "\n" * 990 + f"{i:06d}"} for i in range(300)]
    t = time.perf_counter()
    status, _, _ = call("POST", "/api/docs/label_draft", {"product": P3, "verdicts": [{"cert_id": "EU_X", "jurisdiction": "EU", "findings": fs}]})
    assert status == 200 and time.perf_counter() - t < 3
