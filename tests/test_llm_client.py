"""AgentStream 설명 호출부: 미설정 시 동작·응답 해석·근거 목록·가짜 서버 호출·API."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from certcheck import llm_client
from certcheck.app import explain_demo, health


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for k in ("AGENTSTREAM_URL", "AGENTSTREAM_KEY", "AGENTSTREAM_AUTH_HEADER", "AGENTSTREAM_QUERY_FIELD", "AGENTSTREAM_EXTRA"):
        monkeypatch.delenv(k, raising=False)
    llm_client._cache.clear()


def _server(reply, seen: list):
    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            seen.append((dict(self.headers), json.loads(self.rfile.read(int(self.headers["Content-Length"])))))
            body = reply if isinstance(reply, bytes) else json.dumps(reply).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def test_disabled_keeps_sources_and_health():
    out = explain_demo("D3", "EU_ECOLABEL_RINSEOFF")
    assert out["enabled"] is False and out["status"] == "불가"
    assert out["sources"] and all(s["n"] == i for i, s in enumerate(out["sources"], 1))
    assert any(s["url"] and s["url"].startswith("https://") for s in out["sources"])
    assert health()["llm_model"] is False


def test_parse_answer_shapes():
    assert llm_client.parse_answer('{"answer": "A"}')["text"] == "A"
    assert llm_client.parse_answer('{"data": {"content": "B", "sources": [{"file_name": "EU_CPNP.md"}]}}') == \
        {"text": "B", "rag_sources": ["EU_CPNP.md"]}
    assert llm_client.parse_answer('{"choices": [{"message": {"content": "<think>x</think>C"}}]}')["text"] == "C"
    sse = 'data: {"content": "가"}\n\ndata: {"content": "나"}\n\ndata: [DONE]\n'
    assert llm_client.parse_answer(sse)["text"] == "가나"
    assert llm_client.parse_answer("그냥 글자")["text"] == "그냥 글자"


def test_prompt_keeps_grade_and_numbers():
    out = explain_demo("D3", "EU_ECOLABEL_RINSEOFF")
    from certcheck.app import resources, run_demo
    card = next(c for c in resources()[0] if c["id"] == "EU_ECOLABEL_RINSEOFF")
    v = next(x for x in run_demo("D3")["verdicts"] if x["cert_id"] == "EU_ECOLABEL_RINSEOFF")
    p = llm_client.build_prompt(v, card, {"name_kr": "데모"}, out["sources"])
    assert '판정 등급 "불가"' in p and "[1] " in p and "[kw:" not in p and "Disodium EDTA" in p


def test_explain_against_fake_server(monkeypatch):
    seen = []
    srv = _server({"data": {"answer": "왜 이 등급인가: EDTA 때문입니다 [1]."}}, seen)
    monkeypatch.setenv("AGENTSTREAM_URL", f"http://127.0.0.1:{srv.server_port}/chat")
    monkeypatch.setenv("AGENTSTREAM_KEY", "test-key")
    monkeypatch.setenv("AGENTSTREAM_QUERY_FIELD", "message")
    monkeypatch.setenv("AGENTSTREAM_EXTRA", '{"stream": false}')
    out = explain_demo("D3", "EU_ECOLABEL_RINSEOFF")
    again = explain_demo("D3", "EU_ECOLABEL_RINSEOFF")
    srv.shutdown()
    assert out["ok"] and out["text"].startswith("왜 이 등급인가") and out["cached"] is False
    assert again["cached"] is True and len(seen) == 1  # 같은 판정은 다시 부르지 않는다
    headers, body = seen[0]
    assert headers["Authorization"] == "Bearer test-key" and body["stream"] is False and "불가" in body["message"]


def test_failure_is_short_error_without_key(monkeypatch):
    monkeypatch.setenv("AGENTSTREAM_URL", "http://127.0.0.1:9/none")  # 닫힌 포트
    monkeypatch.setenv("AGENTSTREAM_KEY", "secret-key-value")
    monkeypatch.setenv("AGENTSTREAM_TIMEOUT", "2")
    out = explain_demo("D3", "EU_ECOLABEL_RINSEOFF")
    assert out["enabled"] and out["ok"] is False and len(out["error"]) <= 200
    assert "secret-key-value" not in json.dumps(out) and out["sources"]


def test_unknown_cert_is_404():
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as e:
        explain_demo("D3", "NOPE")
    assert e.value.status_code == 404
