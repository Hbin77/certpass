"""certcheck API 서버 (FastAPI).

실행: 로컬은 uvicorn certcheck.app:app, 대회 서버는 CERTCHECK_BASE=/i/<토큰> uvicorn certcheck.app:asgi (아래 접두사 마운트 참고)
- 공개 URL에는 data/public의 가공 데이터만 노출한다(출제서 공개 범위 규칙).
- 실데이터(data/private)는 CERTCHECK_PRIVATE=1 일 때만 읽고, 응답에 배합비를 싣지 않는다.
"""
from __future__ import annotations

import json
import os
import urllib.error
from datetime import date
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.utils import is_body_allowed_for_status_code
from pydantic import BaseModel, Field
from starlette.datastructures import MutableHeaders
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import STATUS_ORDER
from . import llm_client, ml_client, ocr_client
from .names import convert_korean_names
from .classify import evaluate, evaluate_company, gap_type
from .data import DATA, load_attributes, load_cards, load_reg_index
from .risk import near_matches
from .schemas import CertIds, CompanyIn, Product, Short

MAX_BODY_BYTES = 1024 * 1024  # 요청 본문 상한 1 MiB(성분 500개 제품도 수십 KB)
OCR_MAX_BYTES = 8 * 1024 * 1024  # 포장 사진(/api/ocr)만 8 MiB. 화면이 긴 변 2400px JPEG로 줄여 보내므로 보통 1~2 MB
OCR_TYPES = {"image/jpeg": b"\xff\xd8", "image/png": b"\x89PNG", "image/webp": b"RIFF"}  # 형식별 파일 첫 바이트
# CSP·X-Frame-Options는 넣지 않는다: 화면을 깨거나 대회 플랫폼의 iframe 임베드를 막을 수 있다.
SECURITY_HEADERS = {"X-Content-Type-Options": "nosniff", "Referrer-Policy": "same-origin"}


class BodyTooLarge(HTTPException):
    def __init__(self) -> None:
        super().__init__(413, f"요청 본문이 너무 큽니다(최대 {MAX_BODY_BYTES // 1024} KB).")


class LimitBodySize:
    """본문이 max_bytes를 넘는 요청을 413으로 거절하는 ASGI 미들웨어.
    Content-Length가 크면 본문을 읽지 않고 바로 거절하고, 길이 없이 오는 본문(chunked)은 읽는 동안 세다가 넘는 순간 멈춘다."""

    def __init__(self, app, max_bytes: int = MAX_BODY_BYTES) -> None:
        self.app, self.max_bytes = app, max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        limit = OCR_MAX_BYTES if scope["path"].endswith("/api/ocr") else self.max_bytes
        length = next((v for k, v in scope["headers"] if k == b"content-length"), b"")
        if length.isdigit() and int(length) > limit:
            return await JSONResponse({"detail": BodyTooLarge().detail}, status_code=413)(scope, receive, send)
        received = 0

        async def receive_limited():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise BodyTooLarge()  # 본문을 읽던 FastAPI가 HTTPException을 그대로 413 응답으로 바꾼다
            return message

        await self.app(scope, receive_limited, send)


class SecurityHeaders:
    """모든 응답에 SECURITY_HEADERS를 단다. 이미 있으면 덮어써서 두 번 거쳐도 한 줄씩만 남는다."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for k, v in SECURITY_HEADERS.items():
                    headers[k] = v
            await send(message)

        await self.app(scope, receive, send_with_headers)


class SafeJSONResponse(JSONResponse):
    """입력에 짝 없는 서로게이트(예: "\\ud800")가 섞여 응답(판정 문구·422의 input)으로 되돌아가도 500이 나지 않게,
    UTF-8로 못 적는 그 글자만 \\uXXXX로 적는다. json.dumps가 역슬래시를 늘 두 번 적으므로 결과는 유효한 JSON이다."""

    def render(self, content) -> bytes:
        return json.dumps(content, ensure_ascii=False, allow_nan=False, indent=None,
                          separators=(",", ":")).encode("utf-8", "backslashreplace")


async def _http_error(request, exc: StarletteHTTPException):  # FastAPI 기본 처리기와 같고 응답 클래스만 다르다
    headers = getattr(exc, "headers", None)
    if not is_body_allowed_for_status_code(exc.status_code):
        return Response(status_code=exc.status_code, headers=headers)
    return SafeJSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=headers)


async def _validation_error(request, exc: RequestValidationError):
    return SafeJSONResponse({"detail": jsonable_encoder(exc.errors())}, status_code=422)


# 공개 URL이라 API 문서(/docs·/redoc·/openapi.json)는 열지 않는다. app.openapi()는 코드에서 그대로 쓸 수 있다.
app = FastAPI(title="certcheck — 화장품 수출 인증 사전 적합성 판정", version="0.1.0",
              docs_url=None, redoc_url=None, openapi_url=None, default_response_class=SafeJSONResponse,
              exception_handlers={StarletteHTTPException: _http_error, RequestValidationError: _validation_error})
# 나중에 붙인 미들웨어가 바깥: 보안 헤더 → CORS → 본문 상한 순으로 감싸 413 응답에도 CORS·보안 헤더가 붙는다
app.add_middleware(LimitBodySize)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET", "POST"], allow_headers=["*"])
app.add_middleware(SecurityHeaders)


@lru_cache(maxsize=1)
def resources():
    folder = Path(os.environ.get("CERTCHECK_CERTS", str(DATA / "certs")))
    return load_cards(folder), load_reg_index(), load_attributes()


def demo_products() -> dict:
    return json.loads((DATA / "public" / "products" / "demo_products.json").read_text(encoding="utf-8"))


class EvalRequest(BaseModel):
    product: Product
    company: CompanyIn = Field(default_factory=CompanyIn)
    cert_ids: CertIds | None = None
    eval_date: date | None = None


def select_cards(cards: list[dict], cert_ids: list[str] | None) -> tuple[list[dict], list[str]]:
    """cert_ids로 판정할 카드를 고른다(없거나 비면 전체). 반환 (카드, 모르는 id). 하나도 모르면 422."""
    if not cert_ids:
        return cards, []
    wanted = dict.fromkeys(cert_ids)  # 순서 유지·중복 제거
    known = {c["id"] for c in cards}
    unknown = [x for x in wanted if x not in known]
    if len(unknown) == len(wanted):
        raise HTTPException(422, f"알 수 없는 인증 id입니다: {', '.join(unknown)} (목록: api/certs)")
    return [c for c in cards if c["id"] in wanted], unknown


@app.get("/api/health")
def health():
    cards, reg, attrs = resources()
    return {"ok": True, "cards": len(cards), "reg_jurisdictions": sorted(reg.jurisdictions), "attributes": len(attrs),
            "ml_model": bool(os.environ.get("AISTREAM_URL")), "ocr_model": ocr_client.enabled(),
            "llm_model": llm_client.enabled()}


UNOFFICIAL = ("인증기관의 공식 심사가 아니라 공개된 기준을 참고한 예비 점검입니다. "
              "인증기관 기준 원문·표는 게재하지 않고 아래 근거 문서 링크로만 안내합니다.")


# 관할 → 관세청 국가 코드(2025 화장품 HS 3304 수출 실적, data.go.kr 관세청 품목별 국가별 수출입실적)
MARKET_CODES = {"EU": ["DE", "FR", "NL", "IT", "ES", "PL", "AT", "BE", "SE"], "EAEU": ["RU", "KZ"], "UK": ["GB"], "AE": ["AE"],
                "ASEAN": ["VN", "TH", "ID", "MY", "PH", "SG", "KH", "MM"]}


@lru_cache(maxsize=1)
def export_share() -> dict[str, float]:
    path = DATA / "kr" / "관세청_HS3304_2025_국가별수출.csv"
    if not path.exists():
        return {}
    import csv
    rows = list(csv.DictReader(path.open(encoding="utf-8-sig")))
    total = sum(int(r["export_usd_2025"]) for r in rows) or 1
    return {r["country"]: int(r["export_usd_2025"]) / total for r in rows}


def market_share(jurisdiction: str | None) -> float | None:
    codes = MARKET_CODES.get(jurisdiction or "", [jurisdiction] if jurisdiction else [])
    share = sum(export_share().get(c, 0) for c in codes)
    return round(share, 4) if share else None


@app.get("/api/certs")
def certs():
    cards, _, _ = resources()
    keys = ("id", "name_ko", "name_en", "jurisdiction", "kind", "strategic_kr", "support_rate")
    out = []
    for c in cards:
        d = {k: c.get(k) for k in keys}
        # 출처를 구체적으로: 근거 문서 이름·링크·근거 수준(로컬 원문 경로는 빼고 공개 링크만)
        d["evidence"] = [{"title": e.get("title") or e["url"], "url": e["url"], "level": e.get("level")}
                         for e in c.get("evidence") or [] if str((e or {}).get("url", "")).startswith(("https://", "http://"))]
        if c.get("kind") in ("voluntary_certification", "marketing_label"):
            d["unofficial_notice"] = UNOFFICIAL
        d["export_share_2025"] = market_share(c.get("jurisdiction"))  # 한국 화장품 수출에서 이 시장 비중(추천 근거)
        out.append(d)
    return out


@app.get("/api/demo-products")
def demo():
    return demo_products()


@app.post("/api/evaluate")
def run(req: EvalRequest):
    cards, reg, attrs = resources()
    if not cards:
        raise HTTPException(503, "인증 요건 카드가 아직 없습니다")
    sel, unknown = select_cards(cards, req.cert_ids)
    p = req.product.model_dump()
    names = convert_korean_names(p["ingredients"])
    company = req.company.model_dump(exclude_unset=True)  # 엔진은 dict를 읽는다. 보낸 키만 넘겨 예전 입력과 같은 모양
    verdicts = [evaluate_company(c, company) if c.get("kind") == "company_certification"
                else evaluate(c, p, company, reg, attrs, req.eval_date) for c in sel]
    ml = ml_client.predict(verdicts, {c["id"]: c for c in sel}, p, reg)  # AIStream 모델(미설정이면 enabled=False)
    out = []
    for v in verdicts:
        d = v.to_dict()
        d.pop("features", None)
        d["ml"] = (ml.get("results") or {}).get(v.cert_id)
        for f in d["findings"]:  # 화면의 보완 칸 분류를 엔진 규칙(GAP_TYPES) 하나로 맞춘다
            f["gap"] = gap_type(f["code"]) if f["level"] in ("fail", "cond") else None
        out.append(d)
    out.sort(key=lambda d: (STATUS_ORDER.get(d["status"], 9), d["cert_id"]))
    summary = {}
    for d in out:
        summary[d["status"]] = summary.get(d["status"], 0) + 1
    ml_info = {k: val for k, val in ml.items() if k != "results"}
    return {"product": p["name_kr"], "eval_date": (req.eval_date or date.today()).isoformat(), "summary": summary,
            "verdicts": out, "ml": ml_info, "unknown_cert_ids": unknown, "ingredient_names": names,
            "disclaimer": "예비 판정입니다. 최종 판단은 각 기관과 자격 있는 안전성 평가자가 합니다."}


class ExplainRequest(EvalRequest):
    cert_id: Short


@lru_cache(maxsize=1)
def _demo_keys() -> frozenset:
    """데모 제품(화면의 데모 버튼이 보내는 것)의 정규화된 모양. 이 제품의 설명만 캐시에 고정·파일 저장한다."""
    out = set()
    for x in demo_products()["products"]:
        prod = Product(**{k: v for k, v in x.items() if k in Product.model_fields}).model_dump()
        out.add(json.dumps(prod, sort_keys=True, ensure_ascii=False, default=str))
    return frozenset(out)


@app.post("/api/explain")
def explain(req: ExplainRequest, request: Request):
    """판정 하나의 AI 설명(AgentStream LLM+RAG)과 근거 목록. 판정은 서버가 다시 계산한다(화면이 보낸 판정 문구를 믿지 않음).
    /api/evaluate와 따로 불러 LLM이 판정 표시를 늦추지 않게 한다."""
    return _explain(req, request.client.host if request.client else None)


def _explain(req: ExplainRequest, client: str | None):
    cards, reg, attrs = resources()
    card = next((c for c in cards if c["id"] == req.cert_id), None)
    if not card:
        raise HTTPException(404, f"알 수 없는 인증 id입니다: {req.cert_id}")
    p = req.product.model_dump()
    company = req.company.model_dump(exclude_unset=True)
    verdict = (evaluate_company(card, company) if card.get("kind") == "company_certification"
               else evaluate(card, p, company, reg, attrs, req.eval_date))
    v = verdict.to_dict()
    v.pop("features", None)
    pin = json.dumps(p, sort_keys=True, ensure_ascii=False, default=str) in _demo_keys()
    return llm_client.explain(v, card, p, lambda: ai_alert(verdict, card, p, reg), client=client, pin=pin)


def ai_alert(verdict, card: dict, p: dict, reg) -> dict | None:
    """같은 판정의 AIStream 숨은 불가 경보와 오탈자 의심 성분. 경보가 없거나 ML이 꺼져·실패하면 None(설명은 그대로)."""
    if card.get("kind") == "company_certification":
        return None
    ml = ml_client.predict([verdict], {card["id"]: card}, p, reg)
    r = (ml.get("results") or {}).get(verdict.cert_id) if ml.get("ok") else None
    if not r or not r.get("hidden_fail_alert"):
        return None
    rules = (card.get("ingredient_rules") or "none").upper()
    return {"fail_proba": round(r["fail_proba"], 2), "threshold": ml.get("threshold"),
            "near": near_matches(p, reg, ml_client.PROXY.get(rules, rules))}


@app.post("/api/ocr")
async def ocr(request: Request):
    """포장 사진(본문 그대로, Content-Type image/jpeg·png·webp) → 전성분 목록과 표준 성분명 맞추기."""
    if not ocr_client.enabled():
        raise HTTPException(503, "포장 사진 인식(OCR) 서빙이 아직 연결되지 않았습니다. 전성분을 직접 입력해 주세요.")
    ctype = request.headers.get("content-type", "").split(";")[0].strip().lower()
    if ctype not in OCR_TYPES:
        raise HTTPException(415, "JPEG·PNG·WebP 사진만 올릴 수 있습니다.")
    data = await request.body()
    if not data.startswith(OCR_TYPES[ctype]):
        raise HTTPException(415, "사진 파일이 아니거나 형식이 맞지 않습니다.")
    try:
        return await run_in_threadpool(ocr_client.read_package, data, ctype)
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        raise HTTPException(502, "OCR 서빙이 응답하지 않습니다. 잠시 뒤 다시 시도하거나 전성분을 직접 입력해 주세요.") from e


@app.get("/api/evaluate-demo/{pid}")
def run_demo(pid: str):
    data = demo_products()
    p = next((x for x in data["products"] if x["id"] == pid), None)
    if not p:
        raise HTTPException(404, "데모 제품 없음")
    return run(EvalRequest(product=Product(**{k: v for k, v in p.items() if k in Product.model_fields}), company=data["company"]))


@app.get("/api/explain-demo/{pid}/{cert_id}")
def explain_demo(pid: str, cert_id: str, request: Request = None):
    data = demo_products()
    p = next((x for x in data["products"] if x["id"] == pid), None)
    if not p:
        raise HTTPException(404, "데모 제품 없음")
    if cert_id not in {c["id"] for c in resources()[0]}:  # 긴 값이 ExplainRequest 검증에서 500이 되지 않게 먼저 거른다
        raise HTTPException(404, "알 수 없는 인증 id입니다")
    product = Product(**{k: v for k, v in p.items() if k in Product.model_fields})
    client = request.client.host if request is not None and request.client else None
    return _explain(ExplainRequest(product=product, company=data["company"], cert_id=cert_id), client)


# 서류 초안 생성 라우터(별도 모듈). 모듈 파일이 없을 때만 건너뛰고, 모듈 안의 오류는 그대로 드러낸다.
try:
    from .routes_docs import router as docs_router
except ModuleNotFoundError as e:
    if e.name != f"{__package__}.routes_docs":
        raise
else:
    app.include_router(docs_router)

# 화면: web/ 폴더의 정적 파일. API 경로를 모두 등록한 뒤 마지막에 붙인다.
WEB = Path(__file__).resolve().parents[1] / "web"
if WEB.exists():
    from fastapi.staticfiles import StaticFiles

    app.mount("/", StaticFiles(directory=WEB, html=True), name="web")

# 대회 프록시는 경로 접두사(/i/<토큰>)를 그대로 넘긴다 → 접두사 아래에 앱 전체를 마운트한 진입점.
# 실행: uvicorn certcheck.app:asgi  (환경변수 CERTCHECK_BASE=/i/<토큰>, 없으면 app 그대로)
BASE = os.environ.get("CERTCHECK_BASE", "").rstrip("/")
if BASE:
    asgi = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    asgi.add_middleware(SecurityHeaders)  # 접두사 밖 응답(루트 리다이렉트·404)에도 보안 헤더
    asgi.mount(BASE, app)

    @asgi.get("/")
    def _root_redirect():
        from fastapi.responses import RedirectResponse

        return RedirectResponse(BASE + "/")
else:
    asgi = app
