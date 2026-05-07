"""Integration test: end-to-end pipeline with mock data."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.config.config_loader import ConfigLoader
from src.registry.tax_type_registry import TaxTypeRegistry
from src.pipeline.orchestrator import Orchestrator
from src.models.execution import PipelineContext


def test_pipeline_e2e():
    loader = ConfigLoader(config_root="config")
    main_config = loader.load_main("config/main.yaml")

    registry = TaxTypeRegistry()
    registry.load_all_from_dir("config")

    context = PipelineContext(
        tax_type="VAT_SMALL_SCALE",
        period="2026Q1",
        company_id="测试企业A",
        config_root="config",
    )

    orchestrator = Orchestrator(main_config, registry)
    context = orchestrator.run(context)

    # All steps should succeed
    assert len(context.steps) == 6
    for step in context.steps:
        assert step.status.value == "success", f"Step {step.step_name} failed: {step.error_message}"

    # Compare result should exist
    assert context.compare_result is not None
    assert context.compare_result.summary.total_fields > 0
    assert context.compare_result.summary.match_rate > 0

    print(f"E2E test passed! Match rate: {context.compare_result.summary.match_rate}%")
    print(f"Total fields: {context.compare_result.summary.total_fields}")
    print(f"Match: {context.compare_result.summary.match_count}")
    print(f"Tolerance match: {context.compare_result.summary.tolerance_match_count}")
    print(f"Mismatch: {context.compare_result.summary.mismatch_count}")


if __name__ == "__main__":
    test_pipeline_e2e()