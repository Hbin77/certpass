"""AIStream 모델 호출부: 특징 열 순서·응답 해석·미설정 시 동작."""
import json
import threading
from datetime import date
from http.server import BaseHTTPRequestHandler, HTTPServer

from certcheck import ml_client
from certcheck.classify import evaluate
from certcheck.data import DATA, load_attributes, load_cards, load_reg_index

CLASSES = ["COND", "FAIL", "NOT_APPLICABLE", "PASS"]


def _demo():
    doc = json.loads((DATA / "public/products/demo_products.json").read_text(encoding="utf-8"))
    cards = [c for c in load_cards(DATA / "certs") if c.get("kind") != "company_certification"][:6]
    reg, attrs = load_reg_index(), load_attributes()
    p = doc["products"][2]
    vs = [evaluate(c, p, doc["company"], reg, attrs, date(2026, 11, 7)) for c in cards]
    return vs, {c["id"]: c for c in cards}, p, reg


def test_parse_formats():
    assert [r["label"] for r in ml_client.parse_predictions('{"predictions": ["FAIL", "COND"]}', 2, CLASSES)] == ["FAIL", "COND"]
    r = ml_client.parse_predictions('{"predictions": [[0.1, 0.9, 0, 0]]}', 1, CLASSES)[0]
    assert r["label"] == "FAIL" and r["status"] == "불가" and r["proba"]["FAIL"] == 0.9
    assert ml_client.parse_predictions("[1, 3]", 2, CLASSES)[1]["label"] == "PASS"


def test_feature_rows_match_training_columns():
    vs, cards, p, reg = _demo()
    cols = ml_client.columns()
    rows = ml_client.feature_rows(vs, cards, p, reg, cols)
    assert len(rows) == len(vs) and all(len(r) == len(cols) for r in rows)
    for v, r in zip(vs, rows):
        row = dict(zip(cols, r))
        assert row[f"cert_{v.cert_id}"] == 1 and row[f"rule_{ml_client.CODE[v.status]}"] == 1


def test_disabled_without_url(monkeypatch):
    monkeypatch.delenv("AISTREAM_URL", raising=False)
    vs, cards, p, reg = _demo()
    assert ml_client.predict(vs, cards, p, reg)["enabled"] is False


def test_predict_against_fake_server(monkeypatch):
    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            n = len(json.loads(self.rfile.read(int(self.headers["Content-Length"])))["dataframe_split"]["data"])
            body = json.dumps({"predictions": [[0.02, 0.95, 0.01, 0.02]] * n}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setenv("AISTREAM_URL", f"http://127.0.0.1:{srv.server_port}/invocations")
    vs, cards, p, reg = _demo()
    out = ml_client.predict(vs, cards, p, reg)
    srv.shutdown()
    assert out["ok"] and len(out["results"]) == len(vs)
    assert out["n_alerts"] == sum(v.status != "불가" for v in vs)


def test_calibration_script_against_fake_server(monkeypatch, tmp_path):
    """서빙 모델 평가 스크립트가 test.csv 형식을 끝까지 처리하는지(가짜 서버: 항상 COND 0.7 / FAIL 0.3)."""
    import csv
    import subprocess
    import sys

    cols = ml_client.columns()
    (tmp_path / "feature_columns.json").write_text(json.dumps(cols), encoding="utf-8")
    with (tmp_path / "test.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols + ["label"])
        for lab, rule in (("FAIL", "rule_COND"), ("COND", "rule_COND"), ("FAIL", "rule_FAIL")):
            w.writerow([1 if c == rule else 0 for c in cols] + [lab])

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            n = len(json.loads(self.rfile.read(int(self.headers["Content-Length"])))["dataframe_split"]["data"])
            body = json.dumps({"predictions": [[0.7, 0.3, 0.0, 0.0]] * n}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    env = {**__import__("os").environ, "AISTREAM_URL": f"http://127.0.0.1:{srv.server_port}/invocations"}
    out = subprocess.run([sys.executable, "-m", "certcheck.calibrate_aistream", str(tmp_path)], capture_output=True, text=True, env=env)
    srv.shutdown()
    assert out.returncode == 0, out.stderr
    res = json.loads(out.stdout)
    assert res["n_test"] == 3 and res["hidden_fail_in_test"] == 1
    point = next(p for p in res["hidden_fail_alert"] if p["thr"] == 0.3)
    assert point["숨은불가_재현율"] == 1.0 and point["경고수"] == 2


def test_parse_aistream_train_output_format():
    body = '{"predictions": [{"label": "FAIL", "proba_COND": 0.1, "proba_FAIL": 0.8, "proba_NOT_APPLICABLE": 0.05, "proba_PASS": 0.05}]}'
    r = ml_client.parse_predictions(body, 1, CLASSES)[0]
    assert r["label"] == "FAIL" and r["proba"]["FAIL"] == 0.8


def test_image_serving_mode_against_fake_server(monkeypatch):
    """AIStream CNN 서빙(/infer)처럼 이미지 한 장씩 받아 클래스 확률을 돌려주는 가짜 서버."""
    seen = []

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            seen.append(b"\x89PNG" in body and "multipart/form-data" in self.headers["Content-Type"])
            out = json.dumps({"predicted_class": "FAIL", "confidence": 0.7,
                              "probabilities": {"COND": 0.2, "FAIL": 0.7, "NOT_APPLICABLE": 0.05, "PASS": 0.05}}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(out)

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setenv("AISTREAM_URL", f"http://127.0.0.1:{srv.server_port}/infer")
    monkeypatch.setenv("AISTREAM_FORMAT", "image")
    vs, cards, p, reg = _demo()
    out = ml_client.predict(vs, cards, p, reg)
    srv.shutdown()
    assert out["ok"] and all(seen) and len(seen) == len(vs)
    assert all(r["proba"]["FAIL"] == 0.7 for r in out["results"].values())
