import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.compare_tax_forms import TARGETS, apply_target_web_value_rules


def test_vat_general_main_qmwjse_current_month_uses_qcwjse_position():
    web_raw = {
        "qmwjse_ybxm_bys": "99.99",
        "qcwjse_ybxm_bys": "12.34",
    }

    adjusted = apply_target_web_value_rules(TARGETS["vat_general_main"], web_raw)

    assert adjusted["qmwjse_ybxm_bys"] == "12.34"


def test_vat_general_main_qmwjse_current_month_missing_when_source_missing():
    web_raw = {
        "qmwjse_ybxm_bys": "99.99",
    }

    adjusted = apply_target_web_value_rules(TARGETS["vat_general_main"], web_raw)

    assert adjusted["qmwjse_ybxm_bys"] is None


def test_vat_web_value_rules_do_not_affect_other_targets():
    web_raw = {
        "qmwjse_ybxm_bys": "99.99",
        "qcwjse_ybxm_bys": "12.34",
    }

    adjusted = apply_target_web_value_rules(TARGETS["vat_general_appendix1"], web_raw)

    assert adjusted["qmwjse_ybxm_bys"] == "99.99"
