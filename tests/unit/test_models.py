"""Unit tests for data models."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.models.field_mapping import FieldMapping, DataType, MappingSource
from src.models.compare_result import CompareStatus, FieldCompareResult, CompareResult, CompareSummary
from src.models.execution import StepStatus, StepResult, PipelineContext, ExecutionBatch
from src.models.tax_type import TaxTypeConfig, FormTemplate, CompareRules


def test_field_mapping_serialization():
    m = FieldMapping(
        field_id="sales_amount",
        display_name="销售额",
        data_type=DataType.AMOUNT,
        api_json_path="$data.salesAmount",
        web_selector="#table td[data-col='1']",
        tolerance=0.01,
    )
    json_str = m.model_dump_json()
    restored = FieldMapping.model_validate_json(json_str)
    assert restored.field_id == "sales_amount"
    assert restored.data_type == DataType.AMOUNT
    assert restored.tolerance == 0.01


def test_compare_result_summary():
    s = CompareSummary(
        total_fields=10,
        match_count=7,
        tolerance_match_count=2,
        mismatch_count=1,
        match_rate=90.0,
    )
    assert s.total_fields == 10
    assert s.match_rate == 90.0


def test_execution_batch():
    ctx = PipelineContext(tax_type="VAT", period="2026Q1", company_id="test")
    batch = ExecutionBatch(
        batch_id="test_batch",
        companies=["test"],
        tax_types=["VAT"],
        periods=["2026Q1"],
        contexts=[ctx],
    )
    assert batch.batch_id == "test_batch"
    assert len(batch.contexts) == 1


def test_tax_type_config():
    tc = TaxTypeConfig(
        tax_type_id="VAT_SMALL_SCALE",
        tax_type_name="增值税",
        forms=[
            FormTemplate(
                form_code="VAT_MAIN",
                form_name="增值税主表",
                compare_rules=CompareRules(),
            )
        ],
    )
    assert tc.tax_type_id == "VAT_SMALL_SCALE"
    assert len(tc.forms) == 1
    assert tc.forms[0].compare_rules.default_tolerance_amount == 0.01


def test_data_type_enum():
    assert DataType.AMOUNT == "amount"
    assert DataType.RATE == "rate"
    assert DataType.EMPTY_OR_DASH == "empty_or_dash"


def test_compare_status_enum():
    assert CompareStatus.MATCH == "match"
    assert CompareStatus.MISMATCH == "mismatch"


if __name__ == "__main__":
    test_field_mapping_serialization()
    test_compare_result_summary()
    test_execution_batch()
    test_tax_type_config()
    test_data_type_enum()
    test_compare_status_enum()
    print("All model tests passed!")