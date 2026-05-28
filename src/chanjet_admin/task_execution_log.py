from __future__ import annotations

from typing import Any

import requests

TASK_EXECUTION_LOG_URL = (
    "https://data-task-management.chanapp.chanjet.com/"
    "pub-tax-management/tTaskExecutionLog/getPageListByTaskId"
)

CURRENT_PERIOD_LOG_TYPE = "\u6210\u529f\u4fdd\u5b58\u6570\u636e-\u662f\u5426\u662f\u5f53\u671f"


def fetch_task_execution_logs(task_id: str, timeout: int = 20) -> list[dict[str, Any]]:
    response = requests.get(TASK_EXECUTION_LOG_URL, params={"taskId": task_id}, timeout=timeout)
    response.raise_for_status()
    body = response.json()
    data = body.get("data") or []
    return data if isinstance(data, list) else []


def current_period_flag_from_logs(logs: list[dict[str, Any]], tax_code: str = "sz_zzs") -> bool | None:
    matched = [
        item
        for item in logs
        if str(item.get("logType") or "") == CURRENT_PERIOD_LOG_TYPE
        and (not tax_code or str(item.get("lsn") or "") == tax_code)
    ]
    if not matched:
        return None
    latest = sorted(
        enumerate(matched),
        key=lambda pair: (pair[1].get("createdStamp") or 0, pair[0]),
    )[-1][1]
    return parse_bool(latest.get("logInfo"))


def fetch_current_period_flag(task_id: str, tax_code: str = "sz_zzs", timeout: int = 20) -> bool | None:
    return current_period_flag_from_logs(fetch_task_execution_logs(task_id, timeout=timeout), tax_code=tax_code)


def parse_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text == "true":
        return True
    if text == "false":
        return False
    return None
