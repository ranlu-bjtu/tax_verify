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


if __name__ == "__main__":
    test_parse_appendix5_grid_rows_from_page_text()
    print("All appendix5 extraction tests passed!")
