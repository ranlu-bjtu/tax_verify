from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


DECLARATION_FILED = "filed"
DECLARATION_UNFILED = "unfiled"
DECLARATION_UNKNOWN = "unknown"
DECLARATION_ANY = "any"

DECLARATION_STATUS_LABELS = {
    DECLARATION_FILED: "已申报",
    DECLARATION_UNFILED: "未申报",
    DECLARATION_UNKNOWN: "未知",
    DECLARATION_ANY: "不区分申报状态",
}


@dataclass(frozen=True)
class TaxTypeDefinition:
    tax_type: str
    tax_type_name: str
    form_ids: tuple[str, ...]
    backend_tax_type_ids: tuple[int, ...]
    backend_tax_ids: tuple[int, ...] = field(default_factory=tuple)
    backend_taxpayer_type: str = ""
    coverage_statuses: tuple[str, ...] = field(default_factory=tuple)
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "taxType": self.tax_type,
            "taxTypeName": self.tax_type_name,
            "formIds": list(self.form_ids),
            "backendTaxTypeIds": list(self.backend_tax_type_ids),
            "backendTaxIds": list(self.backend_tax_ids),
            "backendTaxPayerType": self.backend_taxpayer_type,
            "coverageStatuses": list(self.coverage_statuses),
            "notes": self.notes,
        }


@dataclass(frozen=True)
class CoverageTarget:
    tax_type: str
    tax_type_name: str
    declaration_status: str
    declaration_status_name: str
    form_ids: tuple[str, ...] = field(default_factory=tuple)
    backend_tax_type_ids: tuple[int, ...] = field(default_factory=tuple)
    backend_tax_ids: tuple[int, ...] = field(default_factory=tuple)
    backend_taxpayer_type: str = ""
    requires_tax_bureau: bool = True
    notes: str = ""

    @property
    def key(self) -> str:
        return f"{self.tax_type}:{self.declaration_status}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "taxType": self.tax_type,
            "taxTypeName": self.tax_type_name,
            "declarationStatus": self.declaration_status,
            "declarationStatusName": self.declaration_status_name,
            "formIds": list(self.form_ids),
            "backendTaxTypeIds": list(self.backend_tax_type_ids),
            "backendTaxIds": list(self.backend_tax_ids),
            "backendTaxPayerType": self.backend_taxpayer_type,
            "requiresTaxBureau": self.requires_tax_bureau,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class CoverageHit:
    target_key: str
    tax_type: str
    tax_type_name: str
    declaration_status: str
    declaration_status_name: str
    tax_no: str
    task_id: str
    cust_name: str = ""
    region: str = ""
    form_id: str = ""
    form_name: str = ""
    source: str = ""
    source_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "targetKey": self.target_key,
            "taxType": self.tax_type,
            "taxTypeName": self.tax_type_name,
            "declarationStatus": self.declaration_status,
            "declarationStatusName": self.declaration_status_name,
            "taxNo": self.tax_no,
            "taskId": self.task_id,
            "custName": self.cust_name,
            "region": self.region,
            "formId": self.form_id,
            "formName": self.form_name,
            "source": self.source,
            "sourcePath": self.source_path,
        }


@dataclass(frozen=True)
class SupplementCandidate:
    target_key: str
    tax_type: str
    tax_type_name: str
    declaration_status: str
    declaration_status_name: str
    task_id: str
    tax_no: str
    period: str = ""
    task_status: str = ""
    backend_tax_type_id: str = ""
    backend_tax_id: str = ""
    backend_query_field: str = "taxTypeId"
    created_stamp: int | None = None
    parse_status: str = DECLARATION_UNKNOWN
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "targetKey": self.target_key,
            "taxType": self.tax_type,
            "taxTypeName": self.tax_type_name,
            "declarationStatus": self.declaration_status,
            "declarationStatusName": self.declaration_status_name,
            "taskId": self.task_id,
            "taxNo": self.tax_no,
            "period": self.period,
            "taskStatus": self.task_status,
            "backendTaxTypeId": self.backend_tax_type_id,
            "backendTaxId": self.backend_tax_id,
            "backendQueryField": self.backend_query_field,
            "createdStamp": self.created_stamp,
            "parseStatus": self.parse_status,
            "reason": self.reason,
        }
