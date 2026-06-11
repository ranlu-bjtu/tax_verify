import json
import csv
import tempfile
from datetime import datetime
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.chanjet_admin.task_query import AdminTask
from src.coverage.analyzer import analyze_run_coverage, write_coverage_status
from src.coverage.models import DECLARATION_ANY, DECLARATION_FILED, DECLARATION_UNFILED
from src.coverage.registry import build_coverage_targets, declaration_statuses_for_collect_statuses
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
                            },
                            "verify": {"status": "success", "returnCode": 0},
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


def test_coverage_analyzer_ignores_failed_verify_reports():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        run_dir = root / "batch" / "ops_failed"
        report_root = root / "reports"
        task_dir = report_root / "task-failed"
        run_dir.mkdir(parents=True)
        task_dir.mkdir(parents=True)
        (run_dir / "state.json").write_text(
            json.dumps(
                {
                    "runId": "ops_failed",
                    "items": {
                        "911": {
                            "collect": {"verifyTaskId": "task-failed"},
                            "verify": {"status": "failed", "returnCode": 124, "reason": "timeout"},
                        }
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (task_dir / "vat_general_main_compare_task-failed_20260526_120000.json").write_text(
            json.dumps(
                {
                    "batch_id": "vat_general_main",
                    "tax_type": "VAT_GENERAL",
                    "declaration_status": "filed",
                    "field_results": [{"field_id": "a", "status": "match"}],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        targets = [
            target
            for target in build_coverage_targets()
            if target.tax_type == "VAT_GENERAL" and target.declaration_status == DECLARATION_FILED
        ]

        payload = analyze_run_coverage(run_dir, report_root=report_root, targets=targets)

        assert payload["summary"]["coveredTargets"] == 0
        assert payload["summary"]["missingTargets"] == 1


def test_missing_coverage_csv_prefers_source_readiness_reason():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        run_dir = root / "batch" / "ops_source_readiness"
        run_dir.mkdir(parents=True)
        (run_dir / "state.json").write_text(
            json.dumps(
                {
                    "runId": "ops_source_readiness",
                    "period": "202605",
                    "coverageSupplement": {
                        "status": "no_candidates",
                        "diagnostics": [
                            {"targetKey": "CIT_A:filed", "reason": "matched_backend_result_json"}
                        ],
                        "sourceReadiness": [
                            {
                                "targetKey": "CIT_A:filed",
                                "status": "current_enterprise_no_cit_signal",
                                "message": "current enterprise scanned 144 accounts but found no CIT A signal",
                                "nextAction": "switch enterprise or create an account set",
                            }
                        ],
                    },
                    "items": {},
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        targets = [target for target in build_coverage_targets(tax_types=["CIT_A"]) if target.key == "CIT_A:filed"]

        write_coverage_status(run_dir, report_root=root / "reports", targets=targets)

        rows = list(csv.DictReader((run_dir / "coverage_missing.csv").open(encoding="utf-8-sig")))
        assert len(rows) == 1
        assert "current enterprise scanned 144 accounts" in rows[0]["supplementReason"]
        assert "switch enterprise" in rows[0]["supplementReason"]


def test_coverage_analyzer_reads_multiple_task_ids_for_one_tax_no():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        run_dir = root / "batch" / "ops_multi"
        report_root = root / "reports"
        (report_root / "task-1").mkdir(parents=True)
        (report_root / "task-2").mkdir(parents=True)
        run_dir.mkdir(parents=True)
        (run_dir / "state.json").write_text(
            json.dumps(
                {
                    "runId": "ops_multi",
                    "items": {
                        "91370102MA7D3P0D2P": {
                            "taxNo": "91370102MA7D3P0D2P",
                            "collect": {
                                "verifyTaskId": "task-1",
                                "verifyTaskIds": ["task-1", "task-2"],
                                "account": {"custName": "company", "areaCode": "37"},
                            },
                            "verifyTasks": {
                                "task-1": {
                                    "status": "success",
                                    "returnCode": 0,
                                    "reportPaths": [str(report_root / "task-1" / "vat.json")],
                                },
                                "task-2": {
                                    "status": "success",
                                    "returnCode": 0,
                                    "reportPaths": [str(report_root / "task-2" / "cit.json")],
                                },
                            },
                        }
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (report_root / "task-1" / "vat.json").write_text(
            json.dumps(
                {
                    "batch_id": "vat_general_main",
                    "tax_type": "VAT_GENERAL",
                    "declaration_status": "已申报",
                    "field_results": [{"field_id": "a", "status": "match"}],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (report_root / "task-2" / "cit.json").write_text(
            json.dumps(
                {
                    "batch_id": "cit_a_main",
                    "tax_type": "CIT_A",
                    "declaration_status": "已申报",
                    "field_results": [{"field_id": "b", "status": "match"}],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        targets = [target for target in build_coverage_targets() if target.tax_type in {"VAT_GENERAL", "CIT_A"}]

        payload = analyze_run_coverage(run_dir, report_root=report_root, targets=targets)

        covered = {target["key"] for target in payload["targets"] if target["covered"]}
    assert "VAT_GENERAL:filed" in covered
    assert "CIT_A:filed" in covered


def test_coverage_analyzer_treats_unknown_declaration_status_as_unfiled():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        run_dir = root / "batch" / "ops_unknown"
        report_root = root / "reports"
        task_dir = report_root / "task-xfs"
        run_dir.mkdir(parents=True)
        task_dir.mkdir(parents=True)
        (run_dir / "state.json").write_text(
            json.dumps(
                {
                    "runId": "ops_unknown",
                    "items": {
                        "91370102MA7D3P0D2P": {
                            "collect": {
                                "verifyTaskId": "task-xfs",
                                "account": {"custName": "company", "areaCode": "37"},
                            },
                            "verify": {"status": "success", "returnCode": 0},
                        }
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (task_dir / "consumption_tax_main_compare_task-xfs_20260601_120000.json").write_text(
            json.dumps(
                {
                    "batch_id": "consumption_tax_main",
                    "tax_type": "CONSUMPTION_TAX",
                    "form_name": "消费税及附加税费申报表",
                    "declaration_status": "未知",
                    "field_results": [{"field_id": "a", "status": "match"}],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        targets = [target for target in build_coverage_targets() if target.tax_type == "CONSUMPTION_TAX"]

        payload = analyze_run_coverage(run_dir, report_root=report_root, targets=targets)

        covered = {target["key"] for target in payload["targets"] if target["covered"]}
        assert "CONSUMPTION_TAX:filed" not in covered
        assert "CONSUMPTION_TAX:unfiled" in covered
        assert payload["summary"]["coveredTargets"] == 1
        assert payload["summary"]["missingTargets"] == 1


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
                            },
                            "verify": {"status": "success", "returnCode": 0},
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
        assert "CBJ_PERSONAL:any" in covered
        assert "CBJ_ANNUAL:any" in missing
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
    state = {
        "runId": "ops_cov",
        "period": "202604",
        "enterprise": "test",
        "items": {
            "911": {
                "taxNo": "911",
                "collect": None,
                "verify": None,
            }
        },
    }
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

    assert applied == ["911__coverage__VAT_GENERAL_filed"]
    assert state["items"]["911"]["collect"] is None
    item = state["items"]["911__coverage__VAT_GENERAL_filed"]
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
                raw={"formId": "vat_general_main"},
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
                raw={
                    "resultJson": json.dumps(
                        {
                            "currentPeriodFlag": True,
                            "formName": "\u589e\u503c\u7a0e\u7eb3\u7a0e\u7533\u62a5\u8868\uff08\u4e00\u822c\u7eb3\u7a0e\u4eba\u9002\u7528\uff09",
                        },
                        ensure_ascii=False,
                    )
                },
            ),
            AdminTask(
                task_id="task-unfiled",
                tax_no="922",
                period="202604",
                task_type_id="3",
                task_type_name="取数",
                status="SUCCESS",
                created_stamp=1,
                raw={
                    "resultJson": json.dumps(
                        {
                            "currentPeriodFlag": False,
                            "formName": "\u589e\u503c\u7a0e\u7eb3\u7a0e\u7533\u62a5\u8868\uff08\u4e00\u822c\u7eb3\u7a0e\u4eba\u9002\u7528\uff09",
                        },
                        ensure_ascii=False,
                    )
                },
            ),
        ]


def test_supplement_planner_queries_each_backend_vat_tax_id_once():
    query = CountingSupplementQuery()
    targets = [
        target
        for target in build_coverage_targets()
        if target.tax_type == "VAT_GENERAL" and target.declaration_status in {"filed", "unfiled"}
    ]
    planner = CoverageSupplementPlanner(query)

    candidates = planner.find_candidates(targets, datetime(2026, 5, 1), datetime(2026, 5, 26), period="202604")

    assert len(query.calls) == 1
    assert query.calls[0]["tax_id"] == 1
    assert query.calls[0]["tax_type_id"] is None
    assert query.calls[0]["taxpayer_type"] == "NORMAL_TAXPAYER"
    assert query.calls[0].get("login_type") is None
    assert query.calls[0]["period"] == "202604"
    assert {candidate.target_key for candidate in candidates} == {"VAT_GENERAL:filed", "VAT_GENERAL:unfiled"}
    assert all(item["queryShared"] for item in planner.last_diagnostics)


def test_supplement_planner_treats_unknown_status_as_unfiled_candidate():
    class UnknownStatusQuery:
        timeout = 20

        def find_collect_tasks_by_filters(self, **_kwargs):
            return [
                AdminTask(
                    task_id="task-unknown",
                    tax_no="911",
                    period="202604",
                    task_type_id="3",
                    task_type_name="取数",
                    status="SUCCESS",
                    created_stamp=1,
                    raw={"resultJson": json.dumps({"formName": "消费税及附加税费申报表"}, ensure_ascii=False)},
                )
            ]

    target = next(
        item
        for item in build_coverage_targets()
        if item.tax_type == "CONSUMPTION_TAX" and item.declaration_status == "unfiled"
    )
    original = supplement_module.fetch_current_period_flag
    try:
        supplement_module.fetch_current_period_flag = lambda task_id, timeout=20, tax_code="": None
        planner = CoverageSupplementPlanner(UnknownStatusQuery())

        candidates = planner.find_candidates([target], datetime(2026, 5, 1), datetime(2026, 5, 26))
    finally:
        supplement_module.fetch_current_period_flag = original

    assert candidates
    assert candidates[0].target_key == "CONSUMPTION_TAX:unfiled"
    assert candidates[0].parse_status == "unknown"


def test_supplement_planner_keeps_multiple_candidates_per_target():
    class MultiCandidateQuery:
        timeout = 20

        def find_collect_tasks_by_filters(self, **_kwargs):
            return [
                AdminTask(
                    task_id=f"task-{index}",
                    tax_no=f"911{index}",
                    period="202605",
                    task_type_id="3",
                    task_type_name="collect",
                    status="SUCCESS",
                    created_stamp=index,
                    raw={"taxPayerType": "NORMAL_TAXPAYER", "currentPeriodFlag": True},
                )
                for index in (3, 2, 1)
            ]

    target = next(
        item
        for item in build_coverage_targets()
        if item.tax_type == "VAT_GENERAL" and item.declaration_status == "filed"
    )
    planner = CoverageSupplementPlanner(MultiCandidateQuery())

    candidates = planner.find_candidates(
        [target],
        datetime(2026, 6, 1),
        datetime(2026, 6, 1),
        max_candidates_per_target=2,
    )

    assert [candidate.task_id for candidate in candidates] == ["task-3", "task-2"]
    assert planner.last_diagnostics[0]["matchedTaskIds"] == ["task-3", "task-2"]
    assert planner.last_diagnostics[0]["candidateCount"] == 2


def test_supplement_planner_prefers_distinct_tax_numbers_before_same_tax_retry():
    class MultiTaxNoQuery:
        timeout = 20

        def find_collect_tasks_by_filters(self, **_kwargs):
            return [
                AdminTask(
                    task_id="task-new-same-tax",
                    tax_no="911-A",
                    period="202605",
                    task_type_id="3",
                    task_type_name="collect",
                    status="SUCCESS",
                    created_stamp=3,
                    raw={"taxPayerType": "NORMAL_TAXPAYER", "currentPeriodFlag": True},
                ),
                AdminTask(
                    task_id="task-old-same-tax",
                    tax_no="911-A",
                    period="202605",
                    task_type_id="3",
                    task_type_name="collect",
                    status="SUCCESS",
                    created_stamp=2,
                    raw={"taxPayerType": "NORMAL_TAXPAYER", "currentPeriodFlag": True},
                ),
                AdminTask(
                    task_id="task-other-tax",
                    tax_no="922-B",
                    period="202605",
                    task_type_id="3",
                    task_type_name="collect",
                    status="SUCCESS",
                    created_stamp=1,
                    raw={"taxPayerType": "NORMAL_TAXPAYER", "currentPeriodFlag": True},
                ),
            ]

    target = next(
        item
        for item in build_coverage_targets()
        if item.tax_type == "VAT_GENERAL" and item.declaration_status == "filed"
    )
    planner = CoverageSupplementPlanner(MultiTaxNoQuery())

    candidates = planner.find_candidates(
        [target],
        datetime(2026, 6, 1),
        datetime(2026, 6, 1),
        max_candidates_per_target=2,
    )

    assert [candidate.task_id for candidate in candidates] == ["task-new-same-tax", "task-other-tax"]
    assert [candidate.tax_no for candidate in candidates] == ["911-A", "922-B"]
    assert planner.last_diagnostics[0]["matchedTaskIds"] == ["task-new-same-tax", "task-other-tax"]


def test_supplement_planner_skips_excluded_task_ids_and_keeps_next_candidate():
    class MultiCandidateQuery:
        timeout = 20

        def find_collect_tasks_by_filters(self, **_kwargs):
            return [
                AdminTask(
                    task_id=f"task-{index}",
                    tax_no=f"911{index}",
                    period="202605",
                    task_type_id="3",
                    task_type_name="collect",
                    status="SUCCESS",
                    created_stamp=index,
                    raw={"taxPayerType": "NORMAL_TAXPAYER", "currentPeriodFlag": True},
                )
                for index in (3, 2)
            ]

    target = next(
        item
        for item in build_coverage_targets()
        if item.tax_type == "VAT_GENERAL" and item.declaration_status == "filed"
    )
    planner = CoverageSupplementPlanner(MultiCandidateQuery())

    candidates = planner.find_candidates(
        [target],
        datetime(2026, 6, 1),
        datetime(2026, 6, 1),
        max_candidates_per_target=1,
        excluded_task_ids_by_target={target.key: {"task-3"}},
    )

    assert [candidate.task_id for candidate in candidates] == ["task-2"]
    assert planner.last_diagnostics[0]["excludedTaskIds"] == ["task-3"]
    assert planner.last_diagnostics[0]["candidateCount"] == 1


def test_non_vat_coverage_targets_use_backend_tax_ids():
    targets = {
        item.tax_type: item
        for item in build_coverage_targets()
        if item.tax_type in {"CIT_A", "CULTURE_FEE", "CONSUMPTION_TAX"} and item.declaration_status == "filed"
    }

    assert {key: target.backend_tax_type_ids for key, target in targets.items()} == {
        "CIT_A": (),
        "CULTURE_FEE": (),
        "CONSUMPTION_TAX": (),
    }
    assert {key: target.backend_tax_ids for key, target in targets.items()} == {
        "CIT_A": (2,),
        "CULTURE_FEE": (3,),
        "CONSUMPTION_TAX": (26,),
    }


def test_supplement_planner_queries_non_vat_backend_tax_ids():
    class NonVatQuery:
        timeout = 20

        def __init__(self):
            self.calls = []

        def find_collect_tasks_by_filters(self, **kwargs):
            self.calls.append(kwargs)
            return []

    targets = [
        item
        for item in build_coverage_targets()
        if item.tax_type in {"CIT_A", "CULTURE_FEE", "CONSUMPTION_TAX"} and item.declaration_status == "filed"
    ]
    query = NonVatQuery()
    planner = CoverageSupplementPlanner(query)

    candidates = planner.find_candidates(targets, datetime(2026, 6, 1), datetime(2026, 6, 1), period="202605")

    assert candidates == []
    assert [call["tax_id"] for call in query.calls] == [2, 3, 26]
    assert all(call["tax_type_id"] is None for call in query.calls)
    assert all(call["period"] == "202605" for call in query.calls)
    assert {item["backendTaxId"] for item in planner.last_diagnostics} == {"2", "3", "26"}
    assert {item["backendTaxTypeId"] for item in planner.last_diagnostics} == {""}


def test_vat_coverage_targets_use_backend_taxpayer_type():
    targets = build_coverage_targets()
    general = next(item for item in targets if item.tax_type == "VAT_GENERAL" and item.declaration_status == "filed")
    small = next(item for item in targets if item.tax_type == "VAT_SMALL" and item.declaration_status == "filed")

    assert general.backend_tax_type_ids == ()
    assert general.backend_tax_ids == (1,)
    assert general.backend_taxpayer_type == "NORMAL_TAXPAYER"
    assert small.backend_tax_type_ids == ()
    assert small.backend_tax_ids == (1,)
    assert small.backend_taxpayer_type == "SMALL_TAXPAYER"


def test_build_coverage_targets_can_filter_tax_types():
    targets = build_coverage_targets(tax_types=["CONSUMPTION_TAX"])

    assert {target.tax_type for target in targets} == {"CONSUMPTION_TAX"}
    assert {target.declaration_status for target in targets} == {"filed", "unfiled"}
    assert len(targets) == 2


def test_build_coverage_targets_can_filter_collect_statuses():
    targets = build_coverage_targets(
        declaration_statuses=declaration_statuses_for_collect_statuses(["collected"]),
        tax_types=["CONSUMPTION_TAX", "CBJ_PERSONAL"],
    )

    assert {(target.tax_type, target.declaration_status) for target in targets} == {
        ("CONSUMPTION_TAX", DECLARATION_FILED),
        ("CBJ_PERSONAL", DECLARATION_ANY),
    }


def test_cbj_coverage_targets_do_not_split_declaration_status():
    targets = [target for target in build_coverage_targets() if target.tax_type.startswith("CBJ_")]

    assert {(target.tax_type, target.declaration_status) for target in targets} == {
        ("CBJ_PERSONAL", DECLARATION_ANY),
        ("CBJ_ANNUAL", DECLARATION_ANY),
    }
    assert {target.key for target in targets} == {"CBJ_PERSONAL:any", "CBJ_ANNUAL:any"}
    assert {target.tax_type: target.backend_tax_type_ids for target in targets} == {
        "CBJ_PERSONAL": (26, 31),
        "CBJ_ANNUAL": (26, 31),
    }
    assert {target.tax_type: target.backend_tax_ids for target in targets} == {
        "CBJ_PERSONAL": (39,),
        "CBJ_ANNUAL": (39,),
    }


def test_supplement_planner_uses_execution_log_current_period_marker():
    original = supplement_module.fetch_current_period_flag
    try:
        supplement_module.fetch_current_period_flag = lambda task_id, timeout=20, tax_code="": True
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


def test_supplement_planner_uses_execution_log_for_cit_unfiled():
    class CitQuery:
        timeout = 20

        def find_collect_tasks_by_filters(self, **_kwargs):
            return [
                AdminTask(
                    task_id="task-cit",
                    tax_no="911",
                    period="202605",
                    task_type_id="3",
                    task_type_name="collect",
                    status="SUCCESS",
                    created_stamp=1,
                    raw={"resultJson": "{}"},
                )
            ]

    original = supplement_module.fetch_current_period_flag
    requested_tax_codes = []
    try:
        def fake_current_period_flag(task_id, timeout=20, tax_code=""):
            requested_tax_codes.append(tax_code)
            return False

        supplement_module.fetch_current_period_flag = fake_current_period_flag
        target = next(
            item
            for item in build_coverage_targets()
            if item.tax_type == "CIT_A" and item.declaration_status == "unfiled"
        )
        planner = CoverageSupplementPlanner(CitQuery())

        candidates = planner.find_candidates([target], datetime(2026, 6, 1), datetime(2026, 6, 1))
    finally:
        supplement_module.fetch_current_period_flag = original

    assert len(candidates) == 1
    assert candidates[0].task_id == "task-cit"
    assert candidates[0].parse_status == "unfiled"
    assert requested_tax_codes == ["sz_qysds"]
    assert planner.last_diagnostics[0]["statusCounts"] == {"unfiled": 1}
    assert planner.last_diagnostics[0]["statusTaskIds"] == {"unfiled": ["task-cit"]}


def test_supplement_planner_allows_cit_filed_unknown_as_probe_candidate():
    class CitUnknownQuery:
        timeout = 20

        def find_collect_tasks_by_filters(self, **_kwargs):
            return [
                AdminTask(
                    task_id="task-cit-unknown",
                    tax_no="911",
                    period="202512",
                    task_type_id="3",
                    task_type_name="collect",
                    status="SUCCESS",
                    created_stamp=1,
                    raw={"resultJson": "{}"},
                )
            ]

    original = supplement_module.fetch_current_period_flag
    try:
        supplement_module.fetch_current_period_flag = lambda task_id, timeout=20, tax_code="": None
        target = next(
            item
            for item in build_coverage_targets()
            if item.tax_type == "CIT_A" and item.declaration_status == "filed"
        )
        planner = CoverageSupplementPlanner(CitUnknownQuery())

        candidates = planner.find_candidates([target], datetime(2026, 6, 1), datetime(2026, 6, 1))
    finally:
        supplement_module.fetch_current_period_flag = original

    assert len(candidates) == 1
    assert candidates[0].task_id == "task-cit-unknown"
    assert candidates[0].parse_status == "unknown"
    assert planner.last_diagnostics[0]["statusCounts"] == {"unknown": 1}
    assert planner.last_diagnostics[0]["statusTaskIds"] == {"unknown": ["task-cit-unknown"]}


def test_supplement_planner_does_not_use_general_vat_task_for_small_target():
    class GeneralVatQuery:
        timeout = 20

        def find_collect_tasks_by_filters(self, **_kwargs):
            return [
                AdminTask(
                    task_id="task-general",
                    tax_no="91320118MAEGB3DU35",
                    period="202604",
                    task_type_id="3",
                    task_type_name="鍙栨暟",
                    status="SUCCESS",
                    created_stamp=3,
                    raw={
                        "resultJson": json.dumps(
                            {
                                "currentPeriodFlag": True,
                                "formId": "vat_general_main",
                                "formName": "\u589e\u503c\u7a0e\u7eb3\u7a0e\u7533\u62a5\u8868\uff08\u4e00\u822c\u7eb3\u7a0e\u4eba\u9002\u7528\uff09",
                            },
                            ensure_ascii=False,
                        )
                    },
                )
            ]

    target = next(
        item
        for item in build_coverage_targets()
        if item.tax_type == "VAT_SMALL" and item.declaration_status == "filed"
    )
    planner = CoverageSupplementPlanner(GeneralVatQuery())

    candidates = planner.find_candidates([target], datetime(2026, 5, 1), datetime(2026, 5, 26))

    assert candidates == []
    assert planner.last_diagnostics[0]["matchedTaskId"] == ""
    assert planner.last_diagnostics[0]["reason"] == "target_tax_type_not_matched"
    assert planner.last_diagnostics[0]["taskTaxTypeCounts"] == {"VAT_GENERAL": 1}


def test_supplement_planner_uses_taxpayer_type_for_small_vat():
    class SmallVatQuery:
        timeout = 20

        def __init__(self):
            self.calls = []

        def find_collect_tasks_by_filters(self, **kwargs):
            self.calls.append(kwargs)
            return [
                AdminTask(
                    task_id="task-small",
                    tax_no="91361003MAEDG6RXXG",
                    period="202605",
                    task_type_id="3",
                    task_type_name="collect",
                    status="SUCCESS",
                    created_stamp=1,
                    raw={"taxPayerType": "SMALL_TAXPAYER", "currentPeriodFlag": False},
                )
            ]

    target = next(
        item
        for item in build_coverage_targets()
        if item.tax_type == "VAT_SMALL" and item.declaration_status == "unfiled"
    )
    query = SmallVatQuery()
    planner = CoverageSupplementPlanner(query)

    candidates = planner.find_candidates([target], datetime(2026, 6, 1), datetime(2026, 6, 1))

    assert query.calls[0]["tax_id"] == 1
    assert query.calls[0]["tax_type_id"] is None
    assert query.calls[0]["taxpayer_type"] == "SMALL_TAXPAYER"
    assert len(candidates) == 1
    assert candidates[0].target_key == "VAT_SMALL:unfiled"
    assert planner.last_diagnostics[0]["taskTaxTypeCounts"] == {}


def test_supplement_planner_queries_cbj_with_backend_tax_id_39():
    class CbjQuery:
        timeout = 20

        def __init__(self):
            self.calls = []

        def find_collect_tasks_by_filters(self, **kwargs):
            self.calls.append(kwargs)
            return []

    targets = [target for target in build_coverage_targets() if target.tax_type.startswith("CBJ_")]
    query = CbjQuery()
    planner = CoverageSupplementPlanner(query)

    candidates = planner.find_candidates(targets, datetime(2026, 6, 1), datetime(2026, 6, 1), period="202605")

    assert candidates == []
    assert len(query.calls) == 1
    assert query.calls[0]["tax_id"] == 39
    assert query.calls[0]["tax_type_id"] is None
    assert query.calls[0]["period"] == "202605"
    assert {item["backendTaxId"] for item in planner.last_diagnostics} == {"39"}
    assert {item["backendTaxTypeId"] for item in planner.last_diagnostics} == {""}


def test_supplement_planner_accepts_cbj_with_required_backend_fields():
    class CbjQuery:
        timeout = 20

        def find_collect_tasks_by_filters(self, **_kwargs):
            return [
                AdminTask(
                    task_id="task-cbj",
                    tax_no="911",
                    period="202605",
                    task_type_id="3",
                    task_type_name="collect",
                    status="SUCCESS",
                    created_stamp=1,
                    raw={
                        "resultJson": json.dumps(
                            {
                                "data": {
                                    "snzzzgrs_cbj": "12",
                                    "snzzzggzze_cbj": "100.00",
                                }
                            },
                            ensure_ascii=False,
                        )
                    },
                )
            ]

    target = next(
        item
        for item in build_coverage_targets()
        if item.tax_type == "CBJ_PERSONAL"
    )
    original = supplement_module.fetch_cbj_mode_from_task_logs
    try:
        supplement_module.fetch_cbj_mode_from_task_logs = lambda task_id, timeout=20: None
        planner = CoverageSupplementPlanner(CbjQuery())
        candidates = planner.find_candidates([target], datetime(2026, 6, 1), datetime(2026, 6, 1))
    finally:
        supplement_module.fetch_cbj_mode_from_task_logs = original

    assert len(candidates) == 1
    assert candidates[0].task_id == "task-cbj"
    assert candidates[0].target_key == "CBJ_PERSONAL:any"


def test_supplement_planner_accepts_cbj_personal_by_task_log_mode_without_required_fields():
    class CbjQuery:
        timeout = 20

        def find_collect_tasks_by_filters(self, **_kwargs):
            return [
                AdminTask(
                    task_id="task-cbj-log",
                    tax_no="911",
                    period="202605",
                    task_type_id="3",
                    task_type_name="collect",
                    status="SUCCESS",
                    created_stamp=1,
                    raw={"taxTypeId": 26, "resultJson": json.dumps({"data": {}}, ensure_ascii=False)},
                )
            ]

    target = next(
        item
        for item in build_coverage_targets()
        if item.tax_type == "CBJ_PERSONAL"
    )
    original = supplement_module.fetch_cbj_mode_from_task_logs
    try:
        supplement_module.fetch_cbj_mode_from_task_logs = lambda task_id, timeout=20: "backend"
        planner = CoverageSupplementPlanner(CbjQuery())
        candidates = planner.find_candidates([target], datetime(2026, 6, 1), datetime(2026, 6, 1))
    finally:
        supplement_module.fetch_cbj_mode_from_task_logs = original

    assert len(candidates) == 1
    assert candidates[0].task_id == "task-cbj-log"
    assert candidates[0].target_key == "CBJ_PERSONAL:any"


def test_supplement_planner_accepts_cbj_personal_by_api_result_fields():
    class CbjQuery:
        timeout = 20

        def find_collect_tasks_by_filters(self, **_kwargs):
            return [
                AdminTask(
                    task_id="task-cbj-api",
                    tax_no="911",
                    period="202605",
                    task_type_id="3",
                    task_type_name="collect",
                    status="SUCCESS",
                    created_stamp=1,
                    raw={"taxId": 39, "resultJson": json.dumps({"data": {}}, ensure_ascii=False)},
                )
            ]

    class CbjApi:
        def __init__(self):
            self.calls = []

        def fetch_by_task_id(self, task_id):
            self.calls.append(task_id)
            return {
                "data": {
                    "sz_cbj": {
                        "snzzzgrs_cbj": "2",
                        "snzzzggzze_cbj": "201442.82",
                    }
                },
                "raw_resultJson": {
                    "sz_cbj": {
                        "code": "sz_cbj",
                        "data": {
                            "cbjzb_qc": {
                                "snzzzgrs_cbj": "2",
                                "snzzzggzze_cbj": "201442.82",
                            }
                        },
                    }
                },
            }

    target = next(
        item
        for item in build_coverage_targets()
        if item.tax_type == "CBJ_PERSONAL"
    )
    original = supplement_module.fetch_cbj_mode_from_task_logs
    api = CbjApi()
    try:
        supplement_module.fetch_cbj_mode_from_task_logs = lambda task_id, timeout=20: None
        planner = CoverageSupplementPlanner(CbjQuery(), api_client=api)
        candidates = planner.find_candidates([target], datetime(2026, 6, 1), datetime(2026, 6, 1))
    finally:
        supplement_module.fetch_cbj_mode_from_task_logs = original

    assert len(candidates) == 1
    assert candidates[0].task_id == "task-cbj-api"
    assert candidates[0].target_key == "CBJ_PERSONAL:any"
    assert api.calls == ["task-cbj-api"]
    assert planner.last_diagnostics[0]["cbjModeSourceCounts"] == {"api_result_fields": 1}


def test_supplement_planner_accepts_cbj_annual_by_task_log_mode_even_when_tax_type_id_is_26():
    class CbjQuery:
        timeout = 20

        def find_collect_tasks_by_filters(self, **_kwargs):
            return [
                AdminTask(
                    task_id="task-cbj-annual",
                    tax_no="911",
                    period="202605",
                    task_type_id="3",
                    task_type_name="collect",
                    status="SUCCESS",
                    created_stamp=1,
                    raw={"taxTypeId": 26, "resultJson": json.dumps({"data": {}}, ensure_ascii=False)},
                )
            ]

    target = next(
        item
        for item in build_coverage_targets()
        if item.tax_type == "CBJ_ANNUAL"
    )
    original = supplement_module.fetch_cbj_mode_from_task_logs
    try:
        supplement_module.fetch_cbj_mode_from_task_logs = lambda task_id, timeout=20: "annual"
        planner = CoverageSupplementPlanner(CbjQuery())
        candidates = planner.find_candidates([target], datetime(2026, 6, 1), datetime(2026, 6, 1))
    finally:
        supplement_module.fetch_cbj_mode_from_task_logs = original

    assert len(candidates) == 1
    assert candidates[0].task_id == "task-cbj-annual"
    assert candidates[0].target_key == "CBJ_ANNUAL:any"


def test_supplement_planner_rejects_cbj_personal_without_required_fields():
    class CbjQuery:
        timeout = 20

        def find_collect_tasks_by_filters(self, **_kwargs):
            return [
                AdminTask(
                    task_id="task-consumption",
                    tax_no="91370102MA7D3P0D2P",
                    period="202605",
                    task_type_id="3",
                    task_type_name="collect",
                    status="SUCCESS",
                    created_stamp=1,
                    raw={
                        "resultJson": json.dumps(
                            {"formName": "消费税及附加税费申报表", "taxCode": "sz_xfs"},
                            ensure_ascii=False,
                        )
                    },
                )
            ]

    class EmptyCbjApi:
        def fetch_by_task_id(self, task_id):
            return {"data": {}, "raw_resultJson": {}}

    target = next(
        item
        for item in build_coverage_targets()
        if item.tax_type == "CBJ_PERSONAL"
    )
    original = supplement_module.fetch_cbj_mode_from_task_logs
    try:
        supplement_module.fetch_cbj_mode_from_task_logs = lambda task_id, timeout=20: None
        planner = CoverageSupplementPlanner(CbjQuery(), api_client=EmptyCbjApi())
        candidates = planner.find_candidates([target], datetime(2026, 6, 1), datetime(2026, 6, 1))
    finally:
        supplement_module.fetch_cbj_mode_from_task_logs = original

    assert candidates == []
    assert planner.last_diagnostics[0]["reason"] == "target_tax_type_not_matched"
    assert planner.last_diagnostics[0]["taskTaxTypeCounts"] == {"unknown": 1}


def test_supplement_planner_emits_progress_events():
    original = supplement_module.fetch_current_period_flag
    try:
        supplement_module.fetch_current_period_flag = lambda task_id, timeout=20, tax_code="": True
        target = next(
            item
            for item in build_coverage_targets()
            if item.tax_type == "VAT_GENERAL" and item.declaration_status == "filed"
        )
        events = []
        planner = CoverageSupplementPlanner(FakeSupplementQuery())

        planner.find_candidates(
            [target],
            datetime(2026, 5, 1),
            datetime(2026, 5, 26),
            progress=events.append,
            timeout_seconds=30,
        )
    finally:
        supplement_module.fetch_current_period_flag = original

    assert [event["event"] for event in events[:2]] == ["query_start", "query_done"]
    assert any(event.get("event") == "target_done" for event in events)


if __name__ == "__main__":
    test_coverage_analyzer_marks_verified_reports_as_hits()
    test_missing_coverage_csv_prefers_source_readiness_reason()
    test_coverage_analyzer_treats_unknown_declaration_status_as_unfiled()
    test_write_coverage_status_outputs_json_and_csv()
    test_cbj_coverage_distinguishes_personal_and_annual_reports()
    test_backend_declaration_status_extractor_handles_common_result_json_fields()
    test_apply_supplement_candidates_to_state_records_existing_task_for_verification()
    test_apply_supplement_candidates_keeps_existing_tax_no_task()
    test_supplement_planner_queries_each_backend_vat_tax_id_once()
    test_supplement_planner_treats_unknown_status_as_unfiled_candidate()
    test_supplement_planner_keeps_multiple_candidates_per_target()
    test_supplement_planner_prefers_distinct_tax_numbers_before_same_tax_retry()
    test_non_vat_coverage_targets_use_backend_tax_ids()
    test_supplement_planner_queries_non_vat_backend_tax_ids()
    test_vat_coverage_targets_use_backend_taxpayer_type()
    test_build_coverage_targets_can_filter_tax_types()
    test_build_coverage_targets_can_filter_collect_statuses()
    test_cbj_coverage_targets_do_not_split_declaration_status()
    test_supplement_planner_uses_execution_log_current_period_marker()
    test_supplement_planner_uses_execution_log_for_cit_unfiled()
    test_supplement_planner_allows_cit_filed_unknown_as_probe_candidate()
    test_supplement_planner_does_not_use_general_vat_task_for_small_target()
    test_supplement_planner_uses_taxpayer_type_for_small_vat()
    test_supplement_planner_queries_cbj_with_backend_tax_id_39()
    test_supplement_planner_accepts_cbj_with_required_backend_fields()
    test_supplement_planner_accepts_cbj_personal_by_task_log_mode_without_required_fields()
    test_supplement_planner_accepts_cbj_personal_by_api_result_fields()
    test_supplement_planner_accepts_cbj_annual_by_task_log_mode_even_when_tax_type_id_is_26()
    test_supplement_planner_rejects_cbj_personal_without_required_fields()
    test_supplement_planner_emits_progress_events()
    print("All coverage framework tests passed!")
