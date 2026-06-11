import sys
import tempfile
from datetime import datetime, timedelta
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


class CapturingPage:
    def __init__(self, url: str, result: dict):
        self.url = url
        self.result = result
        self.script = ""
        self.payload = None

    def evaluate(self, script, payload=None):
        self.script = str(script)
        self.payload = payload
        return self.result


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


class NoNeedSubmitApi(SubmitOnlyApi):
    def submit_collect_task(self, tax_no: str, period: str, tenant_id: int, area_code: str, tax_type_ids: list[int]):
        self.submitted.append((tax_no, period, tenant_id, area_code, tax_type_ids))
        return {
            "successful": True,
            "data": [
                {
                    "msg": "【企业所得税】本期无需申报，请核对财税设置是否需要申报相应税种！"
                }
            ],
        }


class CustomerWorkbenchFallbackApi(SubmitOnlyApi):
    def get_batch_list(self, tax_no: str, period: str, area_code: str):
        return {"data": []}

    def query_customer_workbench(self, tax_no: str):
        return {
            "data": {
                "custList": [
                    {
                        "taxNo": tax_no,
                        "custName": "Fallback Co",
                        "assocTenantId": "12345",
                        "id": "67890",
                        "taxiationArea": "31",
                    }
                ]
            }
        }


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


def test_ydz_api_sends_bearer_authorization_and_token_header():
    page = CapturingPage(
        "https://cloud.chanjet.com/ydzee/u/org/work.html#/home/gzt/batchDeclare",
        {"httpStatus": 200, "data": {"successful": True, "data": []}},
    )
    api = YdzApi(page)

    result = api.get_batch_list("91131102MA07X9YW6M", "202604")

    assert result["successful"] is True
    assert "'authorization': 'Bearer ' + iframeToken" in page.script
    assert "'token': ciaToken" in page.script
    assert "Yidaizhang login token is missing" in page.script


def test_ydz_api_reports_missing_login_token_before_http_error():
    page = CapturingPage(
        "https://cloud.chanjet.com/ydzee/u/org/work.html#/home/gzt/batchDeclare",
        {
            "clientError": "Yidaizhang login token is missing",
            "currentUrl": "https://cloud.chanjet.com/ydzee/u/org/work.html",
            "hasIframeToken": False,
            "hasCiaToken": False,
        },
    )
    api = YdzApi(page)

    try:
        api.get_batch_list("91131102MA07X9YW6M", "202604")
    except YdzApiError as exc:
        assert "Yidaizhang login token is missing" in str(exc)
    else:
        raise AssertionError("Expected YdzApiError")


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


def test_submit_collect_tax_no_uses_customer_workbench_when_batch_list_is_empty():
    api = CustomerWorkbenchFallbackApi()
    collector = YdzCollector(api, enterprise="test")

    result = collector.submit_collect_tax_no("91310115MA1HAHW684", "202605", force=True)

    assert result.submitted is True
    assert result.account is not None
    assert result.account.cust_name == "Fallback Co"
    assert result.account.assoc_tenant_id == 12345
    assert result.account.area_code == "31"
    assert result.account.raw["source"] == "customer_workbench_fallback"
    assert api.submitted[0][:4] == ("91310115MA1HAHW684", "202605", 12345, "31")


def test_submit_collect_tax_no_treats_no_need_warning_as_terminal():
    api = NoNeedSubmitApi()
    collector = YdzCollector(api, enterprise="test")

    result = collector.submit_collect_tax_no("91131102MA07X9YW6M", "202604", force=True)

    assert result.submitted is True
    assert result.status == "NO_NEED_COLLECTED"
    assert result.terminal is True
    assert result.manual_required is False
    assert result.errors == []


def test_default_collect_tax_types_exclude_social_insurance():
    api = SubmitOnlyApi()
    collector = YdzCollector(api, enterprise="test")

    collector.submit_collect_tax_no("91131102MA07X9YW6M", "202604", force=True)

    submitted_tax_type_ids = api.submitted[0][4]
    assert submitted_tax_type_ids == [1, 3, 2, 26, 29, 30, 31]
    assert 30 in submitted_tax_type_ids
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


def test_task_resolver_returns_none_when_no_success_task_is_ready():
    resolver = object.__new__(VerifyTaskResolver)
    tasks = [
        AdminTask("failure-new", "911", "202604", "3", "取数", "FAILURE", 300, {}),
        AdminTask("doing-old", "911", "202604", "3", "取数", "DOING", 100, {}),
        AdminTask("doing-new", "911", "202604", "3", "取数", "DOING", 200, {}),
        AdminTask("schedule-new", "911", "202604", "3", "取数", "SCHEDULE", 400, {}),
    ]

    assert resolver._select_task(tasks) is None
    assert resolver._select_tasks(tasks) == []


def test_task_resolver_rejects_old_task_after_fresh_submission():
    resolver = object.__new__(VerifyTaskResolver)
    submitted_at = datetime.now()
    old_stamp = int((submitted_at - timedelta(minutes=30)).timestamp() * 1000)
    fresh_stamp = int((submitted_at + timedelta(seconds=5)).timestamp() * 1000)
    tasks = [
        AdminTask("success-old", "911", "202604", "3", "取数", "SUCCESS", old_stamp, {}),
        AdminTask("success-fresh", "911", "202604", "3", "取数", "SUCCESS", fresh_stamp, {}),
    ]

    selected = resolver._select_task(tasks, submitted_at=submitted_at)

    assert selected is not None
    assert selected.task_id == "success-fresh"


def test_task_resolver_selects_all_fresh_success_tasks():
    resolver = object.__new__(VerifyTaskResolver)
    submitted_at = datetime.now()
    first_stamp = int((submitted_at + timedelta(seconds=3)).timestamp() * 1000)
    second_stamp = int((submitted_at + timedelta(seconds=4)).timestamp() * 1000)
    tasks = [
        AdminTask("success-a", "911", "202604", "3", "取数", "SUCCESS", first_stamp, {}),
        AdminTask("success-b", "911", "202604", "3", "取数", "SUCCESS", second_stamp, {}),
        AdminTask("failure-newer", "911", "202604", "3", "取数", "FAILURE", second_stamp + 1000, {}),
    ]

    selected = resolver._select_tasks(tasks, submitted_at=submitted_at)

    assert [task.task_id for task in selected] == ["success-b", "success-a"]


def test_task_resolver_returns_none_when_only_old_tasks_after_fresh_submission():
    resolver = object.__new__(VerifyTaskResolver)
    submitted_at = datetime.now()
    old_stamp = int((submitted_at - timedelta(minutes=30)).timestamp() * 1000)
    tasks = [
        AdminTask("success-old", "911", "202604", "3", "取数", "SUCCESS", old_stamp, {}),
    ]

    assert resolver._select_task(tasks, submitted_at=submitted_at) is None


if __name__ == "__main__":
    test_resolve_area_code_prefers_row_value()
    test_resolve_area_code_falls_back_to_tax_no_admin_code()
    test_collect_result_serializes_accountless_failure()
    test_ydz_api_rejects_public_home_before_fetch()
    test_ydz_api_sends_bearer_authorization_and_token_header()
    test_ydz_api_reports_missing_login_token_before_http_error()
    test_detects_period_window_block_warning()
    test_submit_collect_tax_no_does_not_wait_for_terminal_status()
    test_submit_collect_tax_no_uses_customer_workbench_when_batch_list_is_empty()
    test_submit_collect_tax_no_treats_no_need_warning_as_terminal()
    test_default_collect_tax_types_exclude_social_insurance()
    test_custom_collect_tax_types_filter_social_insurance()
    test_no_need_collected_is_terminal_without_manual_required()
    test_social_insurance_failure_is_ignored_not_manual_required()
    test_process_lock_can_be_reacquired_after_release()
    test_task_resolver_prefers_latest_success_over_newer_failure()
    test_task_resolver_returns_none_when_no_success_task_is_ready()
    test_task_resolver_rejects_old_task_after_fresh_submission()
    test_task_resolver_selects_all_fresh_success_tasks()
    test_task_resolver_returns_none_when_only_old_tasks_after_fresh_submission()
    print("All Yidaizhang collector tests passed!")
