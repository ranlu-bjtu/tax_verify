import json
import csv
import tempfile
from datetime import datetime
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.chanjet_admin.task_query import AdminTask
from src.coverage.analyzer import analyze_run_coverage, write_coverage_status
from src.coverage.models import DECLARATION_FILED, DECLARATION_UNFILED
from src.coverage.registry import build_coverage_targets
from src.coverage.registry import normalize_tax_type
from src.coverage.supplement import (
    BackendDeclarationStatusExtractor,
    CoverageSupplementPlanner,
    apply_supplement_candidates_to_state,
)
from src.coverage.models import SupplementCandidate
import src.coverage.supplement as supplement_module


def test_coverage_analyzer_marks_verified_reports_as_hits():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        run_dir = root / "batch" / "ops_cov"
        report_root = root / "reports"
        task_dir = report_root / "task-1"
        run_dir.mkdir(parents=True)
        task_dir.mkdir(parents=True)
        (run_dir / "state.json").write_text(
            json.dumps(
                {
                    "runId": "ops_cov",
                    "period": "202604",
                    "items": {
                        "911": {
                            "collect": {
                                "verifyTaskId": "task-1",
                                "account": {"custName": "company", "areaCode": "13"},
                            }
                        }
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (task_dir / "vat_general_main_compare_task-1_20260526_120000.json").write_text(
            json.dumps(
                {
                    "batch_id": "vat_general_main",
                    "tax_type": "VAT_GENERAL",
                    "form_name": "VAT general main",
                    "declaration_status": "已申报",
                    "field_results": [{"field_id": "a", "status": "match"}],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (task_dir / "culture_fee_main_compare_task-1_20260526_120000.json").write_text(
            json.dumps(
                {
                    "batch_id": "culture_fee_main",
                    "tax_type": "CULTURE_FEE",
                    "form_name": "Culture fee",
                    "current_period_flag": False,
                    "field_results": [],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        targets = [
            target
            for target in build_coverage_targets()
            if target.tax_type in {"VAT_GENERAL", "CULTURE_FEE"}
        ]
        payload = analyze_run_coverage(run_dir, report_root=report_root, targets=targets)

        covered = {target["key"] for target in payload["targets"] if target["covered"]}
        assert "VAT_GENERAL:filed" in covered
        assert "CULTURE_FEE:unfiled" in covered
        assert payload["summary"]["coveredTargets"] == 2
        assert payload["summary"]["missingTargets"] == 2


def test_write_coverage_status_outputs_json_and_csv():
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp) / "ops_cov"
        run_dir.mkdir()
        (run_dir / "state.json").write_text('{"runId":"ops_cov","items":{}}', encoding="utf-8")

        payload = write_coverage_status(run_dir, report_root=Path(tmp) / "reports")

        assert payload["summary"]["missingTargets"] == payload["summary"]["totalTargets"]
        assert (run_dir / "coverage_status.json").exists()
        assert (run_dir / "coverage_matrix.csv").exists()
        assert (run_dir / "coverage_missing.csv").exists()
        rows = list(csv.DictReader((run_dir / "coverage_matrix.csv").open(encoding="utf-8-sig")))
        assert rows
        assert rows[0]["taxType"]
        assert rows[0]["taxTypeName"]
        assert rows[0]["declarationStatusName"]


def test_cbj_coverage_distinguishes_personal_and_annual_reports():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        run_dir = root / "batch" / "ops_cbj"
        report_root = root / "reports"
        task_dir = report_root / "task-cbj"
        run_dir.mkdir(parents=True)
        task_dir.mkdir(parents=True)
        (run_dir / "state.json").write_text(
            json.dumps(
                {
                    "runId": "ops_cbj",
                    "items": {
                        "911": {
                            "collect": {
                                "verifyTaskId": "task-cbj",
                                "account": {"custName": "company", "areaCode": "61"},
                            }
                        }
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (task_dir / "cbj_personal_compare_task-cbj_20260526_120000.json").write_text(
            json.dumps(
                {
                    "batch_id": "cbj_personal",
                    "tax_type": "CBJ_PERSONAL",
                    "form_name": "personal cbj",
                    "declaration_status": "已取数",
                    "field_results": [{"field_id": "snzzzgrs_cbj", "status": "match"}],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        targets = [target for target in build_coverage_targets() if target.tax_type.startswith("CBJ_")]

        payload = analyze_run_coverage(run_dir, report_root=report_root, targets=targets)

        covered = {target["key"] for target in payload["targets"] if target["covered"]}
        missing = {target["key"] for target in payload["missingTargets"]}
        assert "CBJ_PERSONAL:filed" in covered
        assert "CBJ_ANNUAL:filed" in missing
        assert normalize_tax_type("CBJ", form_id="cbj_annual_settlement") == "CBJ_ANNUAL"


def test_backend_declaration_status_extractor_handles_common_result_json_fields():
    extractor = BackendDeclarationStatusExtractor()
    filed = AdminTask(
        task_id="task-1",
        tax_no="911",
        period="202604",
        task_type_id="3",
        task_type_name="取数",
        status="SUCCESS",
        created_stamp=1,
        raw={"resultJson": json.dumps({"data": {"declarationStatus": "已申报"}}, ensure_ascii=False)},
    )
    unfiled = AdminTask(
        task_id="task-2",
        tax_no="922",
        period="202604",
        task_type_id="3",
        task_type_name="取数",
        status="SUCCESS",
        created_stamp=2,
        raw={"resultJson": json.dumps({"data": {"currentPeriodFlag": False}}, ensure_ascii=False)},
    )

    assert extractor.extract(filed) == DECLARATION_FILED
    assert extractor.extract(unfiled) == DECLARATION_UNFILED


def test_apply_supplement_candidates_to_state_records_existing_task_for_verification():
    state = {"runId": "ops_cov", "period": "202604", "enterprise": "test", "items": {}}
    candidates = [
        SupplementCandidate(
            target_key="VAT_GENERAL:filed",
            tax_type="VAT_GENERAL",
            tax_type_name="增值税（一般纳税人）",
            declaration_status="filed",
            declaration_status_name="已申报",
            task_id="task-1",
            tax_no="911",
            period="202604",
            task_status="SUCCESS",
            backend_tax_type_id="1",
            created_stamp=2,
        )
    ]

    applied = apply_supplement_candidates_to_state(state, candidates)

    assert applied == ["911"]
    item = state["items"]["911"]
    assert item["source"] == "backend_supplement"
    assert item["collect"]["verifyTaskId"] == "task-1"
    assert item["collect"]["resolvedTask"]["coverageTarget"] == "VAT_GENERAL:filed"


def test_apply_supplement_candidates_keeps_existing_tax_no_task():
    state = {
        "runId": "ops_cov",
        "period": "202604",
        "items": {
            "911": {
                "taxNo": "911",
                "collect": {"verifyTaskId": "task-old"},
                "verify": {"status": "success"},
            }
        },
    }
    candidates = [
        SupplementCandidate(
            target_key="VAT_GENERAL:unfiled",
            tax_type="VAT_GENERAL",
            tax_type_name="增值税（一般纳税人）",
            declaration_status="unfiled",
            declaration_status_name="未申报",
            task_id="task-new",
            tax_no="911",
            period="202604",
            task_status="SUCCESS",
            backend_tax_type_id="1",
            created_stamp=3,
        )
    ]

    applied = apply_supplement_candidates_to_state(state, candidates)

    assert applied == ["911__coverage__VAT_GENERAL_unfiled"]
    assert state["items"]["911"]["collect"]["verifyTaskId"] == "task-old"
    supplement = state["items"]["911__coverage__VAT_GENERAL_unfiled"]
    assert supplement["taxNo"] == "911"
    assert supplement["collect"]["verifyTaskId"] == "task-new"


class FakeSupplementQuery:
    timeout = 20

    def find_collect_tasks_by_filters(self, **_kwargs):
        return [
            AdminTask(
                task_id="task-1",
                tax_no="911",
                period="202604",
                task_type_id="3",
                task_type_name="取数",
                status="SUCCESS",
                created_stamp=1,
                raw={},
            )
        ]


class CountingSupplementQuery:
    timeout = 20

    def __init__(self):
        self.calls = []

    def find_collect_tasks_by_filters(self, **kwargs):
        self.calls.append(kwargs)
        return [
            AdminTask(
                task_id="task-filed",
                tax_no="911",
                period="202604",
                task_type_id="3",
                task_type_name="取数",
                status="SUCCESS",
                created_stamp=2,
                raw={"resultJson": json.dumps({"currentPeriodFlag": True}, ensure_ascii=False)},
            ),
            AdminTask(
                task_id="task-unfiled",
                tax_no="922",
                period="202604",
                task_type_id="3",
                task_type_name="取数",
                status="SUCCESS",
                created_stamp=1,
                raw={"resultJson": json.dumps({"currentPeriodFlag": False}, ensure_ascii=False)},
            ),
        ]


def test_supplement_planner_queries_each_backend_tax_type_once():
    query = CountingSupplementQuery()
    targets = [
        target
        for target in build_coverage_targets()
        if target.tax_type == "VAT_GENERAL" and target.declaration_status in {"filed", "unfiled"}
    ]
    planner = CoverageSupplementPlanner(query)

    candidates = planner.find_candidates(targets, datetime(2026, 5, 1), datetime(2026, 5, 26))

    assert len(query.calls) == 1
    assert query.calls[0]["tax_type_id"] == 1
    assert {candidate.target_key for candidate in candidates} == {"VAT_GENERAL:filed", "VAT_GENERAL:unfiled"}
    assert all(item["queryShared"] for item in planner.last_diagnostics)


def test_supplement_planner_uses_execution_log_current_period_marker():
    original = supplement_module.fetch_current_period_flag
    try:
        supplement_module.fetch_current_period_flag = lambda task_id, tax_code, timeout: True
        target = next(
            item
            for item in build_coverage_targets()
            if item.tax_type == "VAT_GENERAL" and item.declaration_status == "filed"
        )
        planner = CoverageSupplementPlanner(FakeSupplementQuery())

        candidates = planner.find_candidates([target], datetime(2026, 5, 1), datetime(2026, 5, 26))
    finally:
        supplement_module.fetch_current_period_flag = original

    assert len(candidates) == 1
    assert candidates[0].task_id == "task-1"
    assert candidates[0].parse_status == "filed"
    assert planner.last_diagnostics
    assert planner.last_diagnostics[0]["matchedTaskId"] == "task-1"


if __name__ == "__main__":
    test_coverage_analyzer_marks_verified_reports_as_hits()
    test_write_coverage_status_outputs_json_and_csv()
    test_cbj_coverage_distinguishes_personal_and_annual_reports()
    test_backend_declaration_status_extractor_handles_common_result_json_fields()
    test_apply_supplement_candidates_to_state_records_existing_task_for_verification()
    test_apply_supplement_candidates_keeps_existing_tax_no_task()
    test_supplement_planner_queries_each_backend_tax_type_once()
    test_supplement_planner_uses_execution_log_current_period_marker()
    print("All coverage framework tests passed!")
