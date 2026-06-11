from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import requests
from playwright.sync_api import BrowserContext, Page

from src.chanjet_admin.auth import AdminAuthTokenProvider
from src.chanjet_admin.task_query import ChanjetAdminTaskQuery

PRIVACY_PHONE_PAGE_URL = "https://public-manage.chanjet.com/taxserver#/privacyNumber/newPrivatePhoneNumber"
PROD_PRIVACY_PHONE_API_BASE = "https://data-task-management.chanapp.chanjet.com/pub-tax-management/api/privatePhone"
INTE_PRIVACY_PHONE_API_BASE = "https://data-task-management-chanapp.inte.chanjet.com/pub-tax-management/api/privatePhone"
PRIVACY_PHONE_SUMMARY_URL = f"{PROD_PRIVACY_PHONE_API_BASE}/summary"
PRIVACY_PHONE_DETAIL_URL = f"{PROD_PRIVACY_PHONE_API_BASE}/ref/getDetail"
PRIVACY_PHONE_COPY_URL = f"{PROD_PRIVACY_PHONE_API_BASE}/copyDataByPrivatePhone"
INTE_PRIVACY_PHONE_SUMMARY_URL = f"{INTE_PRIVACY_PHONE_API_BASE}/summary"
INTE_PRIVACY_PHONE_PULL_URL = f"{INTE_PRIVACY_PHONE_API_BASE}/pullPrivateDataByPrivatePhone"


class PrivacyPhoneSyncError(RuntimeError):
    """Raised when the public-manage privacy phone sync API cannot complete."""


@dataclass
class PrivacyPhoneSyncResult:
    private_phone: str
    status: str
    summary_count: int = 0
    detail_count: int = 0
    copy_success: bool = False
    copy_code: str | None = None
    copy_message: str | None = None
    summary_rows: list[dict[str, Any]] = field(default_factory=list)
    detail_rows: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status in {"OK", "DRY_RUN"}

    def to_report(self) -> dict[str, Any]:
        return {
            "privatePhone": self.private_phone,
            "status": self.status,
            "summaryCount": self.summary_count,
            "detailCount": self.detail_count,
            "copySuccess": self.copy_success,
            "copyCode": self.copy_code,
            "copyMessage": self.copy_message,
            "summaryRows": self.summary_rows,
            "detailRows": self.detail_rows,
            "errors": self.errors,
        }


@dataclass
class PrivacyPhonePrepareResult:
    private_phone: str
    status: str
    inte_summary_count: int = 0
    inte_summary_rows: list[dict[str, Any]] = field(default_factory=list)
    online_summary_count: int = 0
    online_detail_count: int = 0
    copy_success: bool = False
    pull_success: bool = False
    copy_message: str | None = None
    pull_message: str | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status in {"EXISTS", "PULLED", "DRY_RUN_EXISTS", "DRY_RUN_MISSING", "SKIPPED"}

    def to_report(self) -> dict[str, Any]:
        return {
            "privatePhone": self.private_phone,
            "status": self.status,
            "inteSummaryCount": self.inte_summary_count,
            "inteSummaryRows": self.inte_summary_rows,
            "onlineSummaryCount": self.online_summary_count,
            "onlineDetailCount": self.online_detail_count,
            "copySuccess": self.copy_success,
            "pullSuccess": self.pull_success,
            "copyMessage": self.copy_message,
            "pullMessage": self.pull_message,
            "errors": self.errors,
        }


def normalize_private_phone(value: str) -> str:
    phone = str(value or "").strip()
    if not phone:
        raise ValueError("private phone is required")
    return phone


def build_summary_payload(private_phone: str, page_no: int = 1, page_size: int = 10) -> dict[str, Any]:
    return {
        "customerDingSettingId": None,
        "phone": None,
        "privatePhone": normalize_private_phone(private_phone),
        "username": None,
        "yshIdCard": None,
        "accountingAgencyName": None,
        "mailbox": None,
        "isTaxBureauConfiguration": None,
        "orgId": None,
        "orgName": None,
        "orderStatus": None,
        "isSoonExpire": None,
        "exceedFlag": None,
        "phoneExpiredFlag": None,
        "pageSize": page_size,
        "pageNo": page_no,
    }


def build_integration_summary_payload(private_phone: str) -> dict[str, Any]:
    return {"privatePhone": normalize_private_phone(private_phone)}


def build_detail_payload(
    private_phone: str,
    org_id: str,
    page_no: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    return {
        "privatePhone": normalize_private_phone(private_phone),
        "phone": None,
        "isException": None,
        "orgId": str(org_id or "").strip(),
        "pageSize": page_size,
        "pageNo": page_no,
    }


def sanitize_summary_row(row: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "id",
        "orgId",
        "orgName",
        "effectOrderNum",
        "effectAuthNum",
        "availableConfigPhone",
        "configuredPhone",
        "bindTaxNoNum",
        "orderStatus",
        "expireDateTime",
    )
    return {key: row.get(key) for key in keys if key in row}


def sanitize_detail_row(row: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "id",
        "orgId",
        "dingTalkId",
        "source",
        "sourceValue",
        "privatePhone",
        "user",
        "agentName",
        "appName",
        "bindId",
        "isException",
        "bindDateTime",
        "expireDateTime",
    )
    return {key: row.get(key) for key in keys if key in row}


class ChanjetPrivacyPhoneSync:
    """Sync privacy-phone binding data through the logged-in public-manage session."""

    def __init__(
        self,
        context: BrowserContext | None = None,
        timeout: int = 20,
        api_base_url: str = PROD_PRIVACY_PHONE_API_BASE,
        token_provider: AdminAuthTokenProvider | None = None,
    ) -> None:
        self.context = context
        self.timeout = timeout
        self.api_base_url = api_base_url.rstrip("/")
        self._admin = ChanjetAdminTaskQuery(context, timeout=timeout, token_provider=token_provider)

    def query_summary_rows(self, private_phone: str, page_no: int = 1, page_size: int = 10) -> list[dict[str, Any]]:
        phone = normalize_private_phone(private_phone)
        page = self._ensure_token_page()
        tokens = self._admin._read_tokens(page)
        data, _tokens = self._post_json(
            self._endpoint("summary"),
            self._summary_payload(phone, page_no=page_no, page_size=page_size),
            tokens,
            page,
        )
        return self._content_rows(data)

    def pull_private_phone(self, private_phone: str) -> dict[str, Any]:
        phone = normalize_private_phone(private_phone)
        page = self._ensure_token_page()
        tokens = self._admin._read_tokens(page)
        data, _tokens = self._get_json(
            self._endpoint("pullPrivateDataByPrivatePhone"),
            {"privatePhone": phone},
            tokens,
            page,
        )
        return data

    def sync_private_phone(self, private_phone: str, dry_run: bool = False) -> PrivacyPhoneSyncResult:
        phone = normalize_private_phone(private_phone)
        page = self._ensure_token_page()
        tokens = self._admin._read_tokens(page)

        summary_data, tokens = self._post_json(
            self._endpoint("summary"),
            self._summary_payload(phone),
            tokens,
            page,
        )
        summary_rows = self._content_rows(summary_data)
        sanitized_summary = [sanitize_summary_row(row) for row in summary_rows]
        if not summary_rows:
            return PrivacyPhoneSyncResult(
                private_phone=phone,
                status="NOT_FOUND",
                summary_count=0,
                errors=[f"private phone {phone} was not found in summary query"],
            )

        detail_rows: list[dict[str, Any]] = []
        for summary in summary_rows:
            org_id = str(summary.get("orgId") or "").strip()
            if not org_id:
                continue
            detail_data, tokens = self._post_json(
                self._endpoint("ref/getDetail"),
                build_detail_payload(phone, org_id),
                tokens,
                page,
            )
            rows = [
                row
                for row in self._content_rows(detail_data)
                if str(row.get("privatePhone") or "").strip() == phone
            ]
            detail_rows.extend(rows)

        sanitized_details = [sanitize_detail_row(row) for row in detail_rows]
        if not detail_rows:
            return PrivacyPhoneSyncResult(
                private_phone=phone,
                status="NOT_FOUND",
                summary_count=len(summary_rows),
                detail_count=0,
                summary_rows=sanitized_summary,
                errors=[f"private phone {phone} was not found in detail query"],
            )

        if dry_run:
            return PrivacyPhoneSyncResult(
                private_phone=phone,
                status="DRY_RUN",
                summary_count=len(summary_rows),
                detail_count=len(detail_rows),
                copy_success=False,
                summary_rows=sanitized_summary,
                detail_rows=sanitized_details,
            )

        copy_data, _tokens = self._get_json(
            self._endpoint("copyDataByPrivatePhone"),
            {"privatePhone": phone},
            tokens,
            page,
        )
        copy_success = str(copy_data.get("code")) == "200" and bool(copy_data.get("success", False))
        if not copy_success:
            return PrivacyPhoneSyncResult(
                private_phone=phone,
                status="FAILED",
                summary_count=len(summary_rows),
                detail_count=len(detail_rows),
                copy_success=False,
                copy_code=str(copy_data.get("code") or ""),
                copy_message=str(copy_data.get("msg") or copy_data.get("message") or ""),
                summary_rows=sanitized_summary,
                detail_rows=sanitized_details,
                errors=[str(copy_data.get("msg") or copy_data.get("message") or "copy API failed")],
            )

        return PrivacyPhoneSyncResult(
            private_phone=phone,
            status="OK",
            summary_count=len(summary_rows),
            detail_count=len(detail_rows),
            copy_success=True,
            copy_code=str(copy_data.get("code") or ""),
            copy_message=str(copy_data.get("msg") or copy_data.get("message") or ""),
            summary_rows=sanitized_summary,
            detail_rows=sanitized_details,
        )

    def _summary_payload(self, private_phone: str, page_no: int = 1, page_size: int = 10) -> dict[str, Any]:
        if self.api_base_url == INTE_PRIVACY_PHONE_API_BASE:
            return build_integration_summary_payload(private_phone)
        return build_summary_payload(private_phone, page_no=page_no, page_size=page_size)

    def _endpoint(self, path: str) -> str:
        return f"{self.api_base_url}/{path.lstrip('/')}"

    def _ensure_token_page(self) -> Page | None:
        if self._admin.token_provider is not None:
            return None
        return self._admin._ensure_page()

    def _ensure_privacy_page(self) -> Page:
        page = self._admin._ensure_page()
        if "privacyNumber/newPrivatePhoneNumber" not in page.url:
            page.goto(PRIVACY_PHONE_PAGE_URL, wait_until="domcontentloaded", timeout=60_000)
            self._admin._wait_for_page_ready(page)
        return page

    def _post_json(
        self,
        url: str,
        payload: dict[str, Any],
        tokens: dict[str, str],
        page: Page | None,
    ) -> tuple[dict[str, Any], dict[str, str]]:
        current_tokens = tokens
        last_data: dict[str, Any] = {}
        for attempt in range(2):
            response = requests.post(
                url,
                headers=self._headers(current_tokens),
                json=payload,
                timeout=self.timeout,
            )
            if getattr(response, "status_code", 0) in {401, 403} and attempt == 0:
                current_tokens = self._admin._read_tokens(page, force_refresh=True)
                continue
            response.raise_for_status()
            last_data = response.json()
            if self._admin._is_auth_failure_response(last_data) and attempt == 0:
                current_tokens = self._admin._read_tokens(page, force_refresh=True)
                continue
            self._raise_if_failed(last_data, url)
            return last_data, current_tokens
        self._raise_if_failed(last_data, url)
        return last_data, current_tokens

    def _get_json(
        self,
        url: str,
        params: dict[str, Any],
        tokens: dict[str, str],
        page: Page | None,
    ) -> tuple[dict[str, Any], dict[str, str]]:
        current_tokens = tokens
        last_data: dict[str, Any] = {}
        for attempt in range(2):
            response = requests.get(
                url,
                headers=self._headers(current_tokens),
                params=params,
                timeout=self.timeout,
            )
            if getattr(response, "status_code", 0) in {401, 403} and attempt == 0:
                current_tokens = self._admin._read_tokens(page, force_refresh=True)
                continue
            response.raise_for_status()
            last_data = response.json()
            if self._admin._is_auth_failure_response(last_data) and attempt == 0:
                current_tokens = self._admin._read_tokens(page, force_refresh=True)
                continue
            self._raise_if_failed(last_data, url)
            return last_data, current_tokens
        self._raise_if_failed(last_data, url)
        return last_data, current_tokens

    def _raise_if_failed(self, data: dict[str, Any], url: str) -> None:
        if str(data.get("code")) == "200" and bool(data.get("success", False)):
            return
        message = data.get("msg") or data.get("message") or "unknown error"
        raise PrivacyPhoneSyncError(f"privacy phone API failed: {url}: {message}")

    def _headers(self, tokens: dict[str, str]) -> dict[str, str]:
        headers = self._admin._headers(tokens)
        if self.api_base_url == INTE_PRIVACY_PHONE_API_BASE:
            headers.pop("token", None)
        return headers

    def _content_rows(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        payload = data.get("data") or {}
        if isinstance(payload, list):
            rows = payload
        elif isinstance(payload, dict):
            rows = payload.get("content") or payload.get("records") or payload.get("list") or []
        else:
            rows = []
        return [row for row in (rows or []) if isinstance(row, dict)]


class ChanjetPrivacyPhoneBridge:
    """Ensure integration backend has privacy-phone data before creating integration account sets."""

    def __init__(
        self,
        context: BrowserContext | None = None,
        timeout: int = 20,
        token_provider: AdminAuthTokenProvider | None = None,
    ) -> None:
        self.online = ChanjetPrivacyPhoneSync(
            context,
            timeout=timeout,
            api_base_url=PROD_PRIVACY_PHONE_API_BASE,
            token_provider=token_provider,
        )
        self.integration = ChanjetPrivacyPhoneSync(
            context,
            timeout=timeout,
            api_base_url=INTE_PRIVACY_PHONE_API_BASE,
            token_provider=token_provider,
        )

    def ensure_integration_private_phone(
        self,
        private_phone: str,
        dry_run: bool = False,
    ) -> PrivacyPhonePrepareResult:
        phone = normalize_private_phone(private_phone)
        inte_rows = self.integration.query_summary_rows(phone)
        if inte_rows:
            return PrivacyPhonePrepareResult(
                private_phone=phone,
                status="DRY_RUN_EXISTS" if dry_run else "EXISTS",
                inte_summary_count=len(inte_rows),
                inte_summary_rows=[sanitize_summary_row(row) for row in inte_rows],
            )
        if dry_run:
            return PrivacyPhonePrepareResult(
                private_phone=phone,
                status="DRY_RUN_MISSING",
                inte_summary_count=0,
                errors=[f"private phone {phone} is not present in integration backend"],
            )

        online_result = self.online.sync_private_phone(phone, dry_run=False)
        if not online_result.ok:
            return PrivacyPhonePrepareResult(
                private_phone=phone,
                status="FAILED",
                inte_summary_count=0,
                online_summary_count=online_result.summary_count,
                online_detail_count=online_result.detail_count,
                copy_success=online_result.copy_success,
                copy_message=online_result.copy_message,
                errors=online_result.errors or ["online privacy phone sync failed"],
            )

        pull_data = self.integration.pull_private_phone(phone)
        pull_success = str(pull_data.get("code")) == "200" and bool(pull_data.get("success", False))
        pull_message = str(pull_data.get("msg") or pull_data.get("message") or "")
        if not pull_success:
            return PrivacyPhonePrepareResult(
                private_phone=phone,
                status="FAILED",
                inte_summary_count=0,
                online_summary_count=online_result.summary_count,
                online_detail_count=online_result.detail_count,
                copy_success=online_result.copy_success,
                pull_success=False,
                copy_message=online_result.copy_message,
                pull_message=pull_message,
                errors=[pull_message or "integration privacy phone pull failed"],
            )

        refreshed_rows = self.integration.query_summary_rows(phone)
        if not refreshed_rows:
            return PrivacyPhonePrepareResult(
                private_phone=phone,
                status="FAILED",
                inte_summary_count=0,
                online_summary_count=online_result.summary_count,
                online_detail_count=online_result.detail_count,
                copy_success=online_result.copy_success,
                pull_success=True,
                copy_message=online_result.copy_message,
                pull_message=pull_message,
                errors=["integration privacy phone pull returned success, but summary is still empty"],
            )

        return PrivacyPhonePrepareResult(
            private_phone=phone,
            status="PULLED",
            inte_summary_count=len(refreshed_rows),
            inte_summary_rows=[sanitize_summary_row(row) for row in refreshed_rows],
            online_summary_count=online_result.summary_count,
            online_detail_count=online_result.detail_count,
            copy_success=online_result.copy_success,
            pull_success=True,
            copy_message=online_result.copy_message,
            pull_message=pull_message,
        )
