import sys
import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.cbj.verification import (
    BackendField,
    annual_query_window,
    build_numeric_comparison,
    find_field,
    report_has_errors,
    save_cbj_report,
)


def test_find_field_searches_flattened_and_raw_nodes():
    node = {"data": {"sz_cbj": {"table.snzzzgrs_cbj": 12}}, "raw": {"x": {"snzzzggzze_cbj": "123.45"}}}

    people = find_field("snzzzgrs_cbj", node)
    wages = find_field("snzzzggzze_cbj", node)

    assert people is not None
    assert people.value == 12
    assert wages is not None
    assert wages.value == "123.45"


def test_annual_query_window_uses_current_year_and_previous_tax_year():
    window = annual_query_window(today=date(2026, 5, 12))

    assert window == {
        "declaration_start": "2026-01-01",
        "declaration_end": "2026-05-12",
        "period_start": "2025-01-01",
        "period_end": "2025-12-31",
    }


def test_cbj_numeric_comparison_detects_match_and_mismatch():
    matched = build_numeric_comparison(
        "snzzzggzze_cbj",
        BackendField("snzzzggzze_cbj", "100.00", "$.field"),
        "100",
        Decimal("0.01"),
    )
    mismatched = build_numeric_comparison(
        "snzzzgrs_cbj",
        BackendField("snzzzgrs_cbj", "12", "$.field"),
        "13",
        Decimal("0"),
    )

    assert matched["status"] == "match"
    assert mismatched["status"] == "mismatch"


def test_cbj_report_has_errors():
    with tempfile.TemporaryDirectory() as tmp:
        report = save_cbj_report(
            "task",
            "personal",
            "test",
            [{"field_id": "snzzzgrs_cbj", "status": "api_missing"}],
            output_root=tmp,
        )

        assert report_has_errors(report) is True


if __name__ == "__main__":
    test_find_field_searches_flattened_and_raw_nodes()
    test_annual_query_window_uses_current_year_and_previous_tax_year()
    test_cbj_numeric_comparison_detects_match_and_mismatch()
    test_cbj_report_has_errors()
    print("All CBJ verification tests passed!")
