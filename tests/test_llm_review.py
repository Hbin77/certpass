"""AI 검토 의견(llm_review): 검토 대상 고르기, 응답 해석, 요청문 형식."""
from certcheck import llm_review


def test_parse_levels_and_fields():
    r = llm_review.parse("판단: 불가 가능성 높음\n이유: 금지 성분과 이름이 같습니다.\n필요한 정보: 없음\n근거: EUCPNP 금지 성분")
    assert r["level"] == "불가 가능성 높음" and r["reason"].startswith("금지") and r["basis"].startswith("EUCPNP")
    assert llm_review.parse("**판단:** 판단 불가\n필요한 정보: 보존제 함량")["level"] == "판단 불가"
    assert llm_review.parse("잘 모르겠습니다")["level"] == "판단 불가"  # 형식을 안 지키면 경보로 올리지 않음


def test_needs_review_only_unsure_non_fail():
    cond = {"status": "조건부", "findings": [{"code": "ING_RESTRICTED_PCT_UNKNOWN", "level": "cond", "message": "x"}]}
    assert llm_review.needs_review(cond)
    assert not llm_review.needs_review({**cond, "status": "불가"})
    assert not llm_review.needs_review({"status": "조건부", "findings": [{"code": "DOC_MISSING", "level": "cond"}]})


def test_prompt_has_no_bracket_line_heads_and_rounds():
    v = {"cert_id": "EU_CPNP", "status": "조건부",
         "findings": [{"code": "ING_BANNED_SUSPECT", "level": "cond", "message": "X: 금지 성분 'y'와 표기가 97% 같음 [kw:a]"}]}
    p = llm_review.build_prompt(v, {"id": "EU_CPNP", "name_ko": "EU", "jurisdiction": "EU"},
                                {"ingredients": [{"inci": "Water", "pct": 70}, {"inci": "X"}]}, {"fail_proba": 0.1234}, [])
    assert "불가 확률 0.12" in p and "[kw:" not in p and "EUCPNP" in p
    assert not any(line.lstrip().startswith("[") for line in p.splitlines())


def test_prompt_hides_formula_and_mixed_level_is_unsure():
    v = {"cert_id": "EU_CPNP", "status": "조건부", "findings": [
        {"code": "ING_RESTRICTED_PCT_UNKNOWN", "level": "cond", "message": "제한 성분 X: 한도 0.5% — 함량 미상 (전성분 순서상 0~8.3%)"}]}
    p = llm_review.build_prompt(v, {"id": "EU_CPNP"}, {"ingredients": [{"inci": "Water", "pct": 70.12, "cas": "7732-18-5"}, {"inci": "X"}]})
    assert "70.12" not in p and "7732-18-5" not in p and "Water" not in p and "전성분 순서상" not in p and "한도 0.5%" in p
    assert llm_review.parse("판단: 불가 가능성 높음 또는 판단 불가")["level"] == "판단 불가"
