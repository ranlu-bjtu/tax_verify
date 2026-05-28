from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import requests
from playwright.sync_api import BrowserContext, Page

LOGGER = logging.getLogger(__name__)

PUBLIC_MANAGE_URL = "https://public-manage.chanjet.com/taxserver#/taskManage/taxTaskList"
TASK_LIST_URL = (
    "https://data-task-management.chanapp.chanjet.com/"
    "pub-tax-management/api/admin/task/getTaskListInternal"
)
COLLECT_TASK_TYPE_ID = "3"


@dataclass(frozen=True)
class AdminTask:
    task_id: str
    tax_no: str
    period: str | None
    task_type_id: str | None
    task_type_name: str | None
    status: str | None
    created_stamp: int | None
    raw: dict[str, Any]


class ChanjetAdminTaskQuery:
    """Query public-manage task list using the logged-in browser session."""

    def __init__(self, context: BrowserContext, timeout: int = 20) -> None:
        self.context = context
        self.timeout = timeout

    def find_collect_tasks(
        self,
        tax_no: str,
        period: str,
        start_time: datetime,
        end_time: datetime,
        page_size: int = 20,
    ) -> list[AdminTask]:
        tasks = self.find_collect_tasks_by_filters(
            start_time=start_time,
            end_time=end_time,
            tax_no=tax_no,
            period=period,
            page_size=page_size,
        )
        return [
            task
            for task in tasks
            if task.tax_no == tax_no
            and task.period == period
            and task.task_type_id == COLLECT_TASK_TYPE_ID
            and task.task_type_name == "\u53d6\u6570"
        ]

    def find_collect_tasks_by_filters(
        self,
        start_time: datetime,
        end_time: datetime,
        tax_no: str = "",
        period: str | None = None,
        tax_type_id: int | str | None = None,
        task_status: str | None = None,
        page_size: int = 50,
    ) -> list[AdminTask]:
        tasks = self.query_tasks(
            start_time=start_time,
            end_time=end_time,
            tax_no=tax_no,
            period=period,
            tax_type_id=tax_type_id,
            task_status=task_status,
            page_size=page_size,
        )
        return [
            task
            for task in tasks
            if task.task_type_id == COLLECT_TASK_TYPE_ID
            and (not task.task_type_name or task.task_type_name == "\u53d6\u6570")
            and (not task_status or str(task.status or "").upper() == str(task_status).upper())
        ]

    def query_tasks(
        self,
        start_time: datetime,
        end_time: datetime,
        tax_no: str = "",
        period: str | None = None,
        tax_type_id: int | str | None = None,
        task_status: str | None = None,
        page_size: int = 50,
    ) -> list[AdminTask]:
        page = self._ensure_page()
        tokens = self._read_tokens(page)
        payload = {
            "pageNo": 1,
            "pageSize": page_size,
            "sortField": "createTime",
            "sortBy": "desc",
            "taskCategorys": "",
            "startTime": self._format_time(start_time),
            "endTime": self._format_time(end_time),
            "taskTypeId": COLLECT_TASK_TYPE_ID,
        }
        if tax_no:
            payload["taxNo"] = tax_no
        if period:
            payload["period"] = period
        if tax_type_id is not None and str(tax_type_id).strip():
            payload["taxTypeId"] = str(tax_type_id).strip()
            payload["taxTypeIds"] = [str(tax_type_id).strip()]
        if task_status:
            payload["status"] = str(task_status)
            payload["taskStatus"] = str(task_status)
        response = requests.post(
            TASK_LIST_URL,
            headers=self._headers(tokens),
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()
        if str(data.get("code")) != "200" or not data.get("success", False):
            raise RuntimeError(
                f"Public task query failed: code={data.get('code')} msg={data.get('msg') or data.get('message')}"
            )
        rows = (data.get("data") or {}).get("content") or []
        tasks = [self._to_task(row) for row in rows]
        return tasks

    def _ensure_page(self) -> Page:
        for page in self.context.pages:
            if "public-manage.chanjet.com/taxserver" in page.url:
                if page.is_closed():
                    continue
                return page
        page = self.context.new_page()
        page.goto(PUBLIC_MANAGE_URL, wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(5000)
        return page

    def _read_tokens(self, page: Page) -> dict[str, str]:
        tokens = page.evaluate(
            """() => ({
                authorization: sessionStorage.getItem('Authorization') || '',
                token: sessionStorage.getItem('access_token') || ''
            })"""
        )
        if not tokens.get("authorization") or not tokens.get("token"):
            raise RuntimeError("Public management login token is missing. Open public-manage and login first.")
        return tokens

    def _headers(self, tokens: dict[str, str]) -> dict[str, str]:
        return {
            "accept": "application/json, text/plain, */*",
            "content-type": "application/json",
            "authorization": tokens["authorization"],
            "token": tokens["token"],
            "referer": "https://public-manage.chanjet.com/",
            "user-agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36"
            ),
        }

    def _to_task(self, row: dict[str, Any]) -> AdminTask:
        task_type_id = row.get("tTaskTypeId") or row.get("ttaskTypeId")
        return AdminTask(
            task_id=str(row.get("id") or ""),
            tax_no=str(row.get("taxNo") or ""),
            period=str(row.get("period") or "") or None,
            task_type_id=str(task_type_id or "") or None,
            task_type_name=row.get("taskTypeName"),
            status=row.get("status"),
            created_stamp=int(row["createdStamp"]) if row.get("createdStamp") is not None else None,
            raw=row,
        )

    def _format_time(self, value: datetime) -> str:
        return value.strftime("%Y-%m-%d %H:%M:%S")


def default_query_window(submitted_at: datetime | None, lookback_hours: int) -> tuple[datetime, datetime]:
    now = datetime.now()
    if submitted_at is None:
        return now - timedelta(hours=lookback_hours), now + timedelta(minutes=5)
    return submitted_at - timedelta(minutes=10), now + timedelta(minutes=5)
