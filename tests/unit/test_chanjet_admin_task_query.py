from datetime import datetime
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import src.chanjet_admin.task_query as task_query
from src.chanjet_admin.auth import AdminAuthTokens
from src.chanjet_admin.task_query import ChanjetAdminTaskQuery
from src.chanjet_admin.task_query import PRIVACY_LOGIN_TYPE_FILTER


class FakePage:
    url = "https://public-manage.chanjet.com/taxserver#/taskManage/taxTaskList"

    def is_closed(self):
        return False

    def evaluate(self, _script):
        return {"authorization": "Bearer token", "token": "access-token"}


class FakeContext:
    pages = [FakePage()]


class FakeTokenProvider:
    def __init__(self):
        self.calls = []

    def get_tokens(self, force_refresh=False):
        self.calls.append(force_refresh)
        suffix = "refreshed" if force_refresh else "token"
        return AdminAuthTokens(authorization=f"Bearer {suffix}", token="access-token", source="test")


class FlakyTokenPage(FakePage):
    def __init__(self):
        self.calls = 0

    def evaluate(self, _script):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("Page.evaluate: Execution context was destroyed, most likely because of a navigation")
        return {"authorization": "Bearer refreshed", "token": "access-token"}

    def wait_for_timeout(self, _ms):
        return None

    def wait_for_load_state(self, *_args, **_kwargs):
        return None


class FlakyContext:
    def __init__(self, page):
        self.pages = [page]


class ForbiddenBackendPage(FakePage):
    def evaluate(self, script):
        if "document.body" in script:
            return "403 无权访问"
        return {"authorization": "", "token": ""}


class ReadyBackendPage(FakePage):
    def evaluate(self, script):
        if "document.body" in script:
            return "报税任务列表"
        return {"authorization": "Bearer ready", "token": "ready-token"}


class CountingTokenPage(FakePage):
    def __init__(self):
        self.calls = 0
        self.authorization = "Bearer token"

    def evaluate(self, _script):
        self.calls += 1
        return {"authorization": self.authorization, "token": "access-token"}


class FakeResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {
            "code": "200",
            "success": True,
            "data": {
                "content": [
                    {
                        "id": "task-1",
                        "taxNo": "911",
                        "period": "202604",
                        "tTaskTypeId": "3",
                        "taskTypeName": "取数",
                        "status": "SUCCESS",
                        "createdStamp": 1,
                        "taxPayerType": "NORMAL_TAXPAYER",
                        "taskTypeName": None,
                        "taskTaxRelVOList": [{"tTaxTypeId": "1", "taxTypeName": "增值税"}],
                    }
                ]
            },
        }


def test_query_tasks_sends_collect_status_and_tax_type_filters():
    captured = {}
    original_post = task_query.requests.post

    def fake_post(url, headers, json, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["payload"] = json
        captured["timeout"] = timeout
        return FakeResponse()

    try:
        task_query.requests.post = fake_post
        query = ChanjetAdminTaskQuery(FakeContext())
        tasks = query.find_collect_tasks_by_filters(
            start_time=datetime(2026, 5, 1),
            end_time=datetime(2026, 5, 26),
            tax_type_id=1,
            taxpayer_type="NORMAL_TAXPAYER",
            task_status="SUCCESS",
            login_type=PRIVACY_LOGIN_TYPE_FILTER,
            page_size=30,
        )
    finally:
        task_query.requests.post = original_post

    payload = captured["payload"]
    assert payload["taskCategorys"] == "2,3"
    assert payload["taskTypeId"] == "3"
    assert payload["taxTypeId"] == "1"
    assert payload["taxTypeIds"] == ["1"]
    assert payload["taxPayerType"] == "NORMAL_TAXPAYER"
    assert payload["status"] == "SUCCESS"
    assert payload["taskStatus"] == "SUCCESS"
    assert payload["mockFlag"] == 0
    assert payload["loginType"] == "YSHDL,DLYW-YSHDL,SDSRDX,DLYW-SDSRDX"
    assert payload["pageSize"] == 30
    assert tasks[0].task_id == "task-1"


def test_query_tasks_sends_backend_tax_id_filter_without_tax_type_filter():
    captured = {}
    original_post = task_query.requests.post

    class CbjResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "code": "200",
                "success": True,
                "data": {
                    "content": [
                        {
                            "id": "task-cbj",
                            "taxNo": "911",
                            "period": "202604",
                            "tTaskTypeId": "3",
                            "taskTypeName": None,
                            "status": "SUCCESS",
                            "createdStamp": 1,
                            "taxTypeId": 26,
                        }
                    ]
                },
            }

    def fake_post(url, headers, json, timeout):
        captured["payload"] = json
        return CbjResponse()

    try:
        task_query.requests.post = fake_post
        query = ChanjetAdminTaskQuery(FakeContext())
        tasks = query.find_collect_tasks_by_filters(
            start_time=datetime(2026, 5, 1),
            end_time=datetime(2026, 5, 26),
            tax_id=39,
            task_status="SUCCESS",
            page_size=30,
        )
    finally:
        task_query.requests.post = original_post

    payload = captured["payload"]
    assert payload["taxId"] == "39"
    assert payload["taskTypeId"] == "3"
    assert "taxTypeId" not in payload
    assert "taxTypeIds" not in payload
    assert [task.task_id for task in tasks] == ["task-cbj"]


def test_query_tasks_can_use_token_provider_without_browser_context():
    captured = {}
    original_post = task_query.requests.post
    provider = FakeTokenProvider()

    def fake_post(url, headers, json, timeout):
        captured["headers"] = headers
        return FakeResponse()

    try:
        task_query.requests.post = fake_post
        query = ChanjetAdminTaskQuery(token_provider=provider)
        tasks = query.find_collect_tasks_by_filters(
            start_time=datetime(2026, 5, 1),
            end_time=datetime(2026, 5, 26),
            task_status="SUCCESS",
        )
    finally:
        task_query.requests.post = original_post

    assert [task.task_id for task in tasks] == ["task-1"]
    assert captured["headers"]["authorization"] == "Bearer token"
    assert provider.calls == [False]


def test_query_tasks_refreshes_token_provider_when_backend_rejects_auth():
    original_post = task_query.requests.post
    provider = FakeTokenProvider()
    post_headers = []

    class UnauthorizedResponse:
        status_code = 401

        def raise_for_status(self):
            return None

        def json(self):
            return {"code": "401", "success": False, "msg": "token expired"}

    responses = [UnauthorizedResponse(), FakeResponse()]

    def fake_post(url, headers, json, timeout):
        post_headers.append(headers["authorization"])
        return responses.pop(0)

    try:
        task_query.requests.post = fake_post
        query = ChanjetAdminTaskQuery(token_provider=provider)
        tasks = query.find_collect_tasks_by_filters(
            start_time=datetime(2026, 5, 1),
            end_time=datetime(2026, 5, 26),
            task_status="SUCCESS",
        )
    finally:
        task_query.requests.post = original_post

    assert [task.task_id for task in tasks] == ["task-1"]
    assert provider.calls == [False, True]
    assert post_headers == ["Bearer token", "Bearer refreshed"]


def test_read_tokens_retries_when_public_manage_page_is_navigating():
    page = FlakyTokenPage()
    query = ChanjetAdminTaskQuery(FlakyContext(page))

    tokens = query._read_tokens(page)

    assert tokens == {"authorization": "Bearer refreshed", "token": "access-token"}
    assert page.calls >= 2


def test_ensure_page_prefers_token_page_over_stale_forbidden_page():
    forbidden = ForbiddenBackendPage()
    ready = ReadyBackendPage()
    query = ChanjetAdminTaskQuery(FlakyContext(forbidden))
    query.context.pages = [forbidden, ready]

    page = query._ensure_page()
    tokens = query._read_tokens(page)

    assert page is ready
    assert tokens == {"authorization": "Bearer ready", "token": "ready-token"}


def test_query_tasks_reuses_public_manage_tokens_for_same_query_instance():
    page = CountingTokenPage()
    calls = []
    original_post = task_query.requests.post

    def fake_post(url, headers, json, timeout):
        calls.append(headers["authorization"])
        return FakeResponse()

    try:
        task_query.requests.post = fake_post
        query = ChanjetAdminTaskQuery(FlakyContext(page))
        query.find_collect_tasks_by_filters(
            start_time=datetime(2026, 5, 1),
            end_time=datetime(2026, 5, 26),
            task_status="SUCCESS",
        )
        query.find_collect_tasks_by_filters(
            start_time=datetime(2026, 5, 1),
            end_time=datetime(2026, 5, 26),
            task_status="SUCCESS",
        )
    finally:
        task_query.requests.post = original_post

    assert page.calls >= 1
    assert calls == ["Bearer token", "Bearer token"]


def test_query_tasks_refreshes_cached_tokens_when_backend_rejects_auth():
    page = CountingTokenPage()
    post_headers = []
    original_post = task_query.requests.post

    def evaluate(_script):
        page.calls += 1
        page.authorization = "Bearer refreshed"
        return {"authorization": page.authorization, "token": "access-token"}

    class UnauthorizedResponse:
        status_code = 401

        def raise_for_status(self):
            return None

        def json(self):
            return {"code": "401", "success": False, "msg": "token expired"}

    responses = [UnauthorizedResponse(), FakeResponse()]

    def fake_post(url, headers, json, timeout):
        post_headers.append(headers["authorization"])
        return responses.pop(0)

    try:
        page.evaluate = evaluate
        task_query.requests.post = fake_post
        query = ChanjetAdminTaskQuery(FlakyContext(page))
        query._token_cache = {"authorization": "Bearer old", "token": "access-token"}
        tasks = query.find_collect_tasks_by_filters(
            start_time=datetime(2026, 5, 1),
            end_time=datetime(2026, 5, 26),
            task_status="SUCCESS",
        )
    finally:
        task_query.requests.post = original_post

    assert [task.task_id for task in tasks] == ["task-1"]
    assert page.calls >= 2
    assert post_headers == ["Bearer old", "Bearer refreshed"]


def test_query_tasks_scans_pages_and_filters_tax_type_client_side():
    calls = []
    original_post = task_query.requests.post

    class Response:
        def __init__(self, rows):
            self.rows = rows

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "code": "200",
                "success": True,
                "data": {"pageTotal": "2", "content": self.rows},
            }

    def fake_post(url, headers, json, timeout):
        calls.append(json)
        if json["pageNo"] == 1:
            return Response(
                [
                    {
                        "id": "task-vat",
                        "taxNo": "911",
                        "period": "202604",
                        "tTaskTypeId": "3",
                        "taskTypeName": "鍙栨暟",
                        "status": "SUCCESS",
                        "createdStamp": 1,
                        "taxPayerType": "SMALL_TAXPAYER",
                        "taskTypeName": None,
                        "taskTaxRelVOList": [{"tTaxTypeId": "1"}],
                    }
                ]
            )
        return Response(
            [
                {
                    "id": "task-cit",
                    "taxNo": "922",
                    "period": "202604",
                    "tTaskTypeId": "3",
                    "taskTypeName": "鍙栨暟",
                    "status": "SUCCESS",
                    "createdStamp": 2,
                    "taxPayerType": "NORMAL_TAXPAYER",
                    "taskTypeName": None,
                    "taskTaxRelVOList": [{"tTaxTypeId": "2"}],
                }
            ]
        )

    try:
        task_query.requests.post = fake_post
        query = ChanjetAdminTaskQuery(FakeContext())
        tasks = query.find_collect_tasks_by_filters(
            start_time=datetime(2026, 5, 1),
            end_time=datetime(2026, 5, 26),
            tax_type_id=2,
            task_status="SUCCESS",
            page_size=30,
        )
    finally:
        task_query.requests.post = original_post

    assert [call["pageNo"] for call in calls] == [1, 2]
    assert [task.task_id for task in tasks] == ["task-cit"]


def test_query_tasks_filters_taxpayer_type_client_side():
    original_post = task_query.requests.post

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "code": "200",
                "success": True,
                "data": {
                    "pageTotal": "1",
                    "content": [
                        {
                            "id": "task-general",
                            "taxNo": "911",
                            "period": "202604",
                            "tTaskTypeId": "3",
                            "taskTypeName": None,
                            "status": "SUCCESS",
                            "createdStamp": 1,
                            "taxPayerType": "NORMAL_TAXPAYER",
                            "taskTaxRelVOList": [{"tTaxTypeId": "1"}],
                        },
                        {
                            "id": "task-small",
                            "taxNo": "922",
                            "period": "202604",
                            "tTaskTypeId": "3",
                            "taskTypeName": None,
                            "status": "SUCCESS",
                            "createdStamp": 2,
                            "taxPayerType": "SMALL_TAXPAYER",
                            "taskTaxRelVOList": [{"tTaxTypeId": "1"}],
                        },
                    ],
                },
            }

    def fake_post(url, headers, json, timeout):
        return Response()

    try:
        task_query.requests.post = fake_post
        query = ChanjetAdminTaskQuery(FakeContext())
        tasks = query.find_collect_tasks_by_filters(
            start_time=datetime(2026, 5, 1),
            end_time=datetime(2026, 5, 26),
            tax_type_id=1,
            taxpayer_type="SMALL_TAXPAYER",
            task_status="SUCCESS",
            page_size=30,
        )
    finally:
        task_query.requests.post = original_post

    assert [task.task_id for task in tasks] == ["task-small"]


if __name__ == "__main__":
    test_query_tasks_sends_collect_status_and_tax_type_filters()
    test_query_tasks_sends_backend_tax_id_filter_without_tax_type_filter()
    test_query_tasks_can_use_token_provider_without_browser_context()
    test_query_tasks_refreshes_token_provider_when_backend_rejects_auth()
    test_read_tokens_retries_when_public_manage_page_is_navigating()
    test_ensure_page_prefers_token_page_over_stale_forbidden_page()
    test_query_tasks_reuses_public_manage_tokens_for_same_query_instance()
    test_query_tasks_refreshes_cached_tokens_when_backend_rejects_auth()
    test_query_tasks_scans_pages_and_filters_tax_type_client_side()
    test_query_tasks_filters_taxpayer_type_client_side()
    print("All Chanjet admin task query tests passed!")
