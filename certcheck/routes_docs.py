"""서류 초안 생성 API — app.py가 include_router로 붙인다.

GET  /api/docs/types       생성 가능한 서류 목록과 설명
POST /api/docs/{doc_type}  본문 {product, company, verdicts?, include_pct?, cert_ids?, eval_date?} → 파일(첨부)
- verdicts가 없으면 certcheck.classify 판정 함수 + certcheck.app.resources()의 카드로 그 자리에서 판정한다
  (cert_ids·eval_date는 /api/evaluate와 같은 뜻).
- include_pct(기본 true)는 inci_list·cpnp_sheet에만 적용된다. 다른 서류에는 함량을 넣지 않는다.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from .classify import evaluate, evaluate_company
from .docs_gen import DOC_TYPES, doc_types, generate
from .schemas import MAX_FINDINGS, MAX_FINDINGS_TOTAL, MAX_VERDICTS, CertIds, CompanyIn, Name, Product, Short, Text

router = APIRouter()


class DocProduct(Product):
    """서류용 제품: 판정 필드에 서류가 읽는 net_content를 더한다. 그 밖의 키(body_area 등)는 그대로 통과."""
    model_config = ConfigDict(extra="allow")
    net_content: Short | None = None


class FindingIn(BaseModel):
    model_config = ConfigDict(extra="allow")
    level: Short | None = None
    code: Short | None = None
    message: Text | None = None
    evidence: Text | None = None
    action: Text | None = None


class VerdictIn(BaseModel):
    """Verdict.to_dict() 모양. /api/evaluate 응답의 verdicts를 그대로 보내면 된다."""
    model_config = ConfigDict(extra="allow")
    product_id: Short | None = None
    product_name: Name | None = None
    cert_id: Short | None = None
    cert_name: Name | None = None
    jurisdiction: Short | None = None
    kind: Short | None = None
    status: Short | None = None
    confidence: float | None = None
    findings: list[FindingIn] = Field(default_factory=list, max_length=MAX_FINDINGS)


class DocRequest(BaseModel):
    product: DocProduct
    company: CompanyIn = Field(default_factory=CompanyIn)
    verdicts: Annotated[list[VerdictIn], Field(max_length=MAX_VERDICTS)] | None = None
    include_pct: bool = True
    cert_ids: CertIds | None = None
    eval_date: date | None = None


@router.get("/api/docs/types")
def list_doc_types():
    return doc_types()


@router.post("/api/docs/{doc_type}")
def make_doc(doc_type: str, req: DocRequest):
    if doc_type not in DOC_TYPES:
        raise HTTPException(404, f"알 수 없는 서류 종류: {doc_type} (가능: {', '.join(DOC_TYPES)})")
    if req.verdicts is not None:
        _limit_findings(doc_type, sum(len(v.findings) for v in req.verdicts))
    # app.py가 이 모듈을 import하므로 순환 import를 피해 호출 시점에 가져온다
    from .app import resources, select_cards

    product = req.product.model_dump()  # 판정·서류에 필요한 기본값이 채워지고, 모델에 없는 키도 그대로 남는다
    company = req.company.model_dump(exclude_unset=True)  # /api/evaluate와 같은 모양
    cards, reg, attrs = resources()
    if req.verdicts is not None:
        verdicts = [v.model_dump() for v in req.verdicts]
    else:
        verdicts = []
        for card in select_cards(cards, req.cert_ids)[0]:
            v = evaluate_company(card, company) if card.get("kind") == "company_certification" else \
                evaluate(card, product, company, reg, attrs, req.eval_date)
            d = v.to_dict()
            d.pop("features", None)
            verdicts.append(d)
        _limit_findings(doc_type, sum(len(d["findings"]) for d in verdicts))
    data, filename, mime = generate(doc_type, product, verdicts, company, cards=cards, include_pct=req.include_pct)
    return Response(content=data, media_type=mime, headers={"Content-Disposition": _attachment(filename)})


# findings마다 표 한 행을 만들어 생성 시간이 findings 수에 비례하는 서류(다른 서류는 본문 1 MiB를 채워도 1초 안)
ROW_PER_FINDING = {"gap_checklist"}


def _limit_findings(doc_type: str, n: int) -> None:
    """모델 검증 오류로 내면 본문 전체가 응답에 실리므로 여기서 짧게 거절한다."""
    if doc_type in ROW_PER_FINDING and n > MAX_FINDINGS_TOTAL:
        raise HTTPException(422, f"판정 findings가 너무 많습니다: {n}개(최대 {MAX_FINDINGS_TOTAL}개). "
                                 "인증(verdicts·cert_ids)을 나눠 요청하세요.")


def _attachment(filename: str) -> str:
    """ASCII 파일명과 RFC 5987 UTF-8 파일명을 함께 넣는다(헤더 주입 방지용 정리 포함)."""
    ascii_name = re.sub(r"[^A-Za-z0-9._-]", "_", filename) or "document"
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename, safe='')}"
