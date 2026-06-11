from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import requests
from playwright.sync_api import BrowserContext, Page

from src.chanjet_admin.auth import AdminAuthTokenProvider

LOGGER = logging.getLogger(__name__)

PUBLIC_MANAGE_URL = "https://public-manage.chanjet.com/taxserver#/taskManage/taxTaskList"
PUBLIC_MANAGE_MARKER = "public-manage.chanjet.com/taxserver"
TASK_LIST_URL = (
    "https://data-task-management.chanapp.chanjet.com/"
    "pub-tax-management/api/admin/task/getTaskListInternal"
)
COLLECT_TASK_TYPE_ID = "3"
BACKEND_LOGIN_TASK_CATEGORYS = "2,3"
MOCK_FLAG_NO = 0
MOCK_FLAG_YES = 1
ACCOUNTSET_LOGIN_TYPE_FILTER = "YSHDL,DLYW-YSHDL,SDSRDX,DLYW-SDSRDX"
PRIVACY_LOGIN_TYPE_FILTER = ACCOUNTSET_LOGIN_TYPE_FILTER
TOKEN_READ_ATTEMPTS = 5
TOKEN_RETRY_DELAY_MS = 1000
MAX_TAX_TYPE_SCAN_PAGES = 20


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
    """Query public-manage task list using a token provider or browser session."""

    def __init__(
        self,
        context: BrowserContext | None = None,
        timeout: int = 20,
        token_provider: AdminAuthTokenProvider | None = None,
    ) -> None:
        self.context = context
        self.timeout = timeout
        self.token_provider = token_provider
        self._token_cache: dict[str, str] | None = None

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
        tax_id: int | str | None = None,
        taxpayer_type: str | None = None,
        task_status: str | None = None,
        is_mock: bool | None = False,
        login_type: str | None = None,
        page_size: int = 50,
    ) -> list[AdminTask]:
        tasks = self.query_tasks(
            start_time=start_time,
            end_time=end_time,
            tax_no=tax_no,
            period=period,
            tax_type_id=tax_type_id,
            tax_id=tax_id,
            taxpayer_type=taxpayer_type,
            backend_task_type_id=COLLECT_TASK_TYPE_ID,
            task_status=task_status,
            is_mock=is_mock,
            login_type=login_type,
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
        tax_id: int | str | None = None,
        taxpayer_type: str | None = None,
        backend_task_type_id: int | str | None = None,
        task_status: str | None = None,
        is_mock: bool | None = False,
        login_type: str | None = None,
        page_size: int = 50,
    ) -> list[AdminTask]:
        page = None if self.token_provider is not None else self._ensure_page()
        tokens = self._read_tokens(page)
        base_payload = {
            "pageSize": page_size,
            "sortField": "createTime",
            "sortBy": "desc",
            "taskCategorys": BACKEND_LOGIN_TASK_CATEGORYS,
            "startTime": self._format_time(start_time),
            "endTime": self._format_time(end_time),
        }
        if is_mock is not None:
            base_payload["mockFlag"] = MOCK_FLAG_YES if is_mock else MOCK_FLAG_NO
        if tax_no:
            base_payload["taxNo"] = tax_no
        if period:
            base_payload["period"] = period
        if tax_type_id is not None and str(tax_type_id).strip():
            base_payload["taxTypeId"] = str(tax_type_id).strip()
            base_payload["taxTypeIds"] = [str(tax_type_id).strip()]
        if tax_id is not None and str(tax_id).strip():
            base_payload["taxId"] = str(tax_id).strip()
        if taxpayer_type:
            base_payload["taxPayerType"] = str(taxpayer_type).strip()
        if backend_task_type_id is not None and str(backend_task_type_id).strip():
            base_payload["taskTypeId"] = str(backend_task_type_id).strip()
        if login_type:
            base_payload["loginType"] = str(login_type).strip()
        if task_status:
            base_payload["status"] = str(task_status)
            base_payload["taskStatus"] = str(task_status)

        results: list[AdminTask] = []
        page_no = 1
        needs_client_scan = bool(
            (tax_type_id is not None and str(tax_type_id).strip()) or str(taxpayer_type or "").strip()
        )
        max_pages = MAX_TAX_TYPE_SCAN_PAGES if needs_client_scan else 1
        while page_no <= max_pages:
            payload = {**base_payload, "pageNo": page_no}
            data, tokens = self._post_task_query(payload, tokens, page)
            if str(data.get("code")) != "200" or not data.get("success", False):
                raise RuntimeError(
                    f"Public task query failed: code={data.get('code')} msg={data.get('msg') or data.get('message')}"
                )
            payload_data = data.get("data") or {}
            rows = payload_data.get("content") or []
            tasks = [self._to_task(row) for row in rows]
            if tax_no:
                tasks = [task for task in tasks if task.tax_no == tax_no]
            if period:
                tasks = [task for task in tasks if task.period == period]
            if tax_type_id is not None and str(tax_type_id).strip():
                tasks = [task for task in tasks if self._task_has_tax_type_id(task, str(tax_type_id).strip())]
            if taxpayer_type:
                tasks = [task for task in tasks if self._task_has_taxpayer_type(task, str(taxpayer_type).strip())]
            if task_status:
                tasks = [task for task in tasks if str(task.status or "").upper() == str(task_status).upper()]
            results.extend(tasks)
            if not rows or not needs_client_scan or len(results) >= page_size:
                break
            page_total = self._safe_int(payload_data.get("pageTotal"))
            if page_total and page_no >= page_total:
                break
            page_no += 1
        return results[:page_size]

    def _post_task_query(
        self,
        payload: dict[str, Any],
        tokens: dict[str, str],
        page: Page | None,
    ) -> tuple[dict[str, Any], dict[str, str]]:
        current_tokens = tokens
        for attempt in range(2):
            response = requests.post(
                TASK_LIST_URL,
                headers=self._headers(current_tokens),
                json=payload,
                timeout=self.timeout,
            )
            if getattr(response, "status_code", 0) in {401, 403} and attempt == 0:
                current_tokens = self._read_tokens(page, force_refresh=True)
                continue
            response.raise_for_status()
            data = response.json()
            if self._is_auth_failure_response(data) and attempt == 0:
                current_tokens = self._read_tokens(page, force_refresh=True)
                continue
            return data, current_tokens
        return data, current_tokens

    def _ensure_page(self) -> Page:
        if self.context is None:
            raise RuntimeError("Public management browser context is not configured.")
        candidates: list[Page] = []
        for page in self.context.pages:
            if page.is_closed():
                continue
            if PUBLIC_MANAGE_MARKER in page.url:
                self._wait_for_page_ready(page)
                candidates.append(page)
        for page in candidates:
            if self._page_has_tokens(page) and not self._page_forbidden(page):
                return page
        for page in reversed(candidates):
            if not self._page_forbidden(page):
                return page
        if candidates:
            return candidates[-1]
        page = self.context.new_page()
        page.goto(PUBLIC_MANAGE_URL, wait_until="domcontentloaded", timeout=60_000)
        self._wait_for_page_ready(page)
        return page

    def _page_has_tokens(self, page: Page) -> bool:
        try:
            tokens = self._read_storage_tokens(page)
        except Exception:
            return False
        return bool(tokens.get("authorization") and tokens.get("token"))

    def _page_forbidden(self, page: Page) -> bool:
        try:
            text = str(
                page.evaluate(
                    "() => String(document.body && document.body.innerText || '')"
                )
                or ""
            )
        except Exception:
            return False
        lower_text = text.lower()
        return ("403" in text or "forbidden" in lower_text) and (
            "无权" in text or "无权访问" in text or "没有权限" in text or "forbidden" in lower_text or "鏃犳潈" in text
        )

    def _read_storage_tokens(self, page: Page) -> dict[str, str]:
        tokens = page.evaluate(
            """() => {
                const read = (store, key) => {
                    try { return store.getItem(key) || ''; } catch (_err) { return ''; }
                };
                return {
                    authorization:
                        read(sessionStorage, 'Authorization') ||
                        read(localStorage, 'Authorization') ||
                        read(sessionStorage, 'authorization') ||
                        read(localStorage, 'authorization'),
                    token:
                        read(sessionStorage, 'access_token') ||
                        read(localStorage, 'access_token') ||
                        read(sessionStorage, 'token') ||
                        read(localStorage, 'token')
                };
            }"""
        )
        return {"authorization": str(tokens.get("authorization") or ""), "token": str(tokens.get("token") or "")}

    def _read_tokens(self, page: Page | None = None, force_refresh: bool = False) -> dict[str, str]:
        if self.token_provider is not None:
            tokens = self.token_provider.get_tokens(force_refresh=force_refresh)
            if not tokens.authorization or not tokens.token:
                raise RuntimeError("Public management token provider returned incomplete tokens.")
            self._token_cache = tokens.as_dict()
            return dict(self._token_cache)
        if self._token_cache and not force_refresh:
            return dict(self._token_cache)
        if force_refresh:
            self._token_cache = None
        last_exc: Exception | None = None
        current_page = page or self._ensure_page()
        for attempt in range(1, TOKEN_READ_ATTEMPTS + 1):
            try:
                if current_page.is_closed():
                    current_page = self._ensure_page()
                if PUBLIC_MANAGE_MARKER not in current_page.url:
                    current_page.goto(PUBLIC_MANAGE_URL, wait_until="domcontentloaded", timeout=60_000)
                self._wait_for_page_ready(current_page)
                tokens = self._read_storage_tokens(current_page)
                if tokens.get("authorization") and tokens.get("token"):
                    self._token_cache = {
                        "authorization": str(tokens.get("authorization") or ""),
                        "token": str(tokens.get("token") or ""),
                    }
                    return dict(self._token_cache)
                last_exc = RuntimeError("Public management login token is missing.")
            except Exception as exc:
                last_exc = exc
                LOGGER.debug("Public management token read attempt %s/%s failed: %s", attempt, TOKEN_READ_ATTEMPTS, exc)
            if attempt < TOKEN_READ_ATTEMPTS:
                try:
                    current_page.wait_for_timeout(TOKEN_RETRY_DELAY_MS)
                except Exception:
                    pass
                current_page = self._ensure_page()
        raise RuntimeError(
            "Public management login token is missing or page is still navigating. Open public-manage and login first."
        ) from last_exc

    def _is_auth_failure_response(self, data: dict[str, Any]) -> bool:
        code = str(data.get("code") or "").strip().lower()
        message = str(data.get("msg") or data.get("message") or "").strip().lower()
        if code in {"401", "403", "unauthorized", "forbidden"}:
            return True
        if str(data.get("success", "")).lower() == "true":
            return False
        return any(marker in message for marker in ("token", "authorization", "unauthorized", "登录", "未登录"))

    def _wait_for_page_ready(self, page: Page) -> None:
        try:
            page.wait_for_load_state("domcontentloaded", timeout=10_000)
        except Exception:
            pass
        try:
            page.wait_for_timeout(500)
        except Exception:
            pass

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

    def _task_has_tax_type_id(self, task: AdminTask, tax_type_id: str) -> bool:
        return tax_type_id in self._task_tax_type_ids(task.raw)

    def _task_has_taxpayer_type(self, task: AdminTask, taxpayer_type: str) -> bool:
        return self._task_taxpayer_type(task.raw).upper() == taxpayer_type.upper()

    def _task_taxpayer_type(self, row: dict[str, Any]) -> str:
        for key in ("taxPayerType", "taxpayerType"):
            value = row.get(key)
            if value not in (None, ""):
                return str(value).strip()
        return ""

    def _task_tax_type_ids(self, row: dict[str, Any]) -> set[str]:
        ids: set[str] = set()
        for key in ("taxTypeId", "tTaxTypeId"):
            value = row.get(key)
            if value not in (None, ""):
                ids.add(str(value))
        for key in ("taxTypeIds", "tTaxTypeIds"):
            value = row.get(key)
            if isinstance(value, list):
                ids.update(str(item) for item in value if item not in (None, ""))
            elif value not in (None, ""):
                ids.add(str(value))
        for rel in row.get("taskTaxRelVOList") or []:
            if not isinstance(rel, dict):
                continue
            value = rel.get("tTaxTypeId") or rel.get("taxTypeId")
            if value not in (None, ""):
                ids.add(str(value))
        return ids

    def _format_time(self, value: datetime) -> str:
        return value.strftime("%Y-%m-%d %H:%M:%S")

    def _safe_int(self, value: Any) -> int:
        try:
            return int(value)
        except Exception:
            return 0


def default_query_window(submitted_at: datetime | None, lookback_hours: int) -> tuple[datetime, datetime]:
    now = datetime.now()
    if submitted_at is None:
        return now - timedelta(hours=lookback_hours), now + timedelta(minutes=5)
    return submitted_at - timedelta(minutes=10), now + timedelta(minutes=5)
