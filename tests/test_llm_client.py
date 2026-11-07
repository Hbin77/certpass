"""AgentStream 설명 호출부: 미설정 시 동작·응답 해석·근거 목록·가짜 서버 호출·API."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from certcheck import llm_client
from certcheck.app import explain_demo, health


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for k in ("AGENTSTREAM_API_KEY", "AGENTSTREAM_CHATBOT_ID", "AGENTSTREAM_BASE_URL", "AGENTSTREAM_TIMEOUT"):
        monkeypatch.delenv(k, raising=False)
    llm_client._cache.clear()


def _ndjson(*events) -> bytes:
    return "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in events).encode()


GOOD = _ndjson({"event": "assistant.delta", "event_id": "e1", "content": "왜 이 등급인가: "},
               {"event": "assistant.delta", "event_id": "e1", "content": "중복"},  # 같은 event_id는 버린다
               {"event": "assistant.delta", "event_id": "e2", "content": [{"type": "thinking", "text": "생각"},
                                                                          {"type": "text", "text": "EDTA 때문입니다 [1]."}]},
               {"event": "tool.result", "references": [{"type": "rag", "source": "EU_ECOLABEL_RINSEOFF.md", "content": "…"}]},
               {"event": "turn.completed", "event_id": "e3"})


def _server(stream: bytes, seen: list, code: int = 200, ctype: str = "application/x-ndjson"):
    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            seen.append((self.path, dict(self.headers), json.loads(self.rfile.read(int(self.headers["Content-Length"])))))
            if self.path.endswith("/sessions"):
                c, body, t = 201, json.dumps({"session_id": "s-123"}).encode(), "application/json"
            else:
                c, body, t = code, stream, ctype
            self.send_response(c)
            self.send_header("Content-Type", t)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def _enable(monkeypatch, port):
    monkeypatch.setenv("AGENTSTREAM_BASE_URL", f"http://127.0.0.1:{port}/agentstream")
    monkeypatch.setenv("AGENTSTREAM_API_KEY", "test-key")
    monkeypatch.setenv("AGENTSTREAM_CHATBOT_ID", "bot-1")


def test_disabled_keeps_sources_and_health():
    out = explain_demo("D3", "EU_ECOLABEL_RINSEOFF")
    assert out["enabled"] is False and out["status"] == "불가"
    assert out["sources"] and all(s["n"] == i for i, s in enumerate(out["sources"], 1))
    assert any(s["url"] and s["url"].startswith("https://") for s in out["sources"])
    assert health()["llm_model"] is False


def test_parse_stream_events():
    out = llm_client.parse_stream(GOOD.splitlines())
    assert out == {"text": "왜 이 등급인가: EDTA 때문입니다 [1].", "rag_sources": ["EU_ECOLABEL_RINSEOFF.md"], "tool_failed": False}
    art = _ndjson({"event": "tool.completed", "type": "tool", "artifact": {"type": "rag_agent", "documents": [
                      {"document": "…", "reference": "CertPass_카드01.md", "evidence": {"section_title": "필요 서류 [EU_CPNP]"}}]}},
                  {"event": "assistant.delta", "content": "답"}, {"event": "turn.completed"})
    assert llm_client.parse_stream(art.splitlines())["rag_sources"] == ["CertPass_카드01.md · 필요 서류 [EU_CPNP]"]
    tf = _ndjson({"event": "tool.failed"}, {"event": "assistant.delta", "content": "답"}, {"event": "turn.completed"})
    assert llm_client.parse_stream(tf.splitlines())["tool_failed"] is True
    rep = _ndjson({"event": "assistant.delta", "content": "초안"}, {"event": "assistant.replace", "content": "<think>x</think>최종"},
                  {"event": "turn.completed"})
    assert llm_client.parse_stream(rep.splitlines())["text"] == "최종"
    with pytest.raises(ValueError, match="turn.failed"):
        llm_client.parse_stream(_ndjson({"event": "turn.failed", "category": "LLM"}).splitlines())
    with pytest.raises(ValueError, match="turn.completed"):
        llm_client.parse_stream(_ndjson({"event": "assistant.delta", "content": "중간에 끊김"}).splitlines())


def test_prompt_keeps_grade_and_numbers():
    out = explain_demo("D3", "EU_ECOLABEL_RINSEOFF")
    from certcheck.app import resources, run_demo
    card = next(c for c in resources()[0] if c["id"] == "EU_ECOLABEL_RINSEOFF")
    v = next(x for x in run_demo("D3")["verdicts"] if x["cert_id"] == "EU_ECOLABEL_RINSEOFF")
    p = llm_client.build_prompt(v, card, {"name_kr": "데모"}, out["sources"])
    assert '판정 등급 "불가"' in p and "근거 1: " in p and "[kw:" not in p and "Disodium EDTA" in p
    assert not any(line.lstrip("- ").startswith("[") for line in p.splitlines())  # 줄 머리 대괄호는 AgentStream이 JSON 표로 읽는다


def test_explain_against_fake_server(monkeypatch):
    seen = []
    srv = _server(GOOD, seen)
    _enable(monkeypatch, srv.server_port)
    out = explain_demo("D3", "EU_ECOLABEL_RINSEOFF")
    again = explain_demo("D3", "EU_ECOLABEL_RINSEOFF")
    srv.shutdown()
    assert out["ok"] and out["text"].startswith("왜 이 등급인가") and out["cached"] is False
    assert out["rag_sources"] == ["EU_ECOLABEL_RINSEOFF.md"]
    assert again["cached"] is True and len(seen) == 2  # 같은 판정은 다시 부르지 않는다(세션 1 + 메시지 1)
    (p1, h1, b1), (p2, h2, b2) = seen
    assert p1 == "/agentstream/open/v1/chatbots/bot-1/sessions" and "query" in b1
    assert p2 == "/agentstream/open/v1/chat-sessions/s-123/messages" and '판정 등급 "불가"' in b2["message"]
    assert {k.lower(): v for k, v in h1.items()}["x-api-key"] == {k.lower(): v for k, v in h2.items()}["x-api-key"] == "test-key"


def test_stream_failure_is_reported(monkeypatch):
    srv = _server(_ndjson({"event": "turn.failed", "category": "RAG"}), [])
    _enable(monkeypatch, srv.server_port)
    out = explain_demo("D3", "EU_ECOLABEL_RINSEOFF")
    srv.shutdown()
    assert out["ok"] is False and "RAG" in out["error"] and out["sources"]


def test_failure_is_short_error_without_key(monkeypatch):
    _enable(monkeypatch, 9)  # 닫힌 포트
    monkeypatch.setenv("AGENTSTREAM_API_KEY", "secret-key-value")
    monkeypatch.setenv("AGENTSTREAM_TIMEOUT", "2")
    out = explain_demo("D3", "EU_ECOLABEL_RINSEOFF")
    assert out["enabled"] and out["ok"] is False and len(out["error"]) <= 200
    assert "secret-key-value" not in json.dumps(out) and out["sources"]


def test_unknown_cert_is_404():
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as e:
        explain_demo("D3", "NOPE")
    assert e.value.status_code == 404


def test_http_error_and_html_are_reported(monkeypatch):
    for code, ctype, want in ((403, "application/json", "CHAT_INVOKE"), (200, "text/html", "HTML")):
        llm_client._cache.clear()
        srv = _server(b"<html>login</html>" if "html" in ctype else b"{}", [], code, ctype)
        _enable(monkeypatch, srv.server_port)
        out = explain_demo("D3", "EU_ECOLABEL_RINSEOFF")
        srv.shutdown()
        assert out["ok"] is False and want in out["error"], out["error"]


def test_health_reads_status(monkeypatch):
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            body = json.dumps({"status": "healthy", "message": "ok", "checked_at": "t"}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    _enable(monkeypatch, srv.server_port)
    h = llm_client.health()
    srv.shutdown()
    assert h["ok"] is True and h["status"] == "healthy"
