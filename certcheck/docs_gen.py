"""서류 초안 생성 — 판정 결과(Verdict.to_dict())와 제품·회사 정보로 제출 서류 초안(docx·xlsx)을 만든다.

    generate(doc_type, product, verdicts, company) -> (파일 바이트, 파일명, MIME)

- 서류 종류는 DOC_TYPES 참고: inci_list, label_draft, cpnp_sheet, mocra_sheet, gap_checklist, support_program.
- 모든 문서 첫머리에 고지문·생성일을 넣고, 비어 있는 값은 '[확인 필요]'로 남긴다.
- 배합비(함량)는 inci_list·cpnp_sheet에만 넣는다. include_pct=False면 그 둘에서도 뺀다.
- 판정 findings의 근거(evidence)를 각주·출처 칸으로 옮겨 사람이 원문을 다시 확인할 수 있게 한다.
- 제품 유형으로 고른 CPNP·FDA 카테고리, 라벨 기능 문구는 추정값이므로 '확인필요'로 표시한다.
"""
from __future__ import annotations

import csv
import io
import re
from bisect import bisect_left
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.opc.constants import CONTENT_TYPE as CT
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.opc.packuri import PackURI
from docx.opc.part import XmlPart
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn
from docx.shared import Mm, Pt
from openpyxl import Workbook
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from . import STATUS_COND, STATUS_FAIL, STATUS_NA, STATUS_ORDER, STATUS_PASS
from .data import DATA
from .normalize import norm_inci

FONT = "맑은 고딕"  # 글꼴 파일 없이도 생성된다. 열람 PC에 없으면 대체 글꼴로 보인다.
DISCLAIMER = "자동 생성된 초안입니다. 최종 제출 전 담당자·현지 책임자·안전성 평가자가 확인해야 합니다."
TBC = "[확인 필요]"
BOX = "□"
MIME = {"docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}
FILL = {"head": "D9E2F3", "note": "FFF2CC", "band": "EDEDED"}
XL_STATUS = {"채움": "E2EFDA", "확인필요": "FFF2CC", "외부필요": "FCE4D6"}
OWNERS = ("자사", "제조사", "외부 전문가", "시험기관", "현지 책임자")

DOC_TYPES = {
    "inci_list": {
        "name_ko": "영문 INCI 전성분표", "name_en": "INCI ingredient list", "format": "docx", "pct": True,
        "description": "함량 내림차순(함량 미상이면 입력 순서) 영문 전성분. 국문명·알레르기 성분 병기, 근거는 각주"},
    "label_draft": {
        "name_ko": "수출 라벨 표시사항 초안", "name_en": "Export label draft (EU/UK/US)", "format": "docx", "pct": False,
        "description": "EU·UK·US 시장별 필수 표시 항목(제품명·기능·용량·전성분·책임자·로트·사용기한/PAO·원산국·주의문구, "
                       "미국 국내 연락처). 빈 항목은 [확인 필요]"},
    "cpnp_sheet": {
        "name_ko": "EU CPNP 신고 항목표", "name_en": "EU CPNP notification sheet", "format": "xlsx", "pct": True,
        "description": "CPNP 신고 12개 항목의 자동 채움 값·출처·상태(채움/확인필요/외부필요)와 처방 시트"},
    "mocra_sheet": {
        "name_ko": "미국 MoCRA 제품 리스팅 항목표", "name_en": "US MoCRA product listing sheet", "format": "xlsx", "pct": False,
        "description": "MoCRA 제품 리스팅 항목(시설 FEI·책임자·라벨상 제품명·카테고리·향료·색소 포함 전성분·미국 대리인·매년 갱신)"},
    "gap_checklist": {
        "name_ko": "인증별 부족 사항 체크리스트", "name_en": "Gap checklist by certification", "format": "docx", "pct": False,
        "description": "여러 인증에 공통되는 조치를 먼저 보이고, 불가·조건부 항목을 인증별로 묶음. 담당·체크박스 포함"},
    "support_program": {
        "name_ko": "중기부 해외규격인증 지원사업 신청 준비 요약", "name_en": "MSS overseas certification support — application prep",
        "format": "docx", "pct": False,
        "description": "판정 대상 중 전략인증(strategic_kr)·일반지원 목록 번호(general_kr_no)가 있는 인증, 지원율·일정, 신청 전 준비물"},
}

# 중기부 해외규격인증 지원사업(2026년 3차 공고, 전략지원 KTR 공고)
SUPPORT_RATE = "전년도 매출에 따라 50~70%, 최대 1억 원(의료기기 1.5억)"
GENERAL_OPEN, GENERAL_CLOSE = date(2026, 10, 14), date(2026, 11, 13)
STRATEGIC_CLOSE = date(2026, 11, 30)
STRATEGIC_COSMETIC = "유럽 CPNP · 영국 SCPN · 미국 FDA(화장품 등록 분야 한정) · 유럽 PPWR(포장재) · 국제 HALAL"
GENERAL_LIST = DATA / "regs" / "해외규격인증_일반583_화장품분류.csv"

# 제품 유형 → (라벨 기능 문구, CPNP 3단계 카테고리, CPNP 물리적 형태, FDA 카테고리[등록·리스팅 가이던스 부록 A]). 모두 추정값.
TYPE_INFO = {
    "cleanser_balm": ("Cleansing balm — removes make-up and impurities",
                      ("Skin products", "Skin cleansing products", "Make-up remover products"), "Solid / balm",
                      "14(a) Skin care preparations — Cleansing"),
    "cleanser_foam": ("Facial cleansing foam", ("Skin products", "Skin cleansing products", "Other skin cleansing products"),
                      "Cream / foam", "14(a) Skin care preparations — Cleansing"),
    "face_cream": ("Face cream", ("Skin products", "Skin care products", "Face care products other than face mask"),
                   "Cream / emulsion", "14(c)1 Skin care preparations — Face and neck, leave-on"),
    "sheet_mask": ("Sheet mask", ("Skin products", "Skin care products", "Face mask"), "Impregnated sheet",
                   "14(c)1 Skin care preparations — Face and neck, leave-on"),
    "toner": ("Face toner", ("Skin products", "Skin care products", "Face care products other than face mask"), "Liquid",
              "14(i) Skin care preparations — Skin fresheners"),
}
# 키 직접 일치가 없을 때만 쓰는 약한 단서. 입술·몸·두발·자외선 제품은 추정하지 않는다(None).
TYPE_KEYWORDS = (("lip", None), ("body", None), ("hair", None), ("sun", None), ("balm", "cleanser_balm"),
                 ("cleans", "cleanser_foam"), ("foam", "cleanser_foam"), ("mask", "sheet_mask"), ("toner", "toner"),
                 ("cream", "face_cream"))
CLAIM_EN = {"whitening": "Brightening", "anti_wrinkle": "Helps reduce the look of fine lines", "moisturizing": "Moisturizing",
            "deep_cleansing": "Deep cleansing", "makeup_removal": "Removes make-up", "cleansing": "Cleansing",
            "radiance": "Radiance", "skin_barrier": "Supports the skin's moisture barrier"}
APPLICATION = {"leave_on": "바르는 제품 (Leave-on)", "rinse_off": "씻어내는 제품 (Rinse-off)"}
COUNTRY = {"KR": "Republic of Korea", "CN": "China", "JP": "Japan", "US": "United States", "FR": "France", "IT": "Italy"}
EU_MEMBERS = {"오스트리아": "Austria", "벨기에": "Belgium", "불가리아": "Bulgaria", "크로아티아": "Croatia", "키프로스": "Cyprus",
              "체코": "Czechia", "덴마크": "Denmark", "에스토니아": "Estonia", "핀란드": "Finland", "프랑스": "France",
              "독일": "Germany", "그리스": "Greece", "헝가리": "Hungary", "아일랜드": "Ireland", "이탈리아": "Italy",
              "라트비아": "Latvia", "리투아니아": "Lithuania", "룩셈부르크": "Luxembourg", "몰타": "Malta",
              "네덜란드": "Netherlands", "폴란드": "Poland", "포르투갈": "Portugal", "루마니아": "Romania",
              "슬로바키아": "Slovakia", "슬로베니아": "Slovenia", "스페인": "Spain", "스웨덴": "Sweden"}
EU_CODES = {"AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU", "IE", "IT", "LV", "LT", "LU", "MT",
            "NL", "PL", "PT", "RO", "SK", "SI", "ES", "SE"}
CERT_KO = {"venture": "벤처기업", "innobiz": "이노비즈", "mainbiz": "메인비즈"}
IMPAIRMENT = {"complete": "완전자본잠식", "partial": "부분자본잠식", "none": "없음"}

RULE_1PCT = ("1% 규칙 — EU 1223/2009 제19조(1)(g): 1% 미만 성분은 1% 초과 성분 뒤에 순서 무관 / 21 CFR 701.3(f): 1% 이하 "
             "성분은 순서 무관, 색소는 마지막 / 화장품법 시행규칙 별표 4: 1% 이하 성분·착향제·착색제는 순서 무관")
ALLERGEN_RULE = "EU 1223/2009 부속서 III: 바르는 제품 0.001%·씻어내는 제품 0.01% 초과 시 전성분에 표시"
GENERIC_PRECAUTIONS = ("For external use only. Avoid contact with eyes; if contact occurs, rinse thoroughly with water. "
                       "Discontinue use if irritation occurs. Keep out of reach of children.")

# 판정 코드 → 담당. 표에 없는 코드는 조치 문구의 단어로 추정한다(_owner).
OWNER_BY_CODE = {
    "LOCAL_ENTITY_MISSING": "자사",  # 현지 책임자를 찾아 계약하는 일은 자사 몫
    "TEST_MISSING": "시험기관", "PROP65_DIOXANE": "시험기관",
    "LABEL_LOCAL": "현지 책임자", "CLAIM_SPECIAL_REG": "현지 책임자", "ING_NOT_IN_INVENTORY": "현지 책임자", "ING_CN_INVENTORY_CHECK": "현지 책임자",
    "ING_NO_DATA": "현지 책임자", "ING_JP_NAME_ONLY": "현지 책임자", "ING_JP_POSITIVE_UNCONFIRMED": "현지 책임자",
    "ING_BANNED": "제조사", "ING_OVER_LIMIT": "제조사", "ING_UNDEFINED": "제조사", "FORMULA_CONCEPT": "제조사",
    "ING_RESTRICTED_PCT_UNKNOWN": "제조사", "ING_BANNED_WITH_EXCEPTION": "제조사", "ING_PEROXIDE": "제조사",
    "ALLERGEN_UNKNOWN": "제조사", "HALAL_FACILITY": "제조사", "SILOXANE_SUNSET": "제조사", "SILOXANE_BANNED": "제조사",
    "SILOXANE_RINSEOFF": "제조사",
}
OWNER_KEYWORDS = (("평가자", "외부 전문가"), ("전문가", "외부 전문가"), ("시험", "시험기관"), ("현지", "현지 책임자"),
                  ("제조사", "제조사"), ("원료", "제조사"), ("처방", "제조사"))
DEFAULT_ACTION = {"FORMULA_CONCEPT": "확정 처방으로 재판정"}

_BAD_XML = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff￾￿]")
MAX_TEXT_LINES = 20  # Word 표 칸·문단 하나의 줄 수 상한(_docx_lines). 정상 서류는 9줄 이하
MAX_ALLERGEN_NOTES = 5  # 성분 하나의 알레르기 근거(inci_list 각주) 상한. 정상 데이터는 3개 이하(같은 성분을 보는 카드 수)
ALLERGEN_SEARCH_BUDGET = 5000  # 서류 하나에서 알레르기 근거 경계를 정규식으로 확인하는 횟수 상한. 정상 데이터는 수십 번


# ---------------------------------------------------------------- 진입점
def doc_types() -> list[dict]:
    """API용 서류 목록과 설명."""
    return [{"doc_type": k, "name_ko": m["name_ko"], "name_en": m["name_en"], "format": m["format"],
             "mime": MIME[m["format"]], "description": m["description"], "include_pct_option": m["pct"]}
            for k, m in DOC_TYPES.items()]


def generate(doc_type: str, product: dict, verdicts: list[dict], company: dict, *,
             cards: list[dict] | None = None, include_pct: bool = True) -> tuple[bytes, str, str]:
    """서류 초안을 만든다. 반환: (파일 바이트, 파일명, MIME).

    cards: 인증 카드 목록 — 지원사업 요약에서 strategic_kr·general_kr_no를 찾는 데 쓴다(판정 dict에 같은 키가 있으면 그 값 우선).
    include_pct: False면 inci_list·cpnp_sheet에서도 함량을 뺀다(다른 서류에는 원래 넣지 않는다).
    """
    meta = DOC_TYPES.get(doc_type)
    if meta is None:
        raise ValueError(f"알 수 없는 서류 종류: {doc_type} (가능: {', '.join(DOC_TYPES)})")
    product = product or {}
    pct = bool(include_pct and meta["pct"])
    # 판정 문구에도 제품 함량이 섞여 있으므로(예: 'D5 1.65%') 함량을 싣지 않는 서류에서는 그 값을 가린다
    values = set() if pct else \
        {x for x in (_pct(i) for i in product.get("ingredients") or [] if isinstance(i, dict)) if x is not None}
    verdicts = [_prep_verdict(v, values) for v in verdicts or [] if isinstance(v, dict)]
    ctx = _Ctx(product=product, verdicts=verdicts, company=company or {},
               cards={c["id"]: c for c in cards or [] if isinstance(c, dict) and c.get("id")}, pct=pct, today=date.today())
    data = BUILDERS[doc_type](ctx)
    pid = re.sub(r"[^A-Za-z0-9_-]+", "", str(ctx.product.get("id") or "")) or "product"
    suffix = "_nopct" if meta["pct"] and not include_pct else ""
    return data, f"{pid}_{doc_type}{suffix}_{ctx.today:%Y%m%d}.{meta['format']}", MIME[meta["format"]]


# ---------------------------------------------------------------- 공통 도우미
@dataclass
class _Ctx:
    product: dict
    verdicts: list[dict]
    company: dict
    cards: dict[str, dict]
    pct: bool
    today: date
    ings: list[dict] = field(init=False)
    ordered: list[dict] = field(init=False)
    by_pct: bool = field(init=False)

    def __post_init__(self) -> None:
        self.ings = [i for i in self.product.get("ingredients") or [] if isinstance(i, dict) and (i.get("inci") or i.get("kr"))]
        self.ordered, self.by_pct = _order(self.ings)

    @property
    def label(self) -> str:
        p = self.product
        names = " / ".join(str(x) for x in (p.get("name_kr"), p.get("name_en")) if x) or TBC
        return f"{names} ({p['id']})" if p.get("id") else names


def _clean(s) -> str:
    """XML·엑셀에 넣을 수 없는 제어문자를 지운다."""
    return _BAD_XML.sub("", "" if s is None else str(s))


def _docx_lines(text) -> list[str]:
    """Word 문단·표 칸에 넣을 줄 목록. python-docx는 줄(run)과 run 안의 \\n·\\r·\\t마다 XML 요소를 만들어
    입력에 줄바꿈이 수천 개면 서류 하나가 수 초씩 걸리므로, 줄바꿈을 \\n 하나로 맞추고 탭은 공백으로 바꾸고 줄 수를 묶는다."""
    lines = _clean(text).replace("\r\n", "\n").replace("\r", "\n").replace("\t", " ").split("\n")
    if len(lines) > MAX_TEXT_LINES:
        lines = lines[:MAX_TEXT_LINES - 1] + [" / ".join(x for x in lines[MAX_TEXT_LINES - 1:] if x.strip())]
    return lines


def _pct(ing: dict) -> float | None:
    v = ing.get("pct")
    try:
        return None if v is None or v == "" else float(v)
    except (TypeError, ValueError):
        return None


def _fmt_pct(x: float) -> str:
    return (f"{x:.4f}" if x >= 0.01 else f"{x:.6f}").rstrip("0").rstrip(".") or "0"


# 판정 문구는 사용자가 보낸 verdicts일 수도 있어 긴 숫자열·공백열에서 시간이 제곱으로 늘지 않게 한다(ReDoS 방지):
# 숫자열·공백열의 첫 글자에서만 시작하고(lookbehind), 자릿수는 float repr이 내는 길이(정수 16·소수 20·지수 3)까지만 본다.
_PCT_IN_TEXT = re.compile(r"(?<!\d)(\d{1,16}(?:[.,]\d{1,20})?(?:e-?\d{1,3})?)\s*%", re.I)
_KW_TAG = re.compile(r"(?<!\s)\s*\[kw:[^\[\]]*\]")  # 카드 태그 안에는 대괄호가 없다


def _prep_verdict(v: dict, values: set[float]) -> dict:
    """판정 문구(message·evidence·action)를 서류용으로 정리: 엔진 태그([kw:…])를 지우고, values(제품 함량)가 있으면
    그 값을 '(함량 비공개)'로 가린다. 한도처럼 함량과 다른 수치는 그대로 둔다."""
    near = sorted(y for y in values if y == y)  # NaN 제외. 수치마다 함량 전체를 훑지 않고 양옆 두 값만 본다

    def repl(m):
        try:
            x = float(m.group(1).replace(",", "."))
        except ValueError:
            return m.group(0)
        i = bisect_left(near, x)
        return "(함량 비공개)" if any(abs(x - y) < 1e-9 for y in near[max(i - 1, 0):i + 1]) else m.group(0)

    def mask(text):
        if not isinstance(text, str):
            return text
        text = _KW_TAG.sub("", text)
        return _PCT_IN_TEXT.sub(repl, text) if values else text

    out = dict(v)
    out["findings"] = [{**f, **{k: mask(f.get(k)) for k in ("message", "evidence", "action")}} if isinstance(f, dict) else f
                       for f in v.get("findings") or []]
    return out


def _order(ings: list[dict]) -> tuple[list[dict], bool]:
    """함량을 알면 내림차순(향료 유래 알레르기 성분만 함량 미상이면 끝에 둔다), 모르면 입력 순서."""
    core = [i for i in ings if i.get("role") != "allergen_from_fragrance"]
    if core and all(_pct(i) is not None for i in core):
        known = sorted((i for i in ings if _pct(i) is not None), key=lambda i: -_pct(i))
        return known + [i for i in ings if _pct(i) is None], True
    return list(ings), False


def _undefined(ing: dict) -> bool:
    return "TBD" in (ing.get("inci") or "") or ing.get("role") == "key_concept"


def _findings(verdicts: list[dict], levels: set[str] | None = None):
    for v in verdicts:
        for f in v.get("findings") or []:
            if isinstance(f, dict) and (levels is None or f.get("level") in levels):
                yield v, f


def _dedupe(items) -> list:
    """빈 값을 빼고 처음 나온 순서로 중복을 지운다(목록을 훑지 않고 집합으로 확인)."""
    out, seen = [], set()
    for x in items:
        if not x:
            continue
        try:
            if x in seen:
                continue
            seen.add(x)
        except TypeError:  # 해시할 수 없는 값(dict 등)만 목록에서 찾는다
            if x in out:
                continue
        out.append(x)
    return out


def _lines(*parts: str) -> str:
    return "\n".join(p for p in parts if p)


def _short(text, n: int = 60) -> str:
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    return text if len(text) <= n else text[: n - 1] + "…"


_I_FIX = str.maketrans({"\u0130": "i", "\u0131": "i"})  # casefold가 re.I와 다르게 접는 글자는 터키어 İ·ı뿐


def _fold(s: str) -> str:
    """대소문자 접기. re.I로 같은 두 글자는 접은 결과도 같다(유니코드 전 글자 대조로 확인)."""
    return s.translate(_I_FIX).casefold()


def _allergens(ctx: _Ctx) -> dict[int, list[str]]:
    """성분(dict id) → 알레르기 근거. 판정의 ALLERGEN_LABEL_RULE(EU 부속서 III 대조)과 제품 입력 role을 함께 본다."""
    rules = list(dict.fromkeys((f.get("message") or "", f.get("evidence") or "", v.get("cert_id") or "")
                               for v, f in _findings(ctx.verdicts) if f.get("code") == "ALLERGEN_LABEL_RULE"))
    # 입력이 크면(성분 500 × 규칙 수백) 정규식 대조와 inci_list 각주가 곱으로 불어난다. 그래서
    # 같은 INCI는 한 번만 찾고, 접은 문구에 접은 INCI가 들어 있을 때만 정규식으로 경계를 확인하며(_fold가 같으면 re.I로도
    # 같은 글자라 결과는 그대로), 성분당 근거 수와 서류 하나의 정규식 확인 횟수에 상한을 둔다(정상 데이터는 둘 다 한참 아래)
    folded = [_fold(msg) for msg, _, _ in rules]
    found: dict[str, list[str]] = {}
    budget = ALLERGEN_SEARCH_BUDGET
    out: dict[int, list[str]] = {}
    for ing in ctx.ings:
        inci = (ing.get("inci") or "").strip()
        notes = []
        if inci:
            if inci not in found:
                pat = re.compile(r"(?<![\w-])" + re.escape(inci) + r"(?![\w-])", re.I)
                key, hits = _fold(inci), []
                for (msg, ev, cid), low in zip(rules, folded):
                    if len(hits) > MAX_ALLERGEN_NOTES or budget <= 0:
                        break
                    note = f"{ev or '판정 근거'} — 판정 {cid}"
                    if note in hits or key not in low:
                        continue
                    budget -= 1
                    if pat.search(msg):
                        hits.append(note)
                if len(hits) > MAX_ALLERGEN_NOTES:
                    hits[MAX_ALLERGEN_NOTES:] = ["그 밖의 근거 생략 — 판정 결과의 ALLERGEN_LABEL_RULE 참조"]
                found[inci] = hits
            notes = found[inci]
        if ing.get("role") == "allergen_from_fragrance" and not notes:
            notes = ["제품 입력값(향료 유래 알레르기 성분 표시)"]
        if notes:
            out[id(ing)] = _dedupe(notes)
    return out


def _type_info(product_type) -> tuple | None:
    t = str(product_type or "").lower()
    if t in TYPE_INFO:
        return TYPE_INFO[t]
    for kw, key in TYPE_KEYWORDS:
        if kw in t:
            return TYPE_INFO.get(key) if key else None
    return None


def _claims(p: dict) -> tuple[list[str], list[str]]:
    """(라벨용 영문 표방 문구, 'free from'이라 라벨 초안에서 뺀 표방)."""
    raw = [str(c) for c in (p.get("claims") or [])]
    free = [c for c in raw if c.startswith("free_from") or c.endswith("_free")]
    return _dedupe(CLAIM_EN.get(c) for c in raw), free


_NET = re.compile(r"(?<!\d)(\d{1,9}(?:[.,]\d{1,6})?)\s*(ml|kg|g|l)\b", re.I)  # 자릿수 상한: 위 _PCT_IN_TEXT와 같은 이유


def _net(raw) -> tuple[str | None, str | None]:
    """용량 → (미터법 표기, 미국 표기: 액량 fl. oz. / 중량 Net wt. oz.)."""
    raw = str(raw or "").strip()
    m = _NET.search(raw)
    if not m:
        return (f"{raw} {TBC} 단위 확인" if raw else None), None
    val, unit = float(m.group(1).replace(",", ".")), m.group(2).lower()
    num = f"{val:g}"
    if unit in ("ml", "l"):
        ml = val * (1000 if unit == "l" else 1)
        metric_unit = "ml" if unit == "ml" else "L"
        return f"{num} {metric_unit}", f"{ml / 29.5735:.2f} fl. oz. ({num} {'mL' if unit == 'ml' else 'L'})"
    grams = val * (1000 if unit == "kg" else 1)
    return f"{num} {unit}", f"Net wt. {grams / 28.3495:.2f} oz. ({num} {unit})"


def _origin(p: dict) -> str | None:
    c = str((p.get("manufacturer") or {}).get("country") or "").strip().upper()
    if not c:
        return None
    return "Made in Korea" if c in ("KR", "KOR") else f"Made in {COUNTRY.get(c, c)}"


def _entity(company: dict, *keys: str) -> dict:
    """company.local_entities에서 현지 책임자·대리인을 찾는다. 값은 이름 문자열 또는 {name, address, phone, email}."""
    le = company.get("local_entities") or {}
    for k in keys:
        v = le.get(k)
        if isinstance(v, str) and v.strip():
            return {"name": v.strip()}
        if isinstance(v, dict) and (v.get("name") or v.get("address")):
            return {kk: str(vv) for kk, vv in v.items() if vv}
    return {}


def _label_name(ing: dict, market: str) -> str:
    """시장별 라벨 성분명: EU·UK는 Aqua·Parfum과 식물명 괄호 속 영어 일반명 생략, 미국은 Water·Fragrance."""
    key = norm_inci(ing.get("inci"))
    if key == "aqua":
        name = "Water" if market == "US" else "Aqua"
    elif key == "parfum":
        name = "Fragrance" if market == "US" else "Parfum"
    else:
        name = ing.get("inci") or f"{TBC} {ing.get('kr') or ''}".strip()
        if market != "US":  # 'Citrus Aurantium Dulcis (Orange) Peel Oil' → 'Citrus Aurantium Dulcis Peel Oil'
            name = re.sub(r"\s*\((?!nano\))[A-Za-z][A-Za-z' -]*\)", "", name)
    return f"{TBC} {name}" if _undefined(ing) else name


def _is_color(ing: dict) -> bool:
    return (ing.get("inci") or "").upper().startswith("CI ") or ing.get("role") in ("colorant", "color")


def _juris_verdicts(ctx: _Ctx, juris: set[str]) -> list[dict]:
    return [v for v in ctx.verdicts if (v.get("jurisdiction") or "").upper() in juris]


def _warnings(verdicts: list[dict]) -> list[str]:
    """EU식 제한 성분 조건에서 라벨 경고문(Warning: …)을 뽑는다."""
    out = []
    for _, f in _findings(verdicts):
        if f.get("code") == "ING_RESTRICTED_CONDITIONS":
            m = re.search(r"Warning:\s*([^|]+)", f.get("message") or "")
            if m:
                out.append(m.group(1).strip())
    return _dedupe(out)


def _action(f: dict) -> str:
    return (f.get("action") or "").strip() or DEFAULT_ACTION.get(f.get("code"), f"{TBC} 조치 정의 필요")


def _owner(f: dict) -> str:
    code = f.get("code") or ""
    if code == "DOC_MISSING":
        m = re.search(r"\(작성: ([^)]+)\)", f.get("message") or "")
        who = m.group(1).strip() if m else ""
        if who in OWNERS:
            return who
        if who == "관공서":
            return "자사"
    if code.startswith("ATTR_"):
        return "제조사"
    if code in OWNER_BY_CODE:
        return OWNER_BY_CODE[code]
    text = f"{f.get('action') or ''} {f.get('message') or ''}"
    return next((who for kw, who in OWNER_KEYWORDS if kw in text), "자사")


def _card_meta(ctx: _Ctx, v: dict) -> dict:
    m = dict(ctx.cards.get(v.get("cert_id"), {}))
    for k in ("strategic_kr", "general_kr_no", "support_rate"):
        if v.get(k) is not None:
            m[k] = v[k]
    return m


def _nos(x) -> list[str]:
    if x is None or x is False or x == "":
        return []
    items = x if isinstance(x, (list, tuple)) else re.split(r"[,;/\s]+", str(x))
    return [str(i).strip() for i in items if str(i).strip()]


@lru_cache(maxsize=1)
def _general_list() -> dict[str, str]:
    """일반지원 583개 목록 번호 → '명칭 — 설명'. 파일이 없으면 빈 dict."""
    if not GENERAL_LIST.exists():
        return {}
    with GENERAL_LIST.open(encoding="utf-8-sig") as f:
        return {r["no"].strip(): f"{r.get('name', '')} — {r.get('desc', '')}" for r in csv.DictReader(f) if r.get("no")}


def _dday(today: date, deadline: date) -> str:
    n = (deadline - today).days
    return f"D-{n}" if n > 0 else "D-day" if n == 0 else "마감"


def _cert_state(s) -> str:
    """회사 인증 상태 값(valid / none / expired_2024 …)을 한국어로."""
    s = str(s or "")
    if s == "valid":
        return "유효"
    if s in ("", "none"):
        return "없음"
    return f"만료({s.split('_')[-1]})" if s.startswith("expired") else s


def _gap_counts(v: dict) -> tuple[int, int]:
    fs = [f for f in v.get("findings") or [] if isinstance(f, dict)]
    return sum(f.get("level") == "fail" for f in fs), sum(f.get("level") == "cond" for f in fs)


# ---------------------------------------------------------------- docx
class _Band(str):
    """표 안의 구분 행(모든 열 병합)."""


class _Docx:
    def __init__(self, ctx: _Ctx, title_ko: str, title_en: str):
        self.doc = Document()
        self._fn_root = None
        self._fn_id = 0
        _docx_defaults(self.doc)
        props = self.doc.core_properties
        props.title, props.author, props.comments = title_ko, "certcheck", DISCLAIMER
        head = self.doc.sections[0].header.paragraphs[0].add_run(
            _clean(f"certcheck 자동 생성 초안 — {title_ko} · 생성일 {ctx.today.isoformat()}"))
        head.font.size = Pt(8)
        self.p(title_ko, bold=True, size=16)
        self.p(title_en, size=11)
        self.table([f"고지 (Notice): {DISCLAIMER}\n생성일 (Generated): {ctx.today.isoformat()}"], [], [174], fill=FILL["note"])
        self.p(f"제품 (Product): {ctx.label} · 회사 (Company): {ctx.company.get('name') or TBC}", size=9)

    def p(self, text: str = "", bold: bool = False, size: float | None = None, notes=()):
        para = self.doc.add_paragraph()
        if text:
            run = para.add_run("\n".join(_docx_lines(text)))
            run.bold = bold or None
            if size:
                run.font.size = Pt(size)
        for n in notes:
            self.footnote(para, n)
        return para

    def h(self, text: str, level: int = 1) -> None:
        self.doc.add_heading("\n".join(_docx_lines(text)), level)

    def bullet(self, text: str) -> None:
        self.doc.add_paragraph("\n".join(_docx_lines(text)), style="List Bullet")

    def table(self, headers: list, rows: list, widths: list[float], fill: str = FILL["head"], size: float = 9,
              bold_head: bool = True):
        """rows의 칸 값: 문자열 또는 (문자열, [각주 문장…]). 행이 _Band면 전체 열을 병합한 구분 행."""
        t = self.doc.add_table(rows=1, cols=len(widths))
        t.style = self.doc.styles["Table Grid"]
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        t.autofit = False
        for cell, h in zip(t.rows[0].cells, headers):
            self._cell(cell, h, size, bold=bold_head, fill=fill)
        t.rows[0]._tr.get_or_add_trPr().append(OxmlElement("w:tblHeader"))  # 쪽이 넘어가면 머리행 반복
        for row in rows:
            cells = t.add_row().cells
            if isinstance(row, _Band):
                self._cell(cells[0].merge(cells[-1]), str(row), size, bold=True, fill=FILL["band"])
                continue
            for cell, val in zip(cells, row):
                self._cell(cell, val, size)
        _set_widths(t, widths)
        self.doc.add_paragraph()
        return t

    def _cell(self, cell, value, size: float, bold: bool = False, fill: str | None = None) -> None:
        text, notes = value if isinstance(value, tuple) else (value, ())
        para = cell.paragraphs[0]
        lines = _docx_lines(text)
        for i, line in enumerate(lines):
            run = para.add_run(line)
            run.font.size = Pt(size)
            run.bold = bold or None
            if i < len(lines) - 1:
                run.add_break()
        for n in notes:
            self.footnote(para, n)
        if fill:
            shd = OxmlElement("w:shd")
            shd.set(qn("w:val"), "clear")
            shd.set(qn("w:color"), "auto")
            shd.set(qn("w:fill"), fill)
            cell._tc.get_or_add_tcPr().insert_element_before(
                shd, "w:noWrap", "w:tcMar", "w:textDirection", "w:tcFitText", "w:vAlign", "w:hideMark")

    def footnote(self, para, text: str) -> None:
        """Word 각주(쪽 아래)를 단다. 첫 각주 때 footnotes 파트를 만든다."""
        if self._fn_root is None:
            self._fn_root = parse_xml(
                f'<w:footnotes {nsdecls("w")}>'
                '<w:footnote w:type="separator" w:id="-1"><w:p><w:pPr><w:spacing w:after="0" w:line="240" '
                'w:lineRule="auto"/></w:pPr><w:r><w:separator/></w:r></w:p></w:footnote>'
                '<w:footnote w:type="continuationSeparator" w:id="0"><w:p><w:pPr><w:spacing w:after="0" w:line="240" '
                'w:lineRule="auto"/></w:pPr><w:r><w:continuationSeparator/></w:r></w:p></w:footnote></w:footnotes>')
            part = XmlPart(PackURI("/word/footnotes.xml"), CT.WML_FOOTNOTES, self._fn_root, self.doc.part.package)
            self.doc.part.relate_to(part, RT.FOOTNOTES)
            settings = self.doc.settings.element
            pr = parse_xml(f'<w:footnotePr {nsdecls("w")}><w:footnote w:id="-1"/><w:footnote w:id="0"/></w:footnotePr>')
            # 스키마 순서상 footnotePr는 endnotePr·compat·docVars·rsids 앞에 온다
            anchor = next((e for e in (settings.find(qn(t)) for t in ("w:endnotePr", "w:compat", "w:docVars", "w:rsids"))
                           if e is not None), None)
            if anchor is not None:
                anchor.addprevious(pr)
            else:
                settings.append(pr)
        self._fn_id += 1
        ref_run = para.add_run()
        ref_run.font.superscript = True
        ref = OxmlElement("w:footnoteReference")
        ref.set(qn("w:id"), str(self._fn_id))
        ref_run._r.append(ref)

        note = OxmlElement("w:footnote")
        note.set(qn("w:id"), str(self._fn_id))
        p = OxmlElement("w:p")
        mark = OxmlElement("w:r")
        mark_pr = OxmlElement("w:rPr")
        va = OxmlElement("w:vertAlign")
        va.set(qn("w:val"), "superscript")
        mark_pr.append(va)
        mark.append(mark_pr)
        mark.append(OxmlElement("w:footnoteRef"))
        body = OxmlElement("w:r")
        body_pr = OxmlElement("w:rPr")
        sz = OxmlElement("w:sz")
        sz.set(qn("w:val"), "16")
        body_pr.append(sz)
        body.append(body_pr)
        t = OxmlElement("w:t")
        t.set(qn("xml:space"), "preserve")
        t.text = " " + _clean(text)
        body.append(t)
        p.append(mark)
        p.append(body)
        note.append(p)
        self._fn_root.append(note)

    def bytes(self) -> bytes:
        buf = io.BytesIO()
        self.doc.save(buf)
        return buf.getvalue()


def _set_rfonts(rfonts) -> None:
    for a in ("w:asciiTheme", "w:hAnsiTheme", "w:eastAsiaTheme", "w:cstheme"):
        rfonts.attrib.pop(qn(a), None)
    for a in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        rfonts.set(qn(a), FONT)


def _docx_defaults(doc) -> None:
    """A4·여백 18mm, 모든 기본 스타일 글꼴을 맑은 고딕으로(테마 글꼴 지정은 지운다)."""
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Mm(210), Mm(297)
    sec.left_margin = sec.right_margin = sec.top_margin = sec.bottom_margin = Mm(18)
    for name in ("Normal", "Heading 1", "Heading 2", "List Bullet"):
        style = doc.styles[name]
        style.font.name = FONT
        _set_rfonts(style.element.rPr.rFonts)
    doc.styles["Normal"].font.size = Pt(10)
    default = doc.styles.element.find("/".join(qn(f"w:{t}") for t in ("docDefaults", "rPrDefault", "rPr", "rFonts")))
    if default is not None:
        _set_rfonts(default)
    # 글꼴이 없는 PC에서도 한글 대체 글꼴이 잡히도록 동아시아 언어를 한국어로 지정
    lang = OxmlElement("w:lang")
    lang.set(qn("w:val"), "en-US")
    lang.set(qn("w:eastAsia"), "ko-KR")
    doc.styles["Normal"].element.rPr.insert_element_before(lang, "w:eastAsianLayout", "w:specVanish", "w:oMath")
    theme_lang = doc.settings.element.find(qn("w:themeFontLang"))
    if theme_lang is not None:
        theme_lang.set(qn("w:eastAsia"), "ko-KR")


def _set_widths(table, widths: list[float]) -> None:
    for col, w in zip(table._tbl.tblGrid.findall(qn("w:gridCol")), widths):
        col.set(qn("w:w"), str(Mm(w).twips))
    for tr in table._tbl.tr_lst:
        pos = 0
        for tc in tr.tc_lst:
            span = tc.grid_span
            tc.width = Mm(sum(widths[pos:pos + span]))
            pos += span


# ---------------------------------------------------------------- xlsx
_THIN = Side(style="thin", color="BFBFBF")
_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)


def _xl_put(ws, r: int, c: int, value, bold: bool = False, fill: str | None = None, size: float = 10, wrap: bool = True):
    cell = ws.cell(row=r, column=c)
    value = _clean(value) if isinstance(value, str) else value
    cell.value = value
    if isinstance(value, str) and value.startswith("="):
        cell.data_type = "s"  # 사용자 입력이 수식으로 실행되지 않게 문자열로 고정
    cell.font = Font(name=FONT, size=size, bold=bold)
    cell.alignment = Alignment(wrap_text=wrap, vertical="top")
    if fill:
        cell.fill = PatternFill("solid", fgColor=fill)
    return cell


def _xl_sheet(wb, ctx: _Ctx, sheet: str, title: str, first: bool = False):
    ws = wb.active if first else wb.create_sheet()
    ws.title = sheet
    _xl_put(ws, 1, 1, title, bold=True, size=14, wrap=False)
    _xl_put(ws, 2, 1, f"고지 (Notice): {DISCLAIMER}", bold=True, fill=FILL["note"], wrap=False)
    _xl_put(ws, 3, 1, f"생성일 (Generated): {ctx.today.isoformat()}   제품 (Product): {ctx.label}   "
                      f"회사 (Company): {ctx.company.get('name') or TBC}", wrap=False)
    ws.oddHeader.center.text = "certcheck 자동 생성 초안 — 제출 전 확인 필요"
    ws.page_setup.orientation = "landscape"
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    return ws


def _xl_table(ws, top: int, headers: list[str], rows: list[list], widths: list[float], status_col: int | None = None) -> int:
    """표를 쓰고 다음 빈 행 번호를 돌려준다. status_col이 있으면 목록 선택·상태별 색을 단다."""
    for j, h in enumerate(headers, 1):
        _xl_put(ws, top, j, h, bold=True, fill=FILL["head"]).border = _BORDER
    for i, row in enumerate(rows, top + 1):
        for j, v in enumerate(row, 1):
            _xl_put(ws, i, j, v).border = _BORDER
    for j, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(j)].width = w
    end = top + len(rows)
    if status_col and rows:
        col = get_column_letter(status_col)
        rng = f"{col}{top + 1}:{col}{end}"
        dv = DataValidation(type="list", formula1=f'"{",".join(XL_STATUS)}"', allow_blank=False)
        ws.add_data_validation(dv)
        dv.add(rng)
        for s, color in XL_STATUS.items():
            ws.conditional_formatting.add(rng, FormulaRule(formula=[f'{col}{top + 1}="{s}"'],
                                                           fill=PatternFill(start_color=color, end_color=color, fill_type="solid")))
    ws.freeze_panes = ws.cell(row=top + 1, column=1)
    return end + 2


def _xl_lines(ws, row: int, title: str, lines: list[str]) -> int:
    _xl_put(ws, row, 1, title, bold=True, wrap=False)
    for i, line in enumerate(lines, row + 1):
        _xl_put(ws, i, 1, line, wrap=False)
    return row + len(lines) + 2


def _xl_bytes(wb, title: str) -> bytes:
    wb.properties.title, wb.properties.creator, wb.properties.description = title, "certcheck", DISCLAIMER
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _verdict_lines(verdicts: list[dict]) -> list[str]:
    lines = []
    for v in verdicts:
        lines.append(f"{v.get('cert_name') or v.get('cert_id')} ({v.get('cert_id')}) — 판정: {v.get('status') or '-'}")
        for f in sorted((f for f in v.get("findings") or [] if isinstance(f, dict) and f.get("level") in ("fail", "cond")),
                        key=lambda f: f.get("level") != "fail"):
            lines.append(f"  · [{'불가' if f.get('level') == 'fail' else '조건부'}] {f.get('message')} → {_action(f)}")
    return lines or ["관련 판정 없음 — 해당 인증 카드로 판정하면 부족 사항이 여기에 나옵니다."]


# ---------------------------------------------------------------- 1. 영문 INCI 전성분표
def _inci_list(ctx: _Ctx) -> bytes:
    d = _Docx(ctx, "영문 INCI 전성분표", "INCI Ingredient List")
    allergens = _allergens(ctx)
    fragrance_gap = any(f.get("code") == "ALLERGEN_UNKNOWN" for _, f in _findings(ctx.verdicts, {"cond", "fail"}))
    show_pct = ctx.pct and any(_pct(i) is not None for i in ctx.ings)
    unknown = sum(_pct(i) is None for i in ctx.ings)
    if ctx.by_pct:
        basis = "함량 내림차순 (Descending by concentration)" + ("" if show_pct else " — 함량 값은 비공개 옵션으로 생략")
    elif unknown < len(ctx.ings):  # 일부만 미상: 미상 성분의 자리를 추측하지 않고 입력 순서를 유지한다
        basis = (f"입력 순서 (Input order) — 함량 미상 성분 {unknown}종이 있어 입력(포장 표기) 순서를 유지함. "
                 "함량을 모두 확인한 뒤 다시 생성하면 내림차순으로 정렬됨")
    else:
        basis = ("입력 순서 (Input order) — 함량 정보가 없어 입력(포장 표기) 순서를 따름. "
                 "1% 이하 성분은 순서 무관이므로 함량 확인 후 경계를 표시해야 함")
    d.h("1. 제품 정보 (Product)")
    d.table(["항목 (Item)", "내용 (Details)"], [
        ["제품명 (Product name)", ctx.label],
        ["적용 방식 (Application)", APPLICATION.get(ctx.product.get("application"), TBC)],
        ["성분 수 (Number of ingredients)", f"{len(ctx.ings)}종"],
        ["정렬 기준 (Order basis)", (basis, [RULE_1PCT])],
    ], [45, 129])

    d.h("2. 전성분 (Ingredient list)")
    headers = ["No.", "INCI 명 (INCI name)", "국문명 (Korean name)", "CAS No."]
    headers += ["함량 % (Conc.)"] if show_pct else []
    headers += ["비고 (Notes)"]
    rows: list = []
    banded = False
    for n, ing in enumerate(ctx.ordered, 1):
        pct = _pct(ing)
        if show_pct and ctx.by_pct and not banded and pct is not None and pct <= 1:
            rows.append(_Band("1% 이하 성분 — 순서 무관 (≤ 1 %, any order)"))
            banded = True
        notes, refs = [], []
        if id(ing) in allergens:
            notes.append("알레르기 성분 (Allergen)")
            refs += [f"향료 알레르기 성분(Fragrance allergen) — 근거: {e}. {ALLERGEN_RULE}." for e in allergens[id(ing)]]
        if _undefined(ing):
            notes.append("처방 미확정 (TBD)")
            refs.append("처방 미확정 성분 — 확정 처방(INCI·함량)으로 교체한 뒤 다시 생성해야 함.")
        if norm_inci(ing.get("inci")) == "parfum" and fragrance_gap:
            notes.append("향료 알레르겐 미확인")
            refs.append(f"향료 알레르기 성분 구성·함량 미보유(판정 ALLERGEN_UNKNOWN) — 향료사 알레르겐 분석서 확보 후 "
                        f"기준 초과 성분을 전성분에 추가. {ALLERGEN_RULE}.")
        if pct is None and (ctx.by_pct or show_pct):
            notes.append("함량 미상 (Unknown %)")
            if ctx.by_pct:
                refs.append("함량 미상 — 목록 끝에 임시로 두었음. 실제 함량으로 위치를 확인해야 함.")
        row = [str(n), ing.get("inci") or TBC, ing.get("kr") or TBC, ing.get("cas") or "-"]
        if show_pct:
            row.append(_fmt_pct(pct) if pct is not None else "미상")
        row.append(("\n".join(notes) or "-", refs))
        rows.append(row)
    d.table(headers, rows, [10, 52, 42, 24, 18, 28] if show_pct else [10, 58, 46, 26, 34])

    d.h("3. 라벨용 한 줄 전성분 (Label line)")
    d.p("Ingredients: " + (", ".join(i.get("inci") or TBC for i in ctx.ordered) or TBC))
    d.h("4. 참고 (Notes)")
    d.bullet("시장별 표기: EU·UK는 정제수 'Aqua'·향료 'Parfum'(제19조(1)(g))이고 식물명 괄호 속 영어 일반명을 쓰지 않음"
             "(EU 공통 성분명 용어집), 미국은 'Water'·'Fragrance'(21 CFR 701.3) — 시장별 문안은 수출 라벨 초안(label_draft) 참고")
    d.bullet("나노 원료는 성분명 뒤 '(nano)', 색소는 마지막에 순서 무관(EU는 CI 번호) 표기")
    d.bullet("알레르기 성분은 판정 근거(EU 부속서 III 대조)와 제품 입력값으로 표시했음 — 향료사 알레르겐 분석서로 최종 확인")
    return d.bytes()


# ---------------------------------------------------------------- 2. 수출 라벨 표시사항 초안
def _label_draft(ctx: _Ctx) -> bytes:
    d = _Docx(ctx, "수출 라벨 표시사항 초안", "Export Label Draft — EU / UK / US")
    d.p("시장별 필수 표시 항목을 제품·회사 정보로 채운 초안입니다. 비어 있는 항목은 [확인 필요]로 남겼고, "
        "'표시 문구 초안' 칸의 영문은 라벨 원고에 옮길 수 있게 썼습니다.", size=9)
    p, company = ctx.product, ctx.company
    info = _type_info(p.get("product_type"))
    func = info[0] if info else f"{TBC} 제품 기능 (Function)"
    claims, free = _claims(p)
    metric, us_net = _net(p.get("net_content"))
    origin = _origin(p) or f"{TBC} 원산국"
    name = p.get("name_en") or f"{TBC} 영문 제품명 (국문: {p.get('name_kr') or '-'})"
    eu_vs = _juris_verdicts(ctx, {"EU"})
    uk_vs = _juris_verdicts(ctx, {"UK", "GB"})
    us_vs = _juris_verdicts(ctx, {"US"})

    def claim_note(vs: list[dict], us: bool) -> str:
        parts = []
        if claims:
            parts.append(f"표방 초안: {' · '.join(claims)} — "
                         + ("외관 개선 표현 유지(구조·기능 표방은 의약품 판단 위험)" if us else "입증 자료 필요(EU 655/2013 공통기준)"))
        if free:
            parts.append(f"라벨 초안에서 뺀 'free from' 표방: {', '.join(free)} — 시장별 표방 기준 확인 후 사용")
        parts += [f"판정: {f.get('message')} ({f.get('evidence') or v.get('cert_id')})"
                  for v, f in _findings(vs) if (f.get("code") or "").startswith("CLAIM_")]
        return "\n".join(_dedupe(parts))

    def allergen_note(vs: list[dict]) -> str:
        if any(f.get("code") == "ALLERGEN_UNKNOWN" for _, f in _findings(vs)):
            return "판정: 향료 알레르기 성분 구성 미보유 — 향료사 분석서 확보 후 기준 초과 성분을 전성분에 추가"
        return ""

    def precautions(vs: list[dict], basis_us: bool) -> str:
        warn = _warnings(vs)
        head = ("Warnings: " + " / ".join(warn) + f"\n{TBC} 위 경고문(판정 근거 원문) 확인") if warn else \
            f"{TBC} {'21 CFR 740 해당 경고문' if basis_us else '안전성 평가(CPSR) 결론에 따른 주의문구'}"
        return f"{head}\n(예시) {GENERIC_PRECAUTIONS}"

    for market in ("EU", "UK", "US"):
        names = ", ".join(_label_name(i, market) for i in ctx.ordered) or TBC
        ingredients = f"Ingredients: {names}"
        if market in ("EU", "UK"):
            vs = eu_vs if market == "EU" else (uk_vs or eu_vs)
            ent = _entity(company, "EU") if market == "EU" else _entity(company, "UK", "GB")
            rp = (ent.get("name") or f"{TBC} {market} 책임자(RP) 이름") + "\n" + (ent.get("address") or f"{TBC} {market} 내 주소")
            art = "제19조" if market == "EU" else "UK 화장품 규정(GB판 1223/2009) 제19조"
            proxy = "" if market == "EU" or uk_vs else " (UK 판정이 없어 EU 판정을 준용)"
            lang = ("출시 회원국 공용어(제19조(5)) — 첫 출시 회원국을 정한 뒤 번역 " + TBC) if market == "EU" else "영어"
            local = _dedupe(f.get("message") for _, f in _findings(vs) if f.get("code") == "LABEL_LOCAL")
            d.h("1. 유럽연합 (EU)" if market == "EU" else "2. 영국 (UK, Great Britain)")
            d.p(f"근거: {'Regulation (EC) No 1223/2009 ' if market == 'EU' else ''}{art} · 표시 언어: {lang}"
                + (f" · 판정: {'; '.join(local)}" if local else "") + proxy, size=9)
            if market == "UK":
                d.p("영국(GB) 출시는 영국 소재 책임자(RP)가 SCPN 신고 — 북아일랜드는 EU 규정을 따른다.", size=9)
            rows = [
                ["제품명 (Product name)", name, f"{'CPNP' if market == 'EU' else 'SCPN'} 신고명과 같게(브랜드·라인·제품명)"],
                ["기능 (Function)", func, _lines(f"{art}(1)(f) — 외관으로 명확하면 생략 가능", claim_note(vs, us=False))],
                ["용량 (Nominal content)", metric or f"{TBC} 중량 또는 부피", f"{art}(1)(b) — 포장 시점의 중량 또는 부피"],
                ["전성분 (Ingredients)", ingredients,
                 _lines(f"{art}(1)(g) — 함량 내림차순, 1% 미만은 순서 무관, 향료는 'Parfum'과 부속서 III 알레르기 성분, "
                        "나노는 '(nano)', 색소는 마지막(CI 번호)",
                        "성분명은 EU 공통 성분명 용어집(결정 (EU) 2019/701) 기준 — 식물명 괄호 속 영어 일반명을 뺐으니 용어집에서 확인",
                        allergen_note(vs))],
                ["책임자 (Responsible person)", rp, f"{art}(1)(a) — 역내 RP 이름·주소, 여러 주소면 PIF 보관 주소 강조"],
                ["로트 (Batch No.)", f"LOT {TBC}", f"{art}(1)(e) — 제조번호(용기가 너무 작으면 포장에만)"],
                ["사용기한/PAO (Durability / PAO)",
                 f"{TBC} 최소 내구 기한 30개월 초과: PAO 기호 + 개월(예: 12M) / 30개월 이하: 'Best used before the end of' + 날짜",
                 f"{art}(1)(c), 부속서 VII 기호"],
                ["원산국 (Country of origin)", origin, f"{art}(1)(a) — 수입품은 원산국 표시"],
                ["주의문구 (Precautions)", precautions(vs, basis_us=False), f"{art}(1)(d) — 부속서 III~VI의 조건·경고문 포함"],
            ]
            preview = [name, func, metric or f"{TBC} 용량", ingredients, rp.replace("\n", ", "),
                       f"LOT {TBC} · PAO/Best before {TBC}", origin]
        else:
            vs = us_vs
            us_ent = _entity(company, "US")
            dist = f"Distributed by: {company.get('name_en') or company.get('name') or TBC} (영문 표기 {TBC})\n{TBC} 영문 주소"
            contact = (f"{us_ent['name']}\n" if us_ent.get("name") else "") + \
                f"{TBC} 미국 내 주소·전화번호 또는 웹사이트(이상사례 보고 접수용)"
            d.h("3. 미국 (US)")
            d.p("근거: FD&C Act·FPLA, 21 CFR 701(표시), MoCRA(2022) · 표시 언어: 영어", size=9)
            rows = [
                ["제품명 (Statement of identity)", name, "21 CFR 701.11 — 주표시면(PDP)에 제품명과 정체(기능)를 표시"],
                ["기능 (Function)", func, _lines("21 CFR 701.11 — 일반 명칭·기능", claim_note(vs, us=True))],
                ["용량 (Net quantity)", us_net or f"{TBC} 용량(미국 단위 + 미터법)",
                 "21 CFR 701.13 — PDP 하단 30% 구역, 'Net wt.'(중량)·'fl. oz.'(액량). 환산값이므로 반올림 확인"],
                ["전성분 (Ingredients)", ingredients,
                 _lines("21 CFR 701.3 — 내림차순, 1% 이하 순서 무관, 색소는 마지막, 향료는 'Fragrance' 가능", allergen_note(vs))],
                ["책임자 (Name and place of business)", dist,
                 "21 CFR 701.12 — 'Manufactured for / Distributed by'. 라벨에 이름이 오른 회사가 MoCRA 책임자(RP)"],
                ["미국 내 연락처 (US domestic contact)", contact,
                 "FD&C Act §609(a)(MoCRA) — 미국 내 주소·전화 또는 전자 연락처, 2024-12-29 시행"],
                ["로트 (Batch No.)", f"LOT {TBC}", "연방 표시 의무는 아님 — 추적·회수 대비 권장"],
                ["사용기한/PAO (Expiration / PAO)", f"{TBC} (선택 표시)", "연방 표시 의무는 아님 — 권장"],
                ["원산국 (Country of origin)", origin, "19 CFR 134 — 수입품 원산지 표시"],
                ["주의문구 (Warnings)", precautions(vs, basis_us=True), "21 CFR 740 — 제품 유형별 경고문 해당 여부 확인"],
            ]
            preview = [name, func, us_net or f"{TBC} Net quantity", ingredients, dist.replace("\n", ", "),
                       contact.replace("\n", ", "), origin]
        d.table(["항목 (Item)", "표시 문구 초안 (Draft text)", "근거·비고 (Basis / Notes)"], rows, [36, 82, 56])
        d.p("라벨 문안 미리보기 (Label copy preview)", bold=True, size=9)
        d.table(["\n".join(preview)], [], [174], fill=FILL["band"], bold_head=False)
    return d.bytes()


# ---------------------------------------------------------------- 3. EU CPNP 신고 항목표
def _cpnp_sheet(ctx: _Ctx) -> bytes:
    p, company = ctx.product, ctx.company
    title = "EU CPNP 신고 항목표 (EU CPNP notification sheet)"
    wb = Workbook()
    ws = _xl_sheet(wb, ctx, "CPNP 신고 항목", title, first=True)
    cpnp_vs = [v for v in ctx.verdicts if "CPNP" in str(v.get("cert_id") or "").upper()]
    eu_vs = _juris_verdicts(ctx, {"EU"})
    rp_gap = any(f.get("code") == "LOCAL_ENTITY_MISSING" for _, f in _findings(cpnp_vs))
    info = _type_info(p.get("product_type"))
    docs = [str(x) for x in p.get("documents") or []]
    show_pct = ctx.pct and any(_pct(i) is not None for i in ctx.ings)
    rows = []

    ent = _entity(company, "EU")
    if ent.get("name"):
        rows.append(["책임자 (Responsible person)", f"{ent['name']} / {ent.get('address') or TBC + ' 주소(PIF 보관 주소)'}",
                     "회사 정보 local_entities.EU", "채움" if ent.get("address") else "확인필요",
                     "제13조(1)(b) — 이름·주소(PIF 보관 장소). 라벨의 RP 표기와 정확히 같아야 함"])
    else:
        rows.append(["책임자 (Responsible person)", f"{TBC} EU 역내 책임자(RP) 미지정",
                     "판정 EU_CPNP: LOCAL_ENTITY_MISSING" if rp_gap else "회사 정보 local_entities 없음", "외부필요",
                     "제13조(1)(b) — 역외 제조품은 EU 역내 RP 지정 필수(수입자 또는 위임 RP)"])
    contact = " / ".join(ent[k] for k in ("contact", "phone", "email") if ent.get(k))
    rows.append(["긴급연락처 (Contact person in case of necessity)", contact or f"{TBC} 연락 담당자 이름·국제전화번호·이메일",
                 "회사 정보 local_entities.EU" if contact else "RP 정보 필요", "채움" if contact else
                 ("확인필요" if ent else "외부필요"), "제13조(1)(e) — 실제 연락 가능한 사람(전화번호는 국가번호 포함)"])
    rows.append(["제품명 (Product name)", p.get("name_en") or f"{TBC} 영문 제품명 (국문: {p.get('name_kr') or '-'})",
                 "제품 정보 name_en" if p.get("name_en") else "제품 정보 name_kr", "채움" if p.get("name_en") else "확인필요",
                 "제13조(1)(a) — 브랜드·라인·제품명(라벨과 같게), 외관으로 기능이 불명확하면 기능 포함"])
    country = str((p.get("manufacturer") or {}).get("country") or "").strip().upper()
    imported = (f"{TBC} 수입 여부·원산국" if not country else "아니오 (Imported: No) — EU 역내 제조" if country in EU_CODES
                else f"예 (Imported: Yes) — 원산국 {COUNTRY.get(country, country)}")
    rows.append(["수입 여부·원산국 (Imported / Country of origin)", imported, "제품 정보 manufacturer.country",
                 "채움" if country else "확인필요", "제13조(1)(c) — 원산국이 여러 곳이면 원산국별로 따로 신고"])
    history = [str(x) for x in company.get("export_history") or []]
    member = _dedupe(en for h in history for ko, en in EU_MEMBERS.items() if ko in h or en.lower() in h.lower())
    rows.append(["첫 출시 회원국 (Member State of first placing)",
                 f"{', '.join(member)} (수출 이력에서 추정)" if member else f"{TBC} 첫 출시 회원국",
                 "회사 정보 export_history" if member else "입력 정보 없음", "확인필요", "제13조(1)(d)"])
    rows.append(["3단계 카테고리 (Category level 1/2/3)", " > ".join(info[1]) + " (추정)" if info else f"{TBC} 카테고리",
                 f"제품 유형 product_type={p.get('product_type') or '-'}", "확인필요",
                 "주 기능 기준으로 1→2→3단계 선택. 실제 선택지는 CPNP 화면에서 확인"])
    rows.append(["물리적 형태 (Physical form)", f"{info[2]} (추정)" if info else f"{TBC} 물리적 형태",
                 f"제품 유형 product_type={p.get('product_type') or '-'}", "확인필요",
                 "CPNP 선택 목록에서 확인('Liquid'는 점도 약 10,000 cP 미만)"])
    pack = [x for x in docs if "packag" in x.lower()]
    rows.append(["특수 용기·도포구 (Special applicator / packaging)",
                 f"{TBC} 일반 용기(병·자·튜브·사셰) 또는 특수 용기·도포구(펌프 스프레이·에어로졸 등) 여부",
                 f"보유 서류: {', '.join(pack)}" if pack else "포장 정보 없음", "확인필요", "예/아니오 선택, '예'면 목록에서 선택"])
    if any(_undefined(i) for i in ctx.ings) or p.get("formula_known") == "concept_only" or not ctx.ings:
        rows.append(["처방 방식 (Formulation: exact / range / frame)", "처방 미확정 — 확정 처방 후 결정",
                     f"제품 정보 formula_known={p.get('formula_known') or '-'}", "외부필요", "제조사의 확정 처방(INCI·함량) 필요"])
    elif ctx.by_pct:
        rows.append(["처방 방식 (Formulation: exact / range / frame)",
                     "정확 농도 (Exact concentrations) — '처방' 시트" + ("" if show_pct else " (함량은 이 파일에서 제외)"),
                     "제품 정보 ingredients[].pct", "채움", "그 밖의 선택지: 농도 범위·사전 정의 프레임 포뮬레이션. 함량 단위 % w/w"])
    else:
        rows.append(["처방 방식 (Formulation: exact / range / frame)",
                     f"{TBC} 프레임 포뮬레이션 또는 정확 농도 — " + (
                         f"함량 미상 성분 {sum(_pct(i) is None for i in ctx.ings)}종이 있어 정확 처방 확보 필요"
                         if any(_pct(i) is not None for i in ctx.ings) else "함량이 없어 정확 처방 확보 필요"),
                     f"제품 정보 formula_known={p.get('formula_known') or '-'}", "외부필요",
                     "제조사에서 정확 처방 확보 → 정확 농도 또는 농도 범위로 신고"])
    cmr = _dedupe(f.get("message") for _, f in _findings(eu_vs)  # 카드 규칙 설명(CARD_*)은 빼고 성분 대조 결과만
                  if str(f.get("code") or "").startswith("ING_") and "CMR" in f"{f.get('message')} {f.get('evidence')}")
    rows.append(["CMR 물질 (CMR 1A/1B substances)", "\n".join(cmr) if cmr else "자동 대조상 CMR 1A/1B 표시 성분 없음",
                 "판정 findings(EU 부속서 대조)" if eu_vs else "EU 판정 없음", "확인필요",
                 "제13조(1)(g) — 이름·CAS/EC 번호. 원료 SDS로 최종 확인"])
    nano = [i.get("inci") for i in ctx.ings if "nano" in (i.get("inci") or "").lower()]
    rows.append(["나노물질 (Nanomaterials)", ", ".join(nano) if nano else "자동 확인상 '(nano)' 표기 성분 없음",
                 "제품 정보 ingredients[].inci", "확인필요",
                 "제13조(1)(f) — 원료 규격서(입자 크기)로 확인. 규제 외 나노물질은 제16조에 따라 출시 6개월 전 별도 신고"])
    labels = [x for x in docs if "label" in x.lower()]
    rows.append(["라벨·포장 사진 (Original labelling & packaging photo)", f"{TBC} EU 출시용 원본 라벨(PDF/JPG) + 포장 사진",
                 f"보유 서류: {', '.join(labels)} (국내용)" if labels else "보유 서류 없음", "확인필요",
                 "제13조(2) — 늦어도 출시 시점까지 제출. 문안은 수출 라벨 초안(label_draft) 참고"])

    rows = [[str(n)] + r for n, r in enumerate(rows, 1)]
    nxt = _xl_table(ws, 5, ["No", "항목 (Item)", "자동 채움 값 (Auto-filled value)", "출처 (Source)", "상태 (Status)",
                            "비고 (Notes)"], rows, [5, 34, 50, 34, 11, 52], status_col=5)
    nxt = _xl_lines(ws, nxt, "관련 판정 (Related verdict — EU CPNP)", _verdict_lines(cpnp_vs))
    _xl_lines(ws, nxt, "참고 (Notes)", [
        "근거: Regulation (EC) No 1223/2009 제13조(1)(a)~(h)·(2), CPNP 사용자 매뉴얼(Guide to Using CPNP, 2026-03-18판)",
        "상태: 채움 = 제품·회사 정보로 채움(검토 필요) / 확인필요 = 추정값 또는 자사 확인 / 외부필요 = RP·제조사 등 외부 자료 필요",
        "카테고리·물리적 형태는 제품 유형으로 추정한 값 — CPNP 선택 목록에서 확인",
    ])

    ws2 = _xl_sheet(wb, ctx, "처방 (Formulation)", "처방 (Formulation) — CPNP 정확 농도 신고용")
    headers = ["No", "INCI", "국문명 (Korean name)", "CAS"] + (["함량 % w/w (Conc.)"] if show_pct else []) + ["비고 (Notes)"]
    allergens = _allergens(ctx)
    frows = []
    for n, ing in enumerate(ctx.ordered, 1):
        pct = _pct(ing)
        note = "; ".join(x for x in ("알레르기 성분" if id(ing) in allergens else "", "처방 미확정" if _undefined(ing) else "",
                                     "함량 미상" if show_pct and pct is None else "") if x) or "-"
        row = [n, ing.get("inci") or TBC, ing.get("kr") or TBC, ing.get("cas") or "-"]
        if show_pct:
            row.append(pct if pct is not None else "미상")
        frows.append(row + [note])
    if show_pct:
        total = round(sum(_pct(i) or 0 for i in ctx.ings), 4)
        frows.append(["", "합계 (Total)", "", "", total, "100%와 차이가 나면 처방 확인"])
    nxt = _xl_table(ws2, 5, headers, frows, [5, 46, 34, 16, 16, 30] if show_pct else [5, 46, 34, 16, 30])
    _xl_lines(ws2, nxt, "참고 (Notes)", [
        "함량은 % w/w로 입력하고 % 기호는 쓰지 않는다(CPNP 매뉴얼)." if show_pct else
        ("함량은 include_pct=false 옵션으로 이 파일에서 제외했습니다." if ctx.by_pct else "제품 정보에 함량이 없습니다."),
        "정렬: 함량 내림차순" if ctx.by_pct else "정렬: 입력 순서(함량 미상)",
    ])
    return _xl_bytes(wb, title)


# ---------------------------------------------------------------- 4. 미국 MoCRA 제품 리스팅 항목표
def _mocra_sheet(ctx: _Ctx) -> bytes:
    p, company = ctx.product, ctx.company
    title = "미국 MoCRA 제품 리스팅 항목표 (US MoCRA product listing sheet)"
    wb = Workbook()
    ws = _xl_sheet(wb, ctx, "MoCRA 리스팅 항목", title, first=True)
    info = _type_info(p.get("product_type"))
    mfr = p.get("manufacturer") or {}
    fei = mfr.get("fei") or mfr.get("fei_number")
    us_vs = _juris_verdicts(ctx, {"US"})
    mocra_vs = [v for v in us_vs if any(k in str(v.get("cert_id") or "").upper() for k in ("MOCRA", "FDA"))]
    agent = _entity(company, "US_AGENT", "US")
    frag = any(norm_inci(i.get("inci")) == "parfum" for i in ctx.ings)
    colors = [i for i in ctx.ings if _is_color(i)]
    undefined = any(_undefined(i) for i in ctx.ings) or not ctx.ings
    summary = f"{len(ctx.ings)}종 — '전성분' 시트 참조" + ("; 향료(Fragrance) 포함" if frag else "") + \
        (f"; 색소 {len(colors)}종" if colors else "")
    rows = [
        ["시설 FEI 번호 (Facility registration number, FEI)", str(fei) if fei else f"{TBC} 제조시설(위탁제조사) FEI",
         "제품 정보 manufacturer.fei" if fei else f"제조사 {mfr.get('name') or TBC}", "채움" if fei else "외부필요",
         "§607(c) — 제조·가공 시설마다. FEI는 FDA FEI 포털에서 발급(통상 7~10영업일). 소규모 사업자 면제로 미등록이면 시설명·주소"],
        ["책임자 (Responsible person — name, contact number)",
         f"{company.get('name') or TBC} (라벨 'Distributed by' 기준) / 연락처 {TBC}", "회사 정보 name", "확인필요",
         "§604(4) — 라벨에 이름이 오른 제조·포장·유통업자. 미국 유통사 이름을 라벨에 쓰면 그 회사가 책임자"],
        ["라벨상 제품명 (Product name as on label)", p.get("name_en") or f"{TBC} 영문 제품명",
         "제품 정보 name_en" if p.get("name_en") else "입력 정보 없음", "채움" if p.get("name_en") else "확인필요",
         "라벨 표기와 글자 그대로 같게"],
        ["카테고리 (Cosmetic product category)", f"{info[3]} (추정)" if info else f"{TBC} 카테고리 코드",
         f"제품 유형 product_type={p.get('product_type') or '-'}", "확인필요", "FDA 등록·리스팅 가이던스 부록 A 코드표에서 확인"],
        ["전성분 (Ingredients incl. fragrances, flavors, colors)", f"{TBC} 처방 미확정" if undefined else summary,
         "제품 정보 ingredients[]", "외부필요" if undefined else "채움",
         "21 CFR 701.3 명칭(또는 일반 명칭). 향료·향미·색소 포함. 함량은 리스팅 항목이 아님"],
        ["해외시설 미국 대리인 (US agent for foreign facility)", agent.get("name") or f"{TBC} 미국 대리인(US Agent) 미지정",
         "회사 정보 local_entities" if agent else "입력 정보 없음", "확인필요" if agent else "외부필요",
         "§607(b) 시설 등록 항목 — 미국 거주·상주 개인 또는 법인(사서함·자동응답 불가)"],
        ["매년 갱신 (Annual listing update)", f"최초 리스팅 후 매년 갱신(변경 없으면 간이 갱신) — 다음 갱신일 {TBC}",
         "FD&C Act §607(c)(5)", "확인필요", "시설 등록은 2년마다 갱신(§607(a)(2)). 신규 제품은 판매 시작 후 120일 안에 리스팅"],
    ]
    rows = [[str(n)] + r for n, r in enumerate(rows, 1)]
    nxt = _xl_table(ws, 5, ["No", "항목 (Item)", "자동 채움 값 (Auto-filled value)", "출처 (Source)", "상태 (Status)",
                            "비고 (Notes)"], rows, [5, 36, 46, 30, 11, 56], status_col=5)
    nxt = _xl_lines(ws, nxt, "관련 판정 (Related verdict — US FDA/MoCRA)", _verdict_lines(mocra_vs or us_vs))
    _xl_lines(ws, nxt, "참고 (Notes)", [
        "근거: FD&C Act §607(MoCRA), FDA 'Registration and Listing of Cosmetic Product Facilities and Products' 가이던스",
        f"소규모 사업자(직전 3년 평균 미국 내 화장품 매출 100만 달러 미만, 물가 보정)는 등록·리스팅 면제 — 눈 점막 접촉·주사·내복용 등 "
        f"§612(b) 제품은 제외 {TBC}",
        "의약품을 겸하는 화장품(예: 자외선 차단제)은 화장품 리스팅 대상이 아님 / 색소·향료·향미·용량만 다른 제품은 한 리스팅으로 묶을 수 있음",
        "제출: Cosmetics Direct(SPL) 또는 종이 서식 FDA Form 5066·5067. 라벨 이미지 등은 선택 제출 항목",
    ])

    ws2 = _xl_sheet(wb, ctx, "전성분 (Ingredients)", "전성분 (Ingredients) — 미국 라벨 명칭 기준, 함량 미포함")
    irows = []
    for n, ing in enumerate(ctx.ordered, 1):
        kind = "향료 (Fragrance)" if norm_inci(ing.get("inci")) == "parfum" else "색소 (Color)" if _is_color(ing) else "일반"
        note = "; ".join(x for x in ("향료 유래 알레르기 성분" if ing.get("role") == "allergen_from_fragrance" else "",
                                     "처방 미확정" if _undefined(ing) else "") if x) or "-"
        irows.append([n, _label_name(ing, "US"), ing.get("kr") or TBC, kind, note])
    nxt = _xl_table(ws2, 5, ["No", "Ingredient (US label name)", "국문명 (Korean name)", "구분 (Type)", "비고 (Notes)"], irows,
                    [5, 46, 34, 16, 30])
    _xl_lines(ws2, nxt, "참고 (Notes)", ["정렬: 함량 내림차순(함량 값은 싣지 않음)" if ctx.by_pct else "정렬: 입력 순서(함량 미상)"])
    return _xl_bytes(wb, title)


# ---------------------------------------------------------------- 5. 인증별 부족 사항 체크리스트
def _gap_checklist(ctx: _Ctx) -> bytes:
    d = _Docx(ctx, "인증별 부족 사항 체크리스트", "Gap Checklist by Certification")
    vs = sorted(ctx.verdicts, key=lambda v: (STATUS_ORDER.get(v.get("status"), 9), str(v.get("cert_id") or "")))
    d.h("판정 요약 (Verdict summary)")
    if not vs:
        d.p(f"판정 결과가 없습니다 — 인증 카드와 판정 결과를 확인하세요 {TBC}")
        return d.bytes()
    d.table(["인증 (Certification)", "관할 (Jurisdiction)", "판정 (Status)", "불가 (Fail)", "조건부 (Cond.)"],
            [[f"{v.get('cert_name') or v.get('cert_id')} ({v.get('cert_id')})", v.get("jurisdiction") or "-",
              v.get("status") or "-", *map(str, _gap_counts(v))] for v in vs], [82, 24, 24, 22, 22])

    acts: dict[str, dict] = defaultdict(lambda: {"certs": [], "items": [], "owner": ""})
    for v, f in _findings(vs, {"fail", "cond"}):
        e = acts[_action(f)]
        e["certs"].append(v.get("cert_id"))
        e["items"].append(f.get("message"))
        e["owner"] = e["owner"] or _owner(f)
    for e in acts.values():  # 다 모은 뒤 한 번만 중복 제거(항목마다 하면 같은 조치가 많을 때 시간이 세제곱으로 는다)
        e["certs"], e["items"] = _dedupe(e["certs"]), _dedupe(e["items"])
    # 조치 문구가 없는 항목('[확인 필요] 조치 정의 필요')은 서로 다른 일이므로 공통 조치로 묶지 않는다
    common = sorted(((a, e) for a, e in acts.items() if len(e["certs"]) >= 2 and not a.startswith(TBC)),
                    key=lambda x: (-len(x[1]["certs"]), x[0]))
    d.h("1. 여러 인증에 공통되는 조치 — 먼저 처리 (Common actions)")
    if common:
        d.p("같은 조치 문구가 2개 이상 인증에 나온 항목입니다. 한 번 처리하면 여러 인증의 부족 사항이 함께 줄어듭니다.", size=9)
        rows = []
        for a, e in common:
            items = e["items"][:6] + ([f"외 {len(e['items']) - 6}건"] if len(e["items"]) > 6 else [])
            rows.append([BOX, a, f"{len(e['certs'])}개: " + ", ".join(e["certs"]), "\n".join(items), e["owner"]])
        d.table(["확인 (Done)", "조치 (Action)", "관련 인증 (Certifications)", "세부 항목 (Details)", "담당 (Owner)"], rows,
                [15, 44, 38, 57, 20])
    else:
        d.p("여러 인증에 공통되는 조치가 없습니다.")

    d.h("2. 인증별 부족 사항 (Gaps by certification)")
    gaps = [v for v in vs if any(f.get("level") in ("fail", "cond") for f in v.get("findings") or [] if isinstance(f, dict))]
    for v in gaps:
        fs = sorted((f for f in v.get("findings") or [] if isinstance(f, dict) and f.get("level") in ("fail", "cond")),
                    key=lambda f: f.get("level") != "fail")
        d.h(f"{v.get('cert_name') or v.get('cert_id')} ({v.get('cert_id')}) — {v.get('jurisdiction') or '-'} · {v.get('status')}", 2)
        d.table(["확인 (Done)", "구분 (Type)", "부족 사항 (Gap)", "조치 (Action)", "담당 (Owner)", "근거 (Evidence)"],
                [[BOX, "불가" if f.get("level") == "fail" else "조건부", f.get("message") or "-", _action(f), _owner(f),
                  f.get("evidence") or "-"] for f in fs], [15, 14, 52, 43, 20, 30])
    if not gaps:
        d.p("불가·조건부 항목이 없습니다.")

    d.h("3. 참고 (Notes)")
    for status in (STATUS_PASS, STATUS_NA):
        names = [f"{v.get('cert_name') or v.get('cert_id')}" for v in vs if v.get("status") == status]
        if names:
            d.bullet(f"{status}({len(names)}): " + ", ".join(names))
    d.bullet(f"담당 구분: {' / '.join(OWNERS)} — 판정 코드·조치 문구로 추정한 값이므로 실제 담당자를 지정하세요.")
    d.bullet("불가 = 재처방해야 통과 / 조건부 = 재처방 없이 서류·현지 책임자·문구·시험 보완으로 통과 (모두 예비 판정)")
    return d.bytes()


# ---------------------------------------------------------------- 6. 중기부 해외규격인증 지원사업 신청 준비 요약
def _support_program(ctx: _Ctx) -> bytes:
    d = _Docx(ctx, "중기부 해외규격인증 지원사업 신청 준비 요약", "MSS Overseas Certification Support — Application Prep")
    t = ctx.today
    d.h("1. 사업 개요 (Program overview)")
    d.table(["항목 (Item)", "내용 (Details)"], [
        ["지원 내용 (Support)", f"해외규격인증 획득 비용 지원 — {SUPPORT_RATE}"],
        ["일반지원 모집 (General support)",
         f"2026년 3차 공고: {GENERAL_OPEN.isoformat()} ~ {GENERAL_CLOSE.isoformat()} ({_dday(t, GENERAL_CLOSE)})"],
        ["전략지원 (Strategic support)", f"전략지원 KTR 공고: 마감 {STRATEGIC_CLOSE.isoformat()} ({_dday(t, STRATEGIC_CLOSE)})"],
        ["화장품 관련 전략인증 (Strategic certifications)", STRATEGIC_COSMETIC],
        ["목록 밖 인증 (Unlisted certifications)", "일반지원 583개 목록 밖 인증은 '비공고 규격인증'으로 신청 가능 — 사업 가이드 별첨 "
                                               "1-4호 작성, 운영위원회 심의(단순 마케팅·기업 홍보용 인증은 제외)"],
        ["신청처 (Where to apply)", "smes.go.kr/globalcerti"],
    ], [48, 126])

    d.h("2. 판정 대상 중 지원 대상 인증 (Eligible certifications)")
    targets = []
    for v in ctx.verdicts:
        m = _card_meta(ctx, v)
        strategic, nos = m.get("strategic_kr") is True, _nos(m.get("general_kr_no"))
        if strategic or nos:
            targets.append((v, m, strategic, nos))
    # 신청 준비 순서: 전략 → 일반, 그 안에서 통과 가능 → 조건부 → 불가 → 해당 없음
    readiness = {STATUS_PASS: 0, STATUS_COND: 1, STATUS_FAIL: 2, STATUS_NA: 3}
    targets.sort(key=lambda x: (not x[2], readiness.get(x[0].get("status"), 9), str(x[0].get("cert_id") or "")))
    advice = {STATUS_PASS: "현재 상태로 신청 가능 — 견적서·신청서 준비", STATUS_COND: "보완 항목 처리 계획과 함께 신청",
              STATUS_FAIL: "재처방 후 신청 권장", STATUS_NA: "이 제품은 대상 아님 — 신청 제외"}
    if targets:
        general = _general_list()
        rows = []
        for v, m, strategic, nos in targets:
            kinds = (["전략인증 (KTR 공고)"] if strategic else []) + \
                [f"일반지원 No.{n}" + (f" ({general[n]})" if n in general else "") for n in nos]
            if m.get("support_rate"):
                kinds.append(f"지원율: {m['support_rate']}")
            nf, nc = _gap_counts(v)
            gaps = sorted(_findings([v], {"fail", "cond"}), key=lambda vf: vf[1].get("level") != "fail")
            top = _dedupe(_short(f.get("message")) for _, f in gaps)[:3]
            rec = advice.get(v.get("status"), TBC) + ("\n주요 보완: " + "; ".join(top) if top else "")
            rows.append(["전략" if strategic else "일반", f"{v.get('cert_name') or v.get('cert_id')} ({v.get('cert_id')})",
                         v.get("jurisdiction") or "-", v.get("status") or "-", f"불가 {nf} / 조건부 {nc}", "\n".join(kinds), rec])
        d.table(["구분 (Type)", "인증 (Certification)", "관할", "판정 (Status)", "보완 (Gaps)", "지원 구분·목록 번호 (Program)",
                 "권장 (Advice)"], rows, [13, 36, 17, 15, 19, 36, 38])
    else:
        d.p("판정 대상 중 전략인증(strategic_kr)·일반지원 목록 번호(general_kr_no)가 있는 인증이 없습니다. "
            f"인증 카드의 지원 대상 정보를 확인하세요 {TBC}")
    listed = {id(x[0]) for x in targets}
    unlisted = _dedupe(f"{v.get('cert_name') or v.get('cert_id')} — {v.get('status')}" for v in ctx.verdicts
                       if v.get("status") != STATUS_NA and id(v) not in listed
                       and re.search(r"비공고|목록에 없음", str(_card_meta(ctx, v).get("support_rate") or "")))
    if unlisted:
        d.p("목록 밖 인증 — 비공고 규격인증 신청 후보 (운영위원회 심의, 지원 여부 미정)", bold=True, size=9)
        for u in unlisted:
            d.bullet(u)

    d.h("3. 신청 전 준비물 체크리스트 (Pre-application checklist)")
    docs = [str(x) for x in (ctx.product.get("documents") or []) + (ctx.company.get("documents") or [])]

    def has(*kws: str) -> list[str]:
        return [x for x in docs if any(k in x.lower() for k in kws)]

    product_docs = has("ingredient", "formula", "brochure", "leaflet", "catalog")
    tests = has("test")
    certs = ctx.company.get("company_certs") or {}
    history = ctx.company.get("export_history") or []
    eligible = [v for v, _, _, _ in targets if v.get("status") != STATUS_NA]
    nf = sum(_gap_counts(v)[0] for v in eligible)
    nc = sum(_gap_counts(v)[1] for v in eligible)
    fin = ctx.company.get("financial") if isinstance(ctx.company.get("financial"), dict) else {}
    impairment = str(fin.get("capital_impairment") or "")
    fin_text = (f"자본잠식: {IMPAIRMENT.get(impairment, impairment)} ({fin.get('fiscal_year') or '-'} 회계연도)"
                if impairment else TBC)
    if impairment == "complete":
        d.p("주의: 회사 정보에 완전자본잠식으로 입력되어 있습니다. 준비물보다 먼저 공고문의 신청 제외 요건에 해당하는지 확인하세요.",
            bold=True, size=9)
    d.table(["확인 (Done)", "준비물 (Item)", "자동 확인 (Auto check)", "비고 (Notes)"], [
        [BOX, "사업자등록증 (Business registration)", TBC, ""],
        [BOX, "중소기업 확인서 (SME confirmation)", TBC, "중소기업현황정보시스템(sminfo.mss.go.kr) 발급"],
        [BOX, "전년도 재무제표·매출액 증빙 (Prior-year financial statements)", TBC, "지원율(50~70%) 산정 기준"],
        [BOX, "재무 상태 (Financial status)", fin_text, f"자본잠식 등 신청 제외 요건 해당 여부는 공고문에서 확인 {TBC}"],
        [BOX, "수출 실적 증빙 (Export record)", f"수출 이력 {len(history)}건 입력됨" if history else f"{TBC} 수출 이력 없음",
         "수출실적증명서 등"],
        [BOX, "인증기관·시험기관 견적서 (Quotation)", TBC, "인증별 비용 견적 — 지원금 산정 근거"],
        [BOX, "대상 제품 자료 (Product dossier)", "보유: " + ", ".join(product_docs) if product_docs else TBC,
         "전성분표·제품 사진·카탈로그. 영문 전성분은 INCI 전성분표 초안(inci_list) 사용"],
        [BOX, "시험성적서 (Test reports)", "보유: " + ", ".join(tests) if tests else TBC, ""],
        [BOX, "기업 인증 현황 (Company certifications)",
         ", ".join(f"{CERT_KO.get(k, k)}: {_cert_state(s)}" for k, s in certs.items()) or TBC, "가점·우대 여부는 공고문에서 확인"],
        [BOX, "인증별 보완 계획 (Gap plan)", f"지원 대상 인증 {len(eligible)}개 — 불가 {nf}건 · 조건부 {nc}건",
         "인증별 부족 사항 체크리스트(gap_checklist) 참고"],
    ], [15, 56, 50, 53])
    d.p("준비물은 일반적인 신청 서류 기준입니다. 공고문·사업 가이드(운영지침)에서 최종 확인하세요.", size=9)

    d.h("4. 출처 (Sources)")
    d.bullet(f"중소벤처기업부 해외규격인증 지원사업 2026년 3차 공고(모집 {GENERAL_OPEN:%m-%d}~{GENERAL_CLOSE:%m-%d}) — "
             "붙임 1 국가별 일반지원 해외규격인증 지원대상(583개)")
    d.bullet(f"전략인증 지원 KTR 공고(마감 {STRATEGIC_CLOSE:%m-%d}) — smes.go.kr/globalcerti/info/ktrInfo.do")
    d.bullet(f"지원율: {SUPPORT_RATE}")
    return d.bytes()


BUILDERS = {"inci_list": _inci_list, "label_draft": _label_draft, "cpnp_sheet": _cpnp_sheet, "mocra_sheet": _mocra_sheet,
            "gap_checklist": _gap_checklist, "support_program": _support_program}
