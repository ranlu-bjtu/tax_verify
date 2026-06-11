"""Tests for comparison scope when API fields are absent."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.compare_tax_forms import TARGETS, compare_target, mappings_for_comparison
from src.models.field_mapping import DataType, FieldMapping


def _mapping(target_id: str, field_id: str) -> FieldMapping:
    target = TARGETS[target_id]
    return FieldMapping(
        tax_type=target.tax_type,
        form_code=target.form_code,
        form_name=target.form_name,
        field_id=field_id,
        display_name=field_id,
        data_type=DataType.AMOUNT,
    )


def test_vat_appendix5_ignores_fields_absent_from_api_response():
    target = TARGETS["vat_general_appendix5"]
    mappings = [
        _mapping("vat_general_appendix5", "api_returned"),
        _mapping("vat_general_appendix5", "api_absent"),
    ]
    api_by_tax = {
        target.tax_code: {
            f"{target.api_table}.api_returned": "100.00",
        }
    }
    web_raw = {
        "api_returned": "100.00",
        "api_absent": "200.00",
    }

    comparison_mappings = mappings_for_comparison(target, mappings, api_by_tax)
    result = compare_target(target, comparison_mappings, api_by_tax, web_raw)

    assert [mapping.field_id for mapping in comparison_mappings] == ["api_returned"]
    assert result.summary.total_fields == 1
    assert result.summary.match_count == 1
    assert result.summary.api_missing_count == 0


def test_all_targets_ignore_fields_absent_from_api_response():
    target = TARGETS["vat_general_main"]
    mappings = [
        _mapping("vat_general_main", "api_returned"),
        _mapping("vat_general_main", "api_absent"),
    ]
    api_by_tax = {
        target.tax_code: {
            f"{target.api_table}.api_returned": "100.00",
        }
    }
    web_raw = {
        "api_returned": "100.00",
        "api_absent": "200.00",
    }

    comparison_mappings = mappings_for_comparison(target, mappings, api_by_tax)
    result = compare_target(target, comparison_mappings, api_by_tax, web_raw)

    assert [mapping.field_id for mapping in comparison_mappings] == ["api_returned"]
    assert result.summary.total_fields == 1
    assert result.summary.match_count == 1
    assert result.summary.api_missing_count == 0


def test_all_targets_ignore_blank_api_values():
    target = TARGETS["consumption_tax_surcharge"]
    mappings = [
        _mapping("consumption_tax_surcharge", "api_returned"),
        _mapping("consumption_tax_surcharge", "api_blank"),
    ]
    api_by_tax = {
        target.tax_code: {
            f"{target.api_table}.api_returned": "100.00",
            f"{target.api_table}.api_blank": "",
        }
    }
    web_raw = {
        "api_returned": "100.00",
        "api_blank": "请选择",
    }

    comparison_mappings = mappings_for_comparison(target, mappings, api_by_tax)
    result = compare_target(target, comparison_mappings, api_by_tax, web_raw)

    assert [mapping.field_id for mapping in comparison_mappings] == ["api_returned"]
    assert result.summary.total_fields == 1
    assert result.summary.match_count == 1
    assert result.summary.api_missing_count == 0


if __name__ == "__main__":
    test_vat_appendix5_ignores_fields_absent_from_api_response()
    test_all_targets_ignore_fields_absent_from_api_response()
    test_all_targets_ignore_blank_api_values()
    print("API returned field comparison policy tests passed.")
