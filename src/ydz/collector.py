from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any

from src.ydz.api import YdzApi
from src.ydz.models import (
    SOCIAL_INSURANCE_TAX_TYPE_IDS,
    TERMINAL_COLLECT_STATUSES,
    YdzAccount,
    YdzCollectResult,
    sanitize_collect_tax_type_ids,
)

LOGGER = logging.getLogger(__name__)

DEFAULT_TAX_TYPE_IDS = sanitize_collect_tax_type_ids()


class YdzCollector:
    def __init__(
        self,
        api: YdzApi,
        enterprise: str,
        query_area_code: str = "00",
        tax_type_ids: list[int] | None = None,
        poll_interval: int = 15,
        poll_timeout: int = 600,
    ) -> None:
        self.api = api
        self.enterprise = enterprise
        self.query_area_code = query_area_code
        self.tax_type_ids = sanitize_collect_tax_type_ids(tax_type_ids)
        self.poll_interval = poll_interval
        self.poll_timeout = poll_timeout

    def collect_tax_no(self, tax_no: str, period: str, force: bool = False) -> YdzCollectResult:
        result = self.submit_collect_tax_no(tax_no=tax_no, period=period, force=force)
        if result.manual_required or result.terminal:
            return result
        return self.poll_collect_status(result)

    def submit_collect_tax_no(self, tax_no: str, period: str, force: bool = False) -> YdzCollectResult:
        result = YdzCollectResult(tax_no=tax_no, period=period, enterprise=self.enterprise)
        account = self.find_account(tax_no, period)
        if account is None:
            result.manual_required = True
            result.errors.append("No Yidaizhang account matched this tax number.")
            return result

        result.account = account
        result.status = account.gather_status
        if account.auth_status and account.auth_status != "AUTHORIZED":
            result.manual_required = True
            result.errors.append(f"Account authorization is not ready: {account.auth_status}")
            return result

        if not force and account.gather_status in {"COLLECTED", "COLLECTED_PART"}:
            result.terminal = True
            self._copy_tax_items(account.raw, result)
            return result

        submit_data = self.api.submit_collect_task(
            tax_no=tax_no,
            period=period,
            tenant_id=account.assoc_tenant_id,
            area_code=account.area_code,
            tax_type_ids=self.tax_type_ids,
        )
        result.submitted = True
        result.submitted_at = datetime.now()
        self._append_submit_warnings(submit_data, result)
        if self._has_social_insurance_message(result.warnings):
            self._record_social_insurance_warning(result)
        if self._has_period_window_block(result.warnings):
            result.manual_required = True
            result.errors.append("Collection submit was blocked by Yidaizhang period window.")
            account = self.find_account(result.tax_no, result.period)
            if account is not None:
                result.account = account
                result.status = account.gather_status
                self._copy_tax_items(account.raw, result)
            return result
        return result

    def find_account(self, tax_no: str, period: str) -> YdzAccount | None:
        data = self.api.get_batch_list(tax_no=tax_no, period=period, area_code=self.query_area_code)
        rows = data.get("data") or []
        if not rows:
            return None
        row = rows[0]
        area_code = self._resolve_area_code(row, tax_no)
        return YdzAccount(
            tax_no=tax_no,
            cust_name=str(row.get("custName") or ""),
            assoc_tenant_id=int(row.get("assocTenantId") or 0),
            account_id=int(row.get("id") or 0),
            area_code=area_code,
            auth_status=row.get("authStatusEnum"),
            gather_status=row.get("gatherInitStatusEnum"),
            raw=row,
        )

    def poll_collect_status(self, result: YdzCollectResult) -> YdzCollectResult:
        deadline = time.time() + self.poll_timeout
        last_status = result.status
        while time.time() < deadline:
            self.refresh_collect_status(result)
            if result.status in TERMINAL_COLLECT_STATUSES:
                return result
            if result.status != last_status:
                LOGGER.info("Yidaizhang collection status changed: %s -> %s", last_status, result.status)
                last_status = result.status
            time.sleep(self.poll_interval)

        result.manual_required = True
        result.errors.append(f"Timed out waiting for collection terminal status; last status={result.status}.")
        return result

    def refresh_collect_status(self, result: YdzCollectResult) -> YdzCollectResult:
        account = self.find_account(result.tax_no, result.period)
        if account is None:
            result.manual_required = True
            result.errors.append("Account disappeared while polling collection status.")
            return result
        result.account = account
        result.status = account.gather_status
        self._copy_tax_items(account.raw, result)
        self._copy_ignored_tax_items(result)
        if result.status in TERMINAL_COLLECT_STATUSES:
            result.terminal = True
            if result.status == "COLLECTED_FAIL" and self._has_supported_collect_failure(result):
                result.manual_required = True
        return result

    def _resolve_area_code(self, row: dict[str, Any], tax_no: str) -> str:
        for key in ("taxiationArea", "areaCode", "taxAreaCode", "provinceCode"):
            value = row.get(key)
            if value:
                return str(value)[:2]
        if len(tax_no) >= 4 and tax_no[2:4].isdigit():
            return tax_no[2:4]
        return self.query_area_code

    def _append_submit_warnings(self, submit_data: dict[str, Any], result: YdzCollectResult) -> None:
        for item in submit_data.get("data") or []:
            msg = item.get("msg")
            if msg:
                result.warnings.append(str(msg))
        if not submit_data.get("successful", True):
            result.manual_required = True
            result.errors.append(str(submit_data.get("rootCause") or submit_data.get("msg") or "Submit failed."))

    def _has_period_window_block(self, warnings: list[str]) -> bool:
        return any(
            "\u53ef\u4ee5\u53d1\u8d77\u7684\u671f\u95f4\u8303\u56f4" in warning
            and "\u8bf7\u5728\u8be5\u671f\u95f4\u5185\u53d1\u8d77\u8be5\u4efb\u52a1" in warning
            for warning in warnings
        )

    def _has_social_insurance_message(self, values: list[str]) -> bool:
        return any("\u793e\u4f1a\u4fdd\u9669\u8d39" in str(value or "") for value in values)

    def _record_social_insurance_warning(self, result: YdzCollectResult) -> None:
        for warning in result.warnings:
            if "\u793e\u4f1a\u4fdd\u9669\u8d39" not in str(warning or ""):
                continue
            result.ignored_tax_items.append(
                {
                    "taxTypeId": 40,
                    "taxTypeName": "\u793e\u4f1a\u4fdd\u9669\u8d39",
                    "message": str(warning),
                    "ignoredReason": "Social insurance fee is intentionally excluded from automatic collection.",
                }
            )

    def _copy_ignored_tax_items(self, result: YdzCollectResult) -> None:
        ignored: list[dict[str, Any]] = []
        for item in result.tax_items:
            if not self._is_social_insurance_item(item):
                continue
            copied = dict(item)
            copied["ignoredReason"] = "Social insurance fee is intentionally excluded from automatic collection."
            ignored.append(copied)
        if ignored:
            result.ignored_tax_items = ignored

    def _has_supported_collect_failure(self, result: YdzCollectResult) -> bool:
        return any(self._failed_tax_item(item) and not self._is_social_insurance_item(item) for item in result.tax_items)

    def _failed_tax_item(self, item: dict[str, Any]) -> bool:
        return str(item.get("initStatusEnum") or "").upper() == "COLLECTED_FAIL" or str(item.get("status") or "").upper() in {
            "FAILURE",
            "FAILED",
            "FAIL",
        }

    def _is_social_insurance_item(self, item: dict[str, Any]) -> bool:
        try:
            tax_type_id = int(item.get("taxTypeId"))
        except (TypeError, ValueError):
            tax_type_id = None
        text = " ".join(
            str(item.get(key) or "")
            for key in ("taxTypeName", "taxName", "name", "message", "status", "initStatusEnum")
        )
        return tax_type_id in SOCIAL_INSURANCE_TAX_TYPE_IDS or "\u793e\u4f1a\u4fdd\u9669\u8d39" in text

    def _copy_tax_items(self, row: dict[str, Any], result: YdzCollectResult) -> None:
        items = []
        for detail in row.get("taxItemDetailList") or []:
            init_json = detail.get("initJson") or {}
            items.append(
                {
                    "taxTypeId": detail.get("taxTypeId"),
                    "taxTypeName": detail.get("taxTypeName") or detail.get("taxName") or detail.get("name"),
                    "initStatusEnum": detail.get("initStatusEnum"),
                    "initStatusTime": detail.get("initStatusTime"),
                    "initTaskId": detail.get("initTaskId"),
                    "initExternalTaskId": detail.get("initExternalTaskId"),
                    "status": init_json.get("status") if isinstance(init_json, dict) else None,
                    "message": init_json.get("msg") if isinstance(init_json, dict) else None,
                    "taxAmount": detail.get("taxAmount"),
                    "rptTaxAmount": detail.get("rptTaxAmount"),
                }
            )
        result.tax_items = items
