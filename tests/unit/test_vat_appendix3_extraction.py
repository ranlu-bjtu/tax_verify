"""Unit tests for VAT general appendix 3 table extraction."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.compare_tax_forms import parse_vat_general_appendix3_rows
from src.models.field_mapping import DataType, FieldMapping


def mapping(field_id: str, line_no: str, row_name: str, col: int) -> FieldMapping:
    return FieldMapping(
        field_id=field_id,
        display_name=field_id,
        row_name=row_name,
        line_no=line_no,
        column_name="",
        data_type=DataType.AMOUNT,
        web_cell_id=field_id,
        web_row_index=0,
        web_col_index=col,
        api_json_path=f"$.{field_id}",
        compare=True,
        form_code="VAT_GENERAL_APPENDIX3",
    )


def test_parse_appendix3_blank_amount_cells_as_zero():
    rows = [
        ["项目及栏次", "本期服务、不动产和无形资产价税合计额", "期初余额", "本期发生额"],
        ["13%税率的项目", "1", "", "", "", "", "", ""],
    ]
    mappings = [
        mapping("msxse_1", "1", "13%税率的项目", 3),
        mapping("qcye_1", "1", "13%税率的项目", 4),
    ]

    data = parse_vat_general_appendix3_rows(rows, mappings)

    assert data["msxse_1"] == "0.00"
    assert data["qcye_1"] == "0.00"


def test_parse_appendix3_numeric_cells_by_line_and_excel_column():
    rows = [
        ["6%税率的项目（不含金融商品转让）", "3", "100.10", "20.20", "30.30", "40.40", "50.50", "60.60"],
    ]
    mappings = [
        mapping("msxse_3", "3", "6%税率的项目(不含金融商品转让)", 3),
        mapping("bqfse_3", "3", "6%税率的项目(不含金融商品转让)", 5),
        mapping("qmye_3", "3", "6%税率的项目(不含金融商品转让)", 8),
    ]

    data = parse_vat_general_appendix3_rows(rows, mappings)

    assert data["msxse_3"] == "100.10"
    assert data["bqfse_3"] == "30.30"
    assert data["qmye_3"] == "60.60"


def test_parse_appendix3_ignores_header_line_numbers():
    rows = [
        ["项目及栏次", "1", "2", "3", "4=2+3", "5", "6=4-5"],
        ["9%税率的项目", "2", "", "8.88", "", "", "", ""],
    ]
    mappings = [
        mapping("qcye_2", "2", "9%税率的项目", 4),
    ]

    data = parse_vat_general_appendix3_rows(rows, mappings)

    assert data["qcye_2"] == "8.88"


if __name__ == "__main__":
    test_parse_appendix3_blank_amount_cells_as_zero()
    test_parse_appendix3_numeric_cells_by_line_and_excel_column()
    test_parse_appendix3_ignores_header_line_numbers()
    print("All appendix3 extraction tests passed!")
