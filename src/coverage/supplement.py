from __future__ import annotations

import json
import time
from datetime import datetime
from typing import Any, Callable

from src.api.api_client import APIClient
from src.chanjet_admin.task_query import AdminTask, ChanjetAdminTaskQuery
from src.chanjet_admin.task_execution_log import fetch_cbj_mode_from_task_logs, fetch_current_period_flag

from .analyzer import normalize_declaration_status
from .models import (
    DECLARATION_ANY,
    DECLARATION_FILED,
    DECLARATION_UNFILED,
    DECLARATION_UNKNOWN,
    CoverageTarget,
    SupplementCandidate,
)

VAT_GENERAL_MARKERS = (
    "vat_general",
    "vatgeneral",
    "vat_general_main",
    "ybnsr",
    "sbzzsybnsr",
    "\u4e00\u822c\u7eb3\u7a0e\u4eba",
    "\u4e00\u822c\u7eb3\u7a0e\u4eba\u9002\u7528",
)

VAT_SMALL_MARKERS = (
    "vat_small",
    "vatsmall",
    "vat_small_main",
    "xgmnsr",
    "sbzzsxgm",
    "\u5c0f\u89c4\u6a21",
    "\u5c0f\u89c4\u6a21\u7eb3\u7a0e\u4eba",
    "\u5c0f\u89c4\u6a21\u7eb3\u7a0e\u4eba\u9002\u7528",
)

EXECUTION_LOG_STATUS_TAX_TYPES = {
    "VAT_GENERAL",
    "VAT_SMALL",
    "CIT_A",
    "CULTURE_FEE",
    "CONSUMPTION_TAX",
    "CBJ_ANNUAL",
}
CBJ_TAX_TYPES = {"CBJ_PERSONAL", "CBJ_ANNUAL"}
CBJ_PERSONAL_REQUIRED_FIELDS = ("snzzzgrs_cbj", "snzzzggzze_cbj")
CBJ_BACKEND_TAX_TYPE_IDS = {"26", "31"}
CBJ_BACKEND_TAX_IDS = {"39"}
EXECUTION_LOG_TAX_CODES = {
    "VAT_GENERAL": "sz_zzs",
    "VAT_SMALL": "sz_zzs",
    "CIT_A": "sz_qysds",
    "CULTURE_FEE": "sz_whsyjsf",
    "CONSUMPTION_TAX": "sz_xfs",
}


def execution_log_tax_code_for_target(target: CoverageTarget) -> str:
    return EXECUTION_LOG_TAX_CODES.get(str(getattr(target, "tax_type", "") or ""), "")


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
        api_client: Any | None = None,
    ) -> None:
        self.query = query
        self.extractor = extractor or BackendDeclarationStatusExtractor()
        self.api_client = api_client or APIClient()
        self.last_diagnostics: list[dict[str, Any]] = []

    def find_candidates(
        self,
        missing_targets: list[CoverageTarget],
        start_time: datetime,
        end_time: datetime,
        period: str | None = None,
        page_size: int = 50,
        max_candidates_per_target: int = 1,
        progress: Callable[[dict[str, Any]], None] | None = None,
        timeout_seconds: int | None = None,
        excluded_task_ids_by_target: dict[str, set[str]] | None = None,
    ) -> list[SupplementCandidate]:
        candidates: list[SupplementCandidate] = []
        self.last_diagnostics = []
        max_candidates_per_target = max(1, int(max_candidates_per_target or 1))
        excluded_task_ids_by_target = {
            str(key): {str(task_id) for task_id in value}
            for key, value in (excluded_task_ids_by_target or {}).items()
        }
        deadline = time.monotonic() + timeout_seconds if timeout_seconds and timeout_seconds > 0 else None
        cbj_mode_cache: dict[str, str] = {}
        cbj_api_field_cache: dict[str, tuple[set[str], str]] = {}
        cbj_source_cache: dict[str, str] = {}
        status_cache: dict[tuple[str, str], str] = {}
        current_period_flag_cache: dict[tuple[str, str], bool | None] = {}
        candidate_task_ids_by_target: dict[str, set[str]] = {}
        candidate_tax_nos_by_target: dict[str, set[str]] = {}
        grouped_targets = list(self._group_targets_by_query_filter(missing_targets).items())
        group_count = len(grouped_targets)
        for group_index, ((query_field, query_id, taxpayer_type), targets) in enumerate(grouped_targets, start=1):
            if deadline and time.monotonic() >= deadline:
                for (remaining_query_field, remaining_query_id, remaining_taxpayer_type), remaining_targets in grouped_targets[
                    group_index - 1 :
                ]:
                    for target in remaining_targets:
                        self.last_diagnostics.append(
                            self._new_diagnostic(
                                target,
                                remaining_query_field,
                                remaining_query_id,
                                remaining_taxpayer_type,
                                len(remaining_targets),
                                reason="supplement_search_timeout",
                            )
                        )
                if progress:
                    progress(
                        {
                            "event": "timeout",
                            "groupIndex": group_index,
                            "groupCount": group_count,
                            "queryField": query_field,
                            "queryValue": str(query_id),
                            "taxTypeId": str(query_id) if query_field == "taxTypeId" else "",
                            "taxId": str(query_id) if query_field == "taxId" else "",
                            "taxPayerType": taxpayer_type,
                        }
                    )
                break
            query_started = time.monotonic()
            if progress:
                progress(
                    {
                        "event": "query_start",
                        "groupIndex": group_index,
                        "groupCount": group_count,
                        "queryField": query_field,
                        "queryValue": str(query_id),
                        "taxTypeId": str(query_id) if query_field == "taxTypeId" else "",
                        "taxId": str(query_id) if query_field == "taxId" else "",
                        "taxPayerType": taxpayer_type,
                        "period": period or "",
                        "targetKeys": [target.key for target in targets],
                    }
                )
            tasks = self.query.find_collect_tasks_by_filters(
                start_time=start_time,
                end_time=end_time,
                period=period or None,
                tax_type_id=query_id if query_field == "taxTypeId" else None,
                tax_id=query_id if query_field == "taxId" else None,
                taxpayer_type=taxpayer_type or None,
                task_status="SUCCESS",
                page_size=page_size,
            )
            if progress:
                progress(
                    {
                        "event": "query_done",
                        "groupIndex": group_index,
                        "groupCount": group_count,
                        "queryField": query_field,
                        "queryValue": str(query_id),
                        "taxTypeId": str(query_id) if query_field == "taxTypeId" else "",
                        "taxId": str(query_id) if query_field == "taxId" else "",
                        "taxPayerType": taxpayer_type,
                        "period": period or "",
                        "queriedCount": len(tasks),
                        "elapsedSeconds": round(time.monotonic() - query_started, 2),
                    }
                )
            for target in targets:
                target_seen_task_ids = candidate_task_ids_by_target.setdefault(target.key, set())
                target_seen_tax_nos = candidate_tax_nos_by_target.setdefault(target.key, set())
                target_excluded_task_ids = excluded_task_ids_by_target.get(target.key, set())
                if len(target_seen_task_ids) >= max_candidates_per_target:
                    continue
                if deadline and time.monotonic() >= deadline:
                    diagnostic = self._new_diagnostic(
                        target,
                        query_field,
                        query_id,
                        taxpayer_type,
                        len(targets),
                        reason="supplement_search_timeout",
                    )
                    diagnostic["queriedCount"] = len(tasks)
                    self.last_diagnostics.append(diagnostic)
                    if progress:
                        progress({"event": "target_done", "diagnostic": diagnostic})
                    continue
                diagnostic = self._new_diagnostic(target, query_field, query_id, taxpayer_type, len(targets))
                diagnostic["queriedCount"] = len(tasks)
                target_candidate_pool: list[SupplementCandidate] = []
                pool_tax_nos: set[str] = set()
                remaining_candidates = max_candidates_per_target - len(target_seen_task_ids)
                for task in tasks:
                    if task.task_id in target_seen_task_ids:
                        continue
                    if task.task_id in target_excluded_task_ids:
                        diagnostic["excludedTaskCount"] = int(diagnostic.get("excludedTaskCount") or 0) + 1
                        diagnostic.setdefault("excludedTaskIds", []).append(task.task_id)
                        continue
                    task_tax_no = str(task.tax_no or "").strip()
                    if len(target_candidate_pool) >= remaining_candidates:
                        if not task_tax_no or task_tax_no in target_seen_tax_nos or task_tax_no in pool_tax_nos:
                            continue
                    task_tax_type = self._infer_task_tax_type(
                        task,
                        target,
                        cbj_mode_cache,
                        cbj_api_field_cache,
                        cbj_source_cache,
                    )
                    if target.tax_type in CBJ_TAX_TYPES:
                        source_counts = diagnostic.setdefault("cbjModeSourceCounts", {})
                        source = cbj_source_cache.get(task.task_id) or "unknown"
                        source_counts[source] = source_counts.get(source, 0) + 1
                    if not self._task_matches_target_tax_type(task_tax_type, target):
                        task_type_counts = diagnostic["taskTaxTypeCounts"]
                        task_type_key = task_tax_type or "unknown"
                        task_type_counts[task_type_key] = task_type_counts.get(task_type_key, 0) + 1
                        continue
                    parse_status = self._extract_status_cached(
                        task,
                        target,
                        status_cache,
                        current_period_flag_cache,
                    )
                    status_counts = diagnostic["statusCounts"]
                    status_counts[parse_status] = status_counts.get(parse_status, 0) + 1
                    status_task_ids = diagnostic.setdefault("statusTaskIds", {}).setdefault(parse_status, [])
                    if len(status_task_ids) < 20 and task.task_id not in status_task_ids:
                        status_task_ids.append(task.task_id)
                    if not self._task_matches_target_declaration_status(parse_status, target):
                        continue
                    candidate = SupplementCandidate(
                        target_key=target.key,
                        tax_type=target.tax_type,
                        tax_type_name=target.tax_type_name,
                        declaration_status=target.declaration_status,
                        declaration_status_name=target.declaration_status_name,
                        task_id=task.task_id,
                        tax_no=task.tax_no,
                        period=task.period or "",
                        task_status=task.status or "",
                        backend_tax_type_id=str(query_id) if query_field == "taxTypeId" else "",
                        backend_tax_id=str(query_id) if query_field == "taxId" else "",
                        backend_query_field=query_field,
                        created_stamp=task.created_stamp,
                        parse_status=parse_status,
                        reason="matched_backend_result_json",
                    )
                    target_candidate_pool.append(candidate)
                    if task_tax_no:
                        pool_tax_nos.add(task_tax_no)
                    if (
                        len(target_candidate_pool) >= remaining_candidates
                        and len(target_seen_tax_nos | pool_tax_nos) >= max_candidates_per_target
                    ):
                        break
                target_candidates = select_diverse_supplement_candidates(
                    target_candidate_pool,
                    remaining_candidates,
                    existing_tax_nos=target_seen_tax_nos,
                    existing_task_ids=target_seen_task_ids,
                )
                for candidate in target_candidates:
                    candidates.append(candidate)
                    target_seen_task_ids.add(candidate.task_id)
                    candidate_tax_no = str(candidate.tax_no or "").strip()
                    if candidate_tax_no:
                        target_seen_tax_nos.add(candidate_tax_no)
                    diagnostic.setdefault("matchedTaskIds", []).append(candidate.task_id)
                    if not diagnostic["matchedTaskId"]:
                        diagnostic["matchedTaskId"] = candidate.task_id
                    diagnostic["reason"] = "matched_backend_result_json"
                if target_candidates:
                    diagnostic["candidateCount"] = len(target_candidates)
                if not diagnostic["matchedTaskId"]:
                    if not tasks:
                        diagnostic["reason"] = "no_success_collect_tasks"
                    elif diagnostic.get("excludedTaskCount") and not diagnostic["statusCounts"] and not diagnostic["taskTaxTypeCounts"]:
                        diagnostic["reason"] = "excluded_known_failed_candidates"
                    elif diagnostic["statusCounts"]:
                        diagnostic["reason"] = "declaration_status_not_matched"
                    elif diagnostic["taskTaxTypeCounts"]:
                        diagnostic["reason"] = "target_tax_type_not_matched"
                    else:
                        diagnostic["reason"] = "declaration_status_unknown"
                self.last_diagnostics.append(diagnostic)
                if progress:
                    progress({"event": "target_done", "diagnostic": diagnostic})
        return candidates

    def _new_diagnostic(
        self,
        target: CoverageTarget,
        query_field: str,
        query_id: int | str,
        taxpayer_type: str,
        shared_count: int,
        reason: str = "",
    ) -> dict[str, Any]:
        return {
            "targetKey": target.key,
            "taxType": target.tax_type,
            "taxTypeName": target.tax_type_name,
            "declarationStatus": target.declaration_status,
            "backendQueryField": query_field,
            "backendQueryValue": str(query_id),
            "backendTaxTypeId": str(query_id) if query_field == "taxTypeId" else "",
            "backendTaxId": str(query_id) if query_field == "taxId" else "",
            "backendTaxPayerType": taxpayer_type,
            "queriedCount": 0,
            "statusCounts": {},
            "statusTaskIds": {},
            "taskTaxTypeCounts": {},
            "cbjModeSourceCounts": {},
            "requiredFieldMissingCount": 0,
            "matchedTaskId": "",
            "matchedTaskIds": [],
            "candidateCount": 0,
            "reason": reason,
            "queryShared": shared_count > 1,
        }

    def _group_targets_by_query_filter(self, targets: list[CoverageTarget]) -> dict[tuple[str, int, str], list[CoverageTarget]]:
        grouped: dict[tuple[str, int, str], list[CoverageTarget]] = {}
        for target in targets:
            if target.backend_tax_ids:
                for tax_id in target.backend_tax_ids:
                    grouped.setdefault(("taxId", int(tax_id), target.backend_taxpayer_type), []).append(target)
                continue
            for tax_type_id in target.backend_tax_type_ids:
                grouped.setdefault(("taxTypeId", int(tax_type_id), target.backend_taxpayer_type), []).append(target)
        return grouped

    def _extract_status_cached(
        self,
        task: AdminTask,
        target: CoverageTarget,
        cache: dict[tuple[str, str], str],
        current_period_flag_cache: dict[tuple[str, str], bool | None],
    ) -> str:
        if target.declaration_status == DECLARATION_ANY:
            return DECLARATION_UNKNOWN
        key = (task.task_id, target.tax_type)
        if key in cache:
            return cache[key]
        parse_status = self.extractor.extract(task)
        if parse_status == DECLARATION_UNKNOWN:
            parse_status = self._extract_from_execution_logs(task, target, current_period_flag_cache)
        cache[key] = parse_status
        return parse_status

    def _extract_from_execution_logs(
        self,
        task: AdminTask,
        target: CoverageTarget,
        current_period_flag_cache: dict[tuple[str, str], bool | None],
    ) -> str:
        if target.tax_type not in EXECUTION_LOG_STATUS_TAX_TYPES:
            return DECLARATION_UNKNOWN
        tax_code = execution_log_tax_code_for_target(target)
        cache_key = (task.task_id, tax_code)
        if cache_key not in current_period_flag_cache:
            try:
                current_period_flag_cache[cache_key] = fetch_current_period_flag(
                    task.task_id,
                    tax_code=tax_code,
                    timeout=self.query.timeout,
                )
            except Exception:
                current_period_flag_cache[cache_key] = None
        flag = current_period_flag_cache[cache_key]
        if flag is True:
            return DECLARATION_FILED
        if flag is False:
            return DECLARATION_UNFILED
        return DECLARATION_UNKNOWN

    def _task_matches_target_tax_type(self, task_tax_type: str, target: CoverageTarget) -> bool:
        if target.tax_type in CBJ_TAX_TYPES:
            return task_tax_type == target.tax_type
        if target.tax_type not in {"VAT_GENERAL", "VAT_SMALL"}:
            return True
        return task_tax_type == target.tax_type

    def _task_matches_target_declaration_status(self, parse_status: str, target: CoverageTarget) -> bool:
        if target.declaration_status == DECLARATION_ANY:
            return True
        if parse_status == DECLARATION_UNKNOWN and target.declaration_status == DECLARATION_UNFILED:
            return True
        if (
            parse_status == DECLARATION_UNKNOWN
            and target.tax_type == "CIT_A"
            and target.declaration_status == DECLARATION_FILED
        ):
            return True
        return parse_status == target.declaration_status

    def _infer_task_tax_type(
        self,
        task: AdminTask,
        target: CoverageTarget | None = None,
        cbj_mode_cache: dict[str, str] | None = None,
        cbj_api_field_cache: dict[str, tuple[set[str], str]] | None = None,
        cbj_source_cache: dict[str, str] | None = None,
    ) -> str:
        if target and target.tax_type in CBJ_TAX_TYPES:
            return self._infer_cbj_task_tax_type(
                task,
                cbj_mode_cache,
                cbj_api_field_cache,
                cbj_source_cache,
            )
        taxpayer_type = self._task_taxpayer_type(task)
        if taxpayer_type == "NORMAL_TAXPAYER":
            return "VAT_GENERAL"
        if taxpayer_type == "SMALL_TAXPAYER":
            return "VAT_SMALL"
        text = " ".join(_iter_text_values(task.raw)).lower()
        if not text:
            return ""
        is_general = any(marker.lower() in text for marker in VAT_GENERAL_MARKERS)
        is_small = any(marker.lower() in text for marker in VAT_SMALL_MARKERS)
        if is_general and not is_small:
            return "VAT_GENERAL"
        if is_small and not is_general:
            return "VAT_SMALL"
        return ""

    def _infer_cbj_task_tax_type(
        self,
        task: AdminTask,
        cbj_mode_cache: dict[str, str] | None = None,
        cbj_api_field_cache: dict[str, tuple[set[str], str]] | None = None,
        cbj_source_cache: dict[str, str] | None = None,
    ) -> str:
        mode = self._fetch_cbj_mode(task, cbj_mode_cache)
        if mode == "annual":
            self._record_cbj_source(task, "execution_log_annual", cbj_source_cache)
            return "CBJ_ANNUAL"
        if mode == "backend":
            self._record_cbj_source(task, "execution_log_personal", cbj_source_cache)
            return "CBJ_PERSONAL"
        if self._cbj_personal_fields_present(task):
            self._record_cbj_source(task, "task_list_fields", cbj_source_cache)
            return "CBJ_PERSONAL"
        api_fields, api_source = self._cbj_personal_fields_present_from_api(task, cbj_api_field_cache)
        if api_fields:
            self._record_cbj_source(task, api_source, cbj_source_cache)
            return "CBJ_PERSONAL"
        backend_ids = self._task_backend_tax_type_ids(task)
        if "31" in backend_ids and "26" not in backend_ids:
            self._record_cbj_source(task, "backend_tax_type_31", cbj_source_cache)
            return "CBJ_ANNUAL"
        if backend_ids.intersection(CBJ_BACKEND_TAX_TYPE_IDS) or self._task_backend_tax_ids(task).intersection(
            CBJ_BACKEND_TAX_IDS
        ):
            self._record_cbj_source(task, api_source or "backend_tax_id_unknown", cbj_source_cache)
            return "CBJ_UNKNOWN"
        self._record_cbj_source(task, api_source or "unknown", cbj_source_cache)
        return ""

    def _fetch_cbj_mode(self, task: AdminTask, cbj_mode_cache: dict[str, str] | None = None) -> str:
        cache = cbj_mode_cache if cbj_mode_cache is not None else {}
        if task.task_id in cache:
            return cache[task.task_id]
        try:
            mode = fetch_cbj_mode_from_task_logs(task.task_id, timeout=self.query.timeout) or ""
        except Exception:
            mode = ""
        cache[task.task_id] = mode
        return mode

    def _cbj_personal_fields_present(self, task: AdminTask) -> set[str]:
        text = "\n".join(_iter_text_values(_parse_nested_json(task.raw))).lower()
        return {field for field in CBJ_PERSONAL_REQUIRED_FIELDS if field.lower() in text}

    def _cbj_personal_fields_present_from_api(
        self,
        task: AdminTask,
        cache: dict[str, tuple[set[str], str]] | None = None,
    ) -> tuple[set[str], str]:
        if not task.task_id:
            return set(), "api_result_missing"
        local_cache = cache if cache is not None else {}
        if task.task_id in local_cache:
            return local_cache[task.task_id]
        try:
            response = self.api_client.fetch_by_task_id(task.task_id)
        except Exception:
            result = (set(), "api_error")
            local_cache[task.task_id] = result
            return result
        if not isinstance(response, dict) or response.get("error"):
            result = (set(), "api_error" if isinstance(response, dict) and response.get("error") else "api_result_missing")
            local_cache[task.task_id] = result
            return result
        search_roots = {
            "data": response.get("data") or {},
            "raw_resultJson": response.get("raw_resultJson") or {},
        }
        text = "\n".join(_iter_text_values(_parse_nested_json(search_roots))).lower()
        fields = {field for field in CBJ_PERSONAL_REQUIRED_FIELDS if field.lower() in text}
        source = "api_result_fields" if set(CBJ_PERSONAL_REQUIRED_FIELDS).issubset(fields) else "api_result_missing"
        result = (fields if source == "api_result_fields" else set(), source)
        local_cache[task.task_id] = result
        return result

    def _record_cbj_source(
        self,
        task: AdminTask,
        source: str,
        cache: dict[str, str] | None = None,
    ) -> None:
        if cache is not None and task.task_id:
            cache[task.task_id] = source

    def _missing_cbj_personal_fields(self, task: AdminTask) -> list[str]:
        present = self._cbj_personal_fields_present(task)
        return [field for field in CBJ_PERSONAL_REQUIRED_FIELDS if field not in present]

    def _task_taxpayer_type(self, task: AdminTask) -> str:
        for key in ("taxPayerType", "taxpayerType"):
            value = task.raw.get(key)
            if value not in (None, ""):
                return str(value).strip().upper()
        return ""

    def _task_backend_tax_type_ids(self, task: AdminTask) -> set[str]:
        ids: set[str] = set()
        for key in ("taxTypeId", "tTaxTypeId"):
            value = task.raw.get(key)
            if value not in (None, ""):
                ids.add(str(value))
        for key in ("taxTypeIds", "tTaxTypeIds"):
            value = task.raw.get(key)
            if isinstance(value, list):
                ids.update(str(item) for item in value if item not in (None, ""))
            elif value not in (None, ""):
                ids.add(str(value))
        for rel in task.raw.get("taskTaxRelVOList") or []:
            if not isinstance(rel, dict):
                continue
            value = rel.get("tTaxTypeId") or rel.get("taxTypeId")
            if value not in (None, ""):
                ids.add(str(value))
        return ids

    def _task_backend_tax_ids(self, task: AdminTask) -> set[str]:
        ids: set[str] = set()
        for key in ("taxId", "taxIds"):
            value = task.raw.get(key)
            if isinstance(value, list):
                ids.update(str(item) for item in value if item not in (None, ""))
            elif value not in (None, ""):
                ids.add(str(value))
        return ids


def _iter_text_values(value: Any) -> list[str]:
    values: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            values.append(str(key))
            values.extend(_iter_text_values(item))
    elif isinstance(value, list):
        for item in value:
            values.extend(_iter_text_values(item))
    elif value is not None:
        values.append(str(value))
    return values


def _parse_nested_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _parse_nested_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_parse_nested_json(item) for item in value]
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text or text[0:1] not in {"{", "["}:
        return value
    try:
        return _parse_nested_json(json.loads(text))
    except Exception:
        return value


def select_diverse_supplement_candidates(
    candidates: list[SupplementCandidate],
    limit: int,
    existing_tax_nos: set[str] | None = None,
    existing_task_ids: set[str] | None = None,
) -> list[SupplementCandidate]:
    limit = max(1, int(limit or 1))
    selected: list[SupplementCandidate] = []
    selected_task_ids = {str(task_id).strip() for task_id in (existing_task_ids or set()) if str(task_id or "").strip()}
    selected_tax_nos = {str(tax_no).strip() for tax_no in (existing_tax_nos or set()) if str(tax_no or "").strip()}

    for candidate in candidates:
        task_id = str(candidate.task_id or "").strip()
        tax_no = str(candidate.tax_no or "").strip()
        if not task_id or task_id in selected_task_ids:
            continue
        if tax_no and tax_no in selected_tax_nos:
            continue
        selected.append(candidate)
        selected_task_ids.add(task_id)
        if tax_no:
            selected_tax_nos.add(tax_no)
        if len(selected) >= limit:
            return selected

    for candidate in candidates:
        task_id = str(candidate.task_id or "").strip()
        if not task_id or task_id in selected_task_ids:
            continue
        selected.append(candidate)
        selected_task_ids.add(task_id)
        if len(selected) >= limit:
            return selected

    return selected


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
                    "backendTaxId": candidate.backend_tax_id,
                    "backendQueryField": candidate.backend_query_field,
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
    suffix = "".join(ch if ch.isalnum() else "_" for ch in candidate.target_key).strip("_") or "supplement"
    key = f"{base_key}__coverage__{suffix}"
    existing = items.get(key)
    existing_task_id = ((existing or {}).get("collect") or {}).get("verifyTaskId") if existing else ""
    if not existing_task_id or existing_task_id == candidate.task_id:
        return key

    task_suffix = "".join(ch if ch.isalnum() else "_" for ch in candidate.task_id).strip("_")
    return f"{key}__{task_suffix}"
