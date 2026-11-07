"""포장 사진 OCR 연결(/api/ocr, ocr_client) 테스트: 가짜 OCR 서빙으로 성분명 맞추기·입력 검증·오류 처리를 확인한다."""
import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from certcheck import ocr_client
from certcheck.app import OCR_MAX_BYTES, app

JPEG = b"\xff\xd8\xff\xe0" + b"0" * 2000


def call(path: str, body: bytes, ctype: str):
    messages, sent = [], [False]

    async def receive():
        if sent[0]:
            return {"type": "http.disconnect"}
        sent[0] = True
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(m):
        messages.append(m)

    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "POST", "scheme": "http",
             "path": path, "raw_path": path.encode(), "root_path": "", "query_string": b"",
             "headers": [(b"host", b"t"), (b"content-type", ctype.encode()), (b"content-length", str(len(body)).encode())],
             "client": ("127.0.0.1", 1), "server": ("t", 80)}
    asyncio.run(app(scope, receive, send))
    start = next(m for m in messages if m["type"] == "http.response.start")
    return start["status"], b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")


@pytest.fixture
def fake_ocr(monkeypatch):
    got = {}

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            n = int(self.headers["Content-Length"])
            got["body"] = self.rfile.read(n)
            got["ctype"] = self.headers["Content-Type"]
            out = {"ingredients": ["정제수", "글리세린", "나이아신아마이드", "부틸렌글라이콜", "소듐하이알루로네이", "알수없는글자"],
                   "lines": [{"text": "전성분: 정제수, 글리세린", "conf": 0.97}], "text": "전성분: 정제수, 글리세린",
                   "words": [{"text": "정제수,"}], "model": {"name": "7팀_package_ocr", "version": "1"}}
            data = json.dumps(out, ensure_ascii=False).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setenv("CERTCHECK_OCR_URL", f"http://127.0.0.1:{srv.server_port}/predict")
    yield got
    srv.shutdown()


def test_match_name_exact_fuzzy_unknown():
    assert ocr_client.match_name("정제수")["match"] == "exact"
    assert ocr_client.match_name("정제수")["inci"].lower() == "water"
    f = ocr_client.match_name("소듐하이알루로네이")  # 줄 끝에서 잘린 OCR 표기
    assert f["match"] == "fuzzy" and f["kr"] == "소듐하이알루로네이트"
    assert ocr_client.match_name("알수없는글자")["match"] == "unknown"


def test_segment_splits_merged_and_joins_broken_names():
    # 쉼표가 빠져 붙은 두 성분, 줄바꿈으로 잘린 한 성분, 목록 기호
    assert ocr_client.segment("세테아릴알코올 잔탄검") == ["세테아릴알코올", "잔탄검"]
    assert ocr_client.segment("다이프로필렌글 라이콜") == ["다이프로필렌글라이콜"]
    assert ocr_client.segment("] 정제수") == ["정제수"]
    items = ocr_client.match_all(["1 정제수", "세테아릴알코올 잔탄검", "정제수"])
    assert [i["kr"] for i in items] == ["정제수", "세테아릴알코올", "잔탄검"]  # 중복 정제수는 한 번만


def test_ocr_route_end_to_end(fake_ocr):
    status, body = call("/api/ocr", JPEG, "image/jpeg")
    assert status == 200
    r = json.loads(body)
    assert r["counts"] == {"exact": 4, "fuzzy": 1, "unknown": 1}
    assert [i["kr"] for i in r["ingredients"]][:2] == ["정제수", "글리세린"]
    assert r["found_section"] is True
    # 사진은 multipart file 필드로 그대로 전달된다
    assert fake_ocr["ctype"].startswith("multipart/form-data") and JPEG in fake_ocr["body"]


def test_ocr_disabled_is_503(monkeypatch):
    monkeypatch.delenv("CERTCHECK_OCR_URL", raising=False)
    assert call("/api/ocr", JPEG, "image/jpeg")[0] == 503


def test_ocr_rejects_non_image(fake_ocr):
    assert call("/api/ocr", b"hello", "text/plain")[0] == 415
    assert call("/api/ocr", b"not a jpeg at all", "image/jpeg")[0] == 415  # 첫 바이트가 JPEG가 아님


def test_ocr_size_limit(fake_ocr):
    big = b"\xff\xd8" + b"0" * (OCR_MAX_BYTES + 1)
    assert call("/api/ocr", big, "image/jpeg")[0] == 413
    # 다른 API의 1 MiB 상한은 그대로(사진 경로만 크다)
    assert call("/api/evaluate", b"{" + b" " * (1024 * 1024 + 10) + b"}", "application/json")[0] == 413


def test_ocr_server_down_is_502(monkeypatch):
    monkeypatch.setenv("CERTCHECK_OCR_URL", "http://127.0.0.1:9/predict")
    monkeypatch.setenv("CERTCHECK_OCR_TIMEOUT", "2")
    assert call("/api/ocr", JPEG, "image/jpeg")[0] == 502
