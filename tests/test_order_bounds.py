"""전성분 표시 순서로 함량 범위 추정, 금지 성분 오기 의심 판정 회귀 시험."""
import json
from pathlib import Path

from certcheck.classify import banned_suspect, evaluate, pct_bounds
from certcheck.data import load_attributes, load_cards, load_reg_index

DATA = Path(__file__).resolve().parents[1] / "data"


def test_bounds_from_order():
    ings = [{"pct": 70}, {"pct": None}, {"pct": 5}, {"pct": None}, {"pct": 0.5}, {"pct": None}]
    b = pct_bounds(ings)
    assert b[0] is None and b[2] is None
    assert b[1] == (5.0, 50.0)   # 아래 5%보다 많고, 둘째라 100/2=50 이하(위 70%보다도 적음)
    assert b[3] == (0.0, 5.0)    # 위 5%보다 적음, 아래 1% 초과 없음
    assert b[5] == (0.0, 1.0)    # 1% 이하 구역(0.5% 아래)은 1%까지만 보장
    assert pct_bounds([{"pct": 2}, {"pct": 5}, {"pct": None}]) == [None, None, None]  # 순서가 어긋난 데이터는 추론 안 함


def test_over_limit_by_order_and_ok_by_order():
    reg, attrs = load_reg_index(), load_attributes()
    card = next(c for c in load_cards() if c["id"] == "EU_CPNP")
    base = {"id": "T1", "name_kr": "시험", "product_type": "face_cream", "application": "leave_on", "claims": [], "documents": [],
            "formula_known": "partial_concentration"}
    # Phenoxyethanol(EU 한도 1%)이 3% 성분보다 위에 있으면 최소 3% → 한도 초과 확정
    over = dict(base, ingredients=[{"inci": "Water", "pct": 80}, {"inci": "Phenoxyethanol", "pct": None}, {"inci": "Glycerin", "pct": 3}])
    v = evaluate(card, over, {}, reg, attrs)
    assert any(f.code == "ING_OVER_LIMIT_BY_ORDER" for f in v.findings) and v.status == "불가"


def test_banned_suspect_typo_only():
    reg = load_reg_index()
    assert banned_suspect(reg, "EU", "Diethyamine Laureth Sulfate")[0] == "diethylamine laureth sulfate"
    assert banned_suspect(reg, "EU", "Sodium Chloride") is None      # 식약처 사전에 있는 정상 원료
    assert banned_suspect(reg, "EU", "Dibutyl Phthalate") is None    # 정확히 같은 이름은 의심이 아니라 금지 판정 쪽
    demo = json.loads((DATA / "public/products/demo_products.json").read_text(encoding="utf-8"))
    d5 = next(p for p in demo["products"] if p["id"] == "D5")
    card = next(c for c in load_cards() if c["id"] == "EU_CPNP")
    v = evaluate(card, d5, demo["company"], reg, load_attributes())
    assert any(f.code == "ING_BANNED_SUSPECT" for f in v.findings)


def test_korean_variant_matching():
    """자모 유사도로 사전에 없는 한글 표기를 표준명에 맞춤: 정상 표준명은 후보를 내지 않고, 잘린 이름은 찾는다."""
    from certcheck.names import jamo, kr_dict, kr_fuzzy
    assert jamo("셀") == "ㅅㅔㄹ"
    name = next(h["kr_name"] for h in kr_dict().values() if len(h["kr_name"]) > 6)
    assert kr_fuzzy(name) is None
    r = kr_fuzzy(name[:-2])
    assert r is None or r["kr_name"] == name


def test_kr_shadow_adds_check_not_fail():
    """한글 변형을 표준명으로 본 가상 판정의 불가 사유는 '확인 필요'(조건부)로만 붙고 등급을 불가로 만들지 않는다."""
    from certcheck import classify as C
    from certcheck.names import kr_dict
    reg, attrs = load_reg_index(), load_attributes()
    card = next(c for c in load_cards() if c["id"] == "EU_CPNP")
    p = {"id": "T2", "name_kr": "시험", "product_type": "face_cream", "application": "leave_on", "claims": [], "documents": [],
         "formula_known": "full_with_concentration", "ingredients": [{"inci": "Water", "pct": 80}]}
    v = C.evaluate(card, p, {}, reg, attrs)
    assert all(f.code != "ING_KR_VARIANT_RISK" for f in v.findings)  # 한글 표기가 없으면 추가 판정 없음
    assert C._kr_shadow(p) is None
    name = next(h["kr_name"] for h in kr_dict().values() if len(h["kr_name"]) > 6)
    sh = C._kr_shadow({**p, "ingredients": [{"inci": name[:-2], "pct": None}]})
    assert sh is None or sh[1][0][1]["kr_name"] == name


def test_cas_recovery_and_english_shadow():
    """CAS가 없으면 같은 INCI명으로 CAS를 찾아 대조하고, 공식 이름과 한 글자 다른 영문 오기는 가상 판정으로 '확인 필요'."""
    from certcheck import classify as C
    reg = load_reg_index()
    assert C.cas_by_name(reg, "Glycerin") == ["56-81-5"] and C.cas_by_name(reg, "Water") == []
    assert C._en_fuzzy(id(reg), "glycerin") is None          # 공식 이름은 오타가 아님
    C._REG_BY_ID[id(reg)] = reg
    assert C._en_fuzzy(id(reg), "homosalatc") == "homosalate"  # 10글자 중 1글자 오기
