import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.compare_tax_forms import parse_vat_general_appendix5_text
from src.models.field_mapping import DataType, FieldMapping


def mapping(field_id: str, col: int | None = None, line_no: str = "", row_name: str = "") -> FieldMapping:
    return FieldMapping(
        field_id=field_id,
        display_name=field_id,
        data_type=DataType.AMOUNT,
        form_code="VAT_GENERAL_APPENDIX5",
        web_col_index=col,
        line_no=line_no,
        row_name=row_name,
    )


def test_parse_appendix5_grid_rows_from_page_text():
    text = """
增值税及附加税费申报表附列资料（五）
纳税人名称
河南雪青新材料有限公司
税（费）款所属期起
2026年4月1日
税（费）款所属期止
2026年4月30日
本期是否适用小微企业“六税两费”减免政策
■ 是  □ 否
减征政策适用主体
□ 个体工商户  ■ 小型微利企业
城市维护建设税
56,641.53
0.00
0.00
0.00
0.07
3,964.91
0.00
50.00
1,982.46
|
0.00
0.00
1,982.45
教育费附加
56,641.53
0.00
0.00
0.00
0.03
1,699.25
0.00
50.00
849.63
|
0.00
0.00
849.62
地方教育附加
56,641.53
0.00
0.00
0.00
0.02
1,132.83
0.00
50.00
566.42
|
0.00
0.00
566.41
合计
169,924.59
0.00
0.00
0.00
--
6,796.99
--
0.00
--
3,398.51
--
0.00
0.00
3,398.48
当期新增投资额
5
0.00
"""
    mappings = [
        mapping("jsyjzzsybzzs_cjs", 3),
        mapping("zzsxejmje_jyf", 4),
        mapping("slzsl_cjs", 7),
        mapping("bqynse_cjs", 8),
        mapping("bqyjse_cjs", 15),
        mapping("bqybtse_cjs", 16),
        mapping("slzsl_jyfj", 7),
        mapping("bqybtse_dfjyfj", 16),
        mapping("bqynse_hj", 8),
        mapping("bqybtse_hj", 16),
        mapping("dqxztze", 15, line_no="5", row_name="当期新增投资额"),
        FieldMapping(field_id="nsrmc", display_name="nsrmc", data_type=DataType.TEXT, form_code="VAT_GENERAL_APPENDIX5"),
        FieldMapping(field_id="bqsfsyxwqylslfjmzc", display_name="bqsfsyxwqylslfjmzc", data_type=DataType.TEXT, form_code="VAT_GENERAL_APPENDIX5"),
        FieldMapping(field_id="jmzcsyzt", display_name="jmzcsyzt", data_type=DataType.TEXT, form_code="VAT_GENERAL_APPENDIX5"),
    ]

    data = parse_vat_general_appendix5_text(text, mappings)

    assert data["nsrmc"] == "河南雪青新材料有限公司"
    assert data["bqsfsyxwqylslfjmzc"] == "是"
    assert data["jmzcsyzt"] == "小型微利企业"
    assert data["jsyjzzsybzzs_cjs"] == "56,641.53"
    assert data["zzsxejmje_jyf"] == "0.00"
    assert data["slzsl_cjs"] == "0.07"
    assert data["bqynse_cjs"] == "3,964.91"
    assert data["bqyjse_cjs"] == "0.00"
    assert data["bqybtse_cjs"] == "1,982.45"
    assert data["slzsl_jyfj"] == "0.03"
    assert data["bqybtse_dfjyfj"] == "566.41"
    assert data["bqynse_hj"] == "6,796.99"
    assert data["bqybtse_hj"] == "3,398.48"
    assert data["dqxztze"] == "0.00"


def test_parse_appendix5_absent_not_applicable_zero_rows():
    text = """
增值税及附加税费申报表附列资料（五）
税（费）种
计税（费）依据
城市维护建设税
1
37,703.27
0.00
0.00
0.00
7.000000%
2,639.23
请选择
0.00
0007049903|SXA031901267|小型微利企业城市维护建设税减征
50.000000%
1,319.62
0.00
0.00
1,319.61
教育费附加
2
37,703.27
0.00
0.00
0.00
3.000000%
1,131.10
请选择
0.00
0061049903|SXA031901273|小型微利企业教育费附加减征
50.000000%
565.55
0.00
0.00
565.55
"""
    mappings = [
        mapping("zzsxejmje_dfjyfj", 4),
        mapping("bqyjse_dfjyfj", 15),
        mapping("dqxztze", 15, line_no="5", row_name="当期新增投资额"),
    ]

    data = parse_vat_general_appendix5_text(text, mappings)

    assert data["zzsxejmje_dfjyfj"] == "0.00"
    assert data["bqyjse_dfjyfj"] == "0.00"
    assert data["dqxztze"] == "0.00"


def test_parse_appendix5_line_separated_rows_with_code_placeholders():
    text = """
增值税及附加税费申报表附列资料（五）
税（费）种
计税（费）依据
城市维护建设税
1
37,703.27
0.00
0.00
0.00
7.000000%
2,639.23
请选择
0.00
0007049903|SXA031901267|小型微利企业城市维护建设税减征
50.000000%
1,319.62
0.00
0.00
1,319.61
教育费附加
2
37,703.27
0.00
0.00
0.00
3.000000%
1,131.10
请选择
0.00
0061049903|SXA031901273|小型微利企业教育费附加减征
50.000000%
565.55
0.00
0.00
565.55
"""
    mappings = [
        mapping("jsyjzzsybzzs_cjs", 3),
        mapping("slzsl_cjs", 7),
        mapping("bqynse_cjs", 8),
        mapping("bqyjse_cjs", 15),
        mapping("bqybtse_cjs", 16),
        mapping("slzsl_jyfj", 7),
        mapping("bqybtse_jyfj", 16),
        mapping("bqybtse_dfjyfj", 16),
    ]

    data = parse_vat_general_appendix5_text(text, mappings)

    assert data["jsyjzzsybzzs_cjs"] == "37,703.27"
    assert data["slzsl_cjs"] == "7.000000%"
    assert data["bqynse_cjs"] == "2,639.23"
    assert data["bqyjse_cjs"] == "0.00"
    assert data["bqybtse_cjs"] == "1,319.61"
    assert data["slzsl_jyfj"] == "3.000000%"
    assert data["bqybtse_jyfj"] == "565.55"
    assert data["bqybtse_dfjyfj"] == "0.00"


def test_parse_appendix5_sparse_zero_rows_default_paid_tax_to_zero():
    text = """
增值税及附加税费申报表附列资料（五）
教育费附加
2
0.00
0.00
0.00
0.00
3.000000%
0.00
0.00
0.00
0.00
0.00
0.00
0.00
地方教育附加
3
0.00
0.00
0.00
0.00
2.000000%
0.00
0.00
0.00
0.00
0.00
0.00
0.00
当期新增投资额
5
0.00
"""
    mappings = [
        mapping("bqyjse_jyfj", 15),
        mapping("bqyjse_dfjyfj", 15),
        mapping("dqxztze", 15, line_no="5", row_name="当期新增投资额"),
    ]

    data = parse_vat_general_appendix5_text(text, mappings)

    assert data["bqyjse_jyfj"] == "0.00"
    assert data["bqyjse_dfjyfj"] == "0.00"
    assert data["dqxztze"] == "0.00"


def test_parse_appendix5_multiline_exemption_text_keeps_paid_tax_column_aligned():
    text = """
增值税及附加税费申报表附列资料（五）
教育费附加	4,300.18	0.00	0.00	0.00	0.03	129.01	0061042802
|按月纳税
的月销售额
免征教育费
附加|《财政部 国家税务总局通知》
12号第一条	129.01	50.00	0.00	|	0.00	0.00	0.00
地方教育附加	4,300.18	0.00	0.00	0.00	0.02	86.00	0099042802
|除小规模
纳税人外月
免征地方教
育附加|
号第一条第（一）款	86.00	50.00	0.00	|	0.00	0.00	0.00
合计	12,900.54	0.00	0.00	0.00	--	516.02	--	215.01	--	150.51	--	0.00	0.00	150.50
"""
    mappings = [
        mapping("bqyjse_jyfj", 15),
        mapping("bqybtse_jyfj", 16),
        mapping("bqyjse_dfjyfj", 15),
        mapping("bqybtse_dfjyfj", 16),
    ]

    data = parse_vat_general_appendix5_text(text, mappings)

    assert data["bqyjse_jyfj"] == "0.00"
    assert data["bqybtse_jyfj"] == "0.00"
    assert data["bqyjse_dfjyfj"] == "0.00"
    assert data["bqybtse_dfjyfj"] == "0.00"


def test_parse_appendix5_present_label_without_value_is_not_synthesized():
    text = """
增值税及附加税费申报表附列资料（五）
城市维护建设税
1
0.00
0.00
0.00
0.00
7.000000%
0.00
0.00
0.00
0.00
0.00
0.00
0.00
地方教育附加
当期新增投资额
"""
    mappings = [
        mapping("zzsxejmje_dfjyfj", 4),
        mapping("dqxztze", 15, line_no="5", row_name="当期新增投资额"),
    ]

    data = parse_vat_general_appendix5_text(text, mappings)

    assert data.get("zzsxejmje_dfjyfj") in (None, "")
    assert data.get("dqxztze") in (None, "")


if __name__ == "__main__":
    test_parse_appendix5_grid_rows_from_page_text()
    test_parse_appendix5_absent_not_applicable_zero_rows()
    test_parse_appendix5_line_separated_rows_with_code_placeholders()
    test_parse_appendix5_sparse_zero_rows_default_paid_tax_to_zero()
    test_parse_appendix5_multiline_exemption_text_keeps_paid_tax_column_aligned()
    test_parse_appendix5_present_label_without_value_is_not_synthesized()
    print("All appendix5 extraction tests passed!")
