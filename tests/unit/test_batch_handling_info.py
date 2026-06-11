import json
import os
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from argparse import Namespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import scripts.batch_collect_verify as batch_module

from scripts.batch_collect_verify import (
    build_ops_status,
    collect_failure_reason,
    collect_task_ids,
    compare_report_reason,
    derive_handling_info,
    direct_verify_reason,
    has_verifiable_items,
    item_requests_cbj_verification,
    load_compare_reports,
    run_coverage_supplement_phase,
    run_verify_phase,
    resolve_cbj_mode,
    safe_write_json_text,
    should_force_collect,
    stage_status_for_item,
    tail_error_reason,
    verification_risks,
    verify_targets_for_item,
)
from src.ydz.models import YdzAccount, YdzCollectResult
from src.ydz.session import YdzSession


def test_parse_tax_nos_strips_utf8_bom_from_file_and_argument():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "tax_nos.txt"
        path.write_text("\ufeff911111111111111111\n", encoding="utf-8")
        args = Namespace(tax_no=["\ufeff922222222222222222"], tax_no_file=str(path))

        assert batch_module.parse_tax_nos(args) == [
            "922222222222222222",
            "911111111111111111",
        ]


def test_collect_failure_reason_prefers_timeout_over_submit_response_noise():
    collect = {
        "errors": ["Timed out waiting for collection terminal status; last status=COLLECTING."],
        "warnings": [
            "銆愪紒涓氭墍寰楃◣銆戞湰鏈熸棤闇€鐢虫姤锛岃鏍稿璐㈢◣璁剧疆鏄惁闇€瑕佺敵鎶ョ浉搴旂◣绉嶏紒",
            "姝ｅ湪鎵ц鍙栨暟浠诲姟锛岃鍕块噸澶嶆彁浜わ紒",
        ],
        "taxItems": [],
    }

    reason = collect_failure_reason(collect)

    assert reason
    assert "鏈湡鏃犻渶鐢虫姤" not in reason
    assert "璇峰嬁閲嶅鎻愪氦" not in reason


def test_collect_failure_reason_skips_no_need_warning():
    collect = {
        "errors": [],
        "warnings": ["銆愬鍊肩◣銆戞湰鏈熸棤闇€鐢虫姤锛岃鏍稿璐㈢◣璁剧疆鏄惁闇€瑕佺敵鎶ョ浉搴旂◣绉嶏紒"],
        "taxItems": [],
    }

    assert collect_failure_reason(collect) == ""


def test_collect_failure_reason_ignores_social_security_failure():
    collect = {
        "errors": [],
        "warnings": [],
        "taxItems": [
            {
                "taxTypeId": 40,
                "initStatusEnum": "COLLECTED_FAIL",
                "status": "FAILURE",
                "message": "social security collect failed",
            }
        ],
    }

    assert collect_failure_reason(collect) == ""


def test_collect_failure_reason_prefers_specific_tax_failure_over_timeout():
    collect = {
        "errors": ["Timed out waiting for collection terminal status; last status=COLLECTING."],
        "warnings": ["銆愬鍊肩◣銆戞湰鏈熸棤闇€鐢虫姤锛岃鏍稿璐㈢◣璁剧疆鏄惁闇€瑕佺敵鎶ョ浉搴旂◣绉嶏紒"],
        "taxItems": [
            {
                "taxTypeId": 40,
                "initStatusEnum": "COLLECTED_FAIL",
                "status": "FAILURE",
                "message": "social security is not supported for collect",
            }
        ],
    }

    assert collect_failure_reason(collect)


def test_manual_handling_reason_is_single_direct_reason():
    handling = derive_handling_info(
        {},
        {
            "status": "COLLECTING",
            "manualRequired": True,
            "errors": ["Timed out waiting for collection terminal status; last status=COLLECTING."],
            "warnings": ["姝ｅ湪鎵ц鍙栨暟浠诲姟锛岃鍕块噸澶嶆彁浜わ紒"],
            "taxItems": [],
        },
        {"status": "skipped"},
    )

    assert handling["manualCategory"]
    assert handling["manualReason"]
    assert handling["manualAction"]


def test_direct_verify_reason_identifies_tax_auth_failure():
    reason = direct_verify_reason(
        {
            "reason": (
                "DeclarationQueryAuthError: 绋庡眬鐧诲綍鎬佹垨鏁板瓧璐︽埛璁よ瘉宸插け鏁堬細"
                "declaration query returned unified login page"
            )
        }
    )

    assert reason


def test_direct_verify_reason_identifies_tpass_login_runtime_error():
    reason = direct_verify_reason(
        {
            "reason": (
                "RuntimeError: Could not open undeclared tax form before target=culture_fee_main; "
                "url=https://tpass.shandong.chinatax.gov.cn:8443/#/login?redirect_uri=https%3A%2F%2Fetax.shandong"
            )
        }
    )

    assert reason
    assert "RuntimeError" not in reason
    assert "tpass.shandong" not in reason


def test_ops_status_normalizes_tpass_stage_reason():
    raw_reason = (
        "RuntimeError: Could not open undeclared tax form before target=culture_fee_main; "
        "url=https://tpass.shandong.chinatax.gov.cn:8443/#/login?redirect_uri=https%3A%2F%2Fetax.shandong"
    )
    status = build_ops_status(
        {
            "runId": "ops-test",
            "items": {
                "911": {
                    "taxNo": "911",
                    "stage": "verified",
                    "stageReason": raw_reason,
                    "collect": {},
                    "verify": {"status": "failed", "reason": raw_reason},
                }
            },
        }
    )

    reason = status["items"][0]["reason"]
    assert reason
    assert "RuntimeError" not in reason
    assert "tpass.shandong" not in reason


def test_direct_verify_reason_identifies_declaration_loading_auth_error():
    reason = direct_verify_reason(
        {
            "reason": (
                "DeclarationQueryAuthError: Tax bureau login state or digital account authentication "
                "is not ready: declaration query did not become usable before timeout; "
                "url=https://etax.henan.chinatax.gov.cn:8443/loading"
            )
        }
    )

    assert reason
    assert "DeclarationQueryAuthError" not in reason
    assert "etax.henan" not in reason


def test_direct_verify_reason_identifies_tax_login_not_ready_error():
    reason = direct_verify_reason(
        {
            "reason": (
                "src.login.task_login_flow.TaxLoginNotReadyError: "
                "Tax bureau login state or digital account authentication is not ready: "
                "unified login page; url=https://tpass.shandong.chinatax.gov.cn:8443/#/login"
            )
        }
    )

    assert reason
    assert "TaxLoginNotReadyError" not in reason
    assert "tpass.shandong" not in reason


def test_direct_verify_reason_identifies_need_force_tax():
    reason = direct_verify_reason(
        {
            "reason": (
                "ForceTaxLoginRequiredError: getClientJob returned needForceTax=true; "
                "the tax bureau has an active task that requires manual force-enter confirmation"
            )
        }
    )

    assert reason
    assert "needForceTax" not in reason


def test_direct_verify_reason_identifies_pending_tax_login_job():
    reason = direct_verify_reason(
        {
            "reason": (
                "src.login.task_login_flow.PendingTaxLoginJobError: "
                "宸叉湁杩涚◣灞€浠诲姟鏈畬鎴愶紝鏂扮殑绋庡眬鐧诲綍琚悗鍙版嫆缁濄€傚師濮嬫彁绀猴細"
                "鎮ㄤ箣鍓嶆墽琛岃繃 杩涚◣灞€(2076614043783903619) 鎿嶄綔骞朵笖鏆傛湭瀹屾垚"
            )
        }
    )

    assert reason
    assert reason
    assert "PendingTaxLoginJobError" not in reason


def test_direct_verify_reason_identifies_unresolved_task_cookie_metadata():
    reason = direct_verify_reason(
        {"reason": "ValueError: Cannot resolve province from task cookie/client job data"}
    )

    assert reason
    assert "ValueError" not in reason
    assert "Cannot resolve" not in reason
    assert "Tax bureau login failed" in reason


def test_cbj_auto_mode_uses_backend_for_personal_tax_item():
    item = {"coverageSupplementTargets": ["CBJ_PERSONAL:any"], "collect": {"taxItems": [{"taxTypeId": 26}]}}

    assert resolve_cbj_mode("auto", item) == "backend"


def test_backend_supplement_verification_limits_targets_to_active_tax_type():
    item = {
        "source": "backend_supplement",
        "coverageSupplementTargets": ["CULTURE_FEE:filed", "VAT_GENERAL:filed"],
    }

    assert verify_targets_for_item("auto", item, "CULTURE_FEE:filed") == "culture_fee_main,culture_fee_deduction"


def test_backend_supplement_target_limit_keeps_explicit_targets_and_cbj_empty():
    explicit = {"source": "backend_supplement", "coverageSupplementTargets": ["CULTURE_FEE:filed"]}
    cbj = {"source": "backend_supplement", "coverageSupplementTargets": ["CBJ_PERSONAL:any"]}

    assert verify_targets_for_item("vat_general_main", explicit, "CULTURE_FEE:filed") == "vat_general_main"
    assert verify_targets_for_item("auto", cbj, "CBJ_PERSONAL:any") == "auto"


def test_final_verify_marks_existing_result_item_verified():
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp)
        state = {
            "items": {
                "911": {
                    "taxNo": "911",
                    "stage": "task_resolved",
                    "collect": {"verifyTaskId": "task-1"},
                    "verify": {"status": "skipped", "reason": "already checked"},
                }
            }
        }

        code = run_verify_phase(Namespace(rerun_verified=False), ["911"], state, run_dir, final=True)

    assert code == 0
    assert state["items"]["911"]["stage"] == "verified"
    assert state["items"]["911"]["stageStatus"] == "skipped"


def test_cbj_auto_mode_uses_annual_for_annual_tax_item():
    item = {"collect": {"taxItems": [{"taxTypeId": 31, "initStatusEnum": "COLLECTED"}]}}

    assert resolve_cbj_mode("auto", item) == "annual"


def test_cbj_auto_mode_prefers_task_log_annual_marker_over_tax_type_26():
    original_fetch = batch_module.fetch_cbj_mode_from_task_logs
    batch_module.fetch_cbj_mode_from_task_logs = lambda task_id: "annual" if task_id == "task-annual" else ""
    try:
        item = {
            "collect": {
                "verifyTaskId": "task-annual",
                "taxItems": [{"taxTypeId": 26, "initStatusEnum": "COLLECTED"}],
            }
        }

        assert resolve_cbj_mode("auto", item) == "annual"
    finally:
        batch_module.fetch_cbj_mode_from_task_logs = original_fetch


def test_not_collected_cbj_tax_item_does_not_request_cbj_verification():
    item = {"collect": {"taxItems": [{"taxTypeId": 31, "initStatusEnum": "NOT_COLLECTED"}]}}

    assert item_requests_cbj_verification(item) is False


def test_safe_write_json_text_writes_valid_json_atomically():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "state.json"

        assert safe_write_json_text(path, '{"ok": true}') is True
        assert path.read_text(encoding="utf-8") == '{"ok": true}'


def test_tail_error_reason_skips_benign_browser_shutdown_lines():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "err.log"
        path.write_text(
            "\n".join(
                [
                    "2026-05-28 INFO src.login.browser_manager: Disconnected from Chrome",
                    "2026-05-28 INFO src.login.browser_manager: Playwright stopped",
                    "(node:1) [DEP0169] DeprecationWarning: url.parse",
                    "RuntimeError: real failure",
                ]
            ),
            encoding="utf-8",
        )

        assert tail_error_reason(path) == "RuntimeError: real failure"


def test_tail_error_reason_prefers_playwright_error_over_stack_tail():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "err.log"
        path.write_text(
            "\n".join(
                [
                    "Traceback (most recent call last):",
                    "  File \"main.py\", line 1, in <module>",
                    "playwright._impl._errors.Error: Page.evaluate: SyntaxError: Invalid regular expression: missing /",
                    "    at eval (<anonymous>)",
                    "    at UtilityScript.evaluate (<anonymous>:302:30)",
                    "    at UtilityScript.<anonymous> (<anonymous>:1:44)",
                ]
            ),
            encoding="utf-8",
        )

        reason = tail_error_reason(path)

    assert reason.startswith("playwright._impl._errors.Error: Page.evaluate: SyntaxError")


def test_rerun_verified_does_not_requeue_task_id_already_verified_this_run():
    state = {
        "items": {
            "911111111111111111": {
                "collect": {"verifyTaskId": "task-1"},
                "verify": {"status": "completed_with_differences"},
            }
        }
    }

    assert has_verifiable_items(
        ["911111111111111111"],
        state,
        rerun_verified=True,
        verified_task_ids={"task-1"},
    ) is False
    assert has_verifiable_items(
        ["911111111111111111"],
        state,
        rerun_verified=True,
        verified_task_ids=set(),
    ) is True


def test_compare_report_reason_can_filter_to_current_run_reports():
    cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        os.chdir(tmp)
        try:
            task_id = "task-filter"
            report_dir = Path("output") / "reports" / task_id
            report_dir.mkdir(parents=True)
            old_path = report_dir / "vat_old_compare_task-filter_20260501_120000.json"
            new_path = report_dir / "vat_new_compare_task-filter_20260601_120000.json"
            old_path.write_text(
                json.dumps({"form_name": "old form", "summary": {"web_missing_count": 3}}, ensure_ascii=False),
                encoding="utf-8",
            )
            new_path.write_text(
                json.dumps({"form_name": "new form", "summary": {"web_missing_count": 0}}, ensure_ascii=False),
                encoding="utf-8",
            )
            old_ts = time.time() - 100
            new_ts = time.time()
            os.utime(old_path, (old_ts, old_ts))
            os.utime(new_path, (new_ts, new_ts))

            reports = load_compare_reports(task_id, since_ts=new_ts - 1)

            assert [Path(report["_sourcePath"]).name for report in reports] == [new_path.name]
            assert compare_report_reason(task_id, reports=reports) == ""
            assert "old form" in compare_report_reason(task_id)
        finally:
            os.chdir(cwd)


def test_no_need_collect_is_success_even_when_verify_was_skipped():
    item = {
        "stage": "collect_no_need",
        "collect": {"status": "NO_NEED_COLLECTED"},
        "verify": {"status": "skipped"},
    }

    assert stage_status_for_item(item) == "success"


def test_final_verify_marks_missing_task_id_as_manual_not_running():
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp)
        state = {
            "runId": "ops_test",
            "period": "202605",
            "items": {
                "911": {
                    "taxNo": "911",
                    "stage": "collect_checked",
                    "stageStatus": "running",
                    "collect": {"status": ""},
                }
            },
        }

        code = run_verify_phase(Namespace(rerun_verified=False), ["911"], state, run_dir, final=True)

    item = state["items"]["911"]
    assert code == 2
    assert item["stage"] == "task_unresolved"
    assert item["stageStatus"] == "manual"
    assert item["verify"]["status"] == "skipped"
    assert stage_status_for_item(item) == "manual"


def test_collect_task_ids_ignore_unfinished_backend_tasks():
    collect = {
        "verifyTaskId": "schedule-task",
        "verifyTaskIds": ["schedule-task", "success-task", "legacy-task"],
        "resolvedTasks": [
            {"taskId": "schedule-task", "status": "SCHEDULE"},
            {"taskId": "success-task", "status": "SUCCESS"},
        ],
    }

    assert collect_task_ids(collect) == ["success-task", "legacy-task"]


def test_coverage_supplement_failure_keeps_diagnostics_defined():
    class FailingSession:
        def __init__(self, **_kwargs):
            pass

        def connect(self):
            raise RuntimeError("Public management login token is missing.")

        def close(self):
            pass

    original_write_coverage_status = batch_module.write_coverage_status
    original_session = batch_module.YdzSession
    try:
        batch_module.write_coverage_status = lambda _run_dir, **_kwargs: {
            "missingTargets": [{"key": "VAT_GENERAL:filed"}]
        }
        batch_module.YdzSession = FailingSession
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            state = {"runId": "ops_test", "period": "202604", "items": {}}
            args = Namespace(
                browser_lock_timeout=1,
                cdp_port=9222,
                chrome_path="chrome.exe",
                user_data_dir="profile",
                plugin_path="plugin",
                coverage_supplement_page_size=50,
                coverage_supplement_timeout=600,
                period="202604",
            )

            code = run_coverage_supplement_phase(args, state, run_dir)
    finally:
        batch_module.write_coverage_status = original_write_coverage_status
        batch_module.YdzSession = original_session

    assert code == 2
    assert state["coverageSupplement"]["status"] == "failed"
    assert state["coverageSupplement"]["diagnostics"] == []


def test_supplement_coverage_requires_clean_current_candidate_verification():
    item = {
        "verify": {"status": "success", "returnCode": 0},
        "verifyTasks": {
            "task-stale": {"status": "success", "returnCode": 0},
            "task-current": {"status": "failed", "returnCode": 124, "reason": "timeout"},
        },
    }

    assert batch_module.supplement_item_has_clean_verification(item, "task-current") is False
    assert batch_module.supplement_item_has_clean_verification(item, "task-stale") is True

    attempt = {}
    batch_module.update_supplement_attempt_record(
        attempt,
        item,
        covered=False,
        task_id="task-current",
        matrix_covered=True,
    )

    assert attempt["status"] == "failed"
    assert attempt["verifyStatus"] == "failed"
    assert attempt["returnCode"] == 124


def test_supplement_remaining_missing_uses_clean_covered_keys_not_matrix_rows():
    targets = [
        Namespace(key="VAT_GENERAL:unfiled"),
        Namespace(key="VAT_SMALL:unfiled"),
        Namespace(key="CULTURE_FEE:unfiled"),
    ]

    remaining = batch_module.supplement_remaining_missing_keys(
        targets,
        covered_keys=["VAT_SMALL:unfiled"],
    )

    assert remaining == ["VAT_GENERAL:unfiled", "CULTURE_FEE:unfiled"]


def test_coverage_supplement_defaults_to_three_candidates():
    original_argv = sys.argv[:]
    try:
        sys.argv = ["batch_collect_verify.py", "--tax-no", "911"]
        args = batch_module.parse_args()
    finally:
        sys.argv = original_argv

    assert args.coverage_supplement_max_candidates == 3
    assert args.coverage_supplement_targets == ""
    assert args.coverage_supplement_only is False
    assert args.coverage_supplement_refresh_cit_from_ydz is False


def test_group_supplement_candidates_prefers_exact_status_before_unknown_probe():
    candidates = [
        Namespace(
            target_key="CIT_A:filed",
            task_id="task-unknown-new",
            created_stamp=3,
            declaration_status="filed",
            parse_status="unknown",
            reason="matched_backend_result_json",
        ),
        Namespace(
            target_key="CIT_A:filed",
            task_id="task-filed-old",
            created_stamp=1,
            declaration_status="filed",
            parse_status="filed",
            reason="matched_backend_result_json",
        ),
    ]

    grouped = batch_module.group_supplement_candidates_by_target(candidates, max_candidates=2)

    assert [candidate.task_id for candidate in grouped["CIT_A:filed"]] == [
        "task-filed-old",
        "task-unknown-new",
    ]


def test_group_supplement_candidates_prefers_fresh_ydz_collect():
    candidates = [
        Namespace(
            target_key="CIT_A:unfiled",
            task_id="task-backend-new",
            created_stamp=3,
            declaration_status="unfiled",
            parse_status="unfiled",
            reason="matched_backend_result_json",
        ),
        Namespace(
            target_key="CIT_A:unfiled",
            task_id="task-fresh-old",
            created_stamp=1,
            declaration_status="unfiled",
            parse_status="unfiled",
            reason="fresh_ydz_collect",
        ),
    ]

    grouped = batch_module.group_supplement_candidates_by_target(candidates, max_candidates=2)

    assert [candidate.task_id for candidate in grouped["CIT_A:unfiled"]] == [
        "task-fresh-old",
        "task-backend-new",
    ]


def test_find_supplement_candidates_prefers_distinct_tax_numbers_across_windows():
    def make_candidate(task_id: str, tax_no: str):
        return batch_module.SupplementCandidate(
            target_key="VAT_SMALL:unfiled",
            tax_type="VAT_SMALL",
            tax_type_name="VAT small",
            declaration_status="unfiled",
            declaration_status_name="unfiled",
            task_id=task_id,
            tax_no=tax_no,
            period="202605",
            task_status="SUCCESS",
            backend_tax_id="1",
            backend_query_field="taxId",
            created_stamp=1,
            parse_status="unfiled",
            reason="matched_backend_result_json",
        )

    class MultiWindowPlanner:
        def __init__(self):
            self.calls = 0
            self.last_diagnostics = []

        def find_candidates(self, *_args, **_kwargs):
            self.calls += 1
            if self.calls == 1:
                self.last_diagnostics = [{"targetKey": "VAT_SMALL:unfiled", "matchedTaskIds": ["task-a-new"]}]
                return [make_candidate("task-a-new", "911-A")]
            self.last_diagnostics = [
                {"targetKey": "VAT_SMALL:unfiled", "matchedTaskIds": ["task-a-old", "task-b"]}
            ]
            return [make_candidate("task-a-old", "911-A"), make_candidate("task-b", "922-B")]

    target = Namespace(key="VAT_SMALL:unfiled", tax_type="VAT_SMALL")
    end_time = datetime(2026, 6, 10, 12, 0, 0)
    original = batch_module.supplement_search_batches
    try:
        batch_module.supplement_search_batches = lambda targets, **_kwargs: [
            (targets, "202605", end_time, end_time, "window-1"),
            (targets, "202605", end_time, end_time, "window-2"),
        ]
        candidates, _diagnostics = batch_module.find_supplement_candidates_for_targets(
            MultiWindowPlanner(),
            [target],
            end_time=end_time,
            base_period="202605",
            lookback_days=30,
            cit_lookback_days=30,
            page_size=50,
            max_candidates_per_target=2,
            timeout_seconds=30,
        )
    finally:
        batch_module.supplement_search_batches = original

    assert [candidate.task_id for candidate in candidates] == ["task-a-new", "task-b"]
    assert [candidate.tax_no for candidate in candidates] == ["911-A", "922-B"]


def test_login_preflight_filters_not_ready_candidate_and_keeps_ready_candidate():
    def make_candidate(task_id: str, tax_no: str):
        return batch_module.SupplementCandidate(
            target_key="VAT_SMALL:unfiled",
            tax_type="VAT_SMALL",
            tax_type_name="VAT small",
            declaration_status="unfiled",
            declaration_status_name="unfiled",
            task_id=task_id,
            tax_no=tax_no,
            period="202605",
            task_status="SUCCESS",
            backend_tax_id="1",
            backend_query_field="taxId",
            created_stamp=1,
            parse_status="unfiled",
            reason="matched_backend_result_json",
        )

    class PreflightPage:
        context = None

        def evaluate(self, script, arg=None):
            if script == "window.robotId || ''":
                return "machine-1"
            if isinstance(arg, dict) and arg.get("url"):
                if arg["taskId"] == "task-bad":
                    return {
                        "flag": 1,
                        "success": True,
                        "data": {"declareJob": {"province": "beijing", "taxNo": "911-A"}, "tydl": {"cookies": {}}},
                    }
                return {
                    "flag": 1,
                    "success": True,
                    "data": {
                        "declareJob": {"province": "beijing", "taxNo": "922-B"},
                        "tydl": {"cookies": {"taskInfo": {"taskId": "inner-ready", "province": "beijing"}}},
                    },
                }
            if isinstance(arg, dict) and arg.get("taskId") == "inner-ready":
                return {"flag": 1, "data": {"tydl": {"cookies": {"taskInfo": {"taskId": "inner-ready"}}}}}
            return ""

    class PreflightQuery:
        def _ensure_page(self):
            return PreflightPage()

    candidates, records = batch_module.preflight_supplement_candidates_login_ready(
        [make_candidate("task-bad", "911-A"), make_candidate("task-ready", "922-B")],
        PreflightQuery(),
    )

    assert [candidate.task_id for candidate in candidates] == ["task-ready"]
    assert [(record["taskId"], record["status"], record["stage"]) for record in records] == [
        ("task-bad", "not_ready", "getClientJob"),
        ("task-ready", "ready", "getTaskCookie"),
    ]


def test_cit_refresh_template_is_removed_when_no_task_id_is_resolved():
    target = Namespace(
        key="CIT_A:filed",
        tax_type="CIT_A",
        tax_type_name="CIT A",
        declaration_status="filed",
        declaration_status_name="filed",
        backend_tax_ids=(2,),
        backend_tax_type_ids=(),
    )

    grouped = batch_module.ensure_cit_refresh_template_candidates({}, [target], period="202605")

    assert list(grouped) == ["CIT_A:filed"]
    assert grouped["CIT_A:filed"][0].task_id == ""
    assert grouped["CIT_A:filed"][0].reason == "current_enterprise_scan_template"
    assert batch_module.filter_supplement_candidates_with_task(grouped) == {}


def test_sort_current_enterprise_cit_accounts_prefers_cit_signal():
    no_signal = YdzAccount(
        tax_no="9112",
        cust_name="No Signal",
        assoc_tenant_id=1,
        account_id=1,
        area_code="11",
        auth_status="AUTHORIZED",
        raw={"taxItemDetailList": []},
    )
    cit_signal = YdzAccount(
        tax_no="9111",
        cust_name="CIT Signal",
        assoc_tenant_id=2,
        account_id=2,
        area_code="11",
        auth_status="AUTHORIZED",
        raw={"taxItemDetailList": [{"taxTypeId": 2, "taxTypeName": "CIT"}]},
    )

    sorted_accounts = batch_module.sort_current_enterprise_cit_accounts([no_signal, cit_signal])

    assert [account.tax_no for account in sorted_accounts] == ["9111", "9112"]


def test_ydz_cit_refresh_periods_prefers_current_collectable_periods():
    args = Namespace(period="202605")
    template = Namespace(period="202512")
    originals = [Namespace(period="202603"), Namespace(period="bad")]

    periods = batch_module.ydz_cit_refresh_periods(args, template, originals)

    assert periods == ["202605"]


def test_direct_cit_fresh_refresh_uses_batch_period_not_historical_candidate_period():
    calls = []

    class Collector:
        def find_account(self, tax_no, period):
            calls.append((tax_no, period))
            return None

    candidate = Namespace(target_key="CIT_A:filed", tax_no="91500105MAEQ3URL80", period="202512")

    record, new_candidates = batch_module.refresh_one_supplement_candidate_from_ydz(
        args=Namespace(period="202605"),
        collector=Collector(),
        resolver=object(),
        candidate=candidate,
    )

    assert calls == [("91500105MAEQ3URL80", "202605")]
    assert record["period"] == "202605"
    assert record["reason"] == "no_ydz_account_in_current_enterprise"
    assert new_candidates == []


def test_explicit_ydz_work_urls_merge_args_and_env_and_redact_label():
    old_value = os.environ.get("YDZ_SUPPLEMENT_WORK_URLS")
    os.environ["YDZ_SUPPLEMENT_WORK_URLS"] = (
        "https://inte-cloud.chanjet.com/ydzee/u1/o1/work.html#/home,"
        "https://cloud.chanjet.com/ydzee/u2/o2/work.html#/home"
    )
    try:
        args = Namespace(
            coverage_supplement_ydz_work_url=[
                "https://cloud.chanjet.com/ydzee/u2/o2/work.html#/home",
                "https://cloud.chanjet.com/ydzee/u3/o3/work.html#/home",
            ]
        )

        urls = batch_module.explicit_ydz_work_urls(args)
        label = batch_module.redact_ydz_work_url_label(urls[0])

        assert urls == [
            "https://cloud.chanjet.com/ydzee/u2/o2/work.html#/home",
            "https://cloud.chanjet.com/ydzee/u3/o3/work.html#/home",
            "https://inte-cloud.chanjet.com/ydzee/u1/o1/work.html#/home",
        ]
        assert label == "cloud.chanjet.com/.../work.html"
        assert "u2" not in label
    finally:
        if old_value is None:
            os.environ.pop("YDZ_SUPPLEMENT_WORK_URLS", None)
        else:
            os.environ["YDZ_SUPPLEMENT_WORK_URLS"] = old_value


def test_ydz_work_url_base_ignores_hash_routes():
    session = YdzSession()

    assert (
        session._work_url_base("https://cloud.chanjet.com/ydzee/u1/o1/work.html#/home/dataBoard")
        == "https://cloud.chanjet.com/ydzee/u1/o1/work.html"
    )
    assert (
        session._work_url_base("https://inte-cloud.chanjet.com/ydzee/u2/o2/work.html#/home/gzt/batchDeclare")
        == "https://inte-cloud.chanjet.com/ydzee/u2/o2/work.html"
    )
    assert session._work_url_base("https://ydz.chanjet.com/") == ""


def test_source_readiness_detects_current_enterprise_without_cit_signal():
    target = Namespace(key="CIT_A:filed")
    candidate = Namespace(target_key="CIT_A:filed", task_id="task-1")
    records = [
        {
            "targetKey": "CIT_A:filed",
            "status": "account_scan",
            "reason": "current_enterprise_account_scan",
            "accountCount": 144,
            "citSignalCount": 0,
        },
        {
            "targetKey": "CIT_A:filed",
            "status": "skipped",
            "reason": "current_enterprise_scan_no_cit_account_signal",
            "accountCount": 144,
        },
    ]

    readiness = batch_module.build_supplement_source_readiness(
        missing_targets=[target],
        diagnostics=[{"targetKey": "CIT_A:filed", "reason": "matched_backend_result_json"}],
        candidates=[candidate],
        ydz_refresh_records=records,
    )

    assert readiness[0]["targetKey"] == "CIT_A:filed"
    assert readiness[0]["status"] == "current_enterprise_no_cit_signal"
    assert readiness[0]["ydzAccountCount"] == 144
    assert readiness[0]["ydzCitSignalCount"] == 0
    assert "144" in readiness[0]["message"]


def test_source_readiness_prefers_other_enterprise_cit_signal():
    target = Namespace(key="CIT_A:filed")
    candidate = Namespace(target_key="CIT_A:filed", task_id="task-1")
    records = [
        {
            "targetKey": "CIT_A:filed",
            "status": "account_scan",
            "reason": "current_enterprise_account_scan",
            "source": "current_enterprise_account_scan",
            "accountCount": 144,
            "citSignalCount": 0,
        },
        {
            "targetKey": "CIT_A:filed",
            "status": "account_scan",
            "reason": "other_enterprise_account_scan",
            "source": "other_enterprise_account_scan",
            "enterprise": "CIT浼佷笟",
            "accountCount": 12,
            "citSignalCount": 2,
            "sampleTaxNos": ["911"],
        },
    ]

    readiness = batch_module.build_supplement_source_readiness(
        missing_targets=[target],
        diagnostics=[{"targetKey": "CIT_A:filed", "reason": "matched_backend_result_json"}],
        candidates=[candidate],
        ydz_refresh_records=records,
    )

    assert readiness[0]["status"] == "other_enterprise_has_cit_signal"
    assert readiness[0]["ydzEnterpriseSuggestions"][0]["enterprise"] == "CIT浼佷笟"
    assert "CIT浼佷笟" in readiness[0]["message"]


def test_source_readiness_prefers_explicit_work_url_cit_signal():
    target = Namespace(key="CIT_A:unfiled")
    candidate = Namespace(target_key="CIT_A:unfiled", task_id="task-1")
    records = [
        {
            "targetKey": "CIT_A:unfiled",
            "status": "account_scan",
            "reason": "explicit_work_url_account_scan",
            "source": "explicit_work_url_account_scan",
            "enterprise": "inte-cloud.chanjet.com/.../work.html",
            "accountCount": 8,
            "citSignalCount": 1,
            "sampleTaxNos": ["911"],
        }
    ]

    readiness = batch_module.build_supplement_source_readiness(
        missing_targets=[target],
        diagnostics=[],
        candidates=[candidate],
        ydz_refresh_records=records,
    )

    assert readiness[0]["status"] == "other_enterprise_has_cit_signal"
    assert readiness[0]["ydzEnterpriseScanCount"] == 1
    assert readiness[0]["ydzEnterpriseSuggestions"][0]["enterprise"] == "inte-cloud.chanjet.com/.../work.html"


def test_source_readiness_prefers_open_work_tab_cit_signal():
    target = Namespace(key="CIT_A:filed")
    records = [
        {
            "targetKey": "CIT_A:filed",
            "status": "account_scan",
            "reason": "open_work_tab_account_scan",
            "source": "open_work_tab_account_scan",
            "enterprise": "cloud.chanjet.com/.../work.html",
            "accountCount": 5,
            "citSignalCount": 1,
            "sampleTaxNos": ["922"],
        }
    ]

    readiness = batch_module.build_supplement_source_readiness(
        missing_targets=[target],
        diagnostics=[],
        candidates=[],
        ydz_refresh_records=records,
    )

    assert readiness[0]["status"] == "other_enterprise_has_cit_signal"
    assert readiness[0]["ydzEnterpriseScanCount"] == 1
    assert readiness[0]["ydzEnterpriseSuggestions"][0]["sampleTaxNos"] == ["922"]


def test_source_readiness_reports_other_enterprise_scan_login_required():
    target = Namespace(key="CIT_A:filed")
    records = [
        {
            "targetKey": "CIT_A:filed",
            "status": "account_scan",
            "reason": "current_enterprise_account_scan",
            "source": "current_enterprise_account_scan",
            "accountCount": 144,
            "citSignalCount": 0,
        },
        {
            "targetKey": "CIT_A:filed",
            "status": "failed",
            "reason": "YDZ_USERNAME/YDZ_PASSWORD is missing",
            "source": "other_enterprise_account_scan",
        },
    ]

    readiness = batch_module.build_supplement_source_readiness(
        missing_targets=[target],
        diagnostics=[],
        candidates=[],
        ydz_refresh_records=records,
    )

    assert readiness[0]["status"] == "other_enterprise_scan_login_required"
    assert "YDZ_USERNAME" in readiness[0]["ydzEnterpriseScanError"]
    assert readiness[0]["nextAction"]


def test_source_readiness_reports_other_enterprise_scan_unavailable():
    target = Namespace(key="CIT_A:filed")
    records = [
        {
            "targetKey": "CIT_A:filed",
            "status": "account_scan",
            "reason": "current_enterprise_account_scan",
            "source": "current_enterprise_account_scan",
            "accountCount": 144,
            "citSignalCount": 0,
        },
        {
            "targetKey": "CIT_A:filed",
            "status": "failed",
            "reason": "Yidaizhang app entry did not open a cloud workbench for the selected enterprise.",
            "source": "other_enterprise_account_scan",
            "enterprise": "娴嬭瘯浼佷笟",
        },
    ]

    readiness = batch_module.build_supplement_source_readiness(
        missing_targets=[target],
        diagnostics=[],
        candidates=[],
        ydz_refresh_records=records,
    )

    assert readiness[0]["status"] == "other_enterprise_scan_unavailable"
    assert "娴嬭瘯浼佷笟" not in readiness[0]["message"]
    assert "work.html" in readiness[0]["nextAction"]


def test_source_readiness_reports_ydz_token_expired_as_login_required():
    target = Namespace(key="CIT_A:filed")
    records = [
        {
            "targetKey": "CIT_A:filed",
            "status": "failed",
            "reason": "/trans/easyacctg/query/getBatchList failed: http=701, code=node.common, msg=token 涓嶈兘涓虹┖! undefined",
        }
    ]

    readiness = batch_module.build_supplement_source_readiness(
        missing_targets=[target],
        diagnostics=[
            {
                "targetKey": "CIT_A:filed",
                "reason": "matched_backend_result_json",
                "matchedTaskIds": ["task-1"],
            }
        ],
        candidates=[],
        ydz_refresh_records=records,
    )

    assert readiness[0]["status"] == "ydz_login_required"
    assert readiness[0]["backendCandidateCount"] == 1
    assert "token" in readiness[0]["message"]
    assert readiness[0]["nextAction"]


def test_source_readiness_reports_ydz_missing_login_token_as_login_required():
    target = Namespace(key="CIT_A:unfiled")
    readiness = batch_module.build_supplement_source_readiness(
        missing_targets=[target],
        diagnostics=[{"targetKey": "CIT_A:unfiled", "reason": "matched_backend_result_json"}],
        candidates=[],
        ydz_refresh_records=[
            {
                "targetKey": "CIT_A:unfiled",
                "status": "failed",
                "reason": "Yidaizhang login token is missing after login refresh.",
            }
        ],
    )

    assert readiness[0]["status"] == "ydz_login_required"
    assert readiness[0]["message"]
    assert readiness[0]["nextAction"]


def test_source_readiness_reports_ydz_no_need_collect_as_source_blocker():
    target = Namespace(key="CIT_A:filed")
    candidate = Namespace(target_key="CIT_A:filed", task_id="task-1")
    readiness = batch_module.build_supplement_source_readiness(
        missing_targets=[target],
        diagnostics=[{"targetKey": "CIT_A:filed", "reason": "matched_backend_result_json"}],
        candidates=[candidate],
        ydz_refresh_records=[
            {
                "targetKey": "CIT_A:filed",
                "status": "failed",
                "reason": "fresh_ydz_collect_no_task_id",
                "collectStatus": "NO_NEED_COLLECTED",
                "warnings": [
                    "\u3010\u4f01\u4e1a\u6240\u5f97\u7a0e\u3011\u672c\u671f\u65e0\u9700\u7533\u62a5"
                ],
            }
        ],
    )

    assert readiness[0]["status"] == "ydz_no_need_collect"
    assert readiness[0]["ydzStatus"] == "ydz_no_need_collect"
    assert "taskId" in readiness[0]["message"]
    assert "\u66f4\u6362\u5019\u9009\u7a0e\u53f7" in readiness[0]["nextAction"]


def test_source_readiness_detects_no_need_collect_without_reason():
    status, reason = batch_module.classify_ydz_source_readiness(
        [{"collectStatus": "NO_NEED_COLLECTED", "reason": ""}]
    )

    assert status == "ydz_no_need_collect"
    assert reason == "NO_NEED_COLLECTED"


def test_parse_coverage_supplement_target_keys_normalizes_aliases():
    keys = batch_module.parse_coverage_supplement_target_keys(
        "cit:filed, VAT_SMALL:not_collected, cbj:any, bad"
    )

    assert keys == ["CIT_A:filed", "VAT_SMALL:unfiled", "CBJ_PERSONAL:any"]


def test_invalid_coverage_supplement_target_does_not_run_full_supplement():
    original_write_coverage_status = batch_module.write_coverage_status
    original_session = batch_module.YdzSession

    class UnexpectedSession:
        def __init__(self, **_kwargs):
            raise AssertionError("YdzSession should not be created for invalid supplement targets")

    try:
        batch_module.write_coverage_status = lambda _run_dir, **_kwargs: {
            "missingTargets": [{"key": "VAT_GENERAL:filed"}]
        }
        batch_module.YdzSession = UnexpectedSession
        with tempfile.TemporaryDirectory() as tmp:
            state = {"runId": "ops_test", "period": "202604", "items": {}}
            args = Namespace(coverage_supplement_targets="not-a-target")

            code = batch_module.run_coverage_supplement_phase(args, state, Path(tmp))
    finally:
        batch_module.write_coverage_status = original_write_coverage_status
        batch_module.YdzSession = original_session

    assert code == 2
    assert state["coverageSupplement"]["status"] == "failed"
    assert state["coverageSupplement"]["requestedTargetKeys"] == []


def test_requested_coverage_supplement_targets_do_not_mutate_coverage_scope():
    original_write_coverage_status = batch_module.write_coverage_status
    original_session = batch_module.YdzSession

    class UnexpectedSession:
        def __init__(self, **_kwargs):
            raise AssertionError("YdzSession should not be created when requested target is not missing")

    try:
        batch_module.write_coverage_status = lambda _run_dir, **_kwargs: {
            "missingTargets": [{"key": "VAT_GENERAL:filed"}]
        }
        batch_module.YdzSession = UnexpectedSession
        with tempfile.TemporaryDirectory() as tmp:
            state = {
                "runId": "ops_test",
                "period": "202604",
                "coverageTaxTypes": ["VAT_GENERAL", "CIT_A"],
                "items": {},
            }
            args = Namespace(coverage_supplement_targets="CIT_A:filed")

            code = batch_module.run_coverage_supplement_phase(args, state, Path(tmp))
    finally:
        batch_module.write_coverage_status = original_write_coverage_status
        batch_module.YdzSession = original_session

    assert code == 0
    assert state["coverageTaxTypes"] == ["VAT_GENERAL", "CIT_A"]
    assert state["coverageSupplement"]["status"] == "not_needed"
    assert state["coverageSupplement"]["requestedTargetKeys"] == ["CIT_A:filed"]


def test_supplement_cit_search_uses_quarter_periods_and_sliced_windows():
    periods = batch_module.supplement_cit_candidate_periods("202605")
    windows = batch_module.supplement_time_windows(datetime(2026, 6, 9, 12, 0, 0), 100)

    assert periods[:3] == ["202605", "202604", "202603"]
    assert "202508" in periods
    assert "202512" in periods
    assert len(periods) >= 12
    assert len(windows) >= 3
    assert all((end - start).days <= 39 for start, end in windows)


def test_declaration_status_override_for_coverage_target():
    assert batch_module.declaration_status_override_for_coverage_target("CIT_A:filed") == "filed"
    assert batch_module.declaration_status_override_for_coverage_target("CIT_A:unfiled") == "unfiled"
    assert batch_module.declaration_status_override_for_coverage_target("CBJ_PERSONAL:any") == ""
    assert batch_module.declaration_status_override_for_coverage_target("") == ""


def test_supplement_attempt_classifies_source_state_conflict():
    item = {
        "verifyTasks": {
            "task-conflict": {
                "status": "failed",
                "returnCode": 1,
                "reason": "scripts.compare_tax_forms.UndeclaredTaxAlreadyDeclaredError: Tax bureau home shows the target already declared",
            }
        }
    }
    attempt = {}

    batch_module.update_supplement_attempt_record(
        attempt,
        item,
        covered=False,
        task_id="task-conflict",
    )

    assert attempt["status"] == "failed"
    assert attempt["failureCategory"] == "source_state_conflict"
    assert attempt["step"]


def test_supplement_attempt_classifies_expired_task_cookie():
    reason = "getTaskCookie failed: login state expired"

    assert batch_module.classify_supplement_failure_category(reason) == "tax_login_expired"


def test_supplement_attempt_classifies_incomplete_get_client_job_metadata():
    reason = (
        "RuntimeError: getClientJob returned incomplete tax-login metadata: "
        "{'hasInnerTaskId': False, 'province': 'beijing'}"
    )

    assert batch_module.classify_supplement_failure_category(reason) == "tax_login_expired"
    assert batch_module.classify_supplement_failure_step(reason) == batch_module.classify_supplement_failure_step(
        "getTaskCookie failed: login state expired"
    )
    assert "getClientJob" in batch_module.normalize_supplement_failure_reason(reason)


def test_supplement_attempt_classifies_get_client_job_failure():
    reason = "RuntimeError: getClientJob failed: 登录连接状态已失效，请重新发起任务"

    assert batch_module.classify_supplement_failure_category(reason) == "tax_login_expired"
    assert batch_module.classify_supplement_failure_step(reason) == batch_module.classify_supplement_failure_step(
        "getTaskCookie failed: login state expired"
    )
    normalized = batch_module.normalize_supplement_failure_reason(reason)
    assert "getClientJob failed:" not in normalized
    assert "Tax bureau login failed" in normalized


def test_supplement_attempt_classifies_unresolved_get_client_job_metadata():
    reasons = [
        "ValueError: Cannot resolve inner taskId from getClientJob response: {'hasInnerTaskId': False}",
        "ValueError: Cannot resolve province from getClientJob response: {'province': ''}",
        "ValueError: Cannot resolve province from task cookie/client job data",
    ]

    for reason in reasons:
        assert batch_module.classify_supplement_failure_category(reason) == "tax_login_expired"
        assert batch_module.classify_supplement_failure_step(reason) == batch_module.classify_supplement_failure_step(
            "getTaskCookie failed: login state expired"
        )
        normalized = batch_module.normalize_supplement_failure_reason(reason)
        assert "Cannot resolve" not in normalized
        assert "Tax bureau login failed" in normalized


def test_supplement_attempt_classifies_same_province_switch_limit():
    reason = "getTaskCookie failed: same-province switch limit, wait 1 hour"

    assert batch_module.classify_supplement_failure_category(reason) == "tax_login_blocked"


def test_standard_supplement_candidate_pool_uses_configured_limit():
    assert batch_module.effective_supplement_max_candidates(3, [Namespace(key="VAT_SMALL:unfiled")]) == 3
    assert batch_module.effective_supplement_max_candidates(10, [Namespace(key="VAT_SMALL:unfiled")]) == 10
    assert batch_module.effective_supplement_max_candidates(3, [Namespace(key="CIT_A:filed")]) == 3
    assert batch_module.effective_supplement_max_candidates(3, [Namespace(key="CONSUMPTION_TAX:filed")]) == 3


def test_standard_supplement_history_candidates_retry_until_covered():
    target_key = "VAT_SMALL:unfiled"
    target = Namespace(
        key=target_key,
        tax_type="VAT_SMALL",
        tax_type_name="VAT small",
        declaration_status="unfiled",
        declaration_status_name="unfiled",
    )
    backends = [
        batch_module.SupplementCandidate(
            target_key=target_key,
            tax_type="VAT_SMALL",
            tax_type_name="VAT small",
            declaration_status="unfiled",
            declaration_status_name="unfiled",
            task_id=f"history-{index}",
            tax_no=f"911-{index}",
            period="202604",
            parse_status="unfiled",
            reason="backend_candidate",
            created_stamp=4 - index,
        )
        for index in range(1, 4)
    ]
    state = {"runId": "ops_test", "period": "202604", "items": {}}
    verified_task_ids = []
    captured_find_kwargs = {}

    class DummyLock:
        def __init__(self, *_args, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

    class DummySession:
        def __init__(self, **_kwargs):
            pass

        def connect(self):
            return object()

        def close(self):
            pass

    def fake_write_coverage_status(_run_dir, **_kwargs):
        covered = bool(state.get("_covered"))
        return {
            "missingTargets": [] if covered else [{"key": target_key}],
            "targets": [{"key": target_key, "covered": covered}],
        }

    def fake_find_supplement_candidates(*_args, **kwargs):
        captured_find_kwargs.update(kwargs)
        return backends, [{"targetKey": target_key, "matchedTaskId": backends[0].task_id, "reason": "matched"}]

    def fake_apply(state_arg, candidates, enterprise=""):
        candidate = candidates[0]
        item_key = f"item-{candidate.task_id}"
        state_arg.setdefault("items", {})[item_key] = {
            "taxNo": candidate.tax_no,
            "collect": {"verifyTaskId": candidate.task_id},
            "verifyTasks": {},
        }
        return [item_key]

    def fake_run_verify(_args, item_keys, state_arg, _run_dir, **_kwargs):
        item = state_arg["items"][item_keys[0]]
        task_id = item["collect"]["verifyTaskId"]
        verified_task_ids.append(task_id)
        if task_id in {"history-1", "history-2"}:
            item["verifyTasks"][task_id] = {
                "status": "failed",
                "returnCode": 2,
                "reason": "getTaskCookie failed: login state expired",
            }
            return 2
        item["verifyTasks"][task_id] = {"status": "success", "returnCode": 0, "reason": ""}
        state_arg["_covered"] = True
        return 0

    originals = {
        "write_coverage_status": batch_module.write_coverage_status,
        "coverage_targets_for_state": batch_module.coverage_targets_for_state,
        "ProcessLock": batch_module.ProcessLock,
        "YdzSession": batch_module.YdzSession,
        "ChanjetAdminTaskQuery": batch_module.ChanjetAdminTaskQuery,
        "CoverageSupplementPlanner": batch_module.CoverageSupplementPlanner,
        "find_supplement_candidates_for_targets": batch_module.find_supplement_candidates_for_targets,
        "apply_supplement_candidates_to_state": batch_module.apply_supplement_candidates_to_state,
        "run_verify_phase": batch_module.run_verify_phase,
    }
    try:
        batch_module.write_coverage_status = fake_write_coverage_status
        batch_module.coverage_targets_for_state = lambda _state: [target]
        batch_module.ProcessLock = DummyLock
        batch_module.YdzSession = DummySession
        batch_module.ChanjetAdminTaskQuery = lambda _context: object()
        batch_module.CoverageSupplementPlanner = lambda _query: object()
        batch_module.find_supplement_candidates_for_targets = fake_find_supplement_candidates
        batch_module.apply_supplement_candidates_to_state = fake_apply
        batch_module.run_verify_phase = fake_run_verify
        with tempfile.TemporaryDirectory() as tmp:
            args = Namespace(
                browser_lock_timeout=1,
                cdp_port=9222,
                chrome_path="chrome.exe",
                user_data_dir="profile",
                plugin_path="plugin",
                coverage_supplement_page_size=50,
                coverage_supplement_timeout=600,
                coverage_supplement_lookback_days=0,
                coverage_supplement_cit_lookback_days=100,
                coverage_supplement_max_candidates=3,
                coverage_supplement_targets="",
                coverage_supplement_refresh_cit_from_ydz=False,
                period="202604",
                enterprise="demo",
            )

            code = batch_module.run_coverage_supplement_phase(args, state, Path(tmp))
    finally:
        for name, value in originals.items():
            setattr(batch_module, name, value)

    attempts = state["coverageSupplement"]["attempts"]
    assert code == 0
    assert verified_task_ids == ["history-1", "history-2", "history-3"]
    assert captured_find_kwargs["max_candidates_per_target"] == 9
    assert [attempt["failureCategory"] for attempt in attempts[:2]] == ["tax_login_expired", "tax_login_expired"]
    assert attempts[2]["status"] == "covered"
    assert state["coverageSupplement"]["maxCandidatesPerTarget"] == 3
    assert state["coverageSupplement"]["candidatePoolLimitPerTarget"] == 9


def test_standard_supplement_preflight_refills_after_not_ready_pool():
    target_key = "VAT_SMALL:unfiled"
    target = Namespace(
        key=target_key,
        tax_type="VAT_SMALL",
        tax_type_name="VAT small",
        declaration_status="unfiled",
        declaration_status_name="unfiled",
    )
    not_ready_candidates = [
        batch_module.SupplementCandidate(
            target_key=target_key,
            tax_type="VAT_SMALL",
            tax_type_name="VAT small",
            declaration_status="unfiled",
            declaration_status_name="unfiled",
            task_id=f"expired-{index}",
            tax_no=f"911-expired-{index}",
            period="202604",
            parse_status="unfiled",
            reason="backend_candidate",
            created_stamp=10 - index,
        )
        for index in range(1, 4)
    ]
    second_not_ready_candidates = [
        batch_module.SupplementCandidate(
            target_key=target_key,
            tax_type="VAT_SMALL",
            tax_type_name="VAT small",
            declaration_status="unfiled",
            declaration_status_name="unfiled",
            task_id=f"expired-{index}",
            tax_no=f"911-expired-{index}",
            period="202604",
            parse_status="unfiled",
            reason="backend_candidate",
            created_stamp=10 - index,
        )
        for index in range(4, 7)
    ]
    ready_candidate = batch_module.SupplementCandidate(
        target_key=target_key,
        tax_type="VAT_SMALL",
        tax_type_name="VAT small",
        declaration_status="unfiled",
        declaration_status_name="unfiled",
        task_id="ready-1",
        tax_no="911-ready",
        period="202604",
        parse_status="unfiled",
        reason="backend_candidate",
        created_stamp=1,
    )
    state = {"runId": "ops_test", "period": "202604", "items": {}}
    find_calls = []
    verified_task_ids = []

    class DummyLock:
        def __init__(self, *_args, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

    class DummySession:
        def __init__(self, **_kwargs):
            pass

        def connect(self):
            return object()

        def close(self):
            pass

    def fake_write_coverage_status(_run_dir, **_kwargs):
        covered = bool(state.get("_covered"))
        return {
            "missingTargets": [] if covered else [{"key": target_key}],
            "targets": [{"key": target_key, "covered": covered}],
        }

    def fake_find_supplement_candidates(*_args, **kwargs):
        excluded = {
            key: set(value)
            for key, value in (kwargs.get("excluded_task_ids_by_target") or {}).items()
        }
        find_calls.append(excluded)
        if len(find_calls) == 1:
            return not_ready_candidates, [
                {"targetKey": target_key, "matchedTaskIds": [candidate.task_id for candidate in not_ready_candidates]}
            ]
        if len(find_calls) == 2:
            assert excluded[target_key] == {candidate.task_id for candidate in not_ready_candidates}
            return second_not_ready_candidates, [
                {
                    "targetKey": target_key,
                    "matchedTaskIds": [candidate.task_id for candidate in second_not_ready_candidates],
                }
            ]
        expected_excluded = {candidate.task_id for candidate in [*not_ready_candidates, *second_not_ready_candidates]}
        assert excluded[target_key] == expected_excluded
        return [ready_candidate], [{"targetKey": target_key, "matchedTaskIds": [ready_candidate.task_id]}]

    def fake_preflight(candidates, _admin_query):
        records = []
        filtered = []
        for candidate in candidates:
            if candidate.task_id.startswith("expired-"):
                records.append(
                    {
                        "targetKey": candidate.target_key,
                        "taxType": candidate.tax_type,
                        "taskId": candidate.task_id,
                        "taxNo": candidate.tax_no,
                        "status": "not_ready",
                        "failureCategory": "tax_login_expired",
                        "reason": "getTaskCookie failed: login state expired",
                    }
                )
            else:
                records.append(
                    {
                        "targetKey": candidate.target_key,
                        "taxType": candidate.tax_type,
                        "taskId": candidate.task_id,
                        "taxNo": candidate.tax_no,
                        "status": "ready",
                        "reason": "login_metadata_ready",
                    }
                )
                filtered.append(candidate)
        return filtered, records

    def fake_apply(state_arg, candidates, enterprise=""):
        candidate = candidates[0]
        item_key = f"item-{candidate.task_id}"
        state_arg.setdefault("items", {})[item_key] = {
            "taxNo": candidate.tax_no,
            "collect": {"verifyTaskId": candidate.task_id},
            "verifyTasks": {},
        }
        return [item_key]

    def fake_run_verify(_args, item_keys, state_arg, _run_dir, **_kwargs):
        item = state_arg["items"][item_keys[0]]
        task_id = item["collect"]["verifyTaskId"]
        verified_task_ids.append(task_id)
        item["verifyTasks"][task_id] = {"status": "success", "returnCode": 0, "reason": ""}
        state_arg["_covered"] = True
        return 0

    originals = {
        "write_coverage_status": batch_module.write_coverage_status,
        "coverage_targets_for_state": batch_module.coverage_targets_for_state,
        "ProcessLock": batch_module.ProcessLock,
        "YdzSession": batch_module.YdzSession,
        "ChanjetAdminTaskQuery": batch_module.ChanjetAdminTaskQuery,
        "CoverageSupplementPlanner": batch_module.CoverageSupplementPlanner,
        "find_supplement_candidates_for_targets": batch_module.find_supplement_candidates_for_targets,
        "preflight_supplement_candidates_login_ready": batch_module.preflight_supplement_candidates_login_ready,
        "apply_supplement_candidates_to_state": batch_module.apply_supplement_candidates_to_state,
        "run_verify_phase": batch_module.run_verify_phase,
    }
    try:
        batch_module.write_coverage_status = fake_write_coverage_status
        batch_module.coverage_targets_for_state = lambda _state: [target]
        batch_module.ProcessLock = DummyLock
        batch_module.YdzSession = DummySession
        batch_module.ChanjetAdminTaskQuery = lambda _context: object()
        batch_module.CoverageSupplementPlanner = lambda _query: object()
        batch_module.find_supplement_candidates_for_targets = fake_find_supplement_candidates
        batch_module.preflight_supplement_candidates_login_ready = fake_preflight
        batch_module.apply_supplement_candidates_to_state = fake_apply
        batch_module.run_verify_phase = fake_run_verify
        with tempfile.TemporaryDirectory() as tmp:
            args = Namespace(
                browser_lock_timeout=1,
                cdp_port=9222,
                chrome_path="chrome.exe",
                user_data_dir="profile",
                plugin_path="plugin",
                coverage_supplement_page_size=50,
                coverage_supplement_timeout=600,
                coverage_supplement_lookback_days=0,
                coverage_supplement_cit_lookback_days=100,
                coverage_supplement_max_candidates=3,
                coverage_supplement_targets="",
                coverage_supplement_refresh_cit_from_ydz=False,
                period="202604",
                enterprise="demo",
            )

            code = batch_module.run_coverage_supplement_phase(args, state, Path(tmp))
    finally:
        for name, value in originals.items():
            setattr(batch_module, name, value)

    assert code == 0
    assert len(find_calls) == 3
    assert verified_task_ids == ["ready-1"]
    assert state["coverageSupplement"]["preflightRefillCount"] == 2
    assert state["coverageSupplement"]["backendCandidateCount"] == 7
    assert state["coverageSupplement"]["preflightReadyCandidateCount"] == 1


def test_standard_supplement_refill_excludes_already_seen_ready_candidates():
    target_key = "VAT_SMALL:unfiled"
    target = Namespace(
        key=target_key,
        tax_type="VAT_SMALL",
        tax_type_name="VAT small",
        declaration_status="unfiled",
        declaration_status_name="unfiled",
    )
    ready_first = batch_module.SupplementCandidate(
        target_key=target_key,
        tax_type="VAT_SMALL",
        tax_type_name="VAT small",
        declaration_status="unfiled",
        declaration_status_name="unfiled",
        task_id="ready-first",
        tax_no="911-ready-first",
        period="202604",
        parse_status="unfiled",
        reason="backend_candidate",
        created_stamp=5,
    )
    expired_first = batch_module.SupplementCandidate(
        target_key=target_key,
        tax_type="VAT_SMALL",
        tax_type_name="VAT small",
        declaration_status="unfiled",
        declaration_status_name="unfiled",
        task_id="expired-first",
        tax_no="911-expired-first",
        period="202604",
        parse_status="unfiled",
        reason="backend_candidate",
        created_stamp=4,
    )
    ready_second = batch_module.SupplementCandidate(
        target_key=target_key,
        tax_type="VAT_SMALL",
        tax_type_name="VAT small",
        declaration_status="unfiled",
        declaration_status_name="unfiled",
        task_id="ready-second",
        tax_no="911-ready-second",
        period="202604",
        parse_status="unfiled",
        reason="backend_candidate",
        created_stamp=3,
    )
    state = {"runId": "ops_test", "period": "202604", "items": {}}
    find_calls = []
    verified_task_ids = []

    class DummyLock:
        def __init__(self, *_args, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

    class DummySession:
        def __init__(self, **_kwargs):
            pass

        def connect(self):
            return object()

        def close(self):
            pass

    def fake_write_coverage_status(_run_dir, **_kwargs):
        covered = bool(state.get("_covered"))
        return {
            "missingTargets": [] if covered else [{"key": target_key}],
            "targets": [{"key": target_key, "covered": covered}],
        }

    def fake_find_supplement_candidates(*_args, **kwargs):
        excluded = {
            key: set(value)
            for key, value in (kwargs.get("excluded_task_ids_by_target") or {}).items()
        }
        find_calls.append(excluded)
        if len(find_calls) == 1:
            return [ready_first, expired_first], [{"targetKey": target_key, "matchedTaskIds": ["ready-first"]}]
        assert excluded[target_key] == {"ready-first", "expired-first"}
        return [ready_second], [{"targetKey": target_key, "matchedTaskIds": ["ready-second"]}]

    def fake_preflight(candidates, _admin_query):
        records = []
        filtered = []
        for candidate in candidates:
            if candidate.task_id.startswith("expired"):
                records.append(
                    {
                        "targetKey": candidate.target_key,
                        "taxType": candidate.tax_type,
                        "taskId": candidate.task_id,
                        "taxNo": candidate.tax_no,
                        "status": "not_ready",
                        "failureCategory": "tax_login_expired",
                        "reason": "getTaskCookie failed: login state expired",
                    }
                )
            else:
                records.append(
                    {
                        "targetKey": candidate.target_key,
                        "taxType": candidate.tax_type,
                        "taskId": candidate.task_id,
                        "taxNo": candidate.tax_no,
                        "status": "ready",
                        "reason": "login_metadata_ready",
                    }
                )
                filtered.append(candidate)
        return filtered, records

    def fake_apply(state_arg, candidates, enterprise=""):
        candidate = candidates[0]
        item_key = f"item-{candidate.task_id}"
        state_arg.setdefault("items", {})[item_key] = {
            "taxNo": candidate.tax_no,
            "collect": {"verifyTaskId": candidate.task_id},
            "verifyTasks": {},
        }
        return [item_key]

    def fake_run_verify(_args, item_keys, state_arg, _run_dir, **_kwargs):
        item = state_arg["items"][item_keys[0]]
        task_id = item["collect"]["verifyTaskId"]
        verified_task_ids.append(task_id)
        item["verifyTasks"][task_id] = {"status": "success", "returnCode": 0, "reason": ""}
        state_arg["_covered"] = True
        return 0

    originals = {
        "write_coverage_status": batch_module.write_coverage_status,
        "coverage_targets_for_state": batch_module.coverage_targets_for_state,
        "ProcessLock": batch_module.ProcessLock,
        "YdzSession": batch_module.YdzSession,
        "ChanjetAdminTaskQuery": batch_module.ChanjetAdminTaskQuery,
        "CoverageSupplementPlanner": batch_module.CoverageSupplementPlanner,
        "find_supplement_candidates_for_targets": batch_module.find_supplement_candidates_for_targets,
        "preflight_supplement_candidates_login_ready": batch_module.preflight_supplement_candidates_login_ready,
        "apply_supplement_candidates_to_state": batch_module.apply_supplement_candidates_to_state,
        "run_verify_phase": batch_module.run_verify_phase,
    }
    try:
        batch_module.write_coverage_status = fake_write_coverage_status
        batch_module.coverage_targets_for_state = lambda _state: [target]
        batch_module.ProcessLock = DummyLock
        batch_module.YdzSession = DummySession
        batch_module.ChanjetAdminTaskQuery = lambda _context: object()
        batch_module.CoverageSupplementPlanner = lambda _query: object()
        batch_module.find_supplement_candidates_for_targets = fake_find_supplement_candidates
        batch_module.preflight_supplement_candidates_login_ready = fake_preflight
        batch_module.apply_supplement_candidates_to_state = fake_apply
        batch_module.run_verify_phase = fake_run_verify
        with tempfile.TemporaryDirectory() as tmp:
            args = Namespace(
                browser_lock_timeout=1,
                cdp_port=9222,
                chrome_path="chrome.exe",
                user_data_dir="profile",
                plugin_path="plugin",
                coverage_supplement_page_size=50,
                coverage_supplement_timeout=600,
                coverage_supplement_lookback_days=0,
                coverage_supplement_cit_lookback_days=100,
                coverage_supplement_max_candidates=3,
                coverage_supplement_targets="",
                coverage_supplement_refresh_cit_from_ydz=False,
                period="202604",
                enterprise="demo",
            )

            code = batch_module.run_coverage_supplement_phase(args, state, Path(tmp))
    finally:
        for name, value in originals.items():
            setattr(batch_module, name, value)

    assert code == 0
    assert len(find_calls) == 2
    assert verified_task_ids == ["ready-first"]
    assert state["coverageSupplement"]["preflightRefillCount"] == 1
    assert state["coverageSupplement"]["backendCandidateCount"] == 3
    assert state["coverageSupplement"]["preflightReadyCandidateCount"] == 2


def test_supplement_final_exit_code_ignores_earlier_failures_after_coverage():
    missing_targets = [Namespace(key="VAT_SMALL:unfiled")]

    code = batch_module.supplement_final_verify_exit_code(
        verify_exit=2,
        remaining_missing=[],
        missing_targets=missing_targets,
        covered_keys=["VAT_SMALL:unfiled"],
        attempts=[
            {"targetKey": "VAT_SMALL:unfiled", "status": "failed", "failureCategory": "tax_login_expired"},
            {"targetKey": "VAT_SMALL:unfiled", "status": "covered"},
        ],
    )

    assert code == 0


def test_supplement_final_exit_code_keeps_non_retryable_failure():
    missing_targets = [Namespace(key="VAT_SMALL:unfiled")]

    code = batch_module.supplement_final_verify_exit_code(
        verify_exit=2,
        remaining_missing=["VAT_SMALL:unfiled"],
        missing_targets=missing_targets,
        covered_keys=[],
        attempts=[
            {"targetKey": "VAT_SMALL:unfiled", "status": "failed", "failureCategory": "verification_failed"},
        ],
    )

    assert code == 2


def test_supplement_excludes_stable_failed_attempts_only():
    attempts = [
        {
            "targetKey": "VAT_SMALL:unfiled",
            "taskId": "task-expired",
            "status": "failed",
            "failureCategory": "tax_login_expired",
        },
        {
            "targetKey": "VAT_SMALL:unfiled",
            "taskId": "task-timeout",
            "status": "failed",
            "failureCategory": "timeout",
        },
        {
            "targetKey": "VAT_GENERAL:unfiled",
            "taskId": "task-conflict",
            "status": "failed",
            "reason": "scripts.compare_tax_forms.UndeclaredTaxAlreadyDeclaredError: already declared",
        },
        {
            "targetKey": "VAT_GENERAL:unfiled",
            "taskId": "task-covered",
            "status": "covered",
            "failureCategory": "source_state_conflict",
        },
    ]

    excluded = batch_module.supplement_excluded_task_ids_from_attempts(attempts)

    assert excluded == {
        "VAT_SMALL:unfiled": {"task-expired"},
        "VAT_GENERAL:unfiled": {"task-conflict"},
    }


def test_supplement_excludes_stable_failed_state_items():
    state = {
        "coverageSupplement": {
            "loginPreflight": [
                {
                    "targetKey": "VAT_SMALL:unfiled",
                    "taskId": "task-preflight-expired",
                    "status": "not_ready",
                    "failureCategory": "tax_login_expired",
                    "reason": "getClientJob returned incomplete tax-login metadata",
                },
                {
                    "targetKey": "VAT_SMALL:unfiled",
                    "taskId": "task-preflight-unknown",
                    "status": "unknown",
                    "reason": "login preflight page unavailable",
                },
            ]
        },
        "items": {
            "tax-a": {
                "source": "backend_supplement",
                "coverageSupplementTargets": ["VAT_SMALL:unfiled"],
                "collect": {"verifyTaskId": "task-expired"},
                "verifyTasks": {
                    "task-expired": {
                        "status": "failed",
                        "reason": "getTaskCookie failed: login state expired",
                    }
                },
            },
            "tax-b": {
                "source": "backend_supplement",
                "coverageSupplementTargets": ["VAT_SMALL:unfiled"],
                "collect": {"verifyTaskId": "task-timeout"},
                "verifyTasks": {
                    "task-timeout": {
                        "status": "failed",
                        "reason": "Verification subprocess timed out after 600s",
                    }
                },
            },
            "tax-c": {
                "source": "backend_supplement",
                "coverageSupplementTargets": ["CIT_A:filed"],
                "collect": {
                    "verifyTaskId": "task-conflict",
                    "resolvedTask": {"coverageTarget": "CIT_A:filed"},
                },
                "verify": {
                    "status": "failed",
                    "reason": "Declaration row was not found for target=cit_a_main",
                },
            },
        }
    }

    excluded = batch_module.supplement_excluded_task_ids_from_state(state)

    assert excluded == {
        "VAT_SMALL:unfiled": {"task-expired", "task-preflight-expired"},
        "CIT_A:filed": {"task-conflict"},
    }


def test_supplement_attempt_classifies_missing_filed_declaration_row():
    reason = "RuntimeError: Declaration row was not found for keywords=('A200000',); period=2026-01-01~2026-03-31"

    assert batch_module.classify_supplement_failure_category(reason) == "source_state_conflict"


def test_merge_supplement_diagnostics_keeps_match_after_later_empty_query():
    diagnostics = [
        {
            "targetKey": "CIT_A:filed",
            "queriedCount": 2,
            "statusCounts": {"filed": 1},
            "statusTaskIds": {"filed": ["task-filed"]},
            "taskTaxTypeCounts": {},
            "cbjModeSourceCounts": {},
            "matchedTaskId": "task-filed",
            "matchedTaskIds": ["task-filed"],
            "candidateCount": 1,
            "reason": "matched_backend_result_json",
            "searchPeriod": "202503",
            "searchStartTime": "2026-04-01T00:00:00",
            "searchEndTime": "2026-05-10T00:00:00",
        },
        {
            "targetKey": "CIT_A:filed",
            "queriedCount": 0,
            "statusCounts": {},
            "statusTaskIds": {"unknown": ["task-unknown"]},
            "taskTaxTypeCounts": {},
            "cbjModeSourceCounts": {},
            "matchedTaskId": "",
            "matchedTaskIds": [],
            "candidateCount": 0,
            "reason": "no_success_collect_tasks",
            "searchPeriod": "202512",
            "searchStartTime": "2026-02-01T00:00:00",
            "searchEndTime": "2026-03-10T00:00:00",
        },
    ]

    merged = batch_module.merge_supplement_diagnostics(diagnostics)

    assert merged[0]["matchedTaskId"] == "task-filed"
    assert merged[0]["candidateCount"] == 1
    assert merged[0]["reason"] == "matched_backend_result_json"
    assert merged[0]["queriedCount"] == 2
    assert merged[0]["statusTaskIds"] == {
        "filed": ["task-filed"],
        "unknown": ["task-unknown"],
    }


def test_batch_coverage_targets_follow_selected_tax_types():
    state = {"coverageTaxTypes": ["CONSUMPTION_TAX"]}

    targets = batch_module.coverage_targets_for_state(state)

    assert {target.tax_type for target in targets} == {"CONSUMPTION_TAX"}
    assert len(targets) == 2


def test_invalid_ydz_signature_is_classified_as_login_expired():
    exc = RuntimeError(
        "/trans/easyacctg/query/getBatchList failed: http=701, code=node.common, msg=invalid signature token"
    )

    assert batch_module.is_ydz_invalid_signature_error(exc) is True
    assert batch_module.friendly_collect_exception(exc)


def test_new_batch_forces_fresh_collection_when_no_task_id():
    args = Namespace(force=False, reuse_collected_task=False)

    assert should_force_collect(args, {}) is True


def test_existing_task_id_is_not_recollected_without_explicit_force():
    args = Namespace(force=False, reuse_collected_task=False)

    assert should_force_collect(args, {"verifyTaskId": "task-1"}) is False


def test_reuse_collected_task_keeps_existing_backend_resolution_mode():
    args = Namespace(force=False, reuse_collected_task=True)

    assert should_force_collect(args, {}) is False


def test_explicit_force_overrides_existing_task_id():
    args = Namespace(force=True, reuse_collected_task=True)

    assert should_force_collect(args, {"verifyTaskId": "task-1"}) is True


def test_multi_task_collect_result_creates_child_verification_items():
    result = YdzCollectResult(tax_no="91370102MA7D3P0D2P", period="202605", enterprise="test")
    result.verify_task_id = "2075110435864560097"
    result.verify_task_ids = ["2075110435864560097", "2075110435864560096"]
    result.resolved_tasks = [
        {"taskId": "2075110435864560097", "status": "SUCCESS"},
        {"taskId": "2075110435864560096", "status": "SUCCESS"},
    ]
    state = {
        "items": {
            "91370102MA7D3P0D2P": {
                "taxNo": "91370102MA7D3P0D2P",
                "period": "202605",
                "collect": result.to_dict(),
            }
        }
    }

    batch_module.sync_multi_task_items(state, "91370102MA7D3P0D2P", result)

    parent = state["items"]["91370102MA7D3P0D2P"]
    child_key = "91370102MA7D3P0D2P__task__2075110435864560096"
    assert parent["multiTaskItemKeys"] == [child_key]
    assert parent["collect"]["verifyTaskIds"] == ["2075110435864560097", "2075110435864560096"]
    assert state["items"][child_key]["taxNo"] == "91370102MA7D3P0D2P"
    assert state["items"][child_key]["collect"]["verifyTaskId"] == "2075110435864560096"
    assert batch_module.verification_item_keys(["91370102MA7D3P0D2P"], state) == [
        "91370102MA7D3P0D2P",
        child_key,
    ]


def test_has_verifiable_items_checks_multi_task_children():
    state = {
        "items": {
            "91370102MA7D3P0D2P": {
                "taxNo": "91370102MA7D3P0D2P",
                "collect": {"verifyTaskId": "task-1", "verifyTaskIds": ["task-1", "task-2"]},
                "multiTaskItemKeys": ["91370102MA7D3P0D2P__task__task_2"],
                "verify": {"status": "success"},
            },
            "91370102MA7D3P0D2P__task__task_2": {
                "taxNo": "91370102MA7D3P0D2P",
                "parentTaxNo": "91370102MA7D3P0D2P",
                "collect": {"verifyTaskId": "task-2", "verifyTaskIds": ["task-2"]},
                "verify": {},
            },
        }
    }

    assert has_verifiable_items(["91370102MA7D3P0D2P"], state) is True


def test_low_coverage_log_without_report_quality_issue_is_not_risk():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        log_path = root / "verify.err.log"
        report_path = root / "report.json"
        log_path.write_text(
            "2026-06-04 WARNING compare_tax_forms: vat_general_appendix1 low web extraction coverage: 46/134 (34.33%)\n",
            encoding="utf-8",
        )
        report_path.write_text(
            json.dumps(
                {
                    "batch_id": "vat_general_appendix1",
                    "summary": {"web_missing_count": 0},
                    "quality_issues": [],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        assert verification_risks({"stderrLog": str(log_path), "reportPaths": [str(report_path)]}) == []


def test_low_coverage_log_with_report_quality_issue_is_risk():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        log_path = root / "verify.err.log"
        report_path = root / "report.json"
        log_path.write_text(
            "2026-06-04 WARNING compare_tax_forms: vat_general_appendix1 low web extraction coverage: 46/134 (34.33%)\n",
            encoding="utf-8",
        )
        report_path.write_text(
            json.dumps(
                {
                    "batch_id": "vat_general_appendix1",
                    "summary": {"web_missing_count": 1},
                    "quality_issues": ["low_web_extraction_coverage"],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        assert verification_risks({"stderrLog": str(log_path), "reportPaths": [str(report_path)]})


if __name__ == "__main__":
    test_parse_tax_nos_strips_utf8_bom_from_file_and_argument()
    test_collect_failure_reason_prefers_timeout_over_submit_response_noise()
    test_collect_failure_reason_skips_no_need_warning()
    test_collect_failure_reason_ignores_social_security_failure()
    test_collect_failure_reason_prefers_specific_tax_failure_over_timeout()
    test_manual_handling_reason_is_single_direct_reason()
    test_direct_verify_reason_identifies_tax_auth_failure()
    test_direct_verify_reason_identifies_tpass_login_runtime_error()
    test_ops_status_normalizes_tpass_stage_reason()
    test_direct_verify_reason_identifies_declaration_loading_auth_error()
    test_direct_verify_reason_identifies_tax_login_not_ready_error()
    test_direct_verify_reason_identifies_need_force_tax()
    test_direct_verify_reason_identifies_pending_tax_login_job()
    test_direct_verify_reason_identifies_unresolved_task_cookie_metadata()
    test_cbj_auto_mode_uses_backend_for_personal_tax_item()
    test_backend_supplement_verification_limits_targets_to_active_tax_type()
    test_backend_supplement_target_limit_keeps_explicit_targets_and_cbj_empty()
    test_final_verify_marks_existing_result_item_verified()
    test_cbj_auto_mode_uses_annual_for_annual_tax_item()
    test_cbj_auto_mode_prefers_task_log_annual_marker_over_tax_type_26()
    test_not_collected_cbj_tax_item_does_not_request_cbj_verification()
    test_safe_write_json_text_writes_valid_json_atomically()
    test_tail_error_reason_skips_benign_browser_shutdown_lines()
    test_tail_error_reason_prefers_playwright_error_over_stack_tail()
    test_final_verify_marks_missing_task_id_as_manual_not_running()
    test_rerun_verified_does_not_requeue_task_id_already_verified_this_run()
    test_coverage_supplement_failure_keeps_diagnostics_defined()
    test_supplement_coverage_requires_clean_current_candidate_verification()
    test_supplement_remaining_missing_uses_clean_covered_keys_not_matrix_rows()
    test_coverage_supplement_defaults_to_three_candidates()
    test_group_supplement_candidates_prefers_exact_status_before_unknown_probe()
    test_group_supplement_candidates_prefers_fresh_ydz_collect()
    test_find_supplement_candidates_prefers_distinct_tax_numbers_across_windows()
    test_login_preflight_filters_not_ready_candidate_and_keeps_ready_candidate()
    test_cit_refresh_template_is_removed_when_no_task_id_is_resolved()
    test_sort_current_enterprise_cit_accounts_prefers_cit_signal()
    test_ydz_cit_refresh_periods_prefers_current_collectable_periods()
    test_direct_cit_fresh_refresh_uses_batch_period_not_historical_candidate_period()
    test_explicit_ydz_work_urls_merge_args_and_env_and_redact_label()
    test_ydz_work_url_base_ignores_hash_routes()
    test_source_readiness_detects_current_enterprise_without_cit_signal()
    test_source_readiness_prefers_other_enterprise_cit_signal()
    test_source_readiness_prefers_explicit_work_url_cit_signal()
    test_source_readiness_prefers_open_work_tab_cit_signal()
    test_source_readiness_reports_other_enterprise_scan_login_required()
    test_source_readiness_reports_other_enterprise_scan_unavailable()
    test_source_readiness_reports_ydz_token_expired_as_login_required()
    test_source_readiness_reports_ydz_missing_login_token_as_login_required()
    test_source_readiness_reports_ydz_no_need_collect_as_source_blocker()
    test_source_readiness_detects_no_need_collect_without_reason()
    test_parse_coverage_supplement_target_keys_normalizes_aliases()
    test_invalid_coverage_supplement_target_does_not_run_full_supplement()
    test_requested_coverage_supplement_targets_do_not_mutate_coverage_scope()
    test_supplement_cit_search_uses_quarter_periods_and_sliced_windows()
    test_declaration_status_override_for_coverage_target()
    test_supplement_attempt_classifies_source_state_conflict()
    test_supplement_attempt_classifies_expired_task_cookie()
    test_supplement_attempt_classifies_incomplete_get_client_job_metadata()
    test_supplement_attempt_classifies_get_client_job_failure()
    test_supplement_attempt_classifies_unresolved_get_client_job_metadata()
    test_supplement_attempt_classifies_same_province_switch_limit()
    test_standard_supplement_candidate_pool_uses_configured_limit()
    test_standard_supplement_history_candidates_retry_until_covered()
    test_standard_supplement_preflight_refills_after_not_ready_pool()
    test_standard_supplement_refill_excludes_already_seen_ready_candidates()
    test_supplement_final_exit_code_ignores_earlier_failures_after_coverage()
    test_supplement_final_exit_code_keeps_non_retryable_failure()
    test_supplement_excludes_stable_failed_state_items()
    test_supplement_attempt_classifies_missing_filed_declaration_row()
    test_merge_supplement_diagnostics_keeps_match_after_later_empty_query()
    test_batch_coverage_targets_follow_selected_tax_types()
    test_invalid_ydz_signature_is_classified_as_login_expired()
    test_new_batch_forces_fresh_collection_when_no_task_id()
    test_existing_task_id_is_not_recollected_without_explicit_force()
    test_reuse_collected_task_keeps_existing_backend_resolution_mode()
    test_explicit_force_overrides_existing_task_id()
    test_multi_task_collect_result_creates_child_verification_items()
    test_has_verifiable_items_checks_multi_task_children()
    test_low_coverage_log_without_report_quality_issue_is_not_risk()
    test_low_coverage_log_with_report_quality_issue_is_risk()
    print("All batch handling info tests passed!")
