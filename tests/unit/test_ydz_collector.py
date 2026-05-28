import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.ydz.api import YdzApi, YdzApiError
from src.ydz.collector import YdzCollector
from src.ydz.models import YdzCollectResult
from src.ydz.task_resolver import VerifyTaskResolver
from src.chanjet_admin.task_query import AdminTask
from src.runtime.process_lock import ProcessLock


class DummyApi:
    pass


class FakePage:
    def __init__(self, url: str):
        self.url = url
        self.evaluated = False

    def evaluate(self, *_args, **_kwargs):
        self.evaluated = True
        return {}


class SubmitOnlyApi:
    def __init__(self):
        self.submitted = []

    def get_batch_list(self, tax_no: str, period: str, area_code: str):
        return {
            "data": [
                {
                    "custName": "Test Co",
                    "assocTenantId": 1,
                    "id": 2,
                    "taxiationArea": "13",
                    "authStatusEnum": "AUTHORIZED",
                    "gatherInitStatusEnum": "COLLECTING",
                    "taxItemDetailList": [],
                }
            ]
        }

    def submit_collect_task(self, tax_no: str, period: str, tenant_id: int, area_code: str, tax_type_ids: list[int]):
        self.submitted.append((tax_no, period, tenant_id, area_code, tax_type_ids))
        return {"successful": True, "data": []}


class NoNeedApi(SubmitOnlyApi):
    def get_batch_list(self, tax_no: str, period: str, area_code: str):
        data = super().get_batch_list(tax_no, period, area_code)
        data["data"][0]["gatherInitStatusEnum"] = "NO_NEED_COLLECTED"
        return data


class SocialInsuranceFailureApi(SubmitOnlyApi):
    def get_batch_list(self, tax_no: str, period: str, area_code: str):
        data = super().get_batch_list(tax_no, period, area_code)
        data["data"][0]["gatherInitStatusEnum"] = "COLLECTING"
        data["data"][0]["taxItemDetailList"] = [
            {
                "taxTypeId": 40,
                "initStatusEnum": "COLLECTED_FAIL",
                "initJson": {"status": "FAILURE", "msg": "【社会保险费】暂不支持【取数】功能！"},
            }
        ]
        return data


def test_resolve_area_code_prefers_row_value():
    collector = YdzCollector(DummyApi(), enterprise="test")

    assert collector._resolve_area_code({"taxiationArea": "13"}, "91131102MA07X9YW6M") == "13"


def test_resolve_area_code_falls_back_to_tax_no_admin_code():
    collector = YdzCollector(DummyApi(), enterprise="test")

    assert collector._resolve_area_code({}, "91131102MA07X9YW6M") == "13"


def test_collect_result_serializes_accountless_failure():
    result = YdzCollectResult(
        tax_no="91131102MA07X9YW6M",
        period="202604",
        enterprise="test",
        manual_required=True,
        status="COLLECTED_FAIL",
    )
    result.errors.append("No account")

    payload = result.to_dict()

    assert payload["taxNo"] == "91131102MA07X9YW6M"
    assert payload["manualRequired"] is True
    assert payload["account"] is None
    assert payload["errors"] == ["No account"]


def test_ydz_api_rejects_public_home_before_fetch():
    page = FakePage("https://ydz.chanjet.com/?a=sztqwl&c=sztqwl")
    api = YdzApi(page)

    try:
        api.get_batch_list("91131102MA07X9YW6M", "202604")
    except YdzApiError as exc:
        assert "API context is not ready" in str(exc)
    else:
        raise AssertionError("Expected YdzApiError")

    assert page.evaluated is False


def test_detects_period_window_block_warning():
    collector = YdzCollector(DummyApi(), enterprise="test")

    assert collector._has_period_window_block([
        "2026年5月增值税的上期取数可以发起的期间范围为2026-06-01至2026-06-30，请在该期间内发起该任务。"
    ])


def test_submit_collect_tax_no_does_not_wait_for_terminal_status():
    api = SubmitOnlyApi()
    collector = YdzCollector(api, enterprise="test", poll_timeout=1)

    result = collector.submit_collect_tax_no("91131102MA07X9YW6M", "202604", force=True)

    assert result.submitted is True
    assert result.terminal is False
    assert result.status == "COLLECTING"
    assert result.submitted_at is not None
    assert api.submitted


def test_default_collect_tax_types_exclude_social_insurance():
    api = SubmitOnlyApi()
    collector = YdzCollector(api, enterprise="test")

    collector.submit_collect_tax_no("91131102MA07X9YW6M", "202604", force=True)

    submitted_tax_type_ids = api.submitted[0][4]
    assert submitted_tax_type_ids == [1, 3, 2, 26, 29, 31]
    assert 40 not in submitted_tax_type_ids


def test_custom_collect_tax_types_filter_social_insurance():
    api = SubmitOnlyApi()
    collector = YdzCollector(api, enterprise="test", tax_type_ids=[1, 30, 40, 48, 3])

    collector.submit_collect_tax_no("91131102MA07X9YW6M", "202604", force=True)

    assert api.submitted[0][4] == [1, 30, 48, 3]


def test_no_need_collected_is_terminal_without_manual_required():
    api = NoNeedApi()
    collector = YdzCollector(api, enterprise="test")
    result = YdzCollectResult(tax_no="91131102MA07X9YW6M", period="202604", enterprise="test", submitted=True)

    collector.refresh_collect_status(result)

    assert result.status == "NO_NEED_COLLECTED"
    assert result.terminal is True
    assert result.manual_required is False


def test_social_insurance_failure_is_ignored_not_manual_required():
    api = SocialInsuranceFailureApi()
    collector = YdzCollector(api, enterprise="test")
    result = YdzCollectResult(tax_no="91131102MA07X9YW6M", period="202604", enterprise="test", submitted=True)

    collector.refresh_collect_status(result)

    assert result.manual_required is False
    assert result.terminal is False
    assert result.status == "COLLECTING"
    assert result.errors == []
    assert result.ignored_tax_items
    assert result.ignored_tax_items[0]["taxTypeId"] == 40


def test_process_lock_can_be_reacquired_after_release():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "tax_browser.lock"
        with ProcessLock(path, timeout=1, owner={"kind": "test"}) as first:
            assert first.acquired is True
        with ProcessLock(path, timeout=1, owner={"kind": "test2"}) as second:
            assert second.acquired is True


def test_task_resolver_prefers_latest_success_over_newer_failure():
    resolver = object.__new__(VerifyTaskResolver)
    tasks = [
        AdminTask("failure-new", "911", "202604", "3", "取数", "FAILURE", 300, {}),
        AdminTask("success-old", "911", "202604", "3", "取数", "SUCCESS", 100, {}),
        AdminTask("success-new", "911", "202604", "3", "取数", "SUCCESS", 200, {}),
    ]

    selected = resolver._select_task(tasks)

    assert selected is not None
    assert selected.task_id == "success-new"


def test_task_resolver_uses_latest_doing_when_no_success():
    resolver = object.__new__(VerifyTaskResolver)
    tasks = [
        AdminTask("failure-new", "911", "202604", "3", "取数", "FAILURE", 300, {}),
        AdminTask("doing-old", "911", "202604", "3", "取数", "DOING", 100, {}),
        AdminTask("doing-new", "911", "202604", "3", "取数", "DOING", 200, {}),
    ]

    selected = resolver._select_task(tasks)

    assert selected is not None
    assert selected.task_id == "doing-new"


if __name__ == "__main__":
    test_resolve_area_code_prefers_row_value()
    test_resolve_area_code_falls_back_to_tax_no_admin_code()
    test_collect_result_serializes_accountless_failure()
    test_ydz_api_rejects_public_home_before_fetch()
    test_detects_period_window_block_warning()
    test_submit_collect_tax_no_does_not_wait_for_terminal_status()
    test_default_collect_tax_types_exclude_social_insurance()
    test_custom_collect_tax_types_filter_social_insurance()
    test_no_need_collected_is_terminal_without_manual_required()
    test_social_insurance_failure_is_ignored_not_manual_required()
    test_process_lock_can_be_reacquired_after_release()
    test_task_resolver_prefers_latest_success_over_newer_failure()
    test_task_resolver_uses_latest_doing_when_no_success()
    print("All Yidaizhang collector tests passed!")
