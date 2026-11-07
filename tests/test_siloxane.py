"""REACH 부속서 XVII 70항(Reg. 2024/1328) D4·D5·D6 판정 회귀 테스트."""
from datetime import date
from pathlib import Path

import pytest
import yaml

from certcheck.classify import Verdict, check_special

CARD = yaml.safe_load((Path(__file__).resolve().parents[1] / "data/certs/EU_REACH_D4D5D6.yaml").read_text(encoding="utf-8"))
NOW = date(2026, 11, 7)


def first_finding(application, inci, pct, eval_date):
    product = {"application": application, "ingredients": [{"inci": inci, "kr": "시험", "pct": pct}]}
    v = Verdict("t", "t", CARD["id"], "n", "EU", "k")
    check_special(v, CARD, product, eval_date)
    return v.findings[0].level, v.findings[0].code


@pytest.mark.parametrize("application, inci, pct, eval_date, expected", [
    ("rinse_off", "CYCLOPENTASILOXANE", 0.5, NOW, ("fail", "SILOXANE_RINSEOFF")),      # 3(a) 2020-01-31 이후
    ("rinse_off", "CYCLOHEXASILOXANE", 0.5, NOW, ("cond", "SILOXANE_SUNSET")),         # D6는 3(b)
    ("rinse_off", "CYCLOHEXASILOXANE", 0.5, date(2027, 6, 7), ("fail", "SILOXANE_BANNED")),
    ("leave_on", "CYCLOPENTASILOXANE", 2.5, date(2027, 6, 6), ("cond", "SILOXANE_SUNSET")),  # "after 6 June 2027"
    ("leave_on", "CYCLOPENTASILOXANE", 2.5, date(2027, 6, 7), ("fail", "SILOXANE_BANNED")),
    ("leave_on", "CYCLOTETRASILOXANE", 0.05, NOW, ("fail", "SILOXANE_D4_BANNED")),     # 화장품 부속서 II
    ("rinse_off", "CYCLOMETHICONE", 2, NOW, ("cond", "SILOXANE_MIX")),
    ("rinse_off", "CYCLOPENTASILOXANE", None, NOW, ("cond", "SILOXANE_PCT_UNKNOWN")),
    ("leave_on", "CYCLOHEXASILOXANE", 0.05, date(2028, 1, 1), ("info", "SILOXANE_UNDER")),
])
def test_siloxane_rules(application, inci, pct, eval_date, expected):
    assert first_finding(application, inci, pct, eval_date) == expected
