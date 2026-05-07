"""Unit tests for Excel mapping loader."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.mapping.excel_loader import ExcelLoader
from src.mapping.mapping_cleaner import normalize_column_name, MappingCleaner
from src.mapping.mapping_validator import MappingValidator


def test_normalize_column_names():
    assert normalize_column_name("税种") == "tax_type"
    assert normalize_column_name("接口字段ID") == "field_id"
    assert normalize_column_name("JSONPath") == "api_json_path"
    assert normalize_column_name("数据类型") == "data_type"
    assert normalize_column_name("是否比对") == "compare"
    assert normalize_column_name("容差") == "tolerance"


def test_mapping_cleaner():
    cleaner = MappingCleaner()
    raw = [{"接口字段ID": "test_field", "数据类型": "amount", "是否比对": "是"}]
    cleaned = cleaner.clean_rows(raw)
    assert cleaned[0]["field_id"] == "test_field"
    assert cleaned[0]["data_type"] == "amount"
    assert cleaned[0]["compare"] is True


def test_excel_loader():
    loader = ExcelLoader(
        "mappings/vat_small_scale_mapping.xlsx",
        sheet="增值税主表",
        header_row=2,
        data_start_row=3,
    )
    mappings = loader.load()
    assert len(mappings) > 0
    # Check that field_id is populated
    field_ids = [m.field_id for m in mappings]
    assert "sales_3_goods" in field_ids
    # Check data_type
    amount_fields = [m for m in mappings if m.data_type.value == "amount"]
    assert len(amount_fields) > 0


def test_excel_sheets():
    loader = ExcelLoader("mappings/vat_small_scale_mapping.xlsx")
    sheets = loader.list_sheets()
    assert len(sheets) >= 2


def test_validator():
    validator = MappingValidator()
    # Valid mappings
    raw = [
        {"field_id": "f1", "display_name": "字段1", "data_type": "amount", "compare": True},
        {"field_id": "f2", "display_name": "字段2", "data_type": "rate", "compare": True},
    ]
    validated = validator.validate(raw)
    assert len(validated) == 2

    # Missing field_id - auto-generated
    raw2 = [{"display_name": "字段X", "data_type": "text"}]
    validated2 = validator.validate(raw2)
    assert len(validated2) == 1
    assert validated2[0].field_id.startswith("auto_field")


if __name__ == "__main__":
    test_normalize_column_names()
    test_mapping_cleaner()
    test_excel_loader()
    test_excel_sheets()
    test_validator()
    print("All mapping tests passed!")