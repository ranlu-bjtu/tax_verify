import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import scripts.compare_tax_forms as compare_tax_forms
from scripts.compare_tax_forms import TARGETS, comparison_quality_issues
from src.models.field_mapping import DataType, FieldMapping


def _amount_mapping(field_id: str) -> FieldMapping:
    target = TARGETS["vat_general_appendix1"]
    return FieldMapping(
        tax_type=target.tax_type,
        form_code=target.form_code,
        form_name=target.form_name,
        field_id=field_id,
        display_name=field_id,
        data_type=DataType.AMOUNT,
    )


def _api_by_tax(field_values: dict[str, str]):
    target = TARGETS["vat_general_appendix1"]
    return {
        target.tax_code: {
            f"{target.api_table}.{field_id}": value
            for field_id, value in field_values.items()
        }
    }


def test_merge_web_data_fill_missing_preserves_existing_values():
    merged = compare_tax_forms.merge_web_data_fill_missing(
        {"field_a": "1.00", "field_b": None, "field_c": ""},
        {"field_a": "9.99", "field_b": "2.00", "field_c": "3.00", "field_d": "4.00"},
    )

    assert merged == {
        "field_a": "1.00",
        "field_b": "2.00",
        "field_c": "3.00",
        "field_d": "4.00",
    }


def test_reliable_web_extraction_retries_when_compare_would_report_web_missing():
    target = TARGETS["vat_general_appendix1"]
    mappings = [_amount_mapping("field_a"), _amount_mapping("field_b")]
    api_by_tax = _api_by_tax({"field_a": "1.00", "field_b": "2.00"})
    extracts = []
    render_attempts = []
    requested_fields = []

    def fake_extract(_page, _target, _mappings):
        extracts.append(1)
        requested_fields.append([mapping.field_id for mapping in _mappings])
        if len(extracts) == 1:
            return {"field_a": "1.00", "field_b": None}
        return {"field_a": "1.00", "field_b": "2.00"}

    originals = _patch_web_extraction(
        extract_web_data_for_target=fake_extract,
        force_target_render_for_extraction=lambda _page, _target, _mappings, attempt: render_attempts.append(attempt),
        extract_missing_web_fields_after_scroll_sweep=lambda _page, _target, _mappings: {},
    )
    try:
        data = compare_tax_forms.extract_web_data_reliably(
            object(),
            target,
            mappings,
            mappings,
            api_by_tax,
            current_period_flag=True,
        )
    finally:
        _restore_web_extraction(originals)

    assert data["field_a"] == "1.00"
    assert data["field_b"] == "2.00"
    assert len(extracts) == 2
    assert requested_fields == [["field_a", "field_b"], ["field_a", "field_b"]]
    assert render_attempts == [1]


def test_reliable_web_extraction_skips_expensive_recovery_when_no_web_missing():
    target = TARGETS["vat_general_appendix1"]
    mappings = [_amount_mapping("field_a"), _amount_mapping("field_b")]
    api_by_tax = _api_by_tax({"field_a": "1.00", "field_b": "0.00"})
    render_attempts = []

    originals = _patch_web_extraction(
        extract_web_data_for_target=lambda _page, _target, _mappings: {"field_a": "1.00", "field_b": None},
        force_target_render_for_extraction=lambda _page, _target, _mappings, attempt: render_attempts.append(attempt),
        extract_missing_web_fields_after_scroll_sweep=lambda _page, _target, _mappings: {},
    )
    try:
        data = compare_tax_forms.extract_web_data_reliably(
            object(),
            target,
            mappings,
            mappings,
            api_by_tax,
            current_period_flag=True,
        )
    finally:
        _restore_web_extraction(originals)

    assert data["field_a"] == "1.00"
    assert data["field_b"] is None
    assert render_attempts == []


def test_reliable_web_extraction_supplements_missing_fields_after_retry():
    target = TARGETS["vat_general_appendix1"]
    mappings = [_amount_mapping("field_a"), _amount_mapping("field_b")]
    api_by_tax = _api_by_tax({"field_a": "1.00", "field_b": "2.00"})
    supplement_requests = []

    def fake_supplement(_page, _target, requested_mappings):
        supplement_requests.append([mapping.field_id for mapping in requested_mappings])
        return {"field_b": "2.00"}

    originals = _patch_web_extraction(
        extract_web_data_for_target=lambda _page, _target, _mappings: {"field_a": "1.00", "field_b": None},
        force_target_render_for_extraction=lambda _page, _target, _mappings, _attempt: None,
        extract_missing_web_fields_after_scroll_sweep=fake_supplement,
    )
    try:
        data = compare_tax_forms.extract_web_data_reliably(
            object(),
            target,
            mappings,
            mappings,
            api_by_tax,
            current_period_flag=True,
        )
    finally:
        _restore_web_extraction(originals)

    assert data["field_b"] == "2.00"
    assert supplement_requests == [["field_b"]]


def test_reliable_web_extraction_uses_missing_fields_for_render_scope():
    target = TARGETS["vat_general_appendix1"]
    mappings = [_amount_mapping("field_a"), _amount_mapping("field_b"), _amount_mapping("field_c")]
    api_by_tax = _api_by_tax({"field_a": "1.00", "field_b": "2.00", "field_c": "3.00"})
    render_requests = []

    def fake_extract(_page, _target, _mappings):
        return {"field_a": "1.00", "field_b": None, "field_c": "3.00"}

    def fake_force(_page, _target, requested_mappings, _attempt):
        render_requests.append([mapping.field_id for mapping in requested_mappings])

    originals = _patch_web_extraction(
        extract_web_data_for_target=fake_extract,
        force_target_render_for_extraction=fake_force,
        extract_missing_web_fields_after_scroll_sweep=lambda _page, _target, _mappings: {},
    )
    try:
        data = compare_tax_forms.extract_web_data_reliably(
            object(),
            target,
            mappings,
            mappings,
            api_by_tax,
            current_period_flag=True,
        )
    finally:
        _restore_web_extraction(originals)

    assert data["field_b"] is None
    assert render_requests
    assert all(request == ["field_b"] for request in render_requests)


def test_reliable_web_extraction_stops_when_recovery_budget_is_exhausted():
    target = TARGETS["vat_general_appendix1"]
    mappings = [_amount_mapping("field_a"), _amount_mapping("field_b")]
    api_by_tax = _api_by_tax({"field_a": "1.00", "field_b": "2.00"})
    render_attempts = []
    clock = {"now": 0.0}

    def fake_extract(_page, _target, _mappings):
        return {"field_a": "1.00", "field_b": None}

    def fake_force(_page, _target, _mappings, attempt):
        render_attempts.append(attempt)
        clock["now"] = compare_tax_forms.WEB_EXTRACTION_RECOVERY_MAX_SECONDS + 1

    originals = _patch_web_extraction(
        extract_web_data_for_target=fake_extract,
        force_target_render_for_extraction=fake_force,
        extract_missing_web_fields_after_scroll_sweep=lambda _page, _target, _mappings: {"field_b": "2.00"},
    )
    original_time = compare_tax_forms.time.time
    try:
        compare_tax_forms.time.time = lambda: clock["now"]
        data = compare_tax_forms.extract_web_data_reliably(
            object(),
            target,
            mappings,
            mappings,
            api_by_tax,
            current_period_flag=True,
        )
    finally:
        compare_tax_forms.time.time = original_time
        _restore_web_extraction(originals)

    assert data["field_a"] == "1.00"
    assert data["field_b"] is None
    assert render_attempts == [1]


def test_low_web_coverage_without_web_missing_is_not_quality_issue():
    result = _comparison_result_stub(web_missing_count=0)

    issues = comparison_quality_issues(
        TARGETS["vat_general_appendix1"],
        result,
        low_web_coverage=True,
        current_period_flag=True,
    )

    assert "low_web_extraction_coverage" not in issues
    assert issues == []


def test_low_web_coverage_with_web_missing_is_quality_issue():
    result = _comparison_result_stub(web_missing_count=2)

    issues = comparison_quality_issues(
        TARGETS["vat_general_appendix1"],
        result,
        low_web_coverage=True,
        current_period_flag=True,
    )

    assert "web_missing=2" in issues
    assert "low_web_extraction_coverage" in issues


class _SummaryStub:
    def __init__(self, web_missing_count: int = 0):
        self.mismatch_count = 0
        self.api_missing_count = 0
        self.web_missing_count = web_missing_count
        self.parse_error_count = 0
        self.mapping_error_count = 0
        self.both_missing_count = 0
        self.total_fields = 2


class _ComparisonResultStub:
    def __init__(self, web_missing_count: int = 0):
        self.summary = _SummaryStub(web_missing_count=web_missing_count)


def _comparison_result_stub(web_missing_count: int = 0):
    return _ComparisonResultStub(web_missing_count=web_missing_count)


def _patch_web_extraction(**replacements):
    originals = {}
    for name, replacement in replacements.items():
        originals[name] = getattr(compare_tax_forms, name)
        setattr(compare_tax_forms, name, replacement)
    return originals


def _restore_web_extraction(originals):
    for name, original in originals.items():
        setattr(compare_tax_forms, name, original)


if __name__ == "__main__":
    test_merge_web_data_fill_missing_preserves_existing_values()
    test_reliable_web_extraction_retries_when_compare_would_report_web_missing()
    test_reliable_web_extraction_skips_expensive_recovery_when_no_web_missing()
    test_reliable_web_extraction_supplements_missing_fields_after_retry()
    test_reliable_web_extraction_uses_missing_fields_for_render_scope()
    test_reliable_web_extraction_stops_when_recovery_budget_is_exhausted()
    test_low_web_coverage_without_web_missing_is_not_quality_issue()
    test_low_web_coverage_with_web_missing_is_quality_issue()
