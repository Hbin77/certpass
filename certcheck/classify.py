"""인증·등록별 사전 적합성 판정 엔진.

등급 정의(발표·화면 공통)
- 불가: 재처방해야만 통과 가능 (금지 성분, 한도 초과, 비건 위반·천연·유기농 공통 비허용 성분 등)
- 조건부: 재처방 없이 통과 가능 — 서류 보완, 현지 책임자 지정, 표방 문구 수정, 시험, 원료 공급사 증명, 미확인 데이터 확인
- 통과 가능: 현재 처방·보유 서류로 통과 가능
- 해당 없음: 이 제품 유형·표방에 적용되지 않음
판정은 예비 판정이며 근거(조문·목록 항목)를 함께 남긴다.
"""
from __future__ import annotations

import fnmatch
import re
from functools import lru_cache
from dataclasses import asdict, dataclass, field
from datetime import date

from . import STATUS_COND, STATUS_FAIL, STATUS_NA, STATUS_ORDER, STATUS_PASS
from .data import RegIndex
from .normalize import norm_inci, split_cas

from rapidfuzz import fuzz, process

# 카드의 성분 규칙 관할 → 통합표에서 실제로 쓸 관할. EU 준용 국가는 EU로 대리 판정하고 '대리' 표시를 남긴다.
MFDS_JURIS = {"KR", "ASEAN", "BR", "AR", "CA", "US"}  # 식약처 API 목록으로 판정하는 관할
PROXY = {"UK": "EU", "ASEAN": "EU", "MY": "EU", "ID": "EU", "TH": "EU", "PH": "EU", "VN": "EU", "SG": "EU",
         "SA": "EU", "AE": "EU", "EAEU": "EU", "TR": "EU", "IN": "EU", "EG": "EU", "MA": "EU", "NZ": "EU",
         "AU": "EU", "CA": "EU", "BR": "EU", "AR": "EU", "CO": "EU", "PE": "EU", "MX": "EU", "IR": "EU",
         "MM": "EU", "KH": "EU", "GLOBAL": "EU"}

CLAIM_KEYWORDS = {"미백": "whitening", "브라이트닝": "whitening", "주름": "anti_wrinkle", "자외선": "sunscreen",
                  "어린이": "children", "영유아": "children", "염모": "hair_dye", "탈모": "hair_loss",
                  "여드름": "acne", "whitening": "whitening", "wrinkle": "anti_wrinkle", "sunscreen": "sunscreen"}

CYCLIC_SILOXANES = {"cyclotetrasiloxane": "D4", "cyclopentasiloxane": "D5", "cyclohexasiloxane": "D6",
                    "cyclomethicone": "D4/D5/D6 혼합"}

ANIMAL_HINTS = {  # 속성표가 없을 때 쓰는 보수적 추정 (heuristic)
    "lactose": "not_ok", "milk": "not_ok", "pearl": "not_ok", "honey": "not_ok", "beeswax": "not_ok",
    "cera alba": "not_ok", "lanolin": "not_ok", "collagen": "depends_on_source", "keratin": "depends_on_source",
    "carmine": "not_ok", "squalane": "depends_on_source", "squalene": "depends_on_source",
    "glycerin": "depends_on_source", "stearate": "depends_on_source", "stearic": "depends_on_source",
    "cetearyl alcohol": "depends_on_source", "cetyl alcohol": "depends_on_source", "ceramide": "depends_on_source",
    "behenyl": "depends_on_source", "arachidyl": "depends_on_source", "isostearate": "depends_on_source",
    "triglyceride": "depends_on_source", "oleate": "depends_on_source", "lauroyl": "depends_on_source",
    "cocoyl": "ok", "lactylate": "depends_on_source", "hyaluronate": "depends_on_source",
}


GAP_TYPES = {  # 부족 사항 분류(화면 표시용). 앞에서부터 접두사 일치
    "ING_BANNED_WITH_EXCEPTION": "성분 확인", "ING_CN_INVENTORY_CHECK": "성분 확인", "ING_BANNED_CONDITIONAL": "성분 확인", "ING_EXCLUDED_CHECK": "성분 확인", "ING_EXCLUDED": "재처방", "ING_BANNED": "재처방", "ING_OVER_LIMIT": "재처방", "ATTR_": "원료 증명", "SILOXANE_BANNED": "재처방",
    "SILOXANE_RINSEOFF": "재처방", "SILOXANE_D4": "재처방", "SILOXANE_SUNSET": "재처방(기한)", "SILOXANE_MIX": "성분 확인",
    "SILOXANE_PCT": "처방 확정", "DOC_DRAFTABLE": "서류(자동 초안)", "DOC_": "서류", "TEST_": "시험",
    "LOCAL_ENTITY": "현지 책임자", "LABEL_": "라벨", "ALLERGEN_": "라벨", "CLAIM_": "표방 문구",
    "HALAL_FACILITY": "제조소 확인", "FORMULA_": "처방 확정", "ING_UNDEFINED": "처방 확정",
    "ING_": "성분 확인", "PACKAGING": "포장재", "PROP65": "성분 확인", "COMPANY_": "회사 요건",
}


# 시험 항목 → 그 시험을 담았다고 볼 보유 서류 ID 패턴. 국내 완제품 성적서는 중금속·미생물·pH 등을 담는다 (추정)
GENERAL_TEST_REPORTS = ("finished_product_test_report*", "bulk_test_report*", "test_report_*")
TEST_EVIDENCE = {
    "stability": ("stability_test*",), "challenge_test": ("challenge_test*", "preservative_efficacy*"),
    "patch_test": ("skin_irritation_test*", "patch_test*"), "packaging_compatibility": ("packaging_compatibility*",),
    **{t: GENERAL_TEST_REPORTS for t in ("heavy_metals", "microbiology", "microbial_limit", "physicochemical")},
}


def gap_type(code: str) -> str:
    for k, g in GAP_TYPES.items():
        if code.startswith(k):
            if k == "ATTR_" and code.endswith("_FAIL"):
                return "재처방"
            return g
    return "기타"


@dataclass
class Finding:
    level: str          # fail / cond / info / na
    code: str
    message: str
    evidence: str = ""
    action: str = ""


@dataclass
class Verdict:
    product_id: str
    product_name: str
    cert_id: str
    cert_name: str
    jurisdiction: str
    kind: str
    status: str = STATUS_PASS
    findings: list[Finding] = field(default_factory=list)
    confidence: float = 1.0
    features: dict = field(default_factory=dict)
    gaps: dict = field(default_factory=dict)

    def add(self, level: str, code: str, message: str, evidence: str = "", action: str = "") -> None:
        self.findings.append(Finding(level, code, message, evidence, action))

    def finalize(self) -> "Verdict":
        gaps: dict[str, int] = {}
        for f in self.findings:
            if f.level not in ("fail", "cond"):
                continue
            g = gap_type(f.code)
            gaps[g] = gaps.get(g, 0) + 1
        self.gaps = gaps
        levels = {f.level for f in self.findings}
        if "na" in levels and not levels & {"fail", "cond"}:
            self.status = STATUS_NA
        elif "fail" in levels:
            self.status = STATUS_FAIL
        elif "cond" in levels:
            self.status = STATUS_COND
        else:
            self.status = STATUS_PASS
        return self

    def to_dict(self) -> dict:
        d = asdict(self)
        d["findings"] = [asdict(f) for f in self.findings]
        return d


# ---------------------------------------------------------------- 공통 도우미
_PCT_RE = re.compile(r"(\d{1,6}(?:[.,]\d{1,6})?)\s*(?:%|g\s*/\s*100\s*g|ｇ／100ｇ)")
_JP_TOTAL_RE = re.compile(r"合計量として\s*(\d{1,6}(?:\.\d{1,6})?)(?!\s*国際単位)")


def parse_pcts(text: str) -> list[float]:
    """한도 표기의 수치 전부(%·g/100g, 일본 '合計量として1.0'). '(a) 2,0 % (b) 3,0 %' → [2.0, 3.0]"""
    if not text:
        return []
    vals = [float(x.replace(",", ".")) for x in _PCT_RE.findall(text)]
    vals += [float(x) for x in _JP_TOTAL_RE.findall(text)]
    return vals


def parse_pct(text: str) -> float | None:
    """첫 한도 수치(하위 호환). 없으면 None."""
    vals = parse_pcts(text)
    return vals[0] if vals else None


def product_claims(p: dict) -> set[str]:
    return set(p.get("claims") or []) | set(p.get("functional_kr") or [])


def ingredient_key(ing: dict) -> str:
    return norm_inci(ing.get("inci"))


def _doc_match(pattern: str, have: list[str]) -> str | None:
    pat = pattern.lower()
    for d in have:
        dl = d.lower()
        if ("*" in pat and fnmatch.fnmatch(dl, pat)) or (pat in dl):
            return d
    return None


def doc_status(hints: list[str], have: list[str], p: dict, company: dict) -> tuple[str, str]:
    """서류 충족 판정. 반환 (have|draftable|missing, 근거).
    힌트 문법: 'formula_known:<값>', 'manufacturer.certs:<인증>', 'company.local_entities:<키>',
    'company.role_kr:<문자열>', 'draft_from:<서류패턴>', 그 밖은 보유 서류 패턴(와일드카드 *)."""
    draft_src = None
    for h in hints or []:
        if ":" in h and not h.startswith("draft_from:"):
            key, val = h.split(":", 1)
            if key == "formula_known" and p.get("formula_known") == val:
                return "have", h
            if key == "manufacturer.certs" and val.lower() in " ".join(p.get("manufacturer", {}).get("certs") or []).lower():
                return "have", h
            if key == "company.local_entities" and val in (company.get("local_entities") or {}):
                return "have", h
            if key == "company.role_kr" and val in (company.get("role_kr") or ""):
                return "have", h
            continue
        if h.startswith("draft_from:"):
            m = _doc_match(h.split(":", 1)[1], have)
            if m and not draft_src:
                draft_src = m
            continue
        m = _doc_match(h, have)
        if m:
            return "have", m
    if draft_src:
        return "draftable", draft_src
    return "missing", ""


def leave_on(p: dict) -> bool:
    return (p.get("application") or "").startswith("leave")


# ---------------------------------------------------------------- 검사 단계
KW_CLAIM_RE = re.compile(r"\[kw:claim\(([^)]*)\)\]")


def check_applicability(v: Verdict, card: dict, p: dict) -> bool:
    """적용 여부. 자유 문장에서 키워드를 추측하지 않고, 구조화된 표시만 쓴다.
    - applies_to.product_types에 'cosmetic'이 있으면 모든 화장품
    - 아니면 product_types를 제품 유형 또는 표방(미백 등)으로 보고 제품과 겹치면 적용
    - applies_to.claims_any 또는 condition 안의 [kw:claim(a|b)] 가 있으면 그 표방이 있어야 적용
    """
    ap = card.get("applies_to") or {}
    types = ap.get("product_types") or ["cosmetic"]
    mine = {p.get("product_type"), p.get("application")} | product_claims(p) | {c.replace("_planned", "") for c in product_claims(p)}
    if "cosmetic" not in types and not (mine & set(types)):
        v.add("na", "SCOPE_TYPE", f"적용 대상({', '.join(types)})에 해당하지 않음")
        return False
    cond = ap.get("condition") or ""
    claims_any = list(ap.get("claims_any") or [])
    for m in KW_CLAIM_RE.findall(cond):
        claims_any += [c.strip() for c in m.split("|") if c.strip()]
    if claims_any and not (mine & set(claims_any)):
        v.add("na", "SCOPE_CLAIM", f"적용 표방({', '.join(claims_any)})이 없음")
        return False
    return True


def _pct_txt(x: float) -> str:
    """화면용 % 숫자: 소수 첫째 자리까지, 끝 0은 뺀다(8.3333 → 8.3, 5.0 → 5)."""
    return f"{x:.1f}".rstrip("0").rstrip(".")


def pct_bounds(ings: list[dict]) -> list[tuple[float, float] | None]:
    """전성분 표시 순서로 함량을 모르는 성분의 (최소, 최대) %를 구한다.
    표시 규칙(국내·EU): 1%를 넘는 성분은 함량 많은 순으로 먼저 적고, 1% 이하는 그 뒤에 순서 없이 적는다.
    - 최대: 이 성분이 1%를 넘으면 위의 모든 성분보다 적으므로 min(위 성분의 알려진 함량, 100/(순번)), 아니면 1% → 둘 중 큰 값
    - 최소: 아래에 1%를 넘는 함량이 알려진 성분이 있으면 이 성분도 1% 초과 구역이라 그 값 이상
    함량이 알려진 성분, 또는 알려진 값끼리 순서가 맞지 않는(데이터 불일치) 제품은 None."""
    known = [(i, x["pct"]) for i, x in enumerate(ings) if isinstance(x.get("pct"), (int, float))]
    big = [q for _, q in known if q > 1]
    if any(a < b for a, b in zip(big, big[1:])):  # 1% 초과 구역의 순서가 이미 어긋나면 순서로 추론하지 않는다
        return [None] * len(ings)
    out: list[tuple[float, float] | None] = []
    for i, x in enumerate(ings):
        if isinstance(x.get("pct"), (int, float)):
            out.append(None)
            continue
        above = [q for j, q in known if j < i]
        below = [q for j, q in known if j > i and q > 1]
        hi = max(1.0, min(min(above, default=100.0), 100.0 / (i + 1)))
        lo = max(below, default=0.0)
        out.append((round(lo, 4), round(hi, 4)) if lo <= hi else None)
    return out


@lru_cache(maxsize=64)
def _banned_names(reg_id: int, juris: str) -> tuple[str, ...]:
    reg = _REG_BY_ID[reg_id]
    return tuple(sorted({k for (j, k), rows in reg.by_key.items()
                         if j == juris and len(k) > 5 and any(r.list_type == "banned" for r in rows)}))


_REG_BY_ID: dict[int, RegIndex] = {}


@lru_cache(maxsize=20000)
def _suspect(reg_id: int, juris: str, key: str) -> tuple[str, float] | None:
    names = _banned_names(reg_id, juris)
    if not names or len(key) < 6:
        return None
    hit, score, _ = process.extractOne(key, names, scorer=fuzz.ratio)
    return (hit, round(score / 100, 2)) if 90 <= score < 100 else None  # 100이면 같은 이름(금지 판정 쪽)


_HANGUL = re.compile(r"[가-힣]")
SOURCE_KR = "식약처 화장품 원료성분정보(data.go.kr 15111774) 자모 유사도 대조"


def kr_fuzzy(name: str) -> dict | None:
    from .names import kr_fuzzy as _kf  # names는 data·normalize만 import → 순환 없음
    return _kf(name)


@lru_cache(maxsize=4)
def _cas_index(reg_id: int) -> dict[str, tuple[str, ...]]:
    """INCI 키 → CAS: 식약처 원료성분사전 + 모든 관할 목록에서 이름(INCI)과 CAS가 함께 적힌 행."""
    from .names import kr_dict
    reg = _REG_BY_ID[reg_id]
    out: dict[str, set[str]] = {}
    for h in kr_dict().values():
        for c in split_cas(h.get("cas")):
            out.setdefault(norm_inci(h.get("inci")), set()).add(c)
    for (_, k), rows in reg.by_key.items():  # 목록의 이름 키(INCI 또는 영문 물질명)와 그 행의 CAS
        for r in rows:
            if len(r.cas) == 1:
                out.setdefault(k, set()).update(r.cas)
    return {k: tuple(sorted(v)) for k, v in out.items() if k and len(v) <= 3}


def cas_by_name(reg: RegIndex, inci: str) -> list[str]:
    """CAS가 없는 입력 성분의 CAS 후보(정확히 같은 INCI명 기준, 후보가 4개 이상이면 모호해 쓰지 않음)."""
    _REG_BY_ID[id(reg)] = reg
    return list(_cas_index(id(reg)).get(norm_inci(inci), ()))


def banned_suspect(reg: RegIndex, juris: str, inci: str) -> tuple[str, float] | None:
    """정확히 일치하지 않지만 금지 성분 이름과 90% 이상 같은 표기(오탈자 의심). 식약처 원료성분사전에 있는 정상 원료명은 제외."""
    from .names import inci_to_kr  # names는 data·normalize만 import → 순환 없음
    key = norm_inci(inci)
    if not key or key in inci_to_kr():
        return None
    _REG_BY_ID[id(reg)] = reg
    return _suspect(id(reg), juris, key)


def check_ingredients(v: Verdict, card: dict, p: dict, reg: RegIndex, attrs: dict | None = None) -> None:
    rules = (card.get("ingredient_rules") or "none").upper()
    if rules in ("NONE", ""):
        return
    juris = rules if rules in reg.jurisdictions else PROXY.get(rules, rules)
    proxied = juris != rules
    # 통합표에 없는 나라가 EU 목록을 대용으로 적은 카드(README 규약). EU·영국·이집트(EU 부속서 채택)만 EU 목록으로 확정 판정
    substitute = rules == "EU" and card.get("jurisdiction") not in ("EU", "UK", "EG")
    if substitute and card.get("jurisdiction") in reg.jurisdictions:  # 식약처 API로 현지 목록이 생긴 나라
        juris, rules, substitute = card["jurisdiction"], card["jurisdiction"], False
    if juris in MFDS_JURIS:
        v.add("info", "ING_SOURCE_MFDS", f"{juris} 성분 규정은 식약처 화장품 사용제한 원료정보(국가별) 기준 — 현지 최신 고시와 차이 확인",
              "식약처 화장품 사용제한 원료정보 API(data.go.kr 15111772)")
        v.confidence = min(v.confidence, 0.9)
    if juris not in reg.jurisdictions:
        v.add("cond", "ING_NO_DATA", f"{rules} 성분 규정 데이터 미보유 — 현지 목록 대조 필요", action="현지 금지·제한 목록으로 성분 대조")
        v.confidence = min(v.confidence, 0.5)
        return
    if proxied or substitute:
        local = rules if proxied else card.get("jurisdiction")
        v.add("info", "ING_PROXY", f"{local} 성분 규정은 {juris} 목록으로 대리 판정(유사 규정) — 현지 차이 확인 필요")
        v.confidence = min(v.confidence, 0.75)
    if juris == "JP" and not reg.has_inci.get("JP"):
        v.add("cond", "ING_JP_NAME_ONLY", "일본 化粧品基準 목록이 일본어 성분명만 있어 영문 전성분 대조가 불완전 — 일본어 성분명 매핑 필요",
              "化粧品基準(告示331号)", "일본어 성분명(JCIA 표시명칭)으로 재대조")
        v.confidence = min(v.confidence, 0.6)
    if juris == "JP":
        v.add("info", "ING_JP_SOURCE", "일본 化粧品基準 2016년판 목록 기준(2024 개정 2건 미반영), 의약품 성분 배합 금지(총칙)는 목록으로 판정 불가")
        v.confidence = min(v.confidence, 0.9)
    if juris == "CN":
        v.add("info", "ING_CN_SPEC_2015", "중국 금지·제한 목록은 식약처 화장품 사용제한 원료정보(data.go.kr 15111772) 기준 — 최신 NMPA 공고(2021 제74호·2026 제99호 등)로 최종 확인 필요")
        v.confidence = min(v.confidence, 0.8)
        if p.get("ingredients"):
            # IECIC(기존 사용 화장품 원료 목록) 원문은 운영진 검토에서 저작권 확인 불가로 넣지 않았다 → 등재 여부는 사용자가 원문으로 확인
            v.add("cond", "ING_CN_INVENTORY_CHECK", "중국 기존 사용 화장품 원료 목록(IECIC) 등재 확인 필요 — 목록에 없는 성분은 신원료 등록 대상",
                  "NMPA 已使用化妆品原料目录(2021年版 및 이후 공고)", "전성분을 IECIC 표준 중문명으로 대조, 미등재 성분은 신원료 신고")
    has_inventory = any(k.startswith(f"{juris}:inventory") for k in reg.counts)
    first = len(v.findings)
    bounds = pct_bounds(p.get("ingredients", []))
    for idx, ing in enumerate(p.get("ingredients", [])):
        inci, cas = ing.get("inci") or "", split_cas(ing.get("cas"))
        if "TBD" in inci or ing.get("role") == "key_concept":
            v.add("cond", "ING_UNDEFINED", f"처방 미확정 성분: {ing.get('kr')} — 처방 확정 후 재판정", action="처방서(INCI·함량) 확보")
            continue
        hits = reg.lookup(juris, inci, cas)
        if not cas and (cas2 := cas_by_name(reg, inci)):
            # CAS가 비어 있으면 성분명(정확히 같은 INCI)으로 식약처 원료사전·다른 관할 목록의 CAS를 찾아 한 번 더 대조해 합친다.
            # 이름으로 제한 행만 걸리고 금지 행은 CAS로만 맞춰지는 경우(현지어 이름 목록)가 있어 이름 결과가 있어도 함께 본다
            seen = {id(r) for r, _ in hits}
            hits = hits + [(r, how) for r, how in reg.lookup(juris, inci, cas2) if id(r) not in seen]
        types = {r.list_type for r, _ in hits}
        pct = ing.get("pct")
        key = ingredient_key(ing)
        other_annex = bool(types & {"restricted"} or any(t.startswith("allowed_") for t in types))
        limited = []  # (행, 근거) — 제한·허용 목록 행은 용도 판단을 위해 모아서 본다
        for r, how in hits:
            ref = f"{r.jurisdiction} {r.source_ref} ({r.source_file}, {r.last_update})".strip()
            if r.list_type == "banned":
                text = f"{r.name} {r.conditions}".lower()
                if any(x in text for x in CONDITIONAL_BAN):
                    v.add("cond", "ING_BANNED_CONDITIONAL", f"{inci}: 조건이 붙은 금지({r.name[:70]}) — 조건(과산화물가 등) 충족 여부를 원료 성적서로 확인", ref,
                          "원료사 성적서로 조건 확인(조건을 넘으면 재처방)")
                elif key == "cyclomethicone":
                    v.add("cond", "ING_CYCLOMETHICONE_MIX", f"{inci}: D4(금지)·D5·D6 혼합 명칭 — D4 미포함과 D5·D6 함량을 원료 성적서로 확인", ref,
                          "원료사 구성비·성적서 확보(D4가 있으면 재처방)")
                elif (any(x in text for x in NATURAL_EXCEPTION) and any(w in key for w in NATURAL_WORDS)) \
                        or any(x in text for x in REFINING_EXCEPTION):
                    v.add("cond", "ING_BANNED_WITH_EXCEPTION", f"금지 목록 예외조건 대상: {inci} — {r.name[:60]} {r.conditions[:100]}", ref,
                          "예외 조건(천연 정유의 정상 함량, 정제 이력 등) 충족을 원료 성적서로 확인")
                elif other_annex and ("except" in text or "exception" in text or "除" in text):
                    v.add("cond", "ING_BANNED_WITH_EXCEPTION", f"금지 목록에서 다른 부속서 허용분으로 제외된 성분일 수 있음: {inci} — {r.name[:80]}", ref,
                          "허용 부속서 항목과 같은 물질·조건인지 확인(아니면 재처방)")
                else:
                    v.add("fail", "ING_BANNED", f"금지 성분: {inci}", ref, "해당 성분 제거 재처방")
            elif r.list_type == "restricted" or r.list_type.startswith("allowed_"):
                low = (r.conditions or "").lower()
                if r.list_type == "restricted" and "indicated in the list of ingredients" in low and not parse_pcts(r.max_conc):
                    if proxied or substitute:  # EU 알레르겐 표시 규칙은 대리 관할에 옮기지 않는다(관할별 규칙은 카드 labeling)
                        continue
                    v.add("info", "ALLERGEN_LABEL_RULE", f"알레르기 표시 대상 {inci} — 바르는 0.001%·씻어내는 0.01% 초과 시 전성분 표시, 현재 전성분에 표시됨", ref)
                elif r.list_type == "restricted" and "peroxide" in low and not parse_pcts(r.max_conc):
                    v.add("cond", "ING_PEROXIDE", f"{inci}: 과산화물가 기준({r.conditions[:80]}) — 원료 성적서 확인 필요", ref,
                          "정유·테르펜 원료 공급사 과산화물가 성적서 확보")
                else:
                    limited.append((r, ref))
        _check_limits(v, inci, pct, limited, p, bounds[idx])
        if not hits and (sus := banned_suspect(reg, juris, inci)):
            v.add("cond", "ING_BANNED_SUSPECT", f"{inci}: 금지 성분 '{sus[0]}'와 표기가 {sus[1]:.0%} 같음 — 오기인지 확인",
                  f"{juris} 금지 목록 이름 대조(정확히 일치하지 않음)", "정확한 INCI명 확인, 금지 성분이면 제거 재처방")
        elif not hits and _HANGUL.search(inci) and (kv := kr_fuzzy(inci)):
            # 사전에 없는 한글 표기(OCR 오독·오타·잘림)를 자모 유사도로 표준명에 맞춰 본다 — 등급은 확정하지 않고 '확인 필요'
            kt = {r.list_type for r, _ in reg.lookup(juris, kv["inci"], [])}
            what = f"{inci}: 한글 표기가 '{kv['kr_name']}'({kv['inci']})와 비슷함({kv['how']} {kv['similarity']:.0%})"
            if "banned" in kt:
                v.add("cond", "ING_BANNED_SUSPECT", f"{what} — 금지 성분, 오기·OCR 오류인지 확인", SOURCE_KR,
                      "포장·전성분표 원문으로 성분명 확인, 금지 성분이면 제거 재처방")
            elif "restricted" in kt and pct is None:  # 함량을 알면 아래 '가상 제품' 판정이 실제 한도 초과일 때만 표시
                v.add("cond", "ING_KR_VARIANT_LIMITED", f"{what} — 한도가 있는 성분인데 함량도 없음, 표기와 함량 확인", SOURCE_KR,
                      "성분명·함량 확인 후 한도 대조")
        if has_inventory and "inventory" not in types and ingredient_key(ing) not in ("parfum",):
            a = (attrs or {}).get(ingredient_key(ing)) or {}
            iec = (a.get("iecic_cn") or "").strip()
            if juris == "CN" and iec.lower().startswith("listed"):
                v.add("info", "ING_INVENTORY_BY_ATTR", f"IECIC 등재 확인(속성표): {inci}", iec[:160])
            else:
                v.add("cond", "ING_NOT_IN_INVENTORY", f"{juris} 기존 원료 목록 미확인: {inci} — 표기 차이이거나 신원료(등록 필요)", iec[:160],
                      "IECIC 표준 중문명으로 재대조, 미등재면 신원료 신고")
        if ing.get("role") == "preservative" and juris == "JP" and not any(t.startswith("allowed_preservative") for t in types):
            v.add("cond", "ING_JP_POSITIVE_UNCONFIRMED", f"일본 보존제 포지티브 리스트 등재 미확인: {inci}", "", "化粧品基準 별표3 대조")
    if substitute:  # 대용 목록 결과는 확정이 아니므로 '현지 목록 확인'(조건부)으로 낮춘다
        for f in v.findings[first:]:
            if f.level == "fail":
                f.level, f.code = "cond", f"ING_PROXY_{f.code[4:]}"
                f.message = f"(EU 목록 기준) {f.message} — {card.get('jurisdiction')} 현지 목록에서 같은지 확인"
                f.action = f"현지 목록 확인 후 같으면 {f.action}"
    _check_fragrance_allergens(v, card, p, juris)


# 특정 조건일 때만 금지('과산화물가가 20mmol/L을 초과하는 d-리모넨')인 행은 성적서 확인(조건부)
CONDITIONAL_BAN = ("과산화물", "peroxide", "초과하는", "exceeding", "more than")
# 금지 행의 예외 중 '증빙으로 풀리는' 것만 조건부로 본다. 천연 정유 예외는 성분 자체가 정유·추출물일 때만(사프롤을 직접 넣으면 금지).
NATURAL_EXCEPTION = ("normal content", "natural essence", "furocoumarin", "天然")
NATURAL_WORDS = (" oil", "extract", "absolute", "essence", "resin", "balsam", "concrete", " water", "juice")
REFINING_EXCEPTION = ("refining history", "精炼", "精煉")


def _check_limits(v: Verdict, inci: str, pct: float | None, limited: list, p: dict,
                  bound: tuple[float, float] | None = None) -> None:
    """제한·허용(포지티브) 목록 행의 한도 비교. 용도가 맞는 행만 쓰고, 맞는 행이 없으면 용도 확인으로 본다.
    함량을 모를 때는 전성분 순서로 구한 범위(bound)로 한도 초과 확정(불가)·한도 이하 확정을 먼저 본다."""
    if not limited:
        return
    fits = [(r, ref) for r, ref in limited if not _scope_excludes((r.product_scope or "").lower(), p)]
    if not fits:
        r, ref = limited[0]
        scopes = "; ".join(sorted({x.product_scope for x, _ in limited if x.product_scope}))[:160]
        v.add("cond", "ING_SCOPE_MISMATCH", f"{inci}: 허용 용도({scopes}) 밖일 수 있음 — 이 제품 용도에 쓸 수 있는지 확인", ref,
              "허용 용도가 아니면 성분 제거 재처방")
        return
    for r, ref in fits:
        kind = "제한 성분" if r.list_type == "restricted" else f"허용 목록({r.list_type})"
        limits = sorted(set(parse_pcts(r.max_conc)))
        scope_note = f" / 적용범위: {r.product_scope}" if r.product_scope else ""
        if pct is None and bound and limits:
            lo, hi = bound
            if lo > limits[-1]:
                v.add("fail", "ING_OVER_LIMIT_BY_ORDER", f"{kind} {inci}: 함량 미상이지만 전성분 순서상 최소 {_pct_txt(lo)}% > 한도 {r.max_conc}{scope_note}",
                      ref, "함량 확인 후 한도 이하로 재처방")
                continue
            if hi <= limits[0]:
                if r.conditions:
                    v.add("cond", "ING_RESTRICTED_CONDITIONS", f"{kind} {inci} 전성분 순서상 최대 {_pct_txt(hi)}% (한도 {r.max_conc}{scope_note}) — 조건/경고문: {r.conditions[:160]}",
                          ref, _cond_action(f"{r.conditions} {r.name}"))
                else:
                    v.add("info", "ING_RESTRICTED_OK_BY_ORDER", f"{kind} {inci}: 함량 미상이지만 전성분 순서상 최대 {_pct_txt(hi)}% ≤ 한도 {r.max_conc}{scope_note}", ref)
                continue
        if pct is None:
            if limits or r.list_type == "restricted":
                rng = f" (전성분 순서상 {_pct_txt(bound[0])}~{_pct_txt(bound[1])}%)" if bound else ""
                v.add("cond", "ING_RESTRICTED_PCT_UNKNOWN", f"{kind} {inci}: 한도 {r.max_conc or '조건부'}{scope_note} — 함량 미상{rng}", ref,
                      "처방 함량 확인 후 한도·조건 대조")
            else:
                v.add("info", "ING_POSITIVE_LIST", f"{kind} 등재: {inci} 한도 {r.max_conc or '없음'}", ref)
        elif limits and pct > limits[-1]:
            v.add("fail", "ING_OVER_LIMIT", f"{kind} {inci} {pct}% > 한도 {r.max_conc}{scope_note}", ref, "함량 낮춰 재처방")
        elif len(limits) > 1 and pct > limits[0]:
            v.add("cond", "ING_RESTRICTED_SCOPE_CHECK", f"{kind} {inci} {pct}% — 용도별 한도({r.max_conc}) 중 적용 한도 확인 필요{scope_note}", ref,
                  "제품 용도에 맞는 한도 확인(초과면 함량 낮춰 재처방)")
        elif r.conditions:
            v.add("cond", "ING_RESTRICTED_CONDITIONS", f"{kind} {inci} {pct}% (한도 {r.max_conc or '조건'}{scope_note}) — 조건/경고문: {r.conditions[:160]}",
                  ref, _cond_action(f"{r.conditions} {r.name}"))
        else:
            v.add("info", "ING_POSITIVE_LIST" if r.list_type.startswith("allowed_") else "ING_RESTRICTED_OK",
                  f"{kind} {inci} {pct}% (한도 {r.max_conc or '없음'}{scope_note})", ref)


_SPEC_WORDS = ("nitros", "니트로", "purity", "순도", "impurit", "불순물", "secondary amine", "2차 아민", "2차 알킬아민", "2급 아민", "이차아민")


def _cond_action(conditions: str) -> str:
    """제한 성분 조건의 종류에 맞는 할 일. 원료 규격(순도·니트로소아민·불순물)이면 성적서 확인, 그 밖에는 라벨 경고문·사용 조건."""
    low = (conditions or "").lower()
    if any(w in low for w in _SPEC_WORDS):
        return "원료 규격서·성적서로 순도·니트로소아민 등 조건 확인(니트로소화 계와 함께 쓰지 않기)"
    return "라벨 경고문·사용 조건 반영"


def _scope_excludes(scope: str, p: dict) -> bool:
    """한도 적용범위가 제품 유형과 맞지 않으면 True (예: 씻어내는 제품 전용 한도인데 우리는 바르는 제품)."""
    if not scope:
        return False
    lo = leave_on(p)
    if lo and ("rinse-off" in scope or "씻어내" in scope) and "leave" not in scope:
        return True
    if not lo and ("leave-on" in scope or "씻어내지" in scope) and "rinse" not in scope:
        return True
    return False


def _check_fragrance_allergens(v: Verdict, card: dict, p: dict, juris: str) -> None:
    lab = card.get("labeling") or {}
    if not lab.get("allergens"):
        return
    ings = p.get("ingredients", [])
    has_fragrance = any(norm_inci(i.get("inci")) == "parfum" for i in ings)
    oils = [i for i in ings if "oil" in norm_inci(i.get("inci")) and "citrus" in norm_inci(i.get("inci"))]
    listed_allergens = [i for i in ings if i.get("role") == "allergen_from_fragrance"]
    if has_fragrance and not any(i.get("pct") for i in listed_allergens):
        v.add("cond", "ALLERGEN_UNKNOWN", "향료 알레르기 성분 구성·함량 미보유 — 표시 기준 판단 불가", lab.get("allergens", ""),
              "향료사 알레르겐 분석서(IFRA·알러젠 목록) 확보 후 라벨 반영")
    elif oils and listed_allergens:
        v.add("info", "ALLERGEN_LISTED", f"정유 유래 알레르기 성분 {len(listed_allergens)}종 전성분에 표시됨({', '.join(i['inci'] for i in listed_allergens)})",
              lab.get("allergens", ""))


def check_claims(v: Verdict, card: dict, p: dict) -> None:
    claims = product_claims(p)
    functional = {c for c in (p.get("functional_kr") or []) if not c.endswith("_planned")}
    for cr in card.get("claim_rules") or []:
        c, eff, note = cr.get("claim"), cr.get("effect"), cr.get("note", "")
        if c not in claims:
            continue
        if card.get("jurisdiction") == "KR" and c in functional and eff in ("needs_special_registration", "not_allowed"):
            v.add("info", "CLAIM_KR_FUNCTIONAL_OK", f"표방 '{c}' — 국내 기능성 보고 품목이라 보고 효능 범위 안에서 허용", note)
            continue
        if eff == "needs_evidence":
            v.add("cond", "CLAIM_NEEDS_EVIDENCE", f"표방 '{c}' — 실증 자료 필요", note, "시험 성적서·인체적용시험 등 실증 자료 확보 또는 문구 수정")
            continue
        if eff == "ok" and cr.get("actives_any"):
            names = {ingredient_key(i) for i in p.get("ingredients", [])}
            hit = [a for a in cr["actives_any"] if norm_inci(a) in names]
            if hit:
                v.add("info", "CLAIM_ACTIVE_FOUND", f"표방 '{c}' — 승인 전례 유효성분 {', '.join(hit)} 포함(승인 범위 함량·문구로만)", note)
            else:
                v.add("cond", "CLAIM_NO_APPROVED_ACTIVE", f"표방 '{c}' — 승인 전례 유효성분 없음", note,
                      "승인 전례 성분으로 재처방, 신규 유효성분 심사(장기·고비용), 또는 표방 삭제")
        elif eff == "ok":
            v.add("info", "CLAIM_OK", f"표방 '{c}' 허용", note)
        elif eff == "needs_special_registration":
            v.add("cond", "CLAIM_SPECIAL_REG", f"표방 '{c}'은 별도 특수 등록 대상", note, "특수 등록 진행 또는 해당 표방 삭제")
        elif eff == "quasi_drug":
            v.add("cond", "CLAIM_QUASI_DRUG", f"표방 '{c}'은 의약부외품 영역", note, "의약부외품 승인 또는 화장품 범위 문구로 수정")
        elif eff == "drug_risk":
            v.add("cond", "CLAIM_DRUG_RISK", f"표방 '{c}'은 의약품 판단 위험", note, "구조·기능 표현 대신 외관 개선 표현으로 수정")
        elif eff == "not_allowed":
            v.add("cond", "CLAIM_NOT_ALLOWED", f"표방 '{c}' 사용 불가", note, "문구 삭제")


def check_documents(v: Verdict, card: dict, p: dict, company: dict) -> None:
    have = list(p.get("documents") or []) + list(company.get("documents") or [])
    for d in card.get("documents_required") or []:
        if isinstance(d, str):
            d = {"id": d, "desc": d}
        st, src = doc_status(d.get("satisfied_by_hint") or [], have, p, company)
        desc = d.get("desc", d.get("id"))
        who = {"external_expert": "외부 전문가", "company": "자사", "manufacturer": "제조사", "lab": "시험기관",
               "authority": "관공서", "certifier": "인증기관", "local_entity": "현지 책임자"}.get(d.get("producer"), d.get("producer") or "")
        if st == "have":
            v.add("info", "DOC_OK", f"보유: {desc}", src)
        elif st == "draftable":
            v.add("cond", "DOC_DRAFTABLE", f"초안 자동 생성 가능: {desc}" + (f" (최종 작성·서명: {who})" if who else ""), f"원자료: {src}",
                  "자동 초안 생성 후 담당 확인")
        else:
            v.add("cond", "DOC_MISSING", f"서류 필요: {desc}" + (f" (작성: {who})" if who else ""), "",
                  f"{who or '담당'}에게 준비 요청")
    tests = card.get("tests_required") or []
    if tests:
        covered = sorted(t for t in tests if any(fnmatch.fnmatch(d, pat) for d in have for pat in TEST_EVIDENCE.get(t, ())))
        missing = [t for t in tests if t not in covered]
        if covered:
            v.add("info", "TEST_OK", f"보유 성적서로 확인: {', '.join(covered)}")
        if missing:
            v.add("cond", "TEST_MISSING", f"시험 확인 필요: {', '.join(missing)}", "", "국내 성적서 항목 대조 후 부족 시험 의뢰")


def check_local_entity(v: Verdict, card: dict, company: dict) -> None:
    le = card.get("local_entity") or {}
    if not le.get("required"):
        return
    juris = card.get("jurisdiction")
    if (company.get("local_entities") or {}).get(juris):
        v.add("info", "LOCAL_ENTITY_OK", f"현지 책임자 보유: {company['local_entities'][juris]}")
    else:
        v.add("cond", "LOCAL_ENTITY_MISSING", f"현지 책임자 지정 필요: {le.get('role', '')}", "", "현지 수입자·대리인 계약")


def check_labeling(v: Verdict, card: dict) -> None:
    lab = card.get("labeling") or {}
    if lab.get("language"):
        v.add("cond", "LABEL_LOCAL", f"현지 라벨 필요: {lab['language']}", "", "현지어 라벨·표시사항 작성(초안 자동 생성 가능)")


def natural_status(attrs: dict, ing: dict) -> tuple[str, str]:
    """천연·유기농 공통 원칙(공개 사실만): 에톡실화·실리콘은 불가, 석유화학·합성·혼합 기원은 확인. 인증기관 기준서·DB는 쓰지 않는다."""
    a = attrs.get(ingredient_key(ing))
    if a:
        first = lambda col: ((a.get(col) or "").split(":")[0].split() or [""])[0].strip(" ,;")  # noqa: E731
        if first("ethoxylated_peg") == "Y":
            return "not_allowed", "에톡실화(PEG·글리세레스 등) 원료 — 주요 천연·유기농 기준 공통 비허용 공정 [성분 속성표]"
        if first("silicone") not in ("", "none"):
            return "not_allowed", f"실리콘 원료({first('silicone')}) — 주요 천연·유기농 기준 공통 비허용 [성분 속성표]"
        origin = first("origin")
        if origin in ("petrochemical", "synthetic"):
            return "depends_on_source", f"{origin} 기원 — 원칙적으로 비허용, 허용 예외(일부 보존제 등) 해당 여부를 인증기관에 확인 [성분 속성표]"
        if origin in ("mixed", "unknown", ""):
            return "depends_on_source", "기원 혼합·미상 — 원료사 기원 증명 필요 [성분 속성표]"
        return "ok", f"{origin} 기원 [성분 속성표]"
    n = ingredient_key(ing)
    if n.startswith("peg-") or "eth-" in n or "glycereth" in n or "siloxane" in n or "dimethicone" in n or "methicone" in n:
        return "not_allowed", "추정(heuristic): 이름상 에톡실화·실리콘 원료"
    return "unknown", "속성표 없음 — 원료사 기원 증명 필요"


def attr_status(attrs: dict, ing: dict, col: str) -> tuple[str, str]:
    if col == "natural":
        return natural_status(attrs, ing)
    a = attrs.get(ingredient_key(ing))
    if a and a.get(col):
        val = a[col].split()[0].strip(" ,;:")
        return val, (a[col] + (f" [{a.get('evidence_level')}]" if a.get("evidence_level") else ""))
    if col == "vegan":
        n = ingredient_key(ing)
        for k, s in ANIMAL_HINTS.items():
            if k in n:
                return s, f"추정(heuristic): '{k}' 포함"
        return "ok", "추정(heuristic): 동물 유래 단서 없음"
    return "unknown", "속성표 없음"


def check_attribute_cert(v: Verdict, card: dict, p: dict, attrs: dict) -> None:
    """비건·할랄·NATRUE·천연·유기농 공통 원칙 같은 성분 속성 기반 인증."""
    cid = card["id"].upper()
    col = "vegan" if "VEGAN" in cid or "V_LABEL" in cid else "halal" if "HALAL" in cid else \
        "natural" if "NATURAL_ORGANIC" in cid or "USDA_ORGANIC" in cid else "natrue" if "NATRUE" in cid else None
    if not col:
        return
    for ing in p.get("ingredients", []):
        st, why = attr_status(attrs, ing, col)
        name = f"{ing.get('kr')}({ing.get('inci')})"
        if st in ("not_ok", "not_allowed") and why.startswith("추정(heuristic)"):
            v.add("cond", f"ATTR_{col.upper()}_CHECK", f"{name}: {col} 기준 불충족 가능성(속성표 미등록, 이름으로 추정)", why,
                  "원료사 기원 증명서로 확인(동물 유래·금지 공정이면 재처방)")
        elif st in ("not_ok", "not_allowed"):
            label = {"natural": "천연·유기농 공통 원칙(USDA 유기농 포함)", "natrue": "NATRUE 기준", "vegan": "비건 기준",
                     "halal": "할랄 기준"}.get(col, f"{col} 기준")
            v.add("fail", f"ATTR_{col.upper()}_FAIL", f"{name}: {label}에 맞지 않음", why, "대체 원료로 재처방")
        elif st in ("depends_on_source", "needs_cert", "unknown"):
            v.add("cond", f"ATTR_{col.upper()}_CHECK", f"{name}: 원료 기원·인증 확인 필요", why, "원료사 기원 증명서·인증서 확보")
    if col == "halal":
        certs = " ".join(p.get("manufacturer", {}).get("certs") or [])
        if "halal" not in certs.lower():
            v.add("cond", "HALAL_FACILITY", "제조소 할랄 관리(전용 라인·교차오염) 미확인", "", "위탁제조사 할랄 대응 여부 확인")


def _norm_pat(pattern) -> str:
    """와일드카드(*)는 살리고 나머지는 성분 키와 같은 규칙으로 정규화한다(norm_inci는 *를 지우므로 조각별로)."""
    return "*".join(norm_inci(part) if part.strip() else "" for part in str(pattern).split("*"))


def check_excluded(v: Verdict, card: dict, p: dict) -> None:
    """카드의 배제 물질(예: EU 에코라벨 기준 4(b)): 농도와 상관없이 들어 있으면 불가, 성분 구성에 따라 갈리면 확인."""
    excl = [_norm_pat(x) for x in card.get("excluded_ingredients") or []]
    checks = card.get("excluded_check") or []
    if not excl and not checks:
        return
    for ing in p.get("ingredients", []):
        k = ingredient_key(ing)
        hit = next((pat for pat in excl if fnmatch.fnmatch(k, pat)), None)
        if hit:
            v.add("fail", "ING_EXCLUDED", f"배제 물질: {ing.get('inci')} — 농도와 상관없이 사용 불가", card.get("excluded_basis", ""), "해당 성분 제거 재처방")
            continue
        for chk in checks:
            if fnmatch.fnmatch(k, _norm_pat(chk.get("pattern", ""))):
                v.add("cond", "ING_EXCLUDED_CHECK", f"{ing.get('inci')}: {chk.get('message', '배제 물질 포함 여부 확인')}", card.get("excluded_basis", ""),
                      "원료사 성분 구성 자료로 확인")
                break


def _eu_siloxane_sunset(v: Verdict, p: dict, eval_date: date) -> None:
    """EU 판매 전반에 걸리는 REACH 70항 일몰을 EU 카드에도 표시한다(바르는 제품 D5·D6, 2027-06-06 이후 금지)."""
    sunset = date(2027, 6, 6)
    if not leave_on(p):
        return
    for ing in p.get("ingredients", []):
        code = CYCLIC_SILOXANES.get(ingredient_key(ing))
        pct = ing.get("pct")
        if code in ("D5", "D6") and (pct is None or pct >= 0.1):
            if eval_date > sunset:
                v.add("fail", "SILOXANE_BANNED", f"{ing.get('inci')}({code}) — EU 바르는 제품 0.1% 이상 금지({sunset} 이후)", "REACH 부속서 XVII 70항 3(b)",
                      "대체 원료로 재처방")
            else:
                v.add("cond", "SILOXANE_SUNSET", f"{ing.get('inci')}({code}) — {sunset} 이후 EU 판매 금지: EU 진입은 재처방 전제로 계획",
                      "REACH 부속서 XVII 70항 3(b)(Reg. 2024/1328)", f"EU 신고 전에 {code} 대체 재처방(신고 후 재처방하면 재신고 필요)")


def check_special(v: Verdict, card: dict, p: dict, eval_date: date) -> None:
    cid = card["id"].upper()
    ings = {ingredient_key(i): i for i in p.get("ingredients", [])}
    if "D4D5D6" in cid or "SILOXANE" in cid:
        found = [(k, CYCLIC_SILOXANES[k], ings[k].get("pct")) for k in CYCLIC_SILOXANES if k in ings]
        if not found:
            v.add("info", "SILOXANE_NONE", "D4/D5/D6 없음")
            return
        # REACH 부속서 XVII 70항(Reg. 2024/1328 원문 대조 2026-11-07):
        # 3(a) 씻어내는 화장품의 D4·D5는 2020-01-31 이후 0.1% 이상 금지
        # 3(b) 그 밖의 모든 화장품(바르는 제품 전부 + 씻어내는 제품의 D6)은 2027-06-06 이후 0.1% 이상 금지
        sunset = date(2027, 6, 6)
        rinse = not leave_on(p)
        for k, code, pct in found:
            label = f"{k}({code})"
            if code == "D4":
                v.add("fail", "SILOXANE_D4_BANNED", f"{label} — EU 화장품 금지 성분(부속서 II ref 1388)", "Reg. (EU) 2019/831, CosIng 부속서 II",
                      "대체 원료로 재처방")
            elif "/" in code:
                v.add("cond", "SILOXANE_MIX", f"{label} — D4·D5·D6 구성비 확인 필요(D4는 금지, D5·D6는 0.1% 기준)", "REACH 부속서 XVII 70항",
                      "원료사 구성비·성적서 확보")
            elif pct is None:
                when = "2020-01-31부터" if rinse and code == "D5" else f"{sunset} 이후"
                v.add("cond", "SILOXANE_PCT_UNKNOWN", f"{label} 함량 미상 — 0.1% 이상이면 {when} EU 판매 금지", "REACH 부속서 XVII 70항(Reg. 2024/1328)",
                      "배합비로 함량 확인")
            elif pct < 0.1:
                v.add("info", "SILOXANE_UNDER", f"{label} {pct}% < 0.1%")
            elif rinse and code == "D5":
                v.add("fail", "SILOXANE_RINSEOFF", f"{label} {pct}% — 씻어내는 제품 0.1% 이상 금지(2020-01-31 이후)", "REACH 부속서 XVII 70항 3(a)", "재처방")
            elif eval_date > sunset:
                v.add("fail", "SILOXANE_BANNED", f"{label} {pct}% — 화장품 0.1% 이상 금지({sunset} 이후)", "REACH 부속서 XVII 70항 3(b)(Reg. 2024/1328)",
                      "대체 원료로 재처방")
            else:
                v.add("cond", "SILOXANE_SUNSET", f"{label} {pct}% — {sunset}까지 판매 가능, 그 뒤 EU 판매 불가", "REACH 부속서 XVII 70항 3(b)(Reg. 2024/1328)",
                      f"{sunset} 전 재처방(그 뒤에도 EU 판매 계획이면 지금 재처방)")
    if "PROP65" in cid:
        pegs = [i["inci"] for i in p.get("ingredients", []) if ingredient_key(i).startswith("peg-") or "eth-" in ingredient_key(i)]
        if pegs:
            v.add("cond", "PROP65_DIOXANE", f"에톡실화 원료({', '.join(pegs)}) — 1,4-다이옥산 불순물(Prop 65 등재) 확인", "CA Prop 65",
                  "다이옥산 시험 성적 확인 후 경고문 필요 여부 판단")
        scents = [i["inci"] for i in p.get("ingredients", [])
                  if ingredient_key(i) in ("parfum", "fragrance") or (" oil" in ingredient_key(i) and "citrus" in ingredient_key(i))]
        if scents:
            v.add("cond", "PROP65_FRAGRANCE", f"향료·감귤 정유({', '.join(scents[:3])}) 구성 미확인 — β-미르센 등 등재 물질 포함 여부 확인", "CA Prop 65 (OEHHA 2015-03-27 β-myrcene 등재)",
                  "향료사 구성 성분표(IFRA·알레르겐 성적서)로 등재 물질 확인 후 경고문 판단")
        if not pegs and not scents:
            v.add("info", "PROP65_NONE", "에톡실화 원료·향료 없음")
    if "PPWR" in cid:
        v.add("cond", "PACKAGING_DATA", "포장재 재질·재활용성·라벨 정보 미보유", "EU PPWR", "포장사양서 기반 재질·재활용 등급 정리")


# ---------------------------------------------------------------- 실행
KR_SHADOW = True  # 한글 변형 표기를 표준명으로 본 '가상 제품'으로 한 번 더 판정(측정 때 끄고 켜서 비교)


@lru_cache(maxsize=4)
def _known_names(reg_id: int) -> tuple[frozenset, tuple[str, ...]]:
    """공식 이름 키: 식약처 원료사전 INCI + 모든 관할 규제 목록 이름(정확히 있는 이름은 오타가 아님)."""
    from .names import kr_dict
    reg = _REG_BY_ID[reg_id]
    names = {norm_inci(h.get("inci")) for h in kr_dict().values()} | {k for (_, k) in reg.by_key}
    names = {n for n in names if n and not _HANGUL.search(n)}
    return frozenset(names), tuple(sorted(n for n in names if len(n) >= 6))


@lru_cache(maxsize=20000)
def _en_fuzzy(reg_id: int, key: str) -> str | None:
    known, pool = _known_names(reg_id)
    if len(key) < 6 or key in known:
        return None
    hit, score, _ = process.extractOne(key, pool, scorer=fuzz.ratio)
    need = 88 if len(key) >= 8 else 92  # 긴 이름은 한 글자 오타가 10% 남짓이라 기준을 낮춘다
    return hit if need <= score < 100 else None


@lru_cache(maxsize=4)
def _kr_reg_index(reg_id: int) -> tuple[list[str], list[str], list[tuple[str, str]]]:
    """규제 목록(식약처 API 등)의 한글 물질명: 원료사전에 없는 금지·제한 물질의 한글 표기 대조용. (키, 자모, (한글명, 조회 이름))"""
    from .data import kr_key
    from .names import jamo
    reg = _REG_BY_ID[reg_id]
    seen: dict[str, tuple[str, str]] = {}
    for (_, k), rows in reg.by_key.items():
        for r in rows:
            if _HANGUL.search(r.name or "") and len(kr_key(r.name)) >= 3:
                seen.setdefault(kr_key(r.name), (r.name, r.inci or k))
    keys = list(seen)
    return keys, [jamo(x) for x in keys], [seen[x] for x in keys]


@lru_cache(maxsize=20000)
def _kr_reg_fuzzy(reg_id: int, name: str) -> dict | None:
    from .data import kr_key
    from .names import jamo
    k = kr_key(name)
    keys, jk, vals = _kr_reg_index(reg_id)
    if len(k) < 3 or k in set(keys):
        return None
    hit, score, idx = process.extractOne(jamo(k), jk, scorer=fuzz.ratio)
    if score >= 88:
        return {"kr_name": vals[idx][0], "inci": vals[idx][1], "how": "규제 목록 한글명 유사", "similarity": round(score / 100, 2)}
    return None


def _kr_shadow(p: dict, reg: RegIndex | None = None) -> tuple[dict, list[tuple[str, dict]]] | None:
    """사전에 없는 표기를 가장 가까운 공식 이름으로 바꾼 사본: 한글은 자모 유사도(식약처 표준명), 영문은 이름 유사도 92% 이상
    (식약처 원료사전 INCI·규제 목록 이름). 바꾼 게 없으면 None."""
    swaps, ings = [], []
    if reg is not None:
        _REG_BY_ID[id(reg)] = reg
    for ing in p.get("ingredients", []):
        name = ing.get("inci") or ""
        kv = kr_fuzzy(name) if _HANGUL.search(name) else None
        if not kv and reg is not None and _HANGUL.search(name):
            kv = _kr_reg_fuzzy(id(reg), name)
        if not kv and reg is not None and not _HANGUL.search(name) and (en := _en_fuzzy(id(reg), norm_inci(name))):
            kv = {"inci": en, "kr_name": en, "how": "영문 이름 유사", "similarity": None}
        if kv:
            swaps.append((name, kv))
            ings.append({**ing, "inci": kv["inci"], "kr": ing.get("kr") if kv.get("how") == "영문 이름 유사" else kv["kr_name"]})
        else:
            ings.append(ing)
    return ({**p, "ingredients": ings}, swaps) if swaps else None


def evaluate(card: dict, p: dict, company: dict, reg: RegIndex, attrs: dict, eval_date: date | None = None,
             _shadow: bool = False) -> Verdict:
    v = _evaluate(card, p, company, reg, attrs, eval_date)
    if _shadow or not KR_SHADOW or v.status == STATUS_FAIL or card.get("kind") == "company_certification":
        return v
    sh = _kr_shadow(p, reg)
    if not sh:
        return v
    # 오기·OCR 변형을 공식 이름으로 보면 새로 생기는 불가 사유(금지·배제·한도 초과·비건·할랄 속성 등)를 '확인 필요'로 붙인다(등급은 확정하지 않음)
    have = {(f.code, f.message) for f in v.findings if f.level == "fail"}
    alt = evaluate(card, sh[0], company, reg, attrs, eval_date, _shadow=True)
    names = ", ".join(f"'{a}'→'{b['kr_name']}'" for a, b in sh[1][:3])
    flagged = any(f.code == "ING_BANNED_SUSPECT" for f in v.findings)  # 금지 성분 오기는 이미 '의심'으로 표시됨
    new = [f for f in alt.findings if f.level == "fail" and (f.code, f.message) not in have and not (flagged and f.code == "ING_BANNED")]
    for f in new[:5]:
        v.add("cond", "ING_KR_VARIANT_RISK", f"성분 표기를 공식 이름으로 보면({names}) 불가 사유: {f.message[:160]} — 표기 확인 필요",
              SOURCE_KR, "포장·전성분표 원문으로 성분명 확인 후 다시 판정")
    if new:
        v.finalize()
        v.features = features(v, p)
    return v


def _evaluate(card: dict, p: dict, company: dict, reg: RegIndex, attrs: dict, eval_date: date | None = None) -> Verdict:
    eval_date = eval_date or date.today()
    v = Verdict(p["id"], p.get("name_kr", ""), card["id"], card.get("name_ko", card["id"]), card.get("jurisdiction", ""),
                card.get("kind", ""))
    if card.get("kind") == "company_certification":
        v.add("na", "COMPANY_LEVEL", "회사 단위 인증 — 회사 판정표 참조")
        return v.finalize()
    if not check_applicability(v, card, p):
        return v.finalize()
    eff = (card.get("applies_to") or {}).get("effective_from")
    if eff and eval_date < date.fromisoformat(str(eff)):
        v.add("na", "SCOPE_NOT_IN_FORCE", f"시행 전 의무(시행일 {eff}) — 지금은 요구 없음, 미리 준비 권장",
              (card.get("timeline") or {}).get("validity", "")[:200], "EU CPSR·아세안 PIF와 같은 안전성 자료로 미리 준비")
        return v.finalize()
    if p.get("formula_known") == "concept_only":
        v.add("cond", "FORMULA_CONCEPT", "처방 미확정(기획 단계) — 확정 처방으로 재판정 필요")
        v.confidence = min(v.confidence, 0.3)
    check_ingredients(v, card, p, reg, attrs)
    check_claims(v, card, p)
    check_attribute_cert(v, card, p, attrs)
    check_excluded(v, card, p)
    check_special(v, card, p, eval_date)
    if card.get("jurisdiction") == "EU" and "D4D5D6" not in card["id"].upper():
        _eu_siloxane_sunset(v, p, eval_date)
    special_cleared = any(f.code in ("SILOXANE_NONE", "PROP65_NONE") for f in v.findings)
    if not special_cleared:  # 전성분상 해당 성분이 아예 없으면 함량 확인 서류는 요구하지 않는다
        check_documents(v, card, p, company)
    check_local_entity(v, card, company)
    check_labeling(v, card)
    for rule in card.get("blocking_rules") or []:
        v.add("info", "CARD_BLOCKING_RULE", f"(카드 규칙) {rule}")
    v.finalize()
    if v.status == STATUS_PASS and not any((e or {}).get("level") == "direct" for e in card.get("evidence") or []):
        v.add("cond", "CARD_EVIDENCE_WEAK", "요건을 원문으로 확인하지 못한 카드(2차 자료·추정) — 통과 확정 전 원문 확인 필요", "",
              "기관 원문·인증기관에 요건 확인")
        v.finalize()
    v.features = features(v, p)
    return v


def evaluate_company(card: dict, company: dict) -> Verdict:
    v = Verdict("COMPANY", company.get("name", ""), card["id"], card.get("name_ko", card["id"]), card.get("jurisdiction", ""),
                card.get("kind", ""))
    key = card["id"].lower().replace("kr_", "")
    st = (company.get("company_certs") or {}).get(key)
    fin = company.get("financial") or {}
    rules_text = " ".join(str(r) for r in (card.get("blocking_rules") or []))
    if "자본잠식" in rules_text and fin.get("capital_impairment") == "complete":
        v.add("fail", "COMPANY_CAPITAL_IMPAIRMENT", f"직전 결산({fin.get('fiscal_year')}) 완전자본잠식 — 신청 결격", rules_text[:160],
              "재무구조 개선(증자 등) 후 재신청")
    if st and st.startswith("expired"):
        v.add("cond", "COMPANY_EXPIRED", f"{card.get('name_ko')} 만료({st}) — 재취득 요건 확인", card.get("notes", "")[:200],
              "요건 충족 여부 점검 후 재신청")
    elif st == "valid":
        v.add("info", "COMPANY_VALID", "유효")
    elif st == "none":
        v.add("cond", "COMPANY_NOT_HELD", f"{card.get('name_ko')} 미보유 — 신규 신청 요건 확인", card.get("notes", "")[:200], "신청 요건·서류 점검 후 신청")
    else:
        v.add("cond", "COMPANY_UNKNOWN", "보유 여부 미확인", "", "회사 정보 확인")
    for d in card.get("documents_required") or []:
        v.add("info", "COMPANY_DOC", f"필요 서류: {d.get('desc', d) if isinstance(d, dict) else d}")
    return v.finalize()


def features(v: Verdict, p: dict) -> dict:
    """ML(AIStream 분류 모델) 학습용 특징 벡터. 판정 결과와 함께 저장해 합성 데이터 학습에 쓴다."""
    codes = [f.code for f in v.findings]

    def cnt(prefix: str) -> int:
        return sum(1 for c in codes if c.startswith(prefix))

    return {
        "n_ingredients": len(p.get("ingredients", [])),
        "leave_on": int(leave_on(p)),
        "has_whitening": int("whitening" in product_claims(p)),
        "has_antiwrinkle": int("anti_wrinkle" in product_claims(p)),
        "formula_with_pct": int(p.get("formula_known") == "full_with_concentration"),
        "formula_concept": int(p.get("formula_known") == "concept_only"),
        "n_banned": sum(1 for c in codes if c == "ING_BANNED"), "n_over_limit": cnt("ING_OVER_LIMIT"),
        "n_banned_suspect": cnt("ING_BANNED_SUSPECT"), "n_over_by_order": cnt("ING_OVER_LIMIT_BY_ORDER"),
        "n_kr_variant_limited": cnt("ING_KR_VARIANT_LIMITED"), "n_kr_variant_risk": cnt("ING_KR_VARIANT_RISK"),
        "n_ok_by_order": cnt("ING_RESTRICTED_OK_BY_ORDER"),
        "n_restricted_unknown": cnt("ING_RESTRICTED_PCT_UNKNOWN"), "n_restricted_cond": cnt("ING_RESTRICTED_CONDITIONS"),
        "n_not_in_inventory": cnt("ING_NOT_IN_INVENTORY"), "ing_no_data": cnt("ING_NO_DATA"), "ing_proxy": cnt("ING_PROXY"),
        "allergen_unknown": cnt("ALLERGEN_UNKNOWN"),
        "n_claim_special": cnt("CLAIM_SPECIAL_REG"), "n_claim_quasi": cnt("CLAIM_QUASI_DRUG"),
        "n_claim_drug_risk": cnt("CLAIM_DRUG_RISK"), "n_claim_not_allowed": cnt("CLAIM_NOT_ALLOWED"),
        "n_attr_fail": sum(1 for c in codes if c.startswith("ATTR_") and c.endswith("_FAIL")),
        "n_attr_check": sum(1 for c in codes if c.startswith("ATTR_") and c.endswith("_CHECK")),
        "n_doc_missing": cnt("DOC_MISSING"), "n_test_missing": cnt("TEST_MISSING"),
        "local_entity_missing": cnt("LOCAL_ENTITY_MISSING"), "label_local": cnt("LABEL_LOCAL"),
        "siloxane_sunset": cnt("SILOXANE_SUNSET"),
        "siloxane_banned": sum(1 for c in codes if c in ("SILOXANE_BANNED", "SILOXANE_RINSEOFF", "SILOXANE_D4_BANNED")),
        "confidence": round(v.confidence, 2),
    }


def evaluate_all(cards: list[dict], products: dict, reg: RegIndex, attrs: dict, eval_date: date | None = None) -> list[Verdict]:
    company = products.get("company", {})
    out = []
    for card in cards:
        if card.get("kind") == "company_certification":
            out.append(evaluate_company(card, company))
            continue
        for p in products.get("products", []):
            out.append(evaluate(card, p, company, reg, attrs, eval_date))
    out.sort(key=lambda v: (v.product_id, STATUS_ORDER.get(v.status, 9), v.cert_id))
    return out
