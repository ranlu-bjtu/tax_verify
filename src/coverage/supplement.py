from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from src.chanjet_admin.task_query import AdminTask, ChanjetAdminTaskQuery
from src.chanjet_admin.task_execution_log import fetch_current_period_flag

from .analyzer import normalize_declaration_status
from .models import DECLARATION_FILED, DECLARATION_UNFILED, DECLARATION_UNKNOWN, CoverageTarget, SupplementCandidate


CURRENT_PERIOD_LOG_CODE_BY_TAX_TYPE = {
    "VAT_GENERAL": "sz_zzs",
    "VAT_SMALL": "sz_zzs",
}


class BackendDeclarationStatusExtractor:
    """Extract filed/unfiled status from a backend task row.

    The exact result JSON field is still pending confirmation. This extractor
    intentionally supports common field names and is isolated so the final
    schema can be added in one place.
    """

    STATUS_KEYS = {
        "declarationStatus",
        "declareStatus",
        "taxDeclareStatus",
        "申报状态",
        "sbzt",
        "sbztDm",
        "currentPeriodFlag",
    }

    RESULT_KEYS = (
        "resultJson",
        "result",
        "taskResult",
        "taskResultJson",
        "executeResult",
        "dataResult",
        "responseData",
    )

    def extract(self, task: AdminTask) -> str:
        payload = self._task_result_payload(task.raw)
        if payload is None:
            return DECLARATION_UNKNOWN
        status_value = self._find_status_value(payload)
        if status_value is None:
            return DECLARATION_UNKNOWN
        return normalize_declaration_status(status_value)

    def _task_result_payload(self, row: dict[str, Any]) -> Any:
        for key in self.RESULT_KEYS:
            if key not in row:
                continue
            value = row.get(key)
            parsed = self._parse_json_value(value)
            if parsed not in (None, "", [], {}):
                return parsed
        return row

    def _parse_json_value(self, value: Any) -> Any:
        if isinstance(value, (dict, list)):
            return value
        if not isinstance(value, str):
            return value
        text = value.strip()
        if not text:
            return ""
        try:
            return json.loads(text)
        except Exception:
            return text

    def _find_status_value(self, value: Any) -> Any:
        if isinstance(value, dict):
            for key, item in value.items():
                if str(key) in self.STATUS_KEYS:
                    return item
            for item in value.values():
                found = self._find_status_value(item)
                if found is not None:
                    return found
        elif isinstance(value, list):
            for item in value:
                found = self._find_status_value(item)
                if found is not None:
                    return found
        return None


class CoverageSupplementPlanner:
    def __init__(
        self,
        query: ChanjetAdminTaskQuery,
        extractor: BackendDeclarationStatusExtractor | None = None,
    ) -> None:
        self.query = query
        self.extractor = extractor or BackendDeclarationStatusExtractor()
        self.last_diagnostics: list[dict[str, Any]] = []

    def find_candidates(
        self,
        missing_targets: list[CoverageTarget],
        start_time: datetime,
        end_time: datetime,
        page_size: int = 50,
    ) -> list[SupplementCandidate]:
        candidates: list[SupplementCandidate] = []
        self.last_diagnostics = []
        for tax_type_id, targets in self._group_targets_by_tax_type_id(missing_targets).items():
            tasks = self.query.find_collect_tasks_by_filters(
                start_time=start_time,
                end_time=end_time,
                tax_type_id=tax_type_id,
                task_status="SUCCESS",
                page_size=page_size,
            )
            status_cache: dict[tuple[str, str], str] = {}
            for target in targets:
                diagnostic = {
                    "targetKey": target.key,
                    "taxType": target.tax_type,
                    "taxTypeName": target.tax_type_name,
                    "declarationStatus": target.declaration_status,
                    "backendTaxTypeId": str(tax_type_id),
                    "queriedCount": 0,
                    "statusCounts": {},
                    "matchedTaskId": "",
                    "reason": "",
                    "queryShared": len(targets) > 1,
                }
                diagnostic["queriedCount"] = len(tasks)
                for task in tasks:
                    parse_status = self._extract_status_cached(task, target, status_cache)
                    status_counts = diagnostic["statusCounts"]
                    status_counts[parse_status] = status_counts.get(parse_status, 0) + 1
                    if parse_status != target.declaration_status:
                        continue
                    candidates.append(
                        SupplementCandidate(
                            target_key=target.key,
                            tax_type=target.tax_type,
                            tax_type_name=target.tax_type_name,
                            declaration_status=target.declaration_status,
                            declaration_status_name=target.declaration_status_name,
                            task_id=task.task_id,
                            tax_no=task.tax_no,
                            period=task.period or "",
                            task_status=task.status or "",
                            backend_tax_type_id=str(tax_type_id),
                            created_stamp=task.created_stamp,
                            parse_status=parse_status,
                            reason="matched_backend_result_json",
                        )
                    )
                    diagnostic["matchedTaskId"] = task.task_id
                    diagnostic["reason"] = "matched_backend_result_json"
                    break
                if not diagnostic["matchedTaskId"]:
                    if not tasks:
                        diagnostic["reason"] = "no_success_collect_tasks"
                    elif diagnostic["statusCounts"]:
                        diagnostic["reason"] = "declaration_status_not_matched"
                    else:
                        diagnostic["reason"] = "declaration_status_unknown"
                self.last_diagnostics.append(diagnostic)
        return candidates

    def _group_targets_by_tax_type_id(self, targets: list[CoverageTarget]) -> dict[int, list[CoverageTarget]]:
        grouped: dict[int, list[CoverageTarget]] = {}
        for target in targets:
            for tax_type_id in target.backend_tax_type_ids:
                grouped.setdefault(int(tax_type_id), []).append(target)
        return grouped

    def _extract_status_cached(
        self,
        task: AdminTask,
        target: CoverageTarget,
        cache: dict[tuple[str, str], str],
    ) -> str:
        key = (task.task_id, target.tax_type)
        if key in cache:
            return cache[key]
        parse_status = self.extractor.extract(task)
        if parse_status == DECLARATION_UNKNOWN:
            parse_status = self._extract_from_execution_logs(task, target)
        cache[key] = parse_status
        return parse_status

    def _extract_from_execution_logs(self, task: AdminTask, target: CoverageTarget) -> str:
        tax_code = CURRENT_PERIOD_LOG_CODE_BY_TAX_TYPE.get(target.tax_type)
        if not tax_code:
            return DECLARATION_UNKNOWN
        flag = fetch_current_period_flag(task.task_id, tax_code=tax_code, timeout=self.query.timeout)
        if flag is True:
            return DECLARATION_FILED
        if flag is False:
            return DECLARATION_UNFILED
        return DECLARATION_UNKNOWN


def choose_representative_candidates(candidates: list[SupplementCandidate]) -> list[SupplementCandidate]:
    chosen: dict[str, SupplementCandidate] = {}
    for candidate in sorted(
        candidates,
        key=lambda item: (
            item.target_key,
            -(item.created_stamp or 0),
            item.task_id,
        ),
    ):
        chosen.setdefault(candidate.target_key, candidate)
    return list(chosen.values())


def apply_supplement_candidates_to_state(
    state: dict[str, Any],
    candidates: list[SupplementCandidate],
    enterprise: str = "",
) -> list[str]:
    """Add representative backend supplement tasks to a batch state.

    The batch verifier can verify any state item that has a taskId. This function
    records one representative task per missing coverage target and keeps the
    original tax-number item when that tax number already points to another task.
    """

    applied_item_keys: list[str] = []
    items = state.setdefault("items", {})
    for candidate in choose_representative_candidates(candidates):
        if not candidate.tax_no or not candidate.task_id:
            continue
        item_key = supplement_item_key(items, candidate)
        item = items.setdefault(
            item_key,
            {
                "taxNo": candidate.tax_no,
                "period": candidate.period or state.get("period") or "",
                "collect": None,
                "verify": None,
            },
        )
        collect = item.get("collect") or {}
        if collect.get("verifyTaskId") and collect.get("verifyTaskId") != candidate.task_id:
            item.setdefault("supplementCandidates", []).append(candidate.to_dict())
            continue
        collect.update(
            {
                "taxNo": candidate.tax_no,
                "period": candidate.period or item.get("period") or state.get("period") or "",
                "enterprise": enterprise or state.get("enterprise") or "",
                "submitted": False,
                "terminal": True,
                "manualRequired": False,
                "status": "BACKEND_SUPPLEMENT",
                "warnings": [],
                "errors": [],
                "verifyTaskId": candidate.task_id,
                "account": {
                    "taxNo": candidate.tax_no,
                    "custName": "",
                    "assocTenantId": 0,
                    "accountId": 0,
                    "areaCode": "",
                    "authStatus": "",
                    "gatherStatus": "BACKEND_SUPPLEMENT",
                },
                "taxItems": [],
                "resolvedTask": {
                    "taskId": candidate.task_id,
                    "taskTypeId": "3",
                    "taskTypeName": "取数",
                    "status": candidate.task_status,
                    "source": "backend_supplement",
                    "coverageTarget": candidate.target_key,
                    "backendTaxTypeId": candidate.backend_tax_type_id,
                },
            }
        )
        item["collect"] = collect
        item["source"] = "backend_supplement"
        item.setdefault("coverageSupplementTargets", [])
        if candidate.target_key not in item["coverageSupplementTargets"]:
            item["coverageSupplementTargets"].append(candidate.target_key)
        applied_item_keys.append(item_key)
    return applied_item_keys


def supplement_item_key(items: dict[str, Any], candidate: SupplementCandidate) -> str:
    base_key = candidate.tax_no
    existing = items.get(base_key)
    existing_task_id = ((existing or {}).get("collect") or {}).get("verifyTaskId") if existing else ""
    if not existing_task_id or existing_task_id == candidate.task_id:
        return base_key

    suffix = "".join(ch if ch.isalnum() else "_" for ch in candidate.target_key).strip("_") or "supplement"
    key = f"{base_key}__coverage__{suffix}"
    existing = items.get(key)
    existing_task_id = ((existing or {}).get("collect") or {}).get("verifyTaskId") if existing else ""
    if not existing_task_id or existing_task_id == candidate.task_id:
        return key

    task_suffix = "".join(ch if ch.isalnum() else "_" for ch in candidate.task_id).strip("_")
    return f"{key}__{task_suffix}"
