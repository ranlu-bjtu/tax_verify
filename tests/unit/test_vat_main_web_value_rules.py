import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.compare_tax_forms import TARGETS, adjusted_web_value_for_compare, api_value, apply_target_web_value_rules
from src.models.field_mapping import DataType, FieldMapping


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


def test_vat_general_main_qmldse_uses_sqldse_row_values():
    web_raw = {
        "qmldse_ybxm_bys": "20.00",
        "qmldse_ybxm_bnlj": "200.00",
        "qmldse_jzjtxm_bys": "30.00",
        "qmldse_jzjtxm_bnlj": "300.00",
        "sqldse_ybxm_bys": "13.00",
        "sqldse_ybxm_bnlj": "130.00",
        "sqldse_jzjtxm_bys": "14.00",
        "sqldse_jzjtxm_bnlj": "140.00",
    }

    adjusted = apply_target_web_value_rules(TARGETS["vat_general_main"], web_raw)

    assert adjusted["qmldse_ybxm_bys"] == "13.00"
    assert adjusted["qmldse_ybxm_bnlj"] == "130.00"
    assert adjusted["qmldse_jzjtxm_bys"] == "14.00"
    assert adjusted["qmldse_jzjtxm_bnlj"] == "140.00"


def test_vat_web_value_rules_do_not_affect_other_targets():
    web_raw = {
        "qmwjse_ybxm_bys": "99.99",
        "qcwjse_ybxm_bys": "12.34",
        "qmldse_ybxm_bys": "20.00",
        "sqldse_ybxm_bys": "13.00",
    }

    adjusted = apply_target_web_value_rules(TARGETS["vat_general_appendix1"], web_raw)

    assert adjusted["qmwjse_ybxm_bys"] == "99.99"
    assert adjusted["qmldse_ybxm_bys"] == "20.00"


def test_vat_general_appendix1_hjxse_6_uses_main_current_sales_when_api_zero():
    appendix_target = TARGETS["vat_general_appendix1"]
    main_target = TARGETS["vat_general_main"]
    api_by_tax = {
        appendix_target.tax_code: {
            f"{appendix_target.api_table}.hjxse_6": "0.0",
            f"{main_target.api_table}.asysljsxse_jzjtxm_bys": "17699.12",
        }
    }

    assert api_value(api_by_tax, appendix_target, "hjxse_6") == "17699.12"


def test_vat_general_appendix1_hjxse_6_keeps_direct_nonzero_api_value():
    appendix_target = TARGETS["vat_general_appendix1"]
    main_target = TARGETS["vat_general_main"]
    api_by_tax = {
        appendix_target.tax_code: {
            f"{appendix_target.api_table}.hjxse_6": "88.00",
            f"{main_target.api_table}.asysljsxse_jzjtxm_bys": "17699.12",
        }
    }

    assert api_value(api_by_tax, appendix_target, "hjxse_6") == "88.00"


def test_vat_general_main_qcwjse_cumulative_compares_directly_without_subtracting_current_month():
    target = TARGETS["vat_general_main"]
    mapping = FieldMapping(
        field_id="qcwjse_ybxm_bnlj",
        display_name="qcwjse_ybxm_bnlj",
        data_type=DataType.AMOUNT,
        tax_type=target.tax_type,
        form_code=target.form_code,
        form_name=target.form_name,
    )
    web_raw = {
        "qcwjse_ybxm_bnlj": "120.00",
        "qcwjse_ybxm_bys": "20.00",
    }

    assert adjusted_web_value_for_compare(target, mapping, web_raw) == "120.00"


def test_vat_general_main_qmldse_cumulative_compares_replaced_value_directly():
    target = TARGETS["vat_general_main"]
    mapping = FieldMapping(
        field_id="qmldse_ybxm_bnlj",
        display_name="qmldse_ybxm_bnlj",
        data_type=DataType.AMOUNT,
        tax_type=target.tax_type,
        form_code=target.form_code,
        form_name=target.form_name,
    )
    web_raw = apply_target_web_value_rules(
        target,
        {
            "qmldse_ybxm_bys": "20.00",
            "qmldse_ybxm_bnlj": "200.00",
            "sqldse_ybxm_bys": "13.00",
            "sqldse_ybxm_bnlj": "130.00",
        },
    )

    assert adjusted_web_value_for_compare(target, mapping, web_raw) == "130.00"


def test_vat_general_main_undeclared_retained_tax_cumulative_subtracts_current_month_even_when_negative():
    target = TARGETS["vat_general_main"]
    mapping = FieldMapping(
        field_id="sqldse_ybxm_bnlj",
        display_name="sqldse_ybxm_bnlj",
        data_type=DataType.AMOUNT,
        tax_type=target.tax_type,
        form_code=target.form_code,
        form_name=target.form_name,
    )
    web_raw = {
        "sqldse_ybxm_bys": "15520.77",
        "sqldse_ybxm_bnlj": "0",
    }

    assert (
        adjusted_web_value_for_compare(
            target,
            mapping,
            web_raw,
            current_period_flag=False,
        )
        == "-15520.77"
    )


def test_vat_general_main_filed_retained_tax_cumulative_keeps_direct_page_value():
    target = TARGETS["vat_general_main"]
    mapping = FieldMapping(
        field_id="sqldse_ybxm_bnlj",
        display_name="sqldse_ybxm_bnlj",
        data_type=DataType.AMOUNT,
        tax_type=target.tax_type,
        form_code=target.form_code,
        form_name=target.form_name,
    )
    web_raw = {
        "sqldse_ybxm_bys": "15520.77",
        "sqldse_ybxm_bnlj": "0",
    }

    assert adjusted_web_value_for_compare(target, mapping, web_raw, current_period_flag=True) == "0"


def test_vat_general_main_qmwjse_cumulative_subtracts_current_month_even_when_negative():
    target = TARGETS["vat_general_main"]
    mapping = FieldMapping(
        field_id="qmwjse_ybxm_bnlj",
        display_name="qmwjse_ybxm_bnlj",
        data_type=DataType.AMOUNT,
        tax_type=target.tax_type,
        form_code=target.form_code,
        form_name=target.form_name,
    )
    web_raw = apply_target_web_value_rules(
        target,
        {
            "qmwjse_ybxm_bys": "99.99",
            "qmwjse_ybxm_bnlj": "5.00",
            "qcwjse_ybxm_bys": "12.00",
        },
    )

    assert adjusted_web_value_for_compare(target, mapping, web_raw) == "-7.00"


def test_vat_general_main_jizhengjitui_cumulative_subtracts_current_month():
    target = TARGETS["vat_general_main"]
    mapping = FieldMapping(
        field_id="asysljsxse_jzjtxm_bnlj",
        display_name="asysljsxse_jzjtxm_bnlj",
        data_type=DataType.AMOUNT,
        tax_type=target.tax_type,
        form_code=target.form_code,
        form_name=target.form_name,
    )
    web_raw = {
        "asysljsxse_jzjtxm_bys": "17,699.12",
        "asysljsxse_jzjtxm_bnlj": "17,699.12",
    }

    assert adjusted_web_value_for_compare(target, mapping, web_raw) == "0.00"


def test_vat_general_main_jizhengjitui_actual_deducted_cumulative_uses_current_when_dom_reads_zero():
    web_raw = {
        "sjdkse_jzjtxm_bys": "113.89",
        "sjdkse_jzjtxm_bnlj": "0.00",
    }

    adjusted = apply_target_web_value_rules(TARGETS["vat_general_main"], web_raw)

    assert adjusted["sjdkse_jzjtxm_bnlj"] == "113.89"


def test_vat_general_main_jizhengjitui_opening_unpaid_is_derived_when_dom_reads_wrong_row():
    web_raw = {
        "ynsehj_jzjtxm_bys": "2,186.99",
        "qcwjse_jzjtxm_bnlj": "157,918.84",
        "bqjnsqynse_jzjtxm_bnlj": "157,918.84",
        "qmwjse_jzjtxm_bys": "-217,944.14",
    }

    adjusted = apply_target_web_value_rules(TARGETS["vat_general_main"], web_raw)

    assert adjusted["qcwjse_jzjtxm_bnlj"] == "-62212.29"


def test_vat_general_main_jizhengjitui_compare_stage_repairs_dom_values():
    target = TARGETS["vat_general_main"]
    opening_mapping = FieldMapping(
        field_id="qcwjse_jzjtxm_bnlj",
        display_name="qcwjse_jzjtxm_bnlj",
        data_type=DataType.AMOUNT,
        tax_type=target.tax_type,
        form_code=target.form_code,
        form_name=target.form_name,
    )
    deducted_mapping = FieldMapping(
        field_id="sjdkse_jzjtxm_bnlj",
        display_name="sjdkse_jzjtxm_bnlj",
        data_type=DataType.AMOUNT,
        tax_type=target.tax_type,
        form_code=target.form_code,
        form_name=target.form_name,
    )
    web_raw = {
        "sjdkse_jzjtxm_bys": "113.89",
        "sjdkse_jzjtxm_bnlj": "0.00",
        "ynsehj_jzjtxm_bys": "2,186.99",
        "qcwjse_jzjtxm_bnlj": "157,918.84",
        "bqjnsqynse_jzjtxm_bnlj": "157,918.84",
        "qmwjse_jzjtxm_bys": "-217,944.14",
    }

    assert adjusted_web_value_for_compare(target, deducted_mapping, web_raw) == "113.89"
    assert adjusted_web_value_for_compare(target, opening_mapping, web_raw) == "-62212.29"
