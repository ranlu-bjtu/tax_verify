from datetime import datetime
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import src.chanjet_admin.task_query as task_query
from src.chanjet_admin.task_query import ChanjetAdminTaskQuery


class FakePage:
    url = "https://public-manage.chanjet.com/taxserver#/taskManage/taxTaskList"

    def is_closed(self):
        return False

    def evaluate(self, _script):
        return {"authorization": "Bearer token", "token": "access-token"}


class FakeContext:
    pages = [FakePage()]


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
            task_status="SUCCESS",
            page_size=30,
        )
    finally:
        task_query.requests.post = original_post

    payload = captured["payload"]
    assert payload["taskTypeId"] == "3"
    assert payload["taxTypeId"] == "1"
    assert payload["taxTypeIds"] == ["1"]
    assert payload["status"] == "SUCCESS"
    assert payload["taskStatus"] == "SUCCESS"
    assert payload["pageSize"] == 30
    assert tasks[0].task_id == "task-1"


if __name__ == "__main__":
    test_query_tasks_sends_collect_status_and_tax_type_filters()
    print("All Chanjet admin task query tests passed!")
