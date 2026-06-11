from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .models import (
    DECLARATION_ANY,
    DECLARATION_FILED,
    DECLARATION_STATUS_LABELS,
    DECLARATION_UNFILED,
    DECLARATION_UNKNOWN,
    CoverageHit,
    CoverageTarget,
)
from .registry import build_coverage_targets, normalize_tax_type, normalize_tax_type_keys, tax_type_from_form_id


def analyze_run_coverage(
    run_dir: str | Path,
    report_root: str | Path | None = None,
    targets: list[CoverageTarget] | None = None,
) -> dict[str, Any]:
    run_path = Path(run_dir)
    state = load_json(run_path / "state.json")
    report_base = Path(report_root) if report_root else Path("output") / "reports"
    selected_tax_types = normalize_tax_type_keys(state.get("coverageTaxTypes") or [])
    coverage_targets = targets or build_coverage_targets(tax_types=selected_tax_types)
    lookup = {(target.tax_type, target.declaration_status): target for target in coverage_targets}
    hits: list[CoverageHit] = []

    for tax_no, item in sorted((state.get("items") or {}).items()):
        collect = item.get("collect") or {}
        account = collect.get("account") or {}
        display_tax_no = str(item.get("taxNo") or tax_no)
        task_ids = item_verification_task_ids(item)
        if not task_ids:
            continue
        verify = item.get("verify") or {}
        for task_id in task_ids:
            task_verify = task_verify_entry(item, task_id)
            if not task_verify and len(task_ids) == 1:
                task_verify = verify
            if not verify_record_is_success(task_verify):
                continue
            report_paths = task_verify.get("reportPaths") or []
            task_reports = load_task_reports_from_paths(report_paths) if report_paths else load_task_reports(report_base, task_id)
            for report_path, report in task_reports:
                form_id = str(report.get("batch_id") or report.get("form_id") or "")
                tax_type = normalize_tax_type(report.get("tax_type"), form_id=form_id)
                declaration_status = normalize_declaration_status(
                    report.get("declaration_status") or report.get("declarationStatus"),
                    current_period_flag=report.get("current_period_flag"),
                    has_field_results=bool(report.get("field_results")),
                )
                target = lookup.get((tax_type, declaration_status)) or lookup.get((tax_type, DECLARATION_ANY))
                if target is None:
                    continue
                hits.append(
                    CoverageHit(
                        target_key=target.key,
                        tax_type=target.tax_type,
                        tax_type_name=target.tax_type_name,
                        declaration_status=target.declaration_status,
                        declaration_status_name=target.declaration_status_name,
                        tax_no=display_tax_no,
                        task_id=task_id,
                        cust_name=str(account.get("custName") or ""),
                        region=str(account.get("areaCode") or "")[:2],
                        form_id=form_id,
                        form_name=str(report.get("form_name") or form_id),
                        source="verified_report",
                        source_path=str(report_path),
                    )
                )

    hits_by_target: dict[str, list[CoverageHit]] = {}
    for hit in dedupe_hits(hits):
        hits_by_target.setdefault(hit.target_key, []).append(hit)

    target_rows = []
    missing_targets = []
    for target in coverage_targets:
        target_hits = hits_by_target.get(target.key, [])
        row = {
            **target.to_dict(),
            "covered": bool(target_hits),
            "hitCount": len(target_hits),
            "examples": [hit.to_dict() for hit in target_hits[:5]],
        }
        target_rows.append(row)
        if not target_hits:
            missing_targets.append(target.to_dict())

    supplement = supplement_status_payload(state, missing_targets)
    return {
        "runId": state.get("runId") or run_path.name,
        "period": state.get("period") or "",
        "generatedAt": datetime.now().isoformat(timespec="seconds"),
        "summary": {
            "totalTargets": len(coverage_targets),
            "coveredTargets": len(coverage_targets) - len(missing_targets),
            "missingTargets": len(missing_targets),
            "hitCount": sum(len(items) for items in hits_by_target.values()),
        },
        "targets": target_rows,
        "hits": [hit.to_dict() for items in hits_by_target.values() for hit in items],
        "missingTargets": missing_targets,
        "supplement": supplement,
    }


def supplement_status_payload(state: dict[str, Any], missing_targets: list[dict[str, Any]]) -> dict[str, Any]:
    recorded = state.get("coverageSupplement") or {}
    if isinstance(recorded, dict) and recorded:
        payload = {"enabled": True, **recorded}
        payload.setdefault("status", "unknown")
        payload.setdefault("message", "")
        return payload
    return {
        "enabled": True,
        "status": "not_run" if missing_targets else "not_needed",
        "message": (
            "后台补齐查询尚未在本次批量流程中执行。"
            if missing_targets
            else "当前批次已覆盖全部目标。"
        ),
    }


def verify_record_is_success(verify: dict[str, Any]) -> bool:
    if not isinstance(verify, dict):
        return False
    if str(verify.get("status") or "") != "success":
        return False
    try:
        return_code = int(verify.get("returnCode") or 0)
    except (TypeError, ValueError):
        return False
    return return_code == 0


def write_coverage_status(
    run_dir: str | Path,
    report_root: str | Path | None = None,
    targets: list[CoverageTarget] | None = None,
) -> dict[str, Any]:
    run_path = Path(run_dir)
    payload = analyze_run_coverage(run_path, report_root=report_root, targets=targets)
    (run_path / "coverage_status.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_coverage_csv(payload, run_path / "coverage_matrix.csv")
    write_missing_coverage_csv(payload, run_path / "coverage_missing.csv")
    return payload


def write_coverage_csv(payload: dict[str, Any], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "taxType",
                "taxTypeName",
                "declarationStatusName",
                "covered",
                "hitCount",
                "exampleTaxNo",
                "exampleTaskId",
                "exampleFormId",
                "exampleSourcePath",
            ],
        )
        writer.writeheader()
        for target in payload.get("targets") or []:
            examples = target.get("examples") or []
            example = examples[0] if examples else {}
            writer.writerow(
                {
                    "taxType": target.get("taxType") or "",
                    "taxTypeName": target.get("taxTypeName") or "",
                    "declarationStatusName": target.get("declarationStatusName") or "",
                    "covered": "Y" if target.get("covered") else "N",
                    "hitCount": target.get("hitCount") or 0,
                    "exampleTaxNo": example.get("taxNo") or "",
                    "exampleTaskId": example.get("taskId") or "",
                    "exampleFormId": example.get("formId") or "",
                    "exampleSourcePath": example.get("sourcePath") or "",
                }
            )


def write_missing_coverage_csv(payload: dict[str, Any], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "taxType",
                "taxTypeName",
                "declarationStatusName",
                "backendTaxTypeIds",
                "backendTaxIds",
                "notes",
                "supplementStatus",
                "supplementReason",
            ],
        )
        writer.writeheader()
        supplement = payload.get("supplement") or {}
        diagnostics = {str(item.get("targetKey") or ""): item for item in supplement.get("diagnostics") or []}
        source_readiness = {
            str(item.get("targetKey") or ""): item
            for item in supplement.get("sourceReadiness") or []
            if isinstance(item, dict)
        }
        for target in payload.get("missingTargets") or []:
            target_key = str(target.get("key") or "")
            diag = diagnostics.get(target_key) or {}
            readiness = source_readiness.get(target_key) or {}
            writer.writerow(
                {
                    "taxType": target.get("taxType") or "",
                    "taxTypeName": target.get("taxTypeName") or "",
                    "declarationStatusName": target.get("declarationStatusName") or "",
                    "backendTaxTypeIds": ",".join(str(item) for item in target.get("backendTaxTypeIds") or []),
                    "backendTaxIds": ",".join(str(item) for item in target.get("backendTaxIds") or []),
                    "notes": target.get("notes") or "",
                    "supplementStatus": supplement.get("status") or "",
                    "supplementReason": format_source_readiness_reason(readiness)
                    or diag.get("reason")
                    or supplement.get("message")
                    or "",
                }
            )


def format_source_readiness_reason(readiness: dict[str, Any]) -> str:
    if not readiness:
        return ""
    message = str(readiness.get("message") or "").strip()
    next_action = str(readiness.get("nextAction") or "").strip()
    if message and next_action:
        return f"{message} 下一步：{next_action}"
    return message or next_action


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def collect_task_ids(collect: dict[str, Any] | None) -> list[str]:
    collect = collect or {}
    values: list[Any] = []
    values.extend(collect.get("verifyTaskIds") or [])
    for key in ("verifyTaskId", "taskId"):
        value = collect.get(key)
        if value:
            values.insert(0, value)
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def item_verification_task_ids(item: dict[str, Any]) -> list[str]:
    collect = item.get("collect") or {}
    task_ids = collect_task_ids(collect)
    if item.get("multiTaskItemKeys") and collect.get("verifyTaskId"):
        return [str(collect.get("verifyTaskId"))]
    return task_ids


def task_verify_entry(item: dict[str, Any], task_id: str) -> dict[str, Any]:
    verify_tasks = item.get("verifyTasks") or {}
    if isinstance(verify_tasks, dict):
        entry = verify_tasks.get(str(task_id)) or {}
        return entry if isinstance(entry, dict) else {}
    if isinstance(verify_tasks, list):
        for entry in verify_tasks:
            if isinstance(entry, dict) and str(entry.get("taskId") or "") == str(task_id):
                return entry
    return {}


def load_task_reports(report_root: Path, task_id: str) -> list[tuple[Path, dict[str, Any]]]:
    task_dir = report_root / str(task_id)
    if not task_dir.exists():
        return []
    reports: list[tuple[Path, dict[str, Any]]] = []
    latest_by_batch: dict[str, tuple[Path, dict[str, Any], float]] = {}
    for path in task_dir.glob("*_compare_*.json"):
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(report, dict):
            continue
        batch_id = str(report.get("batch_id") or tax_type_from_form_id(path.name) or path.stem)
        stamp = path.stat().st_mtime
        current = latest_by_batch.get(batch_id)
        if current is None or stamp > current[2]:
            latest_by_batch[batch_id] = (path, report, stamp)
    for path, report, _stamp in latest_by_batch.values():
        reports.append((path, report))
    return sorted(reports, key=lambda item: str(item[0]))


def load_task_reports_from_paths(paths: list[Any]) -> list[tuple[Path, dict[str, Any]]]:
    reports: list[tuple[Path, dict[str, Any]]] = []
    for value in paths:
        path = Path(str(value or ""))
        if not path.exists():
            continue
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(report, dict):
            reports.append((path, report))
    return sorted(reports, key=lambda item: str(item[0]))


def normalize_declaration_status(
    value: Any,
    current_period_flag: Any = None,
    has_field_results: bool = False,
) -> str:
    if value is False:
        return DECLARATION_UNFILED
    if value is True:
        return DECLARATION_FILED
    if current_period_flag is False:
        return DECLARATION_UNFILED
    if current_period_flag is True:
        return DECLARATION_FILED
    raw = str(value or "").strip()
    text = raw.lower()
    if text == DECLARATION_ANY:
        return DECLARATION_ANY
    if "不区分" in raw:
        return DECLARATION_ANY
    if text in {"filed", "submitted", "success", "collected"}:
        return DECLARATION_FILED
    if text in {"unfiled", "not_filed", "no_declaration", "no_need", "not_collected"}:
        return DECLARATION_UNFILED
    if "未申报" in raw or "无需申报" in raw or "未取数" in raw or "not filed" in text:
        return DECLARATION_UNFILED
    if "已申报" in raw or "申报成功" in raw or "已取数" in raw or "filed" in text:
        return DECLARATION_FILED
    return DECLARATION_UNFILED


def dedupe_hits(hits: list[CoverageHit]) -> list[CoverageHit]:
    result: list[CoverageHit] = []
    seen: set[tuple[str, str, str, str]] = set()
    for hit in hits:
        key = (hit.target_key, hit.tax_no, hit.task_id, hit.form_id)
        if key in seen:
            continue
        seen.add(key)
        result.append(hit)
    return result


def status_label(status: str) -> str:
    return DECLARATION_STATUS_LABELS.get(status, status)
