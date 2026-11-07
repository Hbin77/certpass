"""certcheck — 화장품 제품 정보로 국내외 인증·등록별 사전 적합성(통과 가능/조건부/불가/해당 없음)을 판정한다.

판정은 '예비'다. 최종 판단은 각 기관과 자격 있는 안전성 평가자가 한다.
"""

STATUS_PASS = "통과 가능"
STATUS_COND = "조건부"
STATUS_FAIL = "불가"
STATUS_NA = "해당 없음"
STATUS_ORDER = {STATUS_FAIL: 0, STATUS_COND: 1, STATUS_PASS: 2, STATUS_NA: 3}
