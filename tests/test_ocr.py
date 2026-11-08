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


def test_ocr_retries_transient_500(monkeypatch):
    calls = {"n": 0}

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            calls["n"] += 1
            if calls["n"] == 1:  # 첫 요청은 서빙이 다시 뜨는 중이라 실패
                self.send_response(502)
                self.end_headers()
                return
            data = json.dumps({"ingredients": ["정제수"], "lines": [], "text": "", "words": []}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setenv("CERTCHECK_OCR_URL", f"http://127.0.0.1:{srv.server_port}/predict")
    monkeypatch.setattr(ocr_client, "RETRY_WAIT", (0.01, 0.01))
    status, body = call("/api/ocr", JPEG, "image/jpeg")
    srv.shutdown()
    assert status == 200 and calls["n"] == 2 and json.loads(body)["counts"]["exact"] == 1


def test_ocr_server_down_is_502(monkeypatch):
    monkeypatch.setenv("CERTCHECK_OCR_URL", "http://127.0.0.1:9/predict")
    monkeypatch.setenv("CERTCHECK_OCR_TIMEOUT", "2")
    monkeypatch.setattr(ocr_client, "RETRY_WAIT", (0.01, 0.01))
    assert call("/api/ocr", JPEG, "image/jpeg")[0] == 502


def test_dictionary_keeps_digit_commas():
    # '1,2-Hexanediol'의 쉼표는 이름의 일부다(영문명 여러 개를 잇는 쉼표와 구분)
    assert ocr_client.lookup("1,2-헥산다이올")["inci"] == "1,2-Hexanediol"
    assert ocr_client.lookup("12-Hexanediol")["kr_name"] == "1,2-헥산다이올"


def test_english_inci_lookup():
    assert ocr_client.match_name("Butyrospermum Parkii (Shea) Butter")["kr"] == "시어버터"
    assert ocr_client.match_name("glycerin")["kr"] == "글리세린"


def test_scan_lines_reads_table_rows():
    # 위탁사 전성분표: 번호·성분명·CAS·출처·기능이 한 줄에 섞여 있고 '전성분' 표기가 없다
    lines = ["FORMULA INGREDIENTS STATEMENT", "NO Ingredients Contents(%) CAS No. Source Function",
             "1 정제수 7732-18-5 ICID Solvent", "2. Glycerin 56-81-5 ICID Humectant",
             "3 마그네슘 알루미늄실리케이트 12511-31-8 ICID Viscosity", "4 Butylene Glycol 107-88-0 ICID Skin-Conditioning Agent"]
    assert [i["kr"] for i in ocr_client.scan_lines(lines)] == ["정제수", "글리세린", "마그네슘알루미늄실리케이트", "부틸렌글라이콜"]


def test_choose_prefers_section_unless_lines_find_far_more():
    section = ocr_client.match_all(["정제수", "글리세린", "부틸렌글라이콜"])
    items, method = ocr_client.choose(section, ["전성분: 정제수, 글리세린, 부틸렌글라이콜", "보습 히알루론산 함유"])
    assert method == "section" and len(items) == 3  # 광고 문구 한 단어로 바꾸지 않는다
    wrong = ocr_client.match_all(["STATEMENT"])  # 제목을 전성분 구역으로 잘못 잡은 경우
    items, method = ocr_client.choose(wrong, ["1 정제수 7732-18-5", "2 글리세린 56-81-5", "3 Butylene Glycol 107-88-0"])
    assert method == "lines" and [i["kr"] for i in items] == ["정제수", "글리세린", "부틸렌글라이콜"]


def _tilted_words(deg: float, rows: int = 6, cols: int = 5) -> list[dict]:
    """글자 줄이 deg도 기운 표처럼 단어 상자(축 정렬)를 만든다. 화면 좌표라 음수면 오른쪽으로 갈수록 올라간다."""
    import math
    out = []
    for r in range(rows):
        for c in range(cols):
            x, y = 100 + c * 130, 100 + r * 60 + c * 130 * math.tan(math.radians(deg))
            out.append({"box": [round(x), round(y), round(x + 110), round(y + 30)], "text": "w"})
    return out


def test_estimate_skew_from_word_boxes():
    assert abs(ocr_client.estimate_skew(_tilted_words(0))) < 0.3
    assert abs(ocr_client.estimate_skew(_tilted_words(-4)) + 4) < 0.5
    assert abs(ocr_client.estimate_skew(_tilted_words(3)) - 3) < 0.5
    assert ocr_client.estimate_skew(_tilted_words(0, rows=1, cols=3)) is None  # 단어 쌍이 적으면 재지 않는다


def test_photo_quality_flags_blurry_photos():
    sharp = [{"text": "w", "conf": 0.97, "box": [0, 0, 50, 16]}] * 40
    blurry = [{"text": "w", "conf": 0.5, "box": [0, 0, 30, 8]}] * 25 + sharp[:15]
    assert ocr_client.photo_quality(sharp)["blurry"] is False
    q = ocr_client.photo_quality(blurry)
    assert q["blurry"] is True and q["low_conf_share"] == 0.62 and q["text_px"] == 8
    assert ocr_client.photo_quality(blurry[:10])["blurry"] is False  # 단어가 적으면 판단하지 않는다


def _text_pdf(text: str) -> bytes:
    """글자 정보가 있는 한 쪽짜리 PDF(기본 글꼴 Helvetica, 영문)."""
    stream = f"BT /F1 12 Tf 40 760 Td ({text}) Tj ET".encode()
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
            b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out, offs = bytearray(b"%PDF-1.4\n"), []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    x = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1) + b"".join(b"%010d 00000 n \n" % o for o in offs)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, x)
    return bytes(out)


def test_pdf_with_text_layer_needs_no_ocr(monkeypatch):
    monkeypatch.setenv("CERTCHECK_OCR_URL", "http://127.0.0.1:9/predict")  # 부르면 실패하는 주소: 글자 정보 쪽은 OCR을 안 부른다
    pdf = _text_pdf("INGREDIENTS: Water, Glycerin, Butylene Glycol, Niacinamide, Xanthan Gum. Caution: for external use")
    status, body = call("/api/ocr", pdf, "application/pdf")
    assert status == 200
    r = json.loads(body)
    assert [i["kr"] for i in r["ingredients"]] == ["정제수", "글리세린", "부틸렌글라이콜", "나이아신아마이드", "잔탄검"]
    assert r["pdf"]["pages"] == [{"page": 1, "source": "text"}]


def test_pdf_image_pages_go_to_ocr(fake_ocr):
    from PIL import Image
    import io as _io
    b = _io.BytesIO()
    Image.new("L", (600, 800), 255).save(b, "PDF")  # 글자 정보 없는 그림 PDF(스캔본과 같음)
    status, body = call("/api/ocr", b.getvalue(), "application/pdf")
    assert status == 200
    r = json.loads(body)
    assert r["pdf"]["pages"][0]["source"] == "ocr" and r["counts"]["exact"] == 4
    assert fake_ocr["ctype"].startswith("multipart/form-data") and b"\xff\xd8" in fake_ocr["body"]  # 쪽 그림을 JPEG로 보냄


def test_pdf_broken_is_422(fake_ocr):
    assert call("/api/ocr", b"%PDF-1.4 broken", "application/pdf")[0] == 422
    assert call("/api/ocr", b"not a pdf", "application/pdf")[0] == 415


def _get(path: str):
    messages = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(m):
        messages.append(m)

    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "GET", "scheme": "http",
             "path": path, "raw_path": path.encode(), "root_path": "", "query_string": b"",
             "headers": [(b"host", b"t")], "client": ("127.0.0.1", 1), "server": ("t", 80)}
    asyncio.run(app(scope, receive, send))
    start = next(m for m in messages if m["type"] == "http.response.start")
    return start["status"], b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")


def _post_job(body: bytes, ctype: str):
    path = "/api/ocr"
    messages, sent = [], [False]

    async def receive():
        if sent[0]:
            return {"type": "http.disconnect"}
        sent[0] = True
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(m):
        messages.append(m)

    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "POST", "scheme": "http",
             "path": path, "raw_path": path.encode(), "root_path": "", "query_string": b"mode=job",
             "headers": [(b"host", b"t"), (b"content-type", ctype.encode()), (b"content-length", str(len(body)).encode())],
             "client": ("127.0.0.1", 1), "server": ("t", 80)}
    asyncio.run(app(scope, receive, send))
    start = next(m for m in messages if m["type"] == "http.response.start")
    return start["status"], b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")


def test_ocr_job_submit_then_poll(fake_ocr):
    import time as _t
    status, body = _post_job(JPEG, "image/jpeg")
    assert status == 202
    job = json.loads(body)
    for _ in range(100):
        st, b = _get(f"/api/ocr/jobs/{job['job']}")
        job = json.loads(b)
        if job["status"] in ("done", "error"):
            break
        _t.sleep(0.05)
    assert st == 200 and job["status"] == "done" and job["result"]["counts"]["exact"] == 4
    assert _get("/api/ocr/jobs/" + "0" * 32)[0] == 404 and _get("/api/ocr/jobs/../x")[0] == 404


def test_ocr_job_errors_and_full_queue(monkeypatch):
    import threading as _th
    import time as _t
    from certcheck import app as appmod, ocr_jobs
    monkeypatch.setenv("CERTCHECK_OCR_URL", "http://127.0.0.1:9/predict")  # 서빙 꺼짐 → 작업은 error(502)
    monkeypatch.setenv("CERTCHECK_OCR_TIMEOUT", "2")
    monkeypatch.setattr(ocr_client, "RETRY_WAIT", (0.01, 0.01))
    status, body = _post_job(JPEG, "image/jpeg")
    jid = json.loads(body)["job"]
    for _ in range(200):
        job = json.loads(_get(f"/api/ocr/jobs/{jid}")[1])
        if job["status"] in ("done", "error"):
            break
        _t.sleep(0.05)
    assert job["status"] == "error" and job["error"]["status"] == 502
    gate = _th.Event()
    jobs = ocr_jobs.Jobs(workers=1, max_queue=1)
    monkeypatch.setattr(appmod, "OCR_JOBS", jobs)
    jobs.submit(lambda: gate.wait(5) or {})  # 하나가 처리 중이면 대기열(1) 가득
    assert _post_job(JPEG, "image/jpeg")[0] == 429
    gate.set()


def test_rejoin_digit_commas_from_line_text():
    from certcheck import ocr_client as oc
    raw = ["정제수", "2-헥산다이올", "향료"]
    text = "[전성분] 정제수, 1,2-헥산다이올, 향료"
    assert oc.rejoin_digit_commas(raw, text) == ["정제수", "1,2-헥산다이올", "향료"]
    names = [i["kr"] for i in oc.match_all(raw, text)]
    assert "1,2-헥산다이올" in names


def test_label_info_reads_package_fields():
    from certcheck import ocr_client as oc
    lines = ["카멜리아 수분 크림 50mL", "CAMELLIA MOISTURE CREAM", "[전성분] 정제수, 글리세린, 1,2-헥산다이올, 향료",
             "제조업자·책임판매업자 : 데모 화장품사(가상)", "사용기한 : 제조일로부터 30개월", "Made in Korea"]
    info = oc.label_info(lines)
    assert info == {"net_content": "50 mL", "name_kr": "카멜리아 수분 크림", "name_en": "CAMELLIA MOISTURE CREAM", "manufacturer": "데모 화장품사(가상)",
                    "shelf_life": "제조일로부터 30개월", "country": "KR"}
    assert oc.label_info(["Water, Glycerin, Butylene Glycol, Niacinamide", "나이아신아마이드 2%"]) == {}
    # 기울기 보정 뒤 줄이 섞여도: 영문명에 붙은 용량은 떼고, 국문명은 용량 없는 줄에서도 찾는다
    assert oc.label_info(["카멜리아 수분 크림", "CAMELLIA MOISTURE CREAM 50mL"]) == {
        "name_kr": "카멜리아 수분 크림", "net_content": "50 mL", "name_en": "CAMELLIA MOISTURE CREAM"}
    # 옆 줄이 섞인 값은 버린다
    assert oc.label_info(["제조업자 : 책임판매업자 제조일로부터 : 데모 30개월 화장품사(가상)"]) == {}
    # 표 형식 문서: 이름 칸은 뽑지 않는다
    assert oc.label_info(["총 합계", "IGLYCERIN 글리세린 Glycerin 56-81-5 1-2 HUMECTANT"], names=False) == {}


def test_heading_fragments_and_headers_are_not_ingredients_or_names():
    from certcheck import ocr_client as oc
    names = [i["kr"] or i["raw"] for i in oc.match_all(["리모넨", "알파-터피넨", "피넨", "사용 시"])]
    assert names == ["리모넨", "알파-터피넨", "피넨"]  # 사전에 없는 성분(알파-터피넨)은 남기고 머리말 조각만 버린다
    assert oc.label_info(["제품 정보", "PRODUCT INFORMATION", "카멜리아 수분 크림"]) == {"name_kr": "카멜리아 수분 크림"}


def test_grade_mismatch_detects_other_grade_words():
    from certcheck import llm_client as lc
    assert lc.grade_mismatch("속성표가 없어 '조건부' 판정이 나왔습니다.", "불가")
    assert not lc.grade_mismatch("금지 성분이 있어 '불가' 판정입니다. 인증이 불가능합니다.", "불가")
    assert not lc.grade_mismatch("현재 제품은 통과가 어렵습니다.", "불가")
    for q in ("\u2018\u2019", "\u02bc\u02bc", "\uff07\uff07", "\u300c\u300d", "**"):  # 모델이 쓰는 여러 따옴표
        assert lc.grade_mismatch(f"확인이 필요하므로 {q[0]}조건부{q[-1]} 등급이 확정되었습니다.", "불가")
    assert not lc.grade_mismatch("인증 획득이 불가능합니다.", "불가")
    # 조건을 단 문장은 등급을 바꿔 말한 것이 아니다
    assert not lc.grade_mismatch("2027년 6월 이후에는 불가 판정으로 바뀔 수 있습니다.", "조건부")
    assert not lc.grade_mismatch("보완하지 않으면 불가 판정이 날 수 있습니다.", "조건부")
    v = {"status": "불가", "findings": [], "cert_id": "X"}
    prompt = lc.build_prompt(v, {"id": "X", "name_ko": "X"}, {"ingredients": []}, [])
    assert "'불가' 사유(재처방)를 먼저" in prompt and "다른 등급 이름은 쓰지 마세요" in prompt
