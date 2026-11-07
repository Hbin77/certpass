"""서류 초안 6종 생성·검증 스크립트 (pytest 없이 실행).

    .venv/bin/python -m tests.test_docs_gen        # 프로젝트 루트에서 실행

- 제품: data/public/products/demo_products.json(D1~D4) + 함량 일부 미상 사본(D3P), 카드: tests/fixtures/certs
  (환경변수 CERTCHECK_CERTS로 변경)
- 결과: out/public/docs_test/ 에 저장한 뒤 python-docx·openpyxl로 다시 열어 내용을 검증한다.
- 끝으로 API(/api/docs/types, /api/docs/{doc_type})를 ASGI로 직접 호출해 응답을 확인한다(httpx 불필요).
실패가 하나라도 있으면 종료 코드 1.
"""
from __future__ import annotations

import asyncio
import io
import json
import os
import re
import sys
import zipfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CERTS = Path(os.environ.get("CERTCHECK_CERTS") or ROOT / "tests" / "fixtures" / "certs")
OUT = ROOT / "out" / "public" / "docs_test"

from docx import Document  # noqa: E402
from openpyxl import load_workbook  # noqa: E402

from certcheck.classify import evaluate, evaluate_company  # noqa: E402
from certcheck.data import DATA, load_attributes, load_cards, load_reg_index  # noqa: E402
from certcheck.docs_gen import DISCLAIMER, DOC_TYPES, MIME, OWNERS, TBC, XL_STATUS, _fmt_pct, generate  # noqa: E402

# 테스트 카드에는 일반지원 목록 번호가 없어 지원사업 요약의 '일반지원' 경로를 보려고 메모리에서만 붙인다(583종 목록 번호).
TEST_GENERAL_NO = {"VEGAN_SOCIETY": 572, "CN_NMPA_SPECIAL": 349}
BAND = "1% 이하 성분 — 순서 무관"
FAILS: list[str] = []


def check(cond: bool, msg: str) -> None:
    if not cond:
        FAILS.append(msg)


def docx_read(data: bytes) -> tuple[str, list]:
    """(본문·표·머리글 전체 텍스트, 표 목록)."""
    doc = Document(io.BytesIO(data))
    parts = [p.text for p in doc.paragraphs]
    for t in doc.tables:
        parts += [c.text for row in t.rows for c in row.cells]
    for s in doc.sections:
        parts += [p.text for p in s.header.paragraphs]
    return "\n".join(parts), doc.tables


def footnote_count(data: bytes) -> int:
    names = zipfile.ZipFile(io.BytesIO(data)).namelist()
    if "word/footnotes.xml" not in names:
        return 0
    xml = zipfile.ZipFile(io.BytesIO(data)).read("word/footnotes.xml").decode("utf-8")
    return len(re.findall(r'<w:footnote w:id="[1-9]\d*"', xml))


def xlsx_read(data: bytes) -> dict[str, list[list]]:
    wb = load_workbook(io.BytesIO(data))
    return {ws.title: [list(r) for r in ws.iter_rows(values_only=True)] for ws in wb.worksheets}


def table_rows(sheet: list[list], header_first: str) -> tuple[list, list[list]]:
    """머리행(첫 칸 값이 header_first)과 그 아래 빈 행 전까지의 표."""
    i = next(n for n, r in enumerate(sheet) if r and r[0] == header_first)
    rows = []
    for r in sheet[i + 1:]:
        if not any(v not in (None, "") for v in r):
            break
        rows.append(r)
    return sheet[i], rows


def pct_strings(p: dict) -> list[str]:
    """배합비 노출 검사용 함량 표기(서류 표기와 판정 문구 표기). 정수 값은 쪽·항목 번호와 겹쳐 뺀다."""
    out = set()
    for i in p.get("ingredients", []):
        if i.get("pct") is not None and float(i["pct"]) != int(float(i["pct"])):
            out |= {_fmt_pct(float(i["pct"])), str(i["pct"])}
    return sorted(out)


def leaks(p: dict, text: str) -> list[str]:
    return [s for s in pct_strings(p) if re.search(r"(?<![\d.])" + re.escape(s) + r"(?!\d)", text)]


def verdicts_for(p: dict, company: dict, cards: list[dict], reg, attrs) -> list[dict]:
    out = []
    for c in cards:
        v = evaluate_company(c, company) if c.get("kind") == "company_certification" else evaluate(c, p, company, reg, attrs)
        d = v.to_dict()
        d.pop("features", None)
        out.append(d)
    return out


def check_doc(doc_type: str, data: bytes, p: dict, verdicts: list[dict], cards: list[dict], include_pct: bool) -> None:
    tag = f"{p['id']}/{doc_type}{'' if include_pct else '(nopct)'}"
    today = date.today().isoformat()
    pct_hidden = not (include_pct and DOC_TYPES[doc_type]["pct"])
    if DOC_TYPES[doc_type]["format"] == "docx":
        text, tables = docx_read(data)
        flat = text
    else:
        sheets = xlsx_read(data)
        flat = "\n".join(str(v) for rows in sheets.values() for r in rows for v in r if v is not None)
        for name, rows in sheets.items():
            check(any(DISCLAIMER in str(v) for r in rows[:3] for v in r), f"{tag}: '{name}' 시트 첫머리에 고지문 없음")
    check(DISCLAIMER in flat, f"{tag}: 고지문 없음")
    check("생성일" in flat and today in flat, f"{tag}: 생성일 없음")
    if pct_hidden:
        leaked = leaks(p, flat)
        check(not leaked, f"{tag}: 함량이 들어가면 안 되는데 노출됨 {leaked[:3]}")

    ings = p.get("ingredients", [])
    if doc_type == "inci_list":
        table = tables[2]  # 0 고지문, 1 제품 정보, 2 전성분
        header = [c.text for c in table.rows[0].cells]
        names = [r.cells[1].text for r in table.rows[1:] if r.cells[0].text.isdigit()]
        check(len(names) == len(ings), f"{tag}: 성분 수 불일치 {len(names)} != {len(ings)}")
        has_pct = all(i.get("pct") is not None for i in ings if i.get("role") != "allergen_from_fragrance")
        show_pct = include_pct and any(i.get("pct") is not None for i in ings)
        if has_pct:
            known = sorted((i for i in ings if i.get("pct") is not None), key=lambda i: -i["pct"])
            expect = [i["inci"] for i in known] + [i["inci"] for i in ings if i.get("pct") is None]
            check(names == expect, f"{tag}: 함량 내림차순이 아님")
            check((BAND in text) == include_pct, f"{tag}: 1% 구분선 표시 오류")
        else:  # 함량을 모르거나 일부만 알면 자리를 추측하지 않고 입력 순서
            check(names == [i["inci"] for i in ings], f"{tag}: 함량 미상인데 입력 순서가 아님")
            check("입력 순서" in text and BAND not in text, f"{tag}: 입력 순서 안내 없음 또는 1% 구분선 오표시")
        check(any("함량" in h for h in header) == show_pct, f"{tag}: 함량 열 표시 오류")
        if show_pct:
            notes = {r.cells[1].text: r.cells[-1].text for r in table.rows[1:] if r.cells[0].text.isdigit()}
            for i in ings:
                if i.get("pct") is None:
                    check("함량 미상" in notes.get(i["inci"], ""), f"{tag}: 함량 미상 표시 누락 {i['inci']}")
        for i in ings:
            if i.get("kr"):
                check(i["kr"] in text, f"{tag}: 국문명 누락 {i['kr']}")
        allergens = [i["inci"] for i in ings if i.get("role") == "allergen_from_fragrance"]
        rows = {r.cells[1].text: r.cells[-1].text for r in table.rows[1:] if r.cells[0].text.isdigit()}
        for a in allergens:
            check("알레르기" in rows.get(a, ""), f"{tag}: 알레르기 성분 표시 누락 {a}")
        check(footnote_count(data) >= 1 + len(allergens), f"{tag}: 근거 각주 부족({footnote_count(data)})")
    elif doc_type == "label_draft":
        for h in ("1. 유럽연합 (EU)", "2. 영국 (UK", "3. 미국 (US)"):
            check(h in text, f"{tag}: 시장 섹션 없음 {h}")
        for item in ("제품명", "기능", "용량", "전성분", "책임자", "로트", "사용기한/PAO", "원산국", "주의문구", "미국 내 연락처"):
            check(item in text, f"{tag}: 필수 표시 항목 없음 {item}")
        check(TBC in text and "Made in Korea" in text and "Ingredients:" in text, f"{tag}: 자리표시·원산국·전성분 누락")
        if any(i.get("inci") == "Water" for i in ings):
            check("Aqua" in text and "Water" in text, f"{tag}: 시장별 성분명(Aqua/Water) 변환 없음")
    elif doc_type in ("cpnp_sheet", "mocra_sheet"):
        main = list(sheets.values())[0]
        _, rows = table_rows(main, "No")
        check(len(rows) == (12 if doc_type == "cpnp_sheet" else 7), f"{tag}: 항목 수 {len(rows)}")
        check(all(r[4] in XL_STATUS for r in rows), f"{tag}: 상태 값 오류 {[r[4] for r in rows]}")
        check(all(r[2] and r[3] for r in rows), f"{tag}: 자동 채움 값·출처가 빈 칸")
        if doc_type == "cpnp_sheet":
            head, frows = table_rows(sheets["처방 (Formulation)"], "No")
            show = include_pct and any(i.get("pct") is not None for i in ings)
            check(any("함량" in str(h) for h in head) == show, f"{tag}: 처방 시트 함량 열 표시 오류")
            if show and all(i.get("pct") is not None for i in ings):
                total = frows[-1][4]
                check(abs(total - sum(i["pct"] for i in ings)) < 1e-6, f"{tag}: 합계 오류 {total}")
        else:
            _, irows = table_rows(sheets["전성분 (Ingredients)"], "No")
            check(len(irows) == len(ings), f"{tag}: 전성분 시트 성분 수 불일치")
    elif doc_type == "gap_checklist":
        i1, i2 = text.find("1. 여러 인증에 공통되는 조치"), text.find("2. 인증별 부족 사항")
        check(0 <= i1 < i2, f"{tag}: 공통 조치가 인증별 목록보다 먼저 나오지 않음")
        for v in verdicts:
            if any(f["level"] in ("fail", "cond") for f in v["findings"]):
                check(f"({v['cert_id']}) —" in text, f"{tag}: 인증별 섹션 없음 {v['cert_id']}")
        owners = {r.cells[4].text for t in tables[3:] for r in t.rows[1:] if len(r.cells) == 6}
        check(owners <= set(OWNERS), f"{tag}: 담당 값 오류 {owners - set(OWNERS)}")
        check("□" in text, f"{tag}: 체크박스 없음")
        pct_in_msgs = any(re.search(re.escape(s) + r"\s*%", f["message"]) for v in verdicts for f in v["findings"]
                          if f["level"] in ("fail", "cond") for s in pct_strings(p))
        if pct_in_msgs:
            check("(함량 비공개)" in text, f"{tag}: 판정 문구 속 함량을 가리지 않음")
    elif doc_type == "support_program":
        for s in ("50~70%", "최대 1억", "1.5억", "2026-10-14", "2026-11-13", "2026-11-30", "□"):
            check(s in text, f"{tag}: 지원사업 필수 문구 없음 {s}")
        meta = {c["id"]: c for c in cards}
        for v in verdicts:
            m = meta.get(v["cert_id"], {})
            if m.get("strategic_kr") is True or m.get("general_kr_no"):
                check(f"({v['cert_id']})" in text, f"{tag}: 지원 대상 인증 누락 {v['cert_id']}")
            if m.get("general_kr_no"):
                check(f"No.{m['general_kr_no']}" in text, f"{tag}: 일반지원 목록 번호 누락 {v['cert_id']}")


# ---------------------------------------------------------------- API (ASGI 직접 호출)
async def _asgi(app, method: str, path: str, body=None) -> tuple[int, dict, bytes]:
    payload = json.dumps(body).encode() if body is not None else b""
    messages, sent = [], False

    async def receive():
        nonlocal sent
        if sent:
            return {"type": "http.disconnect"}
        sent = True
        return {"type": "http.request", "body": payload, "more_body": False}

    async def send(message):
        messages.append(message)

    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": method, "scheme": "http",
             "path": path, "raw_path": path.encode(), "root_path": "", "query_string": b"",
             "headers": [(b"host", b"test"), (b"content-type", b"application/json"),
                         (b"content-length", str(len(payload)).encode())],
             "client": ("127.0.0.1", 1), "server": ("test", 80)}
    await app(scope, receive, send)
    start = next(m for m in messages if m["type"] == "http.response.start")
    headers = {k.decode().lower(): v.decode() for k, v in start["headers"]}
    return start["status"], headers, b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")


def check_api(demo: dict, cards: list[dict]) -> int:
    from certcheck.app import app

    calls = 0

    def call(method: str, path: str, body=None):
        nonlocal calls
        calls += 1
        return asyncio.run(_asgi(app, method, path, body))

    paths = app.openapi()["paths"]  # FastAPI 버전에 따라 include_router가 지연 등록되므로 OpenAPI 경로로 확인
    check("/api/docs/types" in paths and "/api/docs/{doc_type}" in paths, "API: 서류 라우터가 app에 등록되지 않음")
    co = demo["company"]
    p3 = next(p for p in demo["products"] if p["id"] == "D3")
    top = _fmt_pct(max(i["pct"] for i in p3["ingredients"] if i.get("pct") is not None))
    status, _, body = call("GET", "/api/docs/types")
    check(status == 200 and [t["doc_type"] for t in json.loads(body)] == list(DOC_TYPES), f"API types: {status}")

    status, headers, body = call("POST", "/api/docs/inci_list", {"product": p3, "company": co})
    check(status == 200 and headers.get("content-type", "").startswith(MIME["docx"]), f"API inci_list: {status}")
    check(headers.get("content-disposition", "").startswith('attachment; filename="D3_inci_list_'),
          f"API inci_list: Content-Disposition {headers.get('content-disposition')}")
    check(status == 200 and top in docx_read(body)[0], "API inci_list: 함량 누락(include_pct 기본값 true)")
    status, _, body = call("POST", "/api/docs/inci_list", {"product": p3, "company": co, "include_pct": False})
    check(status == 200 and not leaks(p3, docx_read(body)[0]), f"API inci_list include_pct=false: {status} 또는 함량 노출")
    status, _, body = call("POST", "/api/docs/cpnp_sheet", {"product": p3, "company": co, "include_pct": False})
    head = table_rows(xlsx_read(body)["처방 (Formulation)"], "No")[0] if status == 200 else ["함량"]
    check(not any("함량" in str(h) for h in head), f"API cpnp_sheet include_pct=false: {status} 또는 함량 열 있음")

    # verdicts 없이 보내면 그 자리에서 판정한다(cert_ids로 범위 지정 가능)
    status, _, body = call("POST", "/api/docs/support_program", {"product": p3, "company": co})
    check(status == 200 and "(EU_CPNP)" in docx_read(body)[0], f"API support_program(판정 자동 실행): {status}")
    only = next((c["id"] for c in cards if c.get("kind") != "company_certification"), None)
    status, _, body = call("POST", "/api/docs/gap_checklist", {"product": p3, "company": co, "cert_ids": [only]})
    summary = [r.cells[0].text for r in docx_read(body)[1][1].rows[1:]] if status == 200 else []  # 표 1 = 판정 요약
    check(status == 200 and len(summary) == 1 and f"({only})" in summary[0],
          f"API gap_checklist cert_ids: {status}, 판정 요약 {summary[:3]}")

    # 파일명 헤더 주입·잘못된 입력
    status, headers, _ = call("POST", "/api/docs/mocra_sheet", {"product": {**p3, "id": 'a"\r\nX-Evil: 1'}, "company": co})
    cd = headers.get("content-disposition", "")
    check(status == 200 and "\r" not in cd and "\n" not in cd and "x-evil" not in headers, f"API 헤더 주입 방어: {cd!r}")
    for body, why in (({"product": {"name_kr": "성분 없음"}}, "제품에 ingredients 없음"),
                      ({"product": p3, "company": {"local_entities": "EU"}}, "local_entities가 문자열"),
                      ({"product": p3, "company": {"company_certs": ["venture"]}}, "company_certs가 목록"),
                      ({"product": p3, "verdicts": [{"cert_id": "X", "findings": [{"code": 5}]}]}, "finding code가 숫자")):
        status, _, _ = call("POST", "/api/docs/gap_checklist", body)
        check(status == 422, f"API 잘못된 입력({why}): {status} (422 기대)")
    status, _, _ = call("POST", "/api/docs/unknown", {"product": p3})
    check(status == 404, f"API 알 수 없는 서류: {status} (404 기대)")
    return calls


def main() -> int:
    # API 경로(app.resources)도 같은 카드 폴더를 쓰게 한다. import 시점에 두면 pytest가 이 파일을 수집할 때 다른 테스트까지 바뀐다
    os.environ["CERTCHECK_CERTS"] = str(CERTS)
    OUT.mkdir(parents=True, exist_ok=True)
    for old in list(OUT.glob("*.docx")) + list(OUT.glob("*.xlsx")):
        old.unlink()
    demo = json.loads((DATA / "public" / "products" / "demo_products.json").read_text(encoding="utf-8"))
    cards = load_cards(CERTS)
    for c in cards:
        if c["id"] in TEST_GENERAL_NO and "general_kr_no" not in c:
            c["general_kr_no"] = TEST_GENERAL_NO[c["id"]]
    reg, attrs = load_reg_index(), load_attributes()
    # 함량이 일부만 있는 경우(주성분 하나가 미상)를 보려고 D3를 바꾼 사본을 하나 더 만든다
    d3 = next(p for p in demo["products"] if p["id"] == "D3")
    partial = {**d3, "id": "D3P", "name_kr": d3["name_kr"] + "(함량 일부 미상)",
               "ingredients": [{**i, "pct": None} if i["inci"] == "Glycerin" else i for i in d3["ingredients"]]}
    products = demo["products"] + [partial]
    print(f"카드 {len(cards)}장({CERTS}) · 제품 {len(products)}개 · 출력 {OUT}")
    made = []
    for p in products:
        verdicts = verdicts_for(p, demo["company"], cards, reg, attrs)
        jobs = [(t, True) for t in DOC_TYPES] + [(t, False) for t in DOC_TYPES if DOC_TYPES[t]["pct"]]
        for doc_type, include_pct in jobs:
            data, name, mime = generate(doc_type, p, verdicts, demo["company"], cards=cards, include_pct=include_pct)
            check(mime == MIME[DOC_TYPES[doc_type]["format"]] and name.endswith(DOC_TYPES[doc_type]["format"]),
                  f"{p['id']}/{doc_type}: 파일명·MIME 오류 {name} {mime}")
            (OUT / name).write_bytes(data)
            try:
                check_doc(doc_type, data, p, verdicts, cards, include_pct)
            except Exception as e:  # 파일이 안 열리거나 구조가 예상과 다르면 실패로 기록
                FAILS.append(f"{p['id']}/{doc_type}: 다시 열기·검증 실패 {type(e).__name__}: {e}")
            made.append((name, len(data)))
    for name, size in made:
        print(f"  {name:45s} {size:>7,d} B")
    n_api = check_api(demo, cards)
    if FAILS:
        print(f"\n실패 {len(FAILS)}건:")
        for f in FAILS:
            print("  -", f)
        return 1
    print(f"\n통과: 서류 {len(made)}개 생성·재열기 검증, API {n_api}건")
    return 0


if __name__ == "__main__":
    sys.exit(main())
