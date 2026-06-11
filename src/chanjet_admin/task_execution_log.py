from __future__ import annotations

from typing import Any

import requests

TASK_EXECUTION_LOG_URL = (
    "https://data-task-management.chanapp.chanjet.com/"
    "pub-tax-management/tTaskExecutionLog/getPageListByTaskId"
)

CURRENT_PERIOD_LOG_TYPE = "\u6210\u529f\u4fdd\u5b58\u6570\u636e-\u662f\u5426\u662f\u5f53\u671f"
CBJ_TASK_RESULT_LOG_TYPE = "\u6b8b\u4fdd\u91d1\u4efb\u52a1\u8fd4\u56de\u7ed3\u679c"
CBJ_ANNUAL_MODE_MARKERS = (
    "\u6570\u636e\u5e93\u672a\u67e5\u8be2\u5230\u8fd4\u56de\u6570\u636e",
    "\u8c03\u7528\u6c47\u7b97\u6e05\u7f34\u53d6\u6570\u63a5\u53e3",
    "\u6c47\u7b97\u6e05\u7f34\u53d6\u6570\u63a5\u53e3",
)
CBJ_PERSONAL_MODE_MARKERS = (
    "\u4e2a\u7a0e",
    "\u4e2a\u4eba\u6240\u5f97\u7a0e",
    "\u7533\u62a5\u6708\u4efd\u6c47\u603b",
    "\u7533\u62a5\u4eba\u6b21\u6c47\u603b",
    "\u7533\u62a5\u4eba\u6b21=\u7533\u62a5\u4eba\u6570\u6c47\u603b",
    "personNum",
    "personNumSum",
    "monthNumSum",
    "amountSum",
)


def fetch_task_execution_logs(task_id: str, timeout: int = 20) -> list[dict[str, Any]]:
    response = requests.get(TASK_EXECUTION_LOG_URL, params={"taskId": task_id}, timeout=timeout)
    response.raise_for_status()
    body = response.json()
    data = body.get("data") or []
    return data if isinstance(data, list) else []


def current_period_flag_from_logs(logs: list[dict[str, Any]], tax_code: str = "") -> bool | None:
    """Return the latest current-period marker by log type.

    When a target tax code is known, prefer marker rows whose `lsn` matches
    that tax code. Multi-tax collection tasks can otherwise let a later VAT or
    culture-fee marker override the CIT A status. If no tax-code-specific row
    exists, fall back to the previous "latest marker" behavior.
    """

    matched = [
        item
        for item in logs
        if str(item.get("logType") or "") == CURRENT_PERIOD_LOG_TYPE
    ]
    if not matched:
        return None
    scoped = current_period_logs_for_tax_code(matched, tax_code)
    if scoped:
        matched = scoped
    latest = sorted(
        enumerate(matched),
        key=lambda pair: (pair[1].get("createdStamp") or 0, pair[0]),
    )[-1][1]
    return parse_bool(latest.get("logInfo"))


def current_period_logs_for_tax_code(logs: list[dict[str, Any]], tax_code: str = "") -> list[dict[str, Any]]:
    expected = str(tax_code or "").strip().lower()
    if not expected:
        return []
    return [
        item
        for item in logs
        if str(item.get("lsn") or "").strip().lower() == expected
    ]


def fetch_current_period_flag(task_id: str, tax_code: str = "", timeout: int = 20) -> bool | None:
    return current_period_flag_from_logs(fetch_task_execution_logs(task_id, timeout=timeout), tax_code=tax_code)


def cbj_mode_from_logs(logs: list[dict[str, Any]]) -> str | None:
    texts = [
        task_log_text(item)
        for item in sorted(
            logs,
            key=lambda value: value.get("createdStamp") or 0,
        )
    ]
    relevant_texts = [
        text
        for text in texts
        if CBJ_TASK_RESULT_LOG_TYPE in text
        or "\u6b8b\u4fdd\u91d1" in text
        or any(marker in text for marker in CBJ_ANNUAL_MODE_MARKERS)
        or any(marker in text for marker in CBJ_PERSONAL_MODE_MARKERS)
    ]
    if any(any(marker in text for marker in CBJ_ANNUAL_MODE_MARKERS) for text in relevant_texts):
        return "annual"
    if any(any(marker in text for marker in CBJ_PERSONAL_MODE_MARKERS) for text in relevant_texts):
        return "backend"
    return None


def fetch_cbj_mode_from_task_logs(task_id: str, timeout: int = 20) -> str | None:
    return cbj_mode_from_logs(fetch_task_execution_logs(task_id, timeout=timeout))


def task_log_text(log: dict[str, Any]) -> str:
    keys = (
        "logType",
        "logInfo",
        "lsn",
        "logContent",
        "logDesc",
        "message",
        "remark",
        "result",
        "content",
    )
    return " ".join(str(log.get(key) or "") for key in keys)


def parse_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text == "true":
        return True
    if text == "false":
        return False
    return None
