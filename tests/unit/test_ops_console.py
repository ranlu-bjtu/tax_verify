import tempfile
import sys
import os
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.ops_console import (
    INDEX_HTML,
    build_backend_login_command,
    build_create_accountset_command,
    build_cit_a_accountset_precheck_command,
    build_privacy_phone_sync_command,
    build_subprocess_env,
    build_batch_command,
    build_existing_run_command,
    cit_a_source_candidate_rows,
    coverage_for_run,
    export_review,
    fallback_ops_status,
    infer_blocker_reason,
    job_status_for_run,
    latest_report,
    parse_tax_nos_text,
    pid_is_running,
    review_items_for_run,
    powershell_command,
    refresh_job_status,
    summarize_accountset_result_file,
    summarize_backend_login_result_file,
    summarize_privacy_phone_result_file,
    summarize_run,
    update_review_item,
    unfinished_tax_nos,
)


def test_parse_tax_nos_text_deduplicates_common_separators():
    tax_nos = parse_tax_nos_text("911111111111111111\n922222222222222222,911111111111111111；933333333333333333")

    assert tax_nos == ["911111111111111111", "922222222222222222", "933333333333333333"]


def test_pid_is_running_checks_without_signalling_current_process():
    assert pid_is_running(os.getpid()) is True
    assert pid_is_running(0) is False


def test_workbench_does_not_show_standalone_backend_login_form():
    assert 'id="backendLoginForm"' not in INDEX_HTML
    assert "登录报税后台" not in INDEX_HTML
    assert 'id="accountsetBackendUsername"' in INDEX_HTML
    assert 'id="accountsetBackendPassword"' in INDEX_HTML
    assert 'id="accountsetYdzAuthMode"' in INDEX_HTML
    assert "自动（账号密码优先）" in INDEX_HTML
    assert 'option value="browser"' in INDEX_HTML
    assert 'option value="password"' in INDEX_HTML


def test_workbench_has_manual_accountset_form():
    assert 'id="manualAccountsetForm"' in INDEX_HTML
    assert 'id="manualAccountsetTaxNo"' in INDEX_HTML
    assert 'id="manualAccountsetCustomerName"' in INDEX_HTML
    assert 'id="manualAccountsetLoginMethod"' in INDEX_HTML
    assert 'option value="SDSRDX"' in INDEX_HTML
    assert 'option value="DLYW-SDSRDX"' in INDEX_HTML
    assert "隐私号/手机号" in INDEX_HTML
    assert 'id="manualAccountsetPassword"' in INDEX_HTML
    assert 'id="manualAccountsetYdzAuthMode"' in INDEX_HTML
    assert "accountsetManualSource: true" in INDEX_HTML


def test_workbench_shows_cit_a_as_optional_small_period_coverage():
    assert 'value="CIT_A"' in INDEX_HTML
    assert 'value="CIT_A" checked' not in INDEX_HTML
    assert 'id="ydzSupplementWorkUrls"' not in INDEX_HTML
    assert "ydzSupplementWorkUrls" not in INDEX_HTML
    assert 'name="scanYdzEnterprises"' not in INDEX_HTML
    assert 'id="precheckCitAccountset"' not in INDEX_HTML
    assert "/api/precheck-cit-accountset" not in INDEX_HTML


def test_cit_a_accountset_precheck_uses_current_gap_candidates_only():
    state = {
        "runId": "coverage_run",
        "period": "202605",
        "coverageSupplement": {
            "missingKeys": ["CIT_A:filed", "CIT_A:unfiled"],
            "sourceReadiness": [
                {
                    "targetKey": "CIT_A:filed",
                    "backendMatchedTaskIds": ["filed-task"],
                },
                {
                    "targetKey": "CIT_A:unfiled",
                    "backendMatchedTaskIds": ["unfiled-task"],
                },
            ],
            "freshYdzRefresh": [
                {
                    "targetKey": "CIT_A:filed",
                    "taxNo": "91500105MAEQ3URL80",
                    "period": "202512",
                    "sourceTaskId": "filed-task",
                    "reason": "no_ydz_account_in_current_enterprise",
                }
            ],
        },
        "items": {
            "filed": {
                "collect": {
                    "taxNo": "91500105MAEQ3URL80",
                    "period": "202512",
                    "verifyTaskId": "filed-task",
                    "resolvedTask": {"coverageTarget": "CIT_A:filed", "taskId": "filed-task"},
                },
                "verify": {"reason": "getTaskCookie failed"},
            },
            "unfiled": {
                "collect": {
                    "taxNo": "91310115MA1HAHW684",
                    "period": "202603",
                    "verifyTaskId": "unfiled-task",
                    "resolvedTask": {"coverageTarget": "CIT_A:unfiled", "taskId": "unfiled-task"},
                },
                "verify": {"reason": "getTaskCookie failed"},
            },
            "old": {
                "collect": {
                    "taxNo": "911111111111111111",
                    "period": "202603",
                    "verifyTaskId": "old-task",
                    "resolvedTask": {"coverageTarget": "CIT_A:unfiled", "taskId": "old-task"},
                },
            },
        },
    }

    rows = cit_a_source_candidate_rows(state)

    assert [row["taxNo"] for row in rows] == ["91500105MAEQ3URL80", "91310115MA1HAHW684"]

    with tempfile.TemporaryDirectory() as batch_tmp, tempfile.TemporaryDirectory() as accountset_tmp:
        run_dir = Path(batch_tmp) / "coverage_run"
        run_dir.mkdir()
        (run_dir / "state.json").write_text(json.dumps(state), encoding="utf-8")

        spec = build_cit_a_accountset_precheck_command(
            {
                "sourceRunId": "coverage_run",
                "precheckRunId": "cit_precheck_test",
                "accountsetEnv": "prod",
                "accountsetYdzUsername": "prod-user",
                "accountsetYdzPassword": "prod-secret",
                "accountsetBackendUsername": "backend-user",
                "accountsetBackendPassword": "backend-secret",
            },
            batch_output_dir=Path(batch_tmp),
            output_dir=Path(accountset_tmp),
        )

        command = spec["command"]
        display = spec["displayCommand"]
        assert command[command.index("--env") + 1] == "prod"
        assert "--dry-run" in command
        assert "prod-secret" not in display
        assert "backend-secret" not in display
        assert Path(spec["taxNoFile"]).read_text(encoding="utf-8").splitlines() == [
            "91500105MAEQ3URL80",
            "91310115MA1HAHW684",
        ]


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
                "skipCoverageSupplement": True,
                "force": True,
                "chromePath": r"D:\Chrome\chrome.exe",
                "pluginPath": r"D:\EtaxPlugin",
                "userDataDir": r"D:\tax_profile",
            },
            output_dir=Path(tmp),
        )

        command = spec["command"]
        display = spec["displayCommand"]

        assert "batch_collect_verify.py" in command[1]
        assert "--verify" in command
        assert "--skip-browser" in command
        assert "--skip-coverage-supplement" in command
        assert "--force" in command
        assert command[command.index("--chrome-path") + 1] == r"D:\Chrome\chrome.exe"
        assert command[command.index("--plugin-path") + 1] == r"D:\EtaxPlugin"
        assert command[command.index("--user-data-dir") + 1] == r"D:\tax_profile"
        assert "--tax-no-file" in command
        assert "YDZ_PASSWORD" not in display
        assert "YDZ_USERNAME" not in display
        assert Path(spec["taxNoFile"]).read_text(encoding="utf-8").splitlines() == [
            "911111111111111111",
            "922222222222222222",
        ]


def test_build_create_accountset_command_uses_existing_customer_script_without_credentials():
    with tempfile.TemporaryDirectory() as tmp:
        spec = build_create_accountset_command(
            {
                "runId": "accountset_test",
                "accountsetEnv": "prod",
                "accountsetTaxNos": "911111111111111111\n922222222222222222,911111111111111111",
                "accountsetOpeningPeriod": "202501",
                "accountsetTaxpayerType": "SMALL_TAXPAYER",
                "accountsetIndustryId": "11079",
                "accountsetCdpPort": 9223,
                "accountsetSessionTimeout": 33,
                "accountsetLookbackDays": "30 180",
                "accountsetChromePath": r"D:\Chrome\chrome.exe",
                "accountsetYdzWorkUrl": "https://ydz.chanjet.com/",
                "accountsetYdzAuthMode": "token",
                "accountsetEnvFile": r"D:\secure\ydz.env",
                "accountsetDryRun": True,
                "accountsetNoLaunchChrome": True,
                "accountsetSkipAutoLogin": True,
            },
            output_dir=Path(tmp),
        )

        command = spec["command"]
        display = spec["displayCommand"]

        assert "ydz_create_customers.py" in command[1]
        assert command[command.index("--env") + 1] == "prod"
        assert command[command.index("--opening-period") + 1] == "202501"
        assert command[command.index("--taxpayer-type") + 1] == "SMALL_TAXPAYER"
        assert command[command.index("--industry-id") + 1] == "11079"
        assert command[command.index("--cdp-port") + 1] == "9223"
        assert command[command.index("--lookback-days") + 1] == "30,180"
        assert "--dry-run" in command
        assert "--no-launch-chrome" in command
        assert "--skip-auto-login" in command
        assert command[command.index("--ydz-auth-mode") + 1] == "token"
        assert command[command.index("--env-file") + 1] == r"D:\secure\ydz.env"
        assert "--output-json" in command
        assert "YDZ_PASSWORD" not in display
        assert "TAX_BACKEND_PASSWORD" not in display
        assert Path(spec["taxNoFile"]).read_text(encoding="utf-8").splitlines() == [
            "911111111111111111",
            "922222222222222222",
        ]


def test_build_create_accountset_command_accepts_password_auth_mode():
    with tempfile.TemporaryDirectory() as tmp:
        spec = build_create_accountset_command(
            {
                "runId": "accountset_password_mode",
                "accountsetEnv": "inte",
                "accountsetTaxNos": "911111111111111111",
                "accountsetYdzAuthMode": "password",
            },
            output_dir=Path(tmp),
        )

        command = spec["command"]

        assert command[command.index("--ydz-auth-mode") + 1] == "password"


def test_build_manual_create_accountset_command_uses_env_source_and_skips_backend_sync():
    with tempfile.TemporaryDirectory() as tmp:
        spec = build_create_accountset_command(
            {
                "runId": "accountset_manual_test",
                "accountsetManualSource": True,
                "accountsetEnv": "inte",
                "accountsetManualTaxNo": "91110116MAEETH8W2C",
                "accountsetManualCustomerName": "Manual Co",
                "accountsetManualAreaName": "Beijing",
                "accountsetManualLoginMethod": "DLYW-YSHDL",
                "accountsetManualProxyTaxNo": "91110116PROXY0001",
                "accountsetManualPrivacyNo": "15500000000",
                "accountsetManualPassword": "manual-secret",
                "accountsetOpeningPeriod": "202501",
                "accountsetTaxpayerType": "SMALL_TAXPAYER",
                "accountsetIndustryId": "11079",
            },
            output_dir=Path(tmp),
        )

        command = spec["command"]
        display = spec["displayCommand"]

        assert "ydz_create_customers.py" in command[1]
        assert command[command.index("--env") + 1] == "inte"
        assert "--manual-source-env" in command
        assert "--skip-privacy-phone-sync" in command
        assert "manual-secret" not in display
        assert "15500000000" not in display
        assert "91110116PROXY0001" not in display
        assert Path(spec["taxNoFile"]).read_text(encoding="utf-8").splitlines() == [
            "91110116MAEETH8W2C",
        ]


def test_build_backend_login_command_runs_login_only_without_credentials_in_display():
    with tempfile.TemporaryDirectory() as tmp:
        spec = build_backend_login_command(
            {
                "runId": "backend_login_test",
                "backendLoginEnv": "inte",
                "backendCdpPort": 9224,
                "backendSessionTimeout": 45,
                "backendChromePath": r"D:\Chrome\chrome.exe",
                "backendEnvFile": r"D:\secure\backend.env",
                "backendNoLaunchChrome": True,
                "backendUsername": "backend-user",
                "backendPassword": "backend-secret",
            },
            output_dir=Path(tmp),
        )

        command = spec["command"]
        display = spec["displayCommand"]

        assert "ydz_create_customers.py" in command[1]
        assert "--login-only" in command
        assert command[command.index("--login-target") + 1] == "backend"
        assert command[command.index("--env") + 1] == "inte"
        assert command[command.index("--cdp-port") + 1] == "9224"
        assert command[command.index("--session-timeout") + 1] == "45"
        assert command[command.index("--env-file") + 1] == r"D:\secure\backend.env"
        assert "--no-launch-chrome" in command
        assert "backend-secret" not in display
        assert "TAX_BACKEND_PASSWORD" not in display
        assert Path(spec["outputJson"]).name == "backend_login_status.json"


def test_build_privacy_phone_sync_command_uses_sync_script_without_credentials():
    with tempfile.TemporaryDirectory() as tmp:
        spec = build_privacy_phone_sync_command(
            {
                "runId": "privacy_phone_test",
                "privacyPhones": "15500000001\n15500000002,15500000001",
                "privacyPhoneCdpPort": 9225,
                "privacyPhoneSessionTimeout": 60,
                "privacyPhoneChromePath": r"D:\Chrome\chrome.exe",
                "privacyPhoneEnvFile": r"D:\secure\backend.env",
                "privacyPhoneDryRun": True,
                "privacyPhoneNoLaunchChrome": True,
                "backendUsername": "backend-user",
                "backendPassword": "backend-secret",
            },
            output_dir=Path(tmp),
        )

        command = spec["command"]
        display = spec["displayCommand"]

        assert "sync_privacy_phone.py" in command[1]
        assert command[command.index("--cdp-port") + 1] == "9225"
        assert command[command.index("--session-timeout") + 1] == "60"
        assert command[command.index("--env-file") + 1] == r"D:\secure\backend.env"
        assert "--dry-run" in command
        assert "--no-launch-chrome" in command
        assert "backend-secret" not in display
        assert "TAX_BACKEND_PASSWORD" not in display
        assert Path(spec["privatePhoneFile"]).read_text(encoding="utf-8").splitlines() == [
            "15500000001",
            "15500000002",
        ]
        assert Path(spec["outputJson"]).name == "privacy_phone_summary.json"


def test_ydz_credentials_are_passed_only_through_child_environment():
    env = build_subprocess_env({"ydzUsername": "test-user", "ydzPassword": "secret-password"})

    assert env["YDZ_USERNAME"] == "test-user"
    assert env["YDZ_PASSWORD"] == "secret-password"
    assert env["NODE_NO_WARNINGS"] == "1"


def test_cit_a_work_urls_are_passed_only_through_child_environment():
    work_urls = "https://cloud.chanjet.com/ydzee/u1/o1/work.html#/home"

    env = build_subprocess_env({"ydzSupplementWorkUrls": work_urls})

    assert env["YDZ_SUPPLEMENT_WORK_URLS"] == work_urls


def test_accountset_credentials_are_passed_to_environment_specific_child_vars():
    env = build_subprocess_env(
        {
            "accountsetEnv": "prod",
            "accountsetYdzUsername": "prod-user",
            "accountsetYdzPassword": "prod-secret",
            "accountsetYdzEnterprise": "prod-enterprise",
            "accountsetYdzWorkUrl": "https://cloud.chanjet.com/ydzee/work.html",
            "accountsetBackendUsername": "backend-user",
            "accountsetBackendPassword": "backend-secret",
        }
    )

    assert env["YDZ_PROD_USERNAME"] == "prod-user"
    assert env["YDZ_PROD_PASSWORD"] == "prod-secret"
    assert env["YDZ_PROD_ENTERPRISE"] == "prod-enterprise"
    assert env["YDZ_PROD_WORK_URL"] == "https://cloud.chanjet.com/ydzee/work.html"
    assert "YDZ_INTE_USERNAME" not in env or env["YDZ_INTE_USERNAME"] != "prod-user"
    assert env["TAX_BACKEND_USERNAME"] == "backend-user"
    assert env["TAX_BACKEND_PASSWORD"] == "backend-secret"


def test_manual_accountset_source_is_passed_to_child_environment():
    env = build_subprocess_env(
        {
            "accountsetManualSource": True,
            "accountsetEnv": "inte",
            "accountsetManualTaxNo": "91110116maeeth8w2c",
            "accountsetManualCustomerName": "Manual Co",
            "accountsetManualAreaName": "Beijing",
            "accountsetManualLoginMethod": "税局隐私号-代理登录",
            "accountsetManualProxyTaxNo": "91110116PROXY0001",
            "accountsetManualPrivacyNo": "15500000000",
            "accountsetManualPassword": "manual-secret",
        }
    )

    assert env["YDZ_MANUAL_TAX_NO"] == "91110116MAEETH8W2C"
    assert env["YDZ_MANUAL_CUSTOMER_NAME"] == "Manual Co"
    assert env["YDZ_MANUAL_AREA_NAME"] == "Beijing"
    assert env["YDZ_MANUAL_LOGIN_METHOD"] == "DLYW-YSHDL"
    assert env["YDZ_MANUAL_PROXY_TAX_NO"] == "91110116PROXY0001"
    assert env["YDZ_MANUAL_PRIVACY_NO"] == "15500000000"
    assert env["YDZ_MANUAL_PASSWORD"] == "manual-secret"


def test_manual_captcha_accountset_source_is_passed_to_child_environment():
    env = build_subprocess_env(
        {
            "accountsetManualSource": True,
            "accountsetEnv": "inte",
            "accountsetManualTaxNo": "91110116maeeth8w2c",
            "accountsetManualCustomerName": "Manual Co",
            "accountsetManualAreaName": "Beijing",
            "accountsetManualLoginMethod": "税局手工录入验证码-代理登录",
            "accountsetManualProxyTaxNo": "91110116PROXY0001",
            "accountsetManualPrivacyNo": "15500000000",
            "accountsetManualPassword": "manual-secret",
        }
    )

    assert env["YDZ_MANUAL_LOGIN_METHOD"] == "DLYW-SDSRDX"
    assert env["YDZ_MANUAL_PROXY_TAX_NO"] == "91110116PROXY0001"
    assert env["YDZ_MANUAL_PRIVACY_NO"] == "15500000000"
    assert env["YDZ_MANUAL_PASSWORD"] == "manual-secret"


def test_backend_login_credentials_are_passed_only_through_child_environment():
    env = build_subprocess_env(
        {
            "backendUsername": "backend-user",
            "backendPassword": "backend-secret",
            "backendUrl": "https://public-manage.example.test/taxserver#/taskManage/taxTaskList",
        }
    )

    assert env["TAX_BACKEND_USERNAME"] == "backend-user"
    assert env["TAX_BACKEND_PASSWORD"] == "backend-secret"
    assert env["TAX_BACKEND_URL"] == "https://public-manage.example.test/taxserver#/taskManage/taxTaskList"


def test_summarize_backend_login_result_file_reports_ready_without_secrets():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "backend_login_status.json"
        path.write_text(
            '{"mode":"login","target":"backend","backendReady":true,"ready":true}',
            encoding="utf-8",
        )

        summary = summarize_backend_login_result_file(path)

        assert summary["backendReady"] is True
        assert summary["problemCount"] == 0
        assert summary["manualRequired"] == 0
        assert "password" not in str(summary).lower()


def test_summarize_privacy_phone_result_file_reports_failed_items():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "privacy_phone_summary.json"
        path.write_text(
            '[{"privatePhone":"15500000001","status":"OK"},'
            '{"privatePhone":"15500000002","status":"NOT_FOUND","errors":["missing"]}]',
            encoding="utf-8",
        )

        summary = summarize_privacy_phone_result_file(path)

        assert summary["totalTaxNos"] == 2
        assert summary["manualRequired"] == 1
        assert summary["problemCount"] == 1
        assert len(summary["privacyPhoneResults"]) == 2


def test_summarize_privacy_phone_result_file_treats_integration_prepare_as_success():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "privacy_phone_summary.json"
        path.write_text(
            '[{"privatePhone":"15500000003","status":"PULLED","inteSummaryCount":1},'
            '{"privatePhone":"15500000001","status":"EXISTS","inteSummaryCount":1}]',
            encoding="utf-8",
        )

        summary = summarize_privacy_phone_result_file(path)

        assert summary["resultLabel"] == "已完成"
        assert summary["totalTaxNos"] == 2
        assert summary["manualRequired"] == 0
        assert summary["problemCount"] == 0


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


def test_existing_run_command_can_skip_coverage_supplement():
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp) / "ops_existing"
        run_dir.mkdir()
        (run_dir / "state.json").write_text(
            '{"runId":"ops_existing","period":"202604","enterprise":"test","items":{"911":{"taxNo":"911"}}}',
            encoding="utf-8",
        )

        spec = build_existing_run_command(
            {"runId": "ops_existing", "skipCoverageSupplement": True},
            ["911"],
            skip_collect=True,
            verify=True,
            output_dir=Path(tmp),
        )

        assert "--skip-coverage-supplement" in spec["command"]


def test_batch_and_existing_run_command_can_scan_ydz_enterprises_for_cit_sources():
    with tempfile.TemporaryDirectory() as tmp:
        batch = build_batch_command(
            {
                "runId": "ops_scan",
                "mode": "full",
                "taxNos": "911111111111111111",
                "period": "202604",
                "enterprise": "test",
                "scanYdzEnterprises": True,
            },
            output_dir=Path(tmp),
        )
        run_dir = Path(tmp) / "ops_existing_scan"
        run_dir.mkdir()
        (run_dir / "state.json").write_text(
            '{"runId":"ops_existing_scan","period":"202604","enterprise":"test","items":{"911":{"taxNo":"911"}}}',
            encoding="utf-8",
        )
        existing = build_existing_run_command(
            {"runId": "ops_existing_scan", "scanYdzEnterprises": True},
            ["911"],
            skip_collect=True,
            verify=True,
            output_dir=Path(tmp),
        )

        for spec in (batch, existing):
            command = spec["command"]
            display = spec["displayCommand"]
            assert "--coverage-supplement-refresh-cit-from-ydz" in command
            assert "--coverage-supplement-scan-ydz-enterprises" in command
            assert "YDZ_PASSWORD" not in display
            assert "YDZ_USERNAME" not in display


def test_batch_and_existing_run_command_use_cit_work_url_without_exposing_it():
    work_url = "https://cloud.chanjet.com/ydzee/u1/o1/work.html#/home"
    with tempfile.TemporaryDirectory() as tmp:
        batch = build_batch_command(
            {
                "runId": "ops_work_url",
                "mode": "full",
                "taxNos": "911111111111111111",
                "period": "202604",
                "enterprise": "test",
                "ydzSupplementWorkUrls": work_url,
            },
            output_dir=Path(tmp),
        )
        run_dir = Path(tmp) / "ops_existing_work_url"
        run_dir.mkdir()
        (run_dir / "state.json").write_text(
            '{"runId":"ops_existing_work_url","period":"202604","enterprise":"test","items":{"911":{"taxNo":"911"}}}',
            encoding="utf-8",
        )
        existing = build_existing_run_command(
            {"runId": "ops_existing_work_url", "ydzSupplementWorkUrls": work_url},
            ["911"],
            skip_collect=True,
            verify=True,
            output_dir=Path(tmp),
        )

        for spec in (batch, existing):
            command = spec["command"]
            display = spec["displayCommand"]
            assert "--coverage-supplement-refresh-cit-from-ydz" in command
            assert "--coverage-supplement-scan-ydz-enterprises" not in command
            assert work_url not in command
            assert work_url not in display


def test_batch_command_passes_selected_coverage_tax_types():
    with tempfile.TemporaryDirectory() as tmp:
        spec = build_batch_command(
            {
                "runId": "test_coverage_filter",
                "mode": "full",
                "taxNos": "911111111111111111",
                "period": "202604",
                "enterprise": "钃濆ぉ涔嬬埍",
                "coverageTaxTypes": ["CONSUMPTION_TAX", "VAT_GENERAL"],
                "coverageCollectStatuses": ["collected"],
            },
            output_dir=Path(tmp),
        )

        command = spec["command"]
        value = command[command.index("--coverage-tax-types") + 1]
        status_value = command[command.index("--coverage-collect-statuses") + 1]
        assert value == "CONSUMPTION_TAX,VAT_GENERAL"
        assert status_value == "collected"


def test_batch_command_default_coverage_excludes_cit_a_for_small_period():
    with tempfile.TemporaryDirectory() as tmp:
        spec = build_batch_command(
            {
                "runId": "test_default_small_period",
                "mode": "full",
                "taxNos": "911111111111111111",
                "period": "202604",
                "enterprise": "蓝天之爱",
            },
            output_dir=Path(tmp),
        )

        command = spec["command"]
        value = command[command.index("--coverage-tax-types") + 1]
        assert "CIT_A" not in value.split(",")
        assert "VAT_GENERAL" in value.split(",")
        assert "CBJ_ANNUAL" in value.split(",")


def test_batch_command_can_explicitly_include_cit_a_when_selected():
    with tempfile.TemporaryDirectory() as tmp:
        spec = build_batch_command(
            {
                "runId": "test_optional_cit_a",
                "mode": "full",
                "taxNos": "911111111111111111",
                "period": "202604",
                "enterprise": "蓝天之爱",
                "coverageTaxTypes": ["CIT_A", "VAT_GENERAL"],
            },
            output_dir=Path(tmp),
        )

        command = spec["command"]
        value = command[command.index("--coverage-tax-types") + 1]
        assert value == "CIT_A,VAT_GENERAL"


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


def test_infer_blocker_reason_identifies_pending_tax_login_job():
    text = "您之前执行过 进税局(2076614043783903619) 操作并且暂未完成，请您耐心等待"

    reason = infer_blocker_reason(text)

    assert reason is not None
    assert "已有进税局任务未完成" in reason["reason"]
    assert "2076614043783903619" in reason["reason"]


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
        os.utime(first, (1, 1))
        os.utime(second, (2, 2))

        summary = summarize_run(second)
        latest = latest_report(output_dir)

        assert summary["statusLabel"] == "需处理"
        assert summary["manualRequired"] == 1
        assert summary["problemCount"] == 2
        assert summary["reviewedCount"] == 1
        assert latest == second / "batch_summary.html"


def test_refresh_job_status_exposes_operator_completion_summary():
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp) / "ops_done"
        run_dir.mkdir()
        (run_dir / "batch_summary.html").write_text("done", encoding="utf-8")
        (run_dir / "batch_summary.csv").write_text(
            "taxNo,manualCategory,problemCount\n"
            "911,,0\n"
            "922,需人工介入,3\n",
            encoding="utf-8-sig",
        )
        log_path = run_dir / "job.log"
        log_path.write_text("batch finished", encoding="utf-8")

        job = refresh_job_status(
            {
                "runId": "ops_done",
                "status": "success",
                "startedAt": "2026-05-29T10:00:00",
                "finishedAt": "2026-05-29T10:02:05",
                "runDir": str(run_dir),
                "logPath": str(log_path),
            }
        )

        assert job["statusLabel"] == "已完成"
        assert job["resultLabel"] == "需处理"
        assert job["totalTaxNos"] == 2
        assert job["manualRequired"] == 1
        assert job["problemCount"] == 3
        assert job["durationText"] == "2分5秒"
        assert "batch finished" in job["logTail"]


def test_refresh_job_status_exposes_accountset_completion_summary():
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp) / "accountset_done"
        run_dir.mkdir()
        summary_path = run_dir / "accountset_summary.json"
        summary_path.write_text(
            '[{"taxNo":"911","status":"OK","name":"测试企业","custId":"c1","errors":[]},'
            '{"taxNo":"922","status":"PARTIAL","name":"待处理企业","custId":"c2","errors":["tax info mismatch"]}]',
            encoding="utf-8",
        )
        log_path = run_dir / "job.log"
        log_path.write_text("accountset finished", encoding="utf-8")

        job = refresh_job_status(
            {
                "runId": "accountset_done",
                "status": "success",
                "startedAt": "2026-06-08T10:00:00",
                "finishedAt": "2026-06-08T10:00:09",
                "runDir": str(run_dir),
                "logPath": str(log_path),
                "summaryPath": str(summary_path),
                "jobType": "accountset",
            }
        )

        assert job["resultLabel"] == "需处理"
        assert job["totalTaxNos"] == 2
        assert job["manualRequired"] == 1
        assert job["problemCount"] == 1
        assert len(job["accountsetResults"]) == 2
        assert job["durationText"] == "9秒"
        assert "accountset finished" in job["logTail"]


def test_refresh_job_status_marks_running_accountset_manual_verification_from_log():
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp) / "accountset_slider"
        run_dir.mkdir()
        log_path = run_dir / "job.log"
        log_path.write_text(
            "WARNING MANUAL_VERIFICATION_REQUIRED ydz env=inte reason=password_login_slider\n",
            encoding="utf-8",
        )

        job = refresh_job_status(
            {
                "runId": "accountset_slider",
                "pid": os.getpid(),
                "status": "running",
                "startedAt": "2026-06-09T10:00:00",
                "runDir": str(run_dir),
                "logPath": str(log_path),
                "summaryPath": str(run_dir / "accountset_summary.json"),
                "jobType": "accountset",
            }
        )

        assert job["status"] == "running"
        assert job["statusLabel"] == "需人工验证"
        assert job["resultLabel"] == "等待易代账滑块"
        assert job["manualRequired"] == 1
        assert job["problemCount"] == 0
        assert "完成易代账滑块" in job["operatorAction"]


def test_refresh_job_status_marks_failed_accountset_slider_timeout_from_log():
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp) / "accountset_slider_failed"
        run_dir.mkdir()
        log_path = run_dir / "job.log"
        log_path.write_text(
            "WARNING MANUAL_VERIFICATION_REQUIRED ydz env=inte reason=password_login_slider\nLogin session is not ready.\n",
            encoding="utf-8",
        )

        job = refresh_job_status(
            {
                "runId": "accountset_slider_failed",
                "pid": 0,
                "status": "failed",
                "startedAt": "2026-06-09T10:00:00",
                "finishedAt": "2026-06-09T10:02:00",
                "runDir": str(run_dir),
                "logPath": str(log_path),
                "summaryPath": str(run_dir / "accountset_summary.json"),
                "jobType": "accountset",
            }
        )

        assert job["statusLabel"] == "已失败"
        assert job["resultLabel"] == "滑块验证未完成"
        assert job["manualRequired"] == 1
        assert job["problemCount"] == 1


def test_summarize_accountset_result_file_marks_dry_run():
    with tempfile.TemporaryDirectory() as tmp:
        summary_path = Path(tmp) / "accountset_summary.json"
        summary_path.write_text(
            '[{"taxNo":"911","status":"DRY_RUN","action":"would_create","errors":[]}]',
            encoding="utf-8",
        )

        summary = summarize_accountset_result_file(summary_path)

        assert summary["resultLabel"] == "预检查完成"
        assert summary["totalTaxNos"] == 1
        assert summary["manualRequired"] == 0


def test_coverage_for_run_writes_operator_coverage_files():
    with tempfile.TemporaryDirectory() as tmp:
        output_dir = Path(tmp)
        run_dir = output_dir / "ops_cov"
        run_dir.mkdir()
        (run_dir / "state.json").write_text(
            '{"runId":"ops_cov","period":"202604","enterprise":"test","coverageTaxTypes":["CONSUMPTION_TAX"],"items":{}}',
            encoding="utf-8",
        )

        payload = coverage_for_run("ops_cov", output_dir=output_dir)

        assert payload["runId"] == "ops_cov"
        assert payload["summary"]["totalTargets"] == 2
        assert {target["taxType"] for target in payload["targets"]} == {"CONSUMPTION_TAX"}
        assert (run_dir / "coverage_status.json").exists()
        assert (run_dir / "coverage_matrix.csv").exists()


def test_missing_run_state_returns_safe_operator_payloads():
    with tempfile.TemporaryDirectory() as tmp:
        output_dir = Path(tmp)
        run_dir = output_dir / "ops_missing"
        run_dir.mkdir()

        status = job_status_for_run("ops_missing", output_dir=output_dir)
        coverage = coverage_for_run("ops_missing", output_dir=output_dir)
        review = review_items_for_run("ops_missing", output_dir=output_dir)

        assert status["status"] == "missing"
        assert status["items"] == []
        assert coverage["supplement"]["status"] == "missing"
        assert coverage["targets"] == []
        assert review["items"] == []


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
    test_pid_is_running_checks_without_signalling_current_process()
    test_workbench_does_not_show_standalone_backend_login_form()
    test_workbench_has_manual_accountset_form()
    test_workbench_shows_cit_a_as_optional_small_period_coverage()
    test_cit_a_accountset_precheck_uses_current_gap_candidates_only()
    test_build_batch_command_wraps_existing_batch_script_without_credentials()
    test_build_create_accountset_command_uses_existing_customer_script_without_credentials()
    test_build_manual_create_accountset_command_uses_env_source_and_skips_backend_sync()
    test_build_backend_login_command_runs_login_only_without_credentials_in_display()
    test_ydz_credentials_are_passed_only_through_child_environment()
    test_manual_accountset_source_is_passed_to_child_environment()
    test_manual_captcha_accountset_source_is_passed_to_child_environment()
    test_backend_login_credentials_are_passed_only_through_child_environment()
    test_verify_existing_command_skips_collect()
    test_batch_command_passes_selected_coverage_tax_types()
    test_batch_command_default_coverage_excludes_cit_a_for_small_period()
    test_batch_command_can_explicitly_include_cit_a_when_selected()
    test_existing_run_command_reuses_state_period_and_enterprise()
    test_infer_blocker_reason_identifies_pending_tax_login_job()
    test_unfinished_tax_nos_excludes_completed_and_no_need()
    test_fallback_ops_status_builds_progress_items()
    test_powershell_command_quotes_spaces()
    test_summarize_and_find_latest_report()
    test_refresh_job_status_exposes_operator_completion_summary()
    test_refresh_job_status_exposes_accountset_completion_summary()
    test_refresh_job_status_marks_running_accountset_manual_verification_from_log()
    test_refresh_job_status_marks_failed_accountset_slider_timeout_from_log()
    test_summarize_accountset_result_file_marks_dry_run()
    test_summarize_backend_login_result_file_reports_ready_without_secrets()
    test_summarize_privacy_phone_result_file_reports_failed_items()
    test_summarize_privacy_phone_result_file_treats_integration_prepare_as_success()
    test_existing_run_command_can_skip_coverage_supplement()
    test_batch_and_existing_run_command_can_scan_ydz_enterprises_for_cit_sources()
    test_batch_and_existing_run_command_use_cit_work_url_without_exposing_it()
    test_coverage_for_run_writes_operator_coverage_files()
    test_missing_run_state_returns_safe_operator_payloads()
    test_review_items_merge_details_and_saved_status()
    test_export_review_creates_operator_file()
    print("All ops console tests passed!")
