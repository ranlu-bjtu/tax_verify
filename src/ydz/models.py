from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


TERMINAL_COLLECT_STATUSES = {"COLLECTED", "COLLECTED_PART", "COLLECTED_FAIL", "NO_NEED_COLLECTED"}
DEFAULT_COLLECT_TAX_TYPE_IDS = [1, 3, 2, 26, 29, 30, 31]
SOCIAL_INSURANCE_TAX_TYPE_IDS = {40}
CBJ_COLLECT_TAX_TYPE_IDS = [26, 31]


def sanitize_collect_tax_type_ids(tax_type_ids: list[int] | None = None) -> list[int]:
    source = DEFAULT_COLLECT_TAX_TYPE_IDS if tax_type_ids is None else tax_type_ids
    sanitized: list[int] = []
    for value in source:
        tax_type_id = int(value)
        if tax_type_id in SOCIAL_INSURANCE_TAX_TYPE_IDS:
            continue
        if tax_type_id not in sanitized:
            sanitized.append(tax_type_id)
    return sanitized


@dataclass(frozen=True)
class YdzAccount:
    tax_no: str
    cust_name: str
    assoc_tenant_id: int
    account_id: int
    area_code: str
    auth_status: str | None = None
    gather_status: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class YdzCollectResult:
    tax_no: str
    period: str
    enterprise: str
    account: YdzAccount | None = None
    submitted: bool = False
    terminal: bool = False
    manual_required: bool = False
    status: str | None = None
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    tax_items: list[dict[str, Any]] = field(default_factory=list)
    ignored_tax_items: list[dict[str, Any]] = field(default_factory=list)
    verify_task_id: str | None = None
    verify_task_ids: list[str] = field(default_factory=list)
    submitted_at: datetime | None = None
    resolved_task: dict[str, Any] | None = None
    resolved_tasks: list[dict[str, Any]] = field(default_factory=list)

    def task_ids(self) -> list[str]:
        values: list[str] = []
        if self.verify_task_id:
            values.append(str(self.verify_task_id))
        values.extend(str(item) for item in self.verify_task_ids if item)
        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            if value in seen:
                continue
            seen.add(value)
            result.append(value)
        return result

    def to_dict(self) -> dict[str, Any]:
        task_ids = self.task_ids()
        resolved_tasks = self.resolved_tasks or ([self.resolved_task] if self.resolved_task else [])
        return {
            "taxNo": self.tax_no,
            "period": self.period,
            "enterprise": self.enterprise,
            "submitted": self.submitted,
            "terminal": self.terminal,
            "manualRequired": self.manual_required,
            "status": self.status,
            "warnings": self.warnings,
            "errors": self.errors,
            "verifyTaskId": task_ids[0] if task_ids else None,
            "verifyTaskIds": task_ids,
            "account": None
            if self.account is None
            else {
                "taxNo": self.account.tax_no,
                "custName": self.account.cust_name,
                "assocTenantId": self.account.assoc_tenant_id,
                "accountId": self.account.account_id,
                "areaCode": self.account.area_code,
                "authStatus": self.account.auth_status,
                "gatherStatus": self.account.gather_status,
            },
            "taxItems": self.tax_items,
            "ignoredTaxItems": self.ignored_tax_items,
            "submittedAt": self.submitted_at.isoformat(timespec="seconds") if self.submitted_at else None,
            "resolvedTask": resolved_tasks[0] if resolved_tasks else None,
            "resolvedTasks": resolved_tasks,
        }
