import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.batch_collect_verify import (
    collect_failure_reason,
    derive_handling_info,
    has_verifiable_items,
    item_requests_cbj_verification,
    resolve_cbj_mode,
    safe_write_json_text,
    tail_error_reason,
)


def test_collect_failure_reason_prefers_timeout_over_submit_response_noise():
    collect = {
        "errors": ["Timed out waiting for collection terminal status; last status=COLLECTING."],
        "warnings": [
            "【企业所得税】本期无需申报，请核对财税设置是否需要申报相应税种！",
            "正在执行取数任务，请勿重复提交！",
        ],
        "taxItems": [],
    }

    reason = collect_failure_reason(collect)

    assert reason == "取数任务长时间未完成，当前仍为取数中。"
    assert "本期无需申报" not in reason
    assert "请勿重复提交" not in reason


def test_collect_failure_reason_skips_no_need_warning():
    collect = {
        "errors": [],
        "warnings": ["【增值税】本期无需申报，请核对财税设置是否需要申报相应税种！"],
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
                "message": "社会保险费取数失败，当前地区不支持自动取数。",
            }
        ],
    }

    assert collect_failure_reason(collect) == ""


def test_collect_failure_reason_prefers_specific_tax_failure_over_timeout():
    collect = {
        "errors": ["Timed out waiting for collection terminal status; last status=COLLECTING."],
        "warnings": ["【增值税】本期无需申报，请核对财税设置是否需要申报相应税种！"],
        "taxItems": [
            {
                "taxTypeId": 40,
                "initStatusEnum": "COLLECTED_FAIL",
                "status": "FAILURE",
                "message": "【社会保险费】暂不支持【取数】功能！（响应id：abc）",
            }
        ],
    }

    assert collect_failure_reason(collect) == "取数任务长时间未完成，当前仍为取数中。"


def test_manual_handling_reason_is_single_direct_reason():
    handling = derive_handling_info(
        {},
        {
            "status": "COLLECTING",
            "manualRequired": True,
            "errors": ["Timed out waiting for collection terminal status; last status=COLLECTING."],
            "warnings": ["正在执行取数任务，请勿重复提交！"],
            "taxItems": [],
        },
        {"status": "skipped"},
    )

    assert handling["manualCategory"] == "需人工介入"
    assert handling["manualReason"] == "取数任务长时间未完成，当前仍为取数中。"
    assert handling["manualAction"] == "在易代账任务列表确认取数是否仍在执行，必要时终止后重试。"


def test_cbj_auto_mode_uses_backend_for_personal_tax_item():
    item = {"coverageSupplementTargets": ["CBJ_PERSONAL:filed"], "collect": {"taxItems": [{"taxTypeId": 26}]}}

    assert resolve_cbj_mode("auto", item) == "backend"


def test_cbj_auto_mode_uses_annual_for_annual_tax_item():
    item = {"collect": {"taxItems": [{"taxTypeId": 31, "initStatusEnum": "COLLECTED"}]}}

    assert resolve_cbj_mode("auto", item) == "annual"


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


if __name__ == "__main__":
    test_collect_failure_reason_prefers_timeout_over_submit_response_noise()
    test_collect_failure_reason_skips_no_need_warning()
    test_collect_failure_reason_ignores_social_security_failure()
    test_collect_failure_reason_prefers_specific_tax_failure_over_timeout()
    test_manual_handling_reason_is_single_direct_reason()
    test_cbj_auto_mode_uses_backend_for_personal_tax_item()
    test_cbj_auto_mode_uses_annual_for_annual_tax_item()
    test_not_collected_cbj_tax_item_does_not_request_cbj_verification()
    test_safe_write_json_text_writes_valid_json_atomically()
    test_tail_error_reason_skips_benign_browser_shutdown_lines()
    test_rerun_verified_does_not_requeue_task_id_already_verified_this_run()
    print("All batch handling info tests passed!")
