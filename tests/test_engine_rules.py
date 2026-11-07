"""성분 규정 대조 회귀 테스트 (코드 리뷰에서 나온 거짓 통과·거짓 불가 사례)."""
from datetime import date


from certcheck.classify import evaluate, evaluate_company, gap_type
from certcheck.data import DATA, load_attributes, load_cards, load_reg_index

REG = load_reg_index()
ATTRS = load_attributes()
CARDS = {c["id"]: c for c in load_cards(DATA / "certs")}
NOW = date(2026, 11, 7)


def run(cert_id, ingredients, application="leave_on", **extra):
    p = {"id": "T", "name_kr": "시험", "product_type": "cosmetic", "application": application, "claims": [],
         "documents": [], "formula_known": "full_with_concentration", "manufacturer": {}, "ingredients": ingredients, **extra}
    v = evaluate(CARDS[cert_id], p, {}, REG, ATTRS, NOW)
    return v, {f.code: f.level for f in v.findings}


def ing(inci, pct=None, cas=None, **kw):
    return {"inci": inci, "kr": inci, "pct": pct, "cas": cas, **kw}


def test_grouped_inci_rows_are_indexed_per_ingredient():
    _, codes = run("EU_CPNP", [ing("Retinol", 2.0)])
    assert codes.get("ING_OVER_LIMIT") == "fail" or codes.get("ING_RESTRICTED_SCOPE_CHECK") == "cond"


def test_positive_list_limits_are_compared():
    _, codes = run("EU_CPNP", [ing("Phenoxyethanol", 2.0, role="preservative")])
    assert codes.get("ING_OVER_LIMIT") == "fail"
    _, codes = run("EU_CPNP", [ing("Phenoxyethanol", 0.8, role="preservative")])
    assert "ING_OVER_LIMIT" not in codes


def test_blend_rows_do_not_match_components():
    _, codes = run("EU_CPNP", [ing("Citric Acid", 0.4, "77-92-9")], application="rinse_off")
    assert "ING_OVER_LIMIT" not in codes


def test_banned_with_exception_only_for_natural_essences():
    _, codes = run("EU_CPNP", [ing("Safrole", 0.01)])
    assert codes.get("ING_BANNED") == "fail"
    _, codes = run("EU_CPNP", [ing("Citrus Paradisi (Grapefruit) Peel Oil", 0.5)])
    assert codes.get("ING_BANNED_WITH_EXCEPTION") == "cond" and "ING_BANNED" not in codes
    assert gap_type("ING_BANNED_WITH_EXCEPTION") == "성분 확인"


def test_mercury_compounds_are_banned():
    _, codes = run("EU_CPNP", [ing("Mercuric Oxide", 0.1)])
    assert codes.get("ING_BANNED") == "fail"


def test_cyclomethicone_is_composition_check_not_banned():
    v, codes = run("EU_CPNP", [ing("Cyclomethicone", 2.0)])
    assert codes.get("ING_CYCLOMETHICONE_MIX") == "cond" and "ING_BANNED" not in codes


def test_vegan_name_heuristic_is_not_a_fail():
    v, codes = run("VEGAN_SOCIETY", [ing("Cocos Nucifera (Coconut) Milk", 1.0)])
    assert v.status != "불가"


def test_application_counts_for_applicability():
    card = {"id": "T_RINSE", "jurisdiction": "EU", "kind": "voluntary_certification", "applies_to": {"product_types": ["rinse_off"]}}
    p = {"id": "T", "product_type": "cosmetic", "ingredients": [ing("Water", 80.0)], "manufacturer": {}}
    assert evaluate(card, {**p, "application": "rinse_off"}, {}, REG, ATTRS, NOW).status != "해당 없음"
    assert evaluate(card, {**p, "application": "leave_on"}, {}, REG, ATTRS, NOW).status == "해당 없음"


def test_not_yet_in_force_duty_is_not_applicable():
    v, codes = run("KR_SAFETY_ASSESSMENT", [ing("Water", 80.0)])
    assert v.status == "해당 없음" and "SCOPE_NOT_IN_FORCE" in codes


def test_ecolabel_covers_leave_on_and_excludes_edta():
    v, codes = run("EU_ECOLABEL_RINSEOFF", [ing("Water", 80.0), ing("Disodium EDTA", 0.05)], application="leave_on")
    assert v.status == "불가" and codes.get("ING_EXCLUDED") == "fail"
    v, codes = run("EU_ECOLABEL_RINSEOFF", [ing("Water", 80.0), ing("Methylparaben", 0.2)])
    assert codes.get("ING_EXCLUDED") == "fail"


def test_eu_cards_flag_siloxane_sunset_for_leave_on():
    _, codes = run("EU_CPNP", [ing("Water", 80.0), ing("Cyclopentasiloxane", 2.5)])
    assert codes.get("SILOXANE_SUNSET") == "cond"


def test_prop65_fragrance_without_composition_is_conditional():
    v, codes = run("US_PROP65", [ing("Water", 80.0), ing("Fragrance", 0.2)])
    assert codes.get("PROP65_FRAGRANCE") == "cond" and v.status == "조건부"


def test_company_not_held_differs_from_unknown():
    v = evaluate_company(CARDS["KR_INNOBIZ"], {"company_certs": {"innobiz": "none"}})
    assert any(f.code == "COMPANY_NOT_HELD" for f in v.findings)


def test_substitute_eu_list_is_not_a_final_fail():
    v, codes = run("SA_SFDA", [ing("Mercuric Oxide", 0.1)])
    assert codes.get("ING_PROXY_BANNED") == "cond" and "ING_BANNED" not in codes
    _, codes = run("EG_EDA", [ing("Mercuric Oxide", 0.1)])  # 이집트는 EU 부속서를 그대로 채택
    assert codes.get("ING_BANNED") == "fail"


def test_usda_organic_uses_natural_principles():
    v, _ = run("USDA_ORGANIC", [ing("PEG-20 Glyceryl Triisostearate", 5.0)])
    assert v.status == "불가"


def test_chemical_name_commas_do_not_split_into_false_bans():
    for cid in ("ID_BPOM", "EU_CPNP"):
        v, codes = run(cid, [ing("Citric Acid", 0.4, "77-92-9")], application="rinse_off")
        assert "ING_BANNED" not in codes and "ING_OVER_LIMIT" not in codes, cid


def test_peroxide_conditional_ban_is_conditional():
    v, codes = run("KR_RESPONSIBLE_SELLER", [ing("Limonene", 0.01, "5989-27-5")])
    assert codes.get("ING_BANNED_CONDITIONAL") == "cond" and "ING_BANNED" not in codes


def test_kr_banned_ingredient_is_caught_from_mfds_list():
    v, codes = run("KR_RESPONSIBLE_SELLER", [ing("2,4,5-Trimethylaniline", 0.1, "137-17-7")])
    assert codes.get("ING_BANNED") == "fail"
