"""API 요청 모델 — app.py(/api/evaluate)와 routes_docs.py(/api/docs)가 함께 쓴다.

공개 URL이 인증 없이 열려 있으므로
- 모든 목록·문자열에 상한을 둬 요청 하나가 CPU·메모리를 오래 붙잡지 못하게 하고(본문 전체 상한은 app.py의 1 MiB),
- 엔진이 dict로 읽는 필드는 타입을 맞춰 잘못된 입력이 500이 아니라 422가 되게 한다.
상한은 실측값에 여유를 둔 값이다: 실데이터·데모 제품은 성분 33개 이하·성분명 54자 이하·판정 문구 240자 이하이고,
성분 500개 제품도 판정 하나의 findings가 523개, 58개 판정 합이 4089개다.
주의: 화면은 /api/evaluate 응답의 verdicts를 그대로 /api/docs에 되보내므로, 서류 내려받기는 본문 1 MiB에 걸려 성분 약 400개,
gap_checklist는 findings 합(MAX_FINDINGS_TOTAL)에 걸려 성분 약 250개 제품까지만 된다(판정은 500개까지).
성분 200개 제품의 서류 요청이 약 0.8 MB·findings 2438개.
"""
from __future__ import annotations

import re
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

_CONTROL = re.compile(r"[\x00-\x1f\x7f]+")


def _one_line(v):
    """한 줄 필드의 줄바꿈·탭 같은 제어문자를 공백으로 바꾼다. 성분명 속 줄바꿈이 판정 문구(카드 × 성분)로 퍼지면
    서류 표의 줄 수가 크게 불어나 생성이 수십 초까지 늘기 때문이다."""
    return _CONTROL.sub(" ", v) if isinstance(v, str) else v


MAX_INGREDIENTS = 500
MAX_ITEMS = 100  # 표방·서류·인증 id·제조사 인증 같은 짧은 목록
MAX_VERDICTS = 200  # 인증 카드(60장 안팎)마다 판정 하나
MAX_FINDINGS = 2000  # 판정 하나의 findings
# 부족 사항 체크리스트(gap_checklist) 요청 하나의 findings 합. 표 행 수라 생성 시간을 정한다(3000개 ≈ 1.6초).
# 성분 200개 제품의 58개 판정이 약 2400개
MAX_FINDINGS_TOTAL = 3000

Short = Annotated[str, BeforeValidator(_one_line), Field(max_length=100)]  # id·코드·상태값(한 줄)
Name = Annotated[str, BeforeValidator(_one_line), Field(max_length=300)]  # 이름·INCI·서류명(한 줄)
Text = Annotated[str, Field(max_length=2000)]  # 판정 문구(message·evidence·action). 여러 줄 허용
CertIds = Annotated[list[Short], Field(max_length=MAX_ITEMS)]


class Ingredient(BaseModel):
    kr: Name | None = None
    inci: Name
    cas: Short | None = None
    pct: float | None = Field(None, ge=0, le=100)  # 화면 입력과 같은 범위. NaN·Infinity도 여기서 걸러진다
    role: Short | None = None


class ManufacturerIn(BaseModel):
    """제조사. 판정은 certs, 서류는 name·country·fei를 읽는다. 그 밖의 키는 그대로 통과."""
    model_config = ConfigDict(extra="allow")
    name: Name | None = None
    country: Short | None = None
    certs: list[Name] = Field(default_factory=list, max_length=MAX_ITEMS)
    fei: Short | None = None
    fei_number: Short | None = None


class Product(BaseModel):
    id: Short = "U1"
    name_kr: Name = "사용자 제품"
    name_en: Name | None = None
    status: Short = "on_market"
    product_type: Short = "cosmetic"
    application: str = Field("leave_on", pattern="^(leave_on|rinse_off)$")
    claims: list[Short] = Field(default_factory=list, max_length=MAX_ITEMS)
    functional_kr: list[Short] = Field(default_factory=list, max_length=MAX_ITEMS)
    documents: list[Name] = Field(default_factory=list, max_length=MAX_ITEMS)
    formula_known: Short = "ingredients_only_no_concentration"
    manufacturer: ManufacturerIn = Field(default_factory=ManufacturerIn)
    ingredients: list[Ingredient] = Field(max_length=MAX_INGREDIENTS)


class CompanyIn(BaseModel):
    """판정·서류가 읽는 회사 필드만 타입을 맞춘다. 그 밖의 키(own_manufacturing·location·annual_production_krw 등)는
    그대로 통과."""
    model_config = ConfigDict(extra="allow")
    name: Name | None = None
    name_en: Name | None = None
    role_kr: Name | None = None
    local_entities: dict[Short, Name | dict | None] = Field(default_factory=dict, max_length=MAX_ITEMS)
    company_certs: dict[Short, Short | None] = Field(default_factory=dict, max_length=MAX_ITEMS)
    documents: list[Name] = Field(default_factory=list, max_length=MAX_ITEMS)
    export_history: list = Field(default_factory=list, max_length=MAX_ITEMS)
    financial: dict | None = None
