import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.compare_tax_forms import (
    TARGETS,
    is_low_web_extraction_coverage,
    load_mappings,
    parse_vat_general_appendix1_text,
    parse_vat_general_appendix1_rows,
    parse_vat_small_appendix1_text,
    parse_vat_small_appendix2_text,
    parse_vat_small_main_text,
)


def test_vat_small_main_text_parser_does_not_read_line_number_as_amount():
    mappings = load_mappings(TARGETS["vat_small_main"])
    text = """
    （一）应征增值税不含税销售额（3%征收率）1 0.00 0.00 0.00 0.00
    增值税专用发票不含税销售额2 0.00 0.00 0.00 0.00
    （四）免税销售额 9=10+11+12 0.00 0.00 0.00 79,207.92
    其中：小微企业免税销售额 10 0.00 0.00 0.00 79,207.92
          其他免税销售额 12 0.00 0.00 0.00 0.00
    本期免税额 19 0.00 0.00 0.00 2,376.24
    其中：小微企业免税额 20 0.00 0.00 0.00 2,376.24
    """

    data = parse_vat_small_main_text(text, mappings)

    assert data["yzzzsbhsxse_fwjbdc_bqs"] == "0.00"
    assert data["yzzzsbhsxse_hwjlw_bnlj"] == "0.00"
    assert data["msxse_fwjbdc_bnlj"] == "79207.92"
    assert data["xwqymsxse_fwjbdc_bnlj"] == "79207.92"
    assert data["qtmsxse_fwjbdc_bnlj"] == "0.00"
    assert data["bqmse_fwjbdc_bnlj"] == "2376.24"
    assert data["xwqymse_fwjbdc_bnlj"] == "2376.24"


def test_vat_small_main_text_parser_subtracts_current_period_from_cumulative_columns():
    mappings = load_mappings(TARGETS["vat_small_main"])
    text = """
    （一）应征增值税不含税销售额（3%征收率）1 0.00 234,788.66 0.00 755,465.07
    增值税专用发票不含税销售额2 0.00 224,887.67 0.00 741,702.69
    其他增值税发票不含税销售额3 0.00 9,900.99 0.00 13,762.38
    本期应纳税额 16 0.00 7,043.66 0.00 22,663.95
    本期应纳税额减征额 18 0.00 4,695.78 0.00 15,109.32
    应纳税额合计 22=16-18或17-18 0.00 2,347.88 0.00 7,554.63
    """

    data = parse_vat_small_main_text(text, mappings)

    assert data["yzzzsbhsxse_fwjbdc_bnlj"] == "520676.41"
    assert data["swjgdkdzzszyfpbhsxse_fwjbdc_bnlj"] == "516815.02"
    assert data["skqjkjdptfpbhsxse_fwjbdc_bnlj"] == "3861.39"
    assert data["bqynse_fwjbdc_bnlj"] == "15620.29"
    assert data["bqynsejze_fwjbdc_bnlj"] == "10413.54"
    assert data["ynsehj_fwjbdc_bqs"] == "2,347.88"
    assert data["ynsehj_fwjbdc_bnlj"] == "5206.75"


def test_vat_small_main_text_parser_derives_tax_total_when_line_22_is_not_rendered():
    mappings = load_mappings(TARGETS["vat_small_main"])
    text = """
    本期应纳税额 16 0.00 7,043.66 0.00 22,663.95
    本期应纳税额减征额 18 0.00 4,695.78 0.00 15,109.32
    """

    data = parse_vat_small_main_text(text, mappings)

    assert data["ynsehj_fwjbdc_bqs"] == "2347.88"
    assert data["ynsehj_fwjbdc_bnlj"] == "5206.75"


def test_vat_small_main_text_parser_reads_split_dom_rows():
    mappings = load_mappings(TARGETS["vat_small_main"])
    row_names = {
        field_id: next(mapping.row_name for mapping in mappings if mapping.field_id == field_id)
        for field_id in (
            "yzzzsbhsxse_fwjbdc_bqs",
            "msxse_fwjbdc_bqs",
            "xwqymsxse_fwjbdc_bqs",
            "bqmse_fwjbdc_bqs",
            "xwqymse_fwjbdc_bqs",
        )
    }
    text = f"""
    提示 自2023年1月1日至2027年12月31日 3%征收率
    {row_names["yzzzsbhsxse_fwjbdc_bqs"]}
    1
    0.00
    0.00
    0.00
    0.00
    {row_names["msxse_fwjbdc_bqs"]}
    9=10+11+12
    0.00
    25,840.53
    0.00
    143,096.54
    {row_names["xwqymsxse_fwjbdc_bqs"]}
    10
    0.00
    25,840.53
    0.00
    143,096.54
    {row_names["bqmse_fwjbdc_bqs"]}
    19
    0.00
    775.22
    0.00
    4,292.89
    {row_names["xwqymse_fwjbdc_bqs"]}
    20
    0.00
    775.22
    0.00
    4,292.89
    """

    data = parse_vat_small_main_text(text, mappings)

    assert data["yzzzsbhsxse_fwjbdc_bqs"] == "0.00"
    assert data["msxse_fwjbdc_bqs"] == "25,840.53"
    assert data["msxse_fwjbdc_bnlj"] == "117256.01"
    assert data["xwqymsxse_fwjbdc_bqs"] == "25,840.53"
    assert data["xwqymsxse_fwjbdc_bnlj"] == "117256.01"
    assert data["bqmse_fwjbdc_bqs"] == "775.22"
    assert data["bqmse_fwjbdc_bnlj"] == "3517.67"
    assert data["xwqymse_fwjbdc_bqs"] == "775.22"
    assert data["xwqymse_fwjbdc_bnlj"] == "3517.67"


def test_vat_small_appendix2_text_parser_reads_rate_and_reduction_ratio():
    mappings = load_mappings(TARGETS["vat_small_appendix2"])
    text = """
    城市维护建设税 0.00 0.00 0.05 0.00 0.00 50.00 0.00
    教育费附加 0.00 0.00 0.03 0.00 0.00 50.00 0.00
    地方教育附加 0.00 0.00 0.02 0.00 0.00 50.00 0.00
    合计 0.00 0.00 —— 0.00 —— 0.00 —— 0.00
    """

    data = parse_vat_small_appendix2_text(text, mappings)

    assert data["slzsl_cjs"] == "0.05"
    assert data["xwqylslfjmzcjzbl_cjs"] == "50.00"
    assert data["slzsl_jyfj"] == "0.03"
    assert data["xwqylslfjmzcjzbl_jyfj"] == "50.00"
    assert data["slzsl_dfjyfj"] == "0.02"
    assert data["xwqylslfjmzcjzbl_dfjyfj"] == "50.00"
    assert data["bqjmsejmxzdm_cjs"] == "0.00"
    assert data["bqyjse_cjs"] == "0.00"
    assert data["bqybtse_cjs"] == "0.00"
    assert data["bqynse_hj"] == "0.00"
    assert data["bqybtse_hj"] == "0.00"
    assert is_low_web_extraction_coverage(TARGETS["vat_small_appendix2"], data, mappings) is False


def test_vat_small_appendix2_text_parser_reads_refund_amount_column():
    mappings = load_mappings(TARGETS["vat_small_appendix2"])
    text = """
    城市维护建设税 2347.88 0.00 0.07 164.35 0.00 50.00 82.18 0.00 82.17
    教育费附加 2347.88 0.00 0.03 70.44 0.00 50.00 35.22 0.00 35.22
    地方教育附加 2347.88 0.00 0.02 46.96 0.00 50.00 23.48 0.00 23.48
    """

    data = parse_vat_small_appendix2_text(text, mappings)

    assert data["bqybtse_cjs"] == "82.17"
    assert data["bqybtse_jyfj"] == "35.22"
    assert data["bqybtse_dfjyfj"] == "23.48"


def test_vat_small_appendix2_text_parser_reads_percent_sign_rates():
    mappings = load_mappings(TARGETS["vat_small_appendix2"])
    row_names = {
        suffix: next(mapping.row_name for mapping in mappings if mapping.field_id == f"slzsl_{suffix}")
        for suffix in ("cjs", "jyfj", "dfjyfj")
    }
    text = f"""
    {row_names["cjs"]} 0.00 0.00 7.000000% 0.00 请选择 0.00 50.00 0.00 0.00 0.00
    {row_names["jyfj"]} 0.00 0.00 3.000000% 0.00 请选择 0.00 50.00 0.00 0.00 0.00
    {row_names["dfjyfj"]} 0.00 0.00 2.000000% 0.00 请选择 0.00 50.00 0.00 0.00 0.00
    """

    data = parse_vat_small_appendix2_text(text, mappings)

    assert data["slzsl_cjs"] == "0.07"
    assert data["slzsl_jyfj"] == "0.03"
    assert data["slzsl_dfjyfj"] == "0.02"
    assert data["xwqylslfjmzcjzbl_cjs"] == "50.00"
    assert data["xwqylslfjmzcjzbl_jyfj"] == "50.00"
    assert data["xwqylslfjmzcjzbl_dfjyfj"] == "50.00"


def test_vat_small_appendix2_text_parser_reads_split_dom_rows():
    mappings = load_mappings(TARGETS["vat_small_appendix2"])
    row_names = {
        suffix: next(mapping.row_name for mapping in mappings if mapping.field_id == f"slzsl_{suffix}")
        for suffix in ("cjs", "jyfj", "dfjyfj")
    }
    text = f"""
    {row_names["cjs"]}
    0.00
    0.00
    7.000000%
    0.00
    请选择
    0.00
    50.00
    0.00
    0.00
    0.00
    {row_names["jyfj"]}
    0.00
    0.00
    3.000000%
    0.00
    请选择
    0.00
    50.00
    0.00
    0.00
    0.00
    {row_names["dfjyfj"]}
    0.00
    0.00
    2.000000%
    0.00
    请选择
    0.00
    50.00
    0.00
    0.00
    0.00
    """

    data = parse_vat_small_appendix2_text(text, mappings)

    assert data["slzsl_cjs"] == "0.07"
    assert data["slzsl_jyfj"] == "0.03"
    assert data["slzsl_dfjyfj"] == "0.02"
    assert data["xwqylslfjmzcjzbl_cjs"] == "50.00"
    assert data["xwqylslfjmzcjzbl_jyfj"] == "50.00"
    assert data["xwqylslfjmzcjzbl_dfjyfj"] == "50.00"


def test_vat_small_appendix1_text_parser_reads_zero_blocks_for_coverage():
    mappings = load_mappings(TARGETS["vat_small_appendix1"])
    text = """
    期初余额 本期发生额 本期扣除额 期末余额
    1 2 3（3≤1＋2之和，且3≤5） 4＝1＋2－3
    0.00 0.00 0.00 0.00
    全部含税收入（适用3%征收率）本期扣除额 含税销售额 不含税销售额
    5 6=3 7＝5－6 8＝7÷（1+征收率）
    0.00 0.00 0.00 0.00
    期初余额 本期发生额 本期扣除额 期末余额
    9 10 11（11≤9＋10之和，且11≤13） 12＝9＋10－11
    0.00 0.00 0.00 0.00
    全部含税收入（适用5%征收率）本期扣除额 含税销售额 不含税销售额
    13 14=11 15＝13－14 16＝15÷1.05
    0.00 0.00 0.00 0.00
    """

    data = parse_vat_small_appendix1_text(text, mappings)

    assert all(data[field_id] == "0.00" for field_id in (
        "qcye",
        "bqfse",
        "bqkce",
        "qmye",
        "ysfwxsqbhssr5",
        "ysfwxsbqkce5",
        "ysfwxshsxse5",
        "ysfwxsbhsxse5",
    ))
    assert is_low_web_extraction_coverage(TARGETS["vat_small_appendix1"], data, mappings) is False


def test_vat_general_appendix1_partial_extraction_is_low_coverage():
    mappings = load_mappings(TARGETS["vat_general_appendix1"])
    web_data = {
        mapping.field_id: "0.00"
        for mapping in mappings[:36]
    }

    assert is_low_web_extraction_coverage(TARGETS["vat_general_appendix1"], web_data, mappings) is True


def test_vat_general_appendix1_text_parser_reads_line_5_virtual_row():
    mappings = load_mappings(TARGETS["vat_general_appendix1"])
    text = """
    项目及栏次 开具增值税专用发票 开具其他发票 未开具发票 纳税检查调整 合计 扣除后
    6%税率 5 94,339.62 5,660.38 0.00 0.00 0.00 0.00 0.00 0.00 94,339.62 5,660.38 100,000.00 0.00 100,000.00 5,660.38
    """

    data = parse_vat_general_appendix1_text(text, mappings)

    assert data["kjskzzszyfpXse_5"] == "94,339.62"
    assert data["kjskzzszyfpXxynse_5"] == "5,660.38"
    assert data["kchXxynse_5"] == "5,660.38"


def test_vat_general_appendix1_row_parser_reads_line_5_virtual_row():
    mappings = load_mappings(TARGETS["vat_general_appendix1"])
    rows = [
        [
            "二、简易计税方法计税",
            "全部征税项目",
            "6%税率",
            "5",
            "94,339.62",
            "5,660.38",
            "0.00",
            "0.00",
            "0.00",
            "0.00",
            "0.00",
            "0.00",
            "94,339.62",
            "5,660.38",
            "100,000.00",
            "0.00",
            "100,000.00",
            "5,660.38",
        ]
    ]

    data = parse_vat_general_appendix1_rows(rows, mappings)

    assert data["kjskzzszyfpXse_5"] == "94339.62"
    assert data["kjskzzszyfpXxynse_5"] == "5660.38"
    assert data["kchXxynse_5"] == "5660.38"


if __name__ == "__main__":
    test_vat_small_main_text_parser_does_not_read_line_number_as_amount()
    test_vat_small_main_text_parser_subtracts_current_period_from_cumulative_columns()
    test_vat_small_main_text_parser_derives_tax_total_when_line_22_is_not_rendered()
    test_vat_small_main_text_parser_reads_split_dom_rows()
    test_vat_small_appendix2_text_parser_reads_rate_and_reduction_ratio()
    test_vat_small_appendix2_text_parser_reads_refund_amount_column()
    test_vat_small_appendix2_text_parser_reads_percent_sign_rates()
    test_vat_small_appendix2_text_parser_reads_split_dom_rows()
    test_vat_small_appendix1_text_parser_reads_zero_blocks_for_coverage()
    test_vat_general_appendix1_partial_extraction_is_low_coverage()
    test_vat_general_appendix1_text_parser_reads_line_5_virtual_row()
    test_vat_general_appendix1_row_parser_reads_line_5_virtual_row()
