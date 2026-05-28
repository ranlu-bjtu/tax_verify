import tempfile
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.ops_console import (
    build_subprocess_env,
    build_batch_command,
    build_existing_run_command,
    coverage_for_run,
    export_review,
    fallback_ops_status,
    latest_report,
    parse_tax_nos_text,
    review_items_for_run,
    powershell_command,
    summarize_run,
    update_review_item,
    unfinished_tax_nos,
)


def test_parse_tax_nos_text_deduplicates_common_separators():
    tax_nos = parse_tax_nos_text("911111111111111111\n922222222222222222,911111111111111111；933333333333333333")

    assert tax_nos == ["911111111111111111", "922222222222222222", "933333333333333333"]


def test_build_batch_command_wraps_existing_batch_script_without_credentials():
    with tempfile.TemporaryDirectory() as tmp:
        spec = build_batch_command(
            {
                "runId": "test_run",
                "mode": "full",
                "taxNos": "911111111111111111\n922222222222222222",
                "period": "202604",
                "enterprise": "蓝天之爱",
                "targets": "auto",
                "skipBrowser": True,
                "force": True,
            },
            output_dir=Path(tmp),
        )

        command = spec["command"]
        display = spec["displayCommand"]

        assert "batch_collect_verify.py" in command[1]
        assert "--verify" in command
        assert "--skip-browser" in command
        assert "--force" in command
        assert "--tax-no-file" in command
        assert "YDZ_PASSWORD" not in display
        assert "YDZ_USERNAME" not in display
        assert Path(spec["taxNoFile"]).read_text(encoding="utf-8").splitlines() == [
            "911111111111111111",
            "922222222222222222",
        ]


def test_ydz_credentials_are_passed_only_through_child_environment():
    env = build_subprocess_env({"ydzUsername": "test-user", "ydzPassword": "secret-password"})

    assert env["YDZ_USERNAME"] == "test-user"
    assert env["YDZ_PASSWORD"] == "secret-password"


def test_verify_existing_command_skips_collect():
    with tempfile.TemporaryDirectory() as tmp:
        spec = build_batch_command(
            {
                "runId": "test_verify",
                "mode": "verify_existing",
                "taxNos": "911111111111111111",
                "period": "202604",
                "enterprise": "蓝天之爱",
            },
            output_dir=Path(tmp),
        )

        assert "--skip-collect" in spec["command"]
        assert "--verify" in spec["command"]


def test_existing_run_command_reuses_state_period_and_enterprise():
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp) / "ops_existing"
        run_dir.mkdir()
        (run_dir / "state.json").write_text(
            '{"runId":"ops_existing","period":"202604","enterprise":"蓝天之爱","items":{"911":{"taxNo":"911"}}}',
            encoding="utf-8",
        )

        spec = build_existing_run_command(
            {"runId": "ops_existing"},
            ["911"],
            skip_collect=True,
            verify=True,
            output_dir=Path(tmp),
        )

        assert "--skip-collect" in spec["command"]
        assert "--verify" in spec["command"]
        assert "--period" in spec["command"]


def test_unfinished_tax_nos_excludes_completed_and_no_need():
    state = {
        "items": {
            "done": {"verify": {"status": "success"}, "collect": {}},
            "diff": {"verify": {"status": "completed_with_differences"}, "collect": {}},
            "noneed": {"verify": {"status": "skipped"}, "collect": {"status": "NO_NEED_COLLECTED"}},
            "manual": {"verify": {}, "collect": {"manualRequired": True}},
            "pending": {"verify": {}, "collect": {}},
        }
    }

    assert unfinished_tax_nos(state) == ["manual", "pending"]
    assert unfinished_tax_nos(state, include_manual=False) == ["pending"]


def test_fallback_ops_status_builds_progress_items():
    state = {
        "runId": "ops_status",
        "period": "202604",
        "enterprise": "蓝天之爱",
        "items": {
            "911": {
                "stage": "verifying",
                "collect": {"verifyTaskId": "task-1", "account": {"custName": "测试企业", "areaCode": "13"}},
                "verify": {},
            }
        },
    }

    status = fallback_ops_status(Path("."), state)

    assert status["runId"] == "ops_status"
    assert status["items"][0]["taxNo"] == "911"
    assert status["items"][0]["taskId"] == "task-1"


def test_powershell_command_quotes_spaces():
    command = powershell_command(["python", "scripts\\batch_collect_verify.py", "--enterprise", "蓝天之爱"])

    assert "'蓝天之爱'" in command


def test_summarize_and_find_latest_report():
    with tempfile.TemporaryDirectory() as tmp:
        output_dir = Path(tmp)
        first = output_dir / "ops_1"
        second = output_dir / "ops_2"
        first.mkdir()
        second.mkdir()
        (first / "batch_summary.html").write_text("first", encoding="utf-8")
        (second / "batch_summary.html").write_text("second", encoding="utf-8")
        (second / "batch_summary.csv").write_text(
            "taxNo,manualCategory,problemCount\n911,需人工介入,2\n",
            encoding="utf-8",
        )
        (second / "ops_review.json").write_text(
            '{"items":{"k1":{"reviewStatus":"处理中"},"k2":{"reviewStatus":"待处理"}}}',
            encoding="utf-8",
        )

        summary = summarize_run(second)
        latest = latest_report(output_dir)

        assert summary["statusLabel"] == "需处理"
        assert summary["manualRequired"] == 1
        assert summary["problemCount"] == 2
        assert summary["reviewedCount"] == 1
        assert latest == second / "batch_summary.html"


def test_coverage_for_run_writes_operator_coverage_files():
    with tempfile.TemporaryDirectory() as tmp:
        output_dir = Path(tmp)
        run_dir = output_dir / "ops_cov"
        run_dir.mkdir()
        (run_dir / "state.json").write_text(
            '{"runId":"ops_cov","period":"202604","enterprise":"test","items":{}}',
            encoding="utf-8",
        )

        payload = coverage_for_run("ops_cov", output_dir=output_dir)

        assert payload["runId"] == "ops_cov"
        assert (run_dir / "coverage_status.json").exists()
        assert (run_dir / "coverage_matrix.csv").exists()


def test_review_items_merge_details_and_saved_status():
    with tempfile.TemporaryDirectory() as tmp:
        output_dir = Path(tmp)
        run_dir = output_dir / "ops_review"
        run_dir.mkdir()
        (run_dir / "state.json").write_text(
            '{"runId":"ops_review","period":"202604","enterprise":"蓝天之爱","items":{}}',
            encoding="utf-8",
        )
        (run_dir / "batch_problem_details.csv").write_text(
            "taxNo,custName,taskId,region,taxTypeName,declarationStatus,formId,formName,fieldId,lineNo,rowName,columnName,status,apiRawValue,webRawValue,summaryPath\n"
            "911,测试企业,task-1,河北(13),增值税,已申报,vat_general_main,增值税纳税申报表（一般纳税人适用）,field_a,1,行名,,mismatch,1,2,output/reports/task-1/summary.html\n",
            encoding="utf-8-sig",
        )

        payload = review_items_for_run("ops_review", output_dir=output_dir)
        key = payload["items"][0]["key"]
        update_review_item("ops_review", key, {"reviewStatus": "处理中", "note": "已分派"}, output_dir=output_dir)
        payload = review_items_for_run("ops_review", output_dir=output_dir)

        assert payload["items"][0]["reviewStatus"] == "处理中"
        assert payload["items"][0]["note"] == "已分派"
        assert payload["items"][0]["reason"] == "接口值与网页值不一致"


def test_export_review_creates_operator_file():
    with tempfile.TemporaryDirectory() as tmp:
        output_dir = Path(tmp)
        run_dir = output_dir / "ops_export"
        run_dir.mkdir()
        (run_dir / "state.json").write_text(
            '{"runId":"ops_export","period":"202604","enterprise":"蓝天之爱","items":{}}',
            encoding="utf-8",
        )
        (run_dir / "batch_problem_details.csv").write_text(
            "taxNo,custName,taskId,region,taxTypeName,declarationStatus,formId,formName,fieldId,lineNo,rowName,columnName,status,apiRawValue,webRawValue,summaryPath\n"
            "911,测试企业,task-1,河北(13),增值税,已申报,vat_general_main,增值税纳税申报表（一般纳税人适用）,field_a,1,行名,,api_missing,,2,output/reports/task-1/summary.html\n",
            encoding="utf-8-sig",
        )

        path = export_review("ops_export", output_dir=output_dir)

        assert path.exists()
        assert path.suffix in {".xlsx", ".csv"}


if __name__ == "__main__":
    test_parse_tax_nos_text_deduplicates_common_separators()
    test_build_batch_command_wraps_existing_batch_script_without_credentials()
    test_ydz_credentials_are_passed_only_through_child_environment()
    test_verify_existing_command_skips_collect()
    test_existing_run_command_reuses_state_period_and_enterprise()
    test_unfinished_tax_nos_excludes_completed_and_no_need()
    test_fallback_ops_status_builds_progress_items()
    test_powershell_command_quotes_spaces()
    test_summarize_and_find_latest_report()
    test_coverage_for_run_writes_operator_coverage_files()
    test_review_items_merge_details_and_saved_status()
    test_export_review_creates_operator_file()
    print("All ops console tests passed!")
