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
    monkeypatch.setattr(llm_client, "CACHE_FILE", "")  # 시험은 파일 캐시를 쓰지 않는다
    monkeypatch.setattr(llm_client, "_cache_loaded", True)
    llm_client._calls.clear()


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
    assert {k: out[k] for k in ("text", "rag_sources", "tool_failed")} == \
        {"text": "왜 이 등급인가: EDTA 때문입니다 [1].", "rag_sources": ["EU_ECOLABEL_RINSEOFF.md"], "tool_failed": False}
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


def test_ai_alert_section_in_prompt():
    """AIStream 경보는 등급과 구분해 'AI 경보:' 규칙과 본문 구역으로 들어가고, 줄 머리에 대괄호가 없으며 확률은 둘째 자리."""
    ai = {"fail_proba": 0.5234, "threshold": 0.25,
          "near": [{"input": "Dibutyl Phthlate", "listed": "dibutyl phthalate", "list_type": "banned", "similarity": 0.97}]}
    out = explain_demo("D3", "EU_ECOLABEL_RINSEOFF")
    v = {"cert_id": "EU_ECOLABEL_RINSEOFF", "status": out["status"], "findings": []}
    p = llm_client.build_prompt(v, {"id": "EU_ECOLABEL_RINSEOFF", "name_ko": "x", "jurisdiction": "EU"}, {"name_kr": "데모"}, out["sources"], ai)
    assert "AI 경보:" in p and "불가 가능성 0.52" in p and "'dibutyl phthalate'" in p and "등급 아님" in p
    assert not any(line.lstrip().startswith("[") for line in p.splitlines())
    assert llm_client.ai_lines(None) == ("", "")


def test_near_matches_skips_dictionary_names():
    """정상 원료 이름(식약처 사전에 있음)은 오탈자 의심에서 빠지고, 사전에 없는 금지 성분 오기만 남는다."""
    from certcheck.data import load_reg_index
    from certcheck.risk import near_matches
    p = {"ingredients": [{"inci": "Sodium Chloride"}, {"inci": "Dibutyl Phthlate"}]}
    got = near_matches(p, load_reg_index(), "EU")
    assert [g["input"] for g in got] == ["Dibutyl Phthlate"] and got[0]["list_type"] == "banned"


def test_kb_tag_grouping_and_hint():
    assert llm_client.kb_tag("EU_CPNP") == "EUCPNP" and llm_client.kb_tag("V_LABEL") == "VLABEL"
    assert llm_client.tag_match("EUEC", "EUECOLABELRINSEOFF") and not llm_client.tag_match("EUREACHD4D5D6", "EUCPNP")
    assert not llm_client.tag_match(None, "EUCPNP")
    docs = [{"ref": "카드01.md", "section": "필요 서류 [EUCPNP EU 화장품 신고(CPNP)]", "tag": "EUCPNP"},
            {"ref": "카드01.md", "section": "표시(라벨) [EUCPNP EU 화장품 신고(CPNP)]", "tag": "EUCPNP"},
            {"ref": "카드01.md", "section": "적용 대상 [EUREACHD4D5D6 EU REACH]", "tag": "EUREACHD4D5D6"}]
    g = llm_client.group_sources(docs, "EU_CPNP")
    assert g == {"rag_sources": ["카드01.md: 필요 서류, 표시(라벨)"], "rag_target": 2, "rag_other": 1}
    from certcheck.app import resources, run_demo
    card = next(c for c in resources()[0] if c["id"] == "EU_CPNP")
    v = next(x for x in run_demo("D3")["verdicts"] if x["cert_id"] == "EU_CPNP")
    assert "꼬리표 'EUCPNP'" in llm_client.build_prompt(v, card, {}, [])
    assert "꼬리표" not in llm_client.build_prompt(v, card, {}, [], kb_hint=False)


def test_unverified_facts():
    corpus = "D5 — 2027-06-06 이후 EU 판매 금지. 바르는 제품 0.001%"
    assert llm_client.unverified_facts("2027 년 6 월 6 일 이후 금지, 0.001 % 초과", corpus) == []
    assert llm_client.unverified_facts("2028년 1월부터, 0.5% 이하", corpus) == ["0.5%", "2028-01"]


def test_rate_limited_retries_once(monkeypatch):
    calls = []
    good = {"text": "답", "rag_sources": [], "tool_failed": False, "docs": []}

    def fake(prompt, timeout, title=""):
        calls.append(1)
        if len(calls) == 1:
            raise llm_client.RateLimited("turn.failed LLM LLM_RATE_LIMITED")
        return dict(good)

    monkeypatch.setenv("AGENTSTREAM_API_KEY", "k")
    monkeypatch.setenv("AGENTSTREAM_CHATBOT_ID", "b")
    monkeypatch.setenv("AGENTSTREAM_RETRY_WAIT", "0")
    monkeypatch.setattr(llm_client, "call", fake)
    out = explain_demo("D3", "EU_CPNP")
    assert out["ok"] and len(calls) == 2


def test_rate_cap_blocks_without_calling(monkeypatch):
    monkeypatch.setenv("AGENTSTREAM_API_KEY", "k")
    monkeypatch.setenv("AGENTSTREAM_CHATBOT_ID", "b")
    monkeypatch.setenv("AGENTSTREAM_RATE_PER_MIN", "1")
    monkeypatch.setattr(llm_client, "call", lambda *a, **k: {"text": "답", "rag_sources": [], "tool_failed": False, "docs": []})
    assert explain_demo("D3", "EU_CPNP")["ok"]
    out = explain_demo("D3", "EU_PPWR")  # 다른 판정 = 새 호출 → 분당 1건 넘음
    assert out["ok"] is False and out["error"].startswith("RateLimit")
    assert explain_demo("D3", "EU_CPNP")["cached"] is True  # 캐시는 상한과 상관없이 나온다


def test_file_cache_roundtrip(monkeypatch, tmp_path):
    f = tmp_path / "c.json"
    monkeypatch.setattr(llm_client, "CACHE_FILE", str(f))
    monkeypatch.setenv("AGENTSTREAM_API_KEY", "k")
    monkeypatch.setenv("AGENTSTREAM_CHATBOT_ID", "b")
    monkeypatch.setattr(llm_client, "call", lambda *a, **k: {"text": "답", "rag_sources": [], "tool_failed": False, "docs": []})
    explain_demo("D3", "EU_CPNP")
    assert f.exists() and "secret" not in f.read_text()
    llm_client._cache.clear()
    monkeypatch.setattr(llm_client, "_cache_loaded", False)
    monkeypatch.setattr(llm_client, "call", lambda *a, **k: (_ for _ in ()).throw(AssertionError("다시 부르면 안 됨")))
    assert explain_demo("D3", "EU_CPNP")["cached"] is True


def _on(monkeypatch, fake):
    monkeypatch.setenv("AGENTSTREAM_API_KEY", "k")
    monkeypatch.setenv("AGENTSTREAM_CHATBOT_ID", "b")
    monkeypatch.setattr(llm_client, "call", fake)


GOOD_RAW = {"text": "답", "rag_sources": [], "tool_failed": False, "docs": []}


def test_cache_hit_skips_ai_and_ignores_ai_result(monkeypatch):
    """캐시에 있으면 AIStream 경보 함수를 부르지 않고, 경보 결과가 달라도 같은 캐시를 쓴다(리뷰 MEDIUM)."""
    _on(monkeypatch, lambda *a, **k: dict(GOOD_RAW))
    from certcheck.app import resources, run_demo
    card = next(c for c in resources()[0] if c["id"] == "EU_CPNP")
    v = next(x for x in run_demo("D3")["verdicts"] if x["cert_id"] == "EU_CPNP")
    assert llm_client.explain(v, card, {}, lambda: {"fail_proba": 0.5, "threshold": 0.2, "near": []})["cached"] is False
    out = llm_client.explain(v, card, {}, lambda: (_ for _ in ()).throw(AssertionError("캐시 적중인데 ML 호출")))
    assert out["cached"] is True and out["ai_alert"]["fail_proba"] == 0.5


def test_busy_when_queue_full_returns_fast(monkeypatch):
    """슬롯을 기다리는 요청이 상한이면 바로 거절해 서버 스레드를 잡지 않고, 분당 상한도 되돌린다(리뷰 HIGH)."""
    import time as _t
    monkeypatch.setenv("AGENTSTREAM_API_KEY", "k")
    monkeypatch.setenv("AGENTSTREAM_CHATBOT_ID", "b")
    monkeypatch.setattr(llm_client, "_waiting", 3)
    t = _t.monotonic()
    out = explain_demo("D3", "EU_CPNP")
    assert out["ok"] is False and out["error"].startswith("RateLimit") and _t.monotonic() - t < 2
    assert not any(llm_client._calls.values())  # 거절된 요청은 상한을 쓰지 않음


def test_per_client_cap(monkeypatch):
    monkeypatch.setenv("AGENTSTREAM_RATE_PER_CLIENT_MIN", "1")
    assert llm_client._rate_take("1.1.1.1") and not llm_client._rate_take("1.1.1.1")
    assert llm_client._rate_take("2.2.2.2")  # 다른 방문자는 따로


def test_only_demo_products_persist(monkeypatch, tmp_path):
    """파일 캐시에는 데모 제품 설명만(사용자가 넣은 처방은 메모리에만, 리뷰 LOW)."""
    f = tmp_path / "c.json"
    monkeypatch.setattr(llm_client, "CACHE_FILE", str(f))
    _on(monkeypatch, lambda *a, **k: dict(GOOD_RAW))
    from certcheck.app import ExplainRequest, _explain, demo_products
    from certcheck.schemas import Product
    data = demo_products()
    p = next(x for x in data["products"] if x["id"] == "D3")
    mine = Product(**{**{k: v for k, v in p.items() if k in Product.model_fields}, "name_kr": "사용자 제품"})
    _explain(ExplainRequest(product=mine, company=data["company"], cert_id="EU_CPNP"), "9.9.9.9")
    assert not f.exists()
    explain_demo("D3", "EU_CPNP")
    saved = json.loads(f.read_text())
    assert len(saved) == 1 and all(v["pin"] for v in saved.values())


def test_demo_entries_not_evicted(monkeypatch):
    monkeypatch.setattr(llm_client, "CACHE_SIZE", 2)
    with llm_client._lock:
        llm_client._cache_put("demo", {"text": "a"}, True)
        for i in range(5):
            llm_client._cache_put(f"u{i}", {"text": "b"}, False)
    assert "demo" in llm_client._cache and len(llm_client._cache) == 2


def test_explain_demo_long_id_is_404():
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as e:
        explain_demo("D3", "A" * 101)
    assert e.value.status_code == 404


def test_regulation_numbers_are_not_dates():
    assert llm_client.unverified_facts("규정 (EU) 2019/1021 및 2021/1870 기준", "x") == []


def test_redirect_is_not_followed(monkeypatch):
    """관문이 다른 곳으로 돌려도 Key를 다시 보내지 않고 실패로 끝낸다(리뷰 LOW)."""
    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            self.send_response(302)
            self.send_header("Location", "http://127.0.0.1:9/login")
            self.end_headers()

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    _enable(monkeypatch, srv.server_port)
    out = explain_demo("D3", "EU_CPNP")
    srv.shutdown()
    assert out["ok"] is False and "302" in out["error"]


def test_slow_stream_without_newline_times_out(monkeypatch):
    """줄바꿈 없이 아주 느리게 오는 응답에도 전체 제한 시간이 걸린다(리뷰 LOW)."""
    import time as _t

    class Drip:
        def read1(self, n):
            _t.sleep(0.3)
            return b"x"

    with pytest.raises(TimeoutError):
        list(llm_client._lines(Drip(), _t.monotonic() + 1, 1))


def test_cache_key_changes_with_ml_model(monkeypatch):
    """AIStream 모델 주소·경보 기준이 바뀌면 예전 설명을 쓰지 않는다(ax-45 지적)."""
    _on(monkeypatch, lambda *a, **k: dict(GOOD_RAW))
    monkeypatch.setenv("AISTREAM_FAIL_THRESHOLD", "0.175")
    assert explain_demo("D3", "EU_CPNP")["cached"] is False
    assert explain_demo("D3", "EU_CPNP")["cached"] is True
    monkeypatch.setenv("AISTREAM_FAIL_THRESHOLD", "0.3")
    assert explain_demo("D3", "EU_CPNP")["cached"] is False
    monkeypatch.setenv("AGENTSTREAM_KB_VERSION", "2")  # 지식베이스를 다시 올리면 새로 만든다
    assert explain_demo("D3", "EU_CPNP")["cached"] is False
    monkeypatch.setenv("AISTREAM_MODEL_VERSION", "v6")  # 같은 주소에 새 모델 버전
    assert explain_demo("D3", "EU_CPNP")["cached"] is False


def test_tag_from_body_with_underscores():
    ev = _ndjson({"event": "tool.completed", "artifact": {"documents": [
        {"reference": "f.md", "document": "# 기간·비용·유\n\n합업소 확인] ... [KR_CFS_EXPORT 대한화장품협회", "evidence": {"section_title": "기간·비용·유"}},
        {"reference": "f.md", "document": "- [EUCPNP] 서명된 CPSR 없음", "evidence": {"section_title": "조건"}}]}},
        {"event": "assistant.delta", "content": "답"}, {"event": "turn.completed"})
    tags = [d["tag"] for d in llm_client.parse_stream(ev.splitlines())["docs"]]
    assert tags == ["KRCFSEXPORT", "EUCPNP"]


def test_kb_every_line_tagged():
    from certcheck.data import DATA, load_cards
    from certcheck.kb_export import card_doc
    for c in load_cards(DATA / "certs"):
        tag = "[" + llm_client.kb_tag(c["id"])
        body = [x for x in card_doc(c).splitlines() if x.startswith("- ")]
        assert body and all(x.startswith("- " + tag) for x in body), c["id"]
