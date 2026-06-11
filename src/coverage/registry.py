from __future__ import annotations

from .models import (
    DECLARATION_ANY,
    DECLARATION_FILED,
    DECLARATION_STATUS_LABELS,
    DECLARATION_UNFILED,
    CoverageTarget,
    TaxTypeDefinition,
)


CBJ_TAX_TYPES = {"CBJ_PERSONAL", "CBJ_ANNUAL"}
COVERAGE_COLLECT_STATUS_COLLECTED = "collected"
COVERAGE_COLLECT_STATUS_NOT_COLLECTED = "not_collected"
DEFAULT_COVERAGE_COLLECT_STATUSES = (
    COVERAGE_COLLECT_STATUS_COLLECTED,
    COVERAGE_COLLECT_STATUS_NOT_COLLECTED,
)
COVERAGE_COLLECT_STATUS_TO_DECLARATION = {
    COVERAGE_COLLECT_STATUS_COLLECTED: DECLARATION_FILED,
    COVERAGE_COLLECT_STATUS_NOT_COLLECTED: DECLARATION_UNFILED,
}


SUPPORTED_TAX_TYPES: tuple[TaxTypeDefinition, ...] = (
    TaxTypeDefinition(
        tax_type="VAT_GENERAL",
        tax_type_name="增值税（一般纳税人）",
        form_ids=(
            "vat_general_main",
            "vat_general_appendix1",
            "vat_general_appendix2",
            "vat_general_appendix3",
            "vat_general_appendix4",
            "vat_general_appendix5",
        ),
        backend_tax_type_ids=(),
        backend_tax_ids=(1,),
        backend_taxpayer_type="NORMAL_TAXPAYER",
        notes="Backend task-list filtering uses taxId=1 for VAT; taxpayer type distinguishes normal taxpayer tasks.",
    ),
    TaxTypeDefinition(
        tax_type="VAT_SMALL",
        tax_type_name="增值税（小规模纳税人）",
        form_ids=("vat_small_main", "vat_small_appendix1", "vat_small_appendix2"),
        backend_tax_type_ids=(),
        backend_tax_ids=(1,),
        backend_taxpayer_type="SMALL_TAXPAYER",
        notes="Backend task-list filtering uses taxId=1 for VAT; taxpayer type distinguishes small taxpayer tasks.",
    ),
    TaxTypeDefinition(
        tax_type="CIT_A",
        tax_type_name="企业所得税（A类）",
        form_ids=("cit_a_main",),
        backend_tax_type_ids=(),
        backend_tax_ids=(2,),
        notes="Backend task-list filtering uses taxId=2 for CIT A; taxTypeId is not a reliable server-side filter.",
    ),
    TaxTypeDefinition(
        tax_type="CULTURE_FEE",
        tax_type_name="文化事业建设费",
        form_ids=("culture_fee_main", "culture_fee_deduction"),
        backend_tax_type_ids=(),
        backend_tax_ids=(3,),
        notes="Backend task-list filtering uses taxId=3 for culture fee; taxTypeId is not a reliable server-side filter.",
    ),
    TaxTypeDefinition(
        tax_type="CONSUMPTION_TAX",
        tax_type_name="消费税",
        form_ids=("consumption_tax_main", "consumption_tax_surcharge"),
        backend_tax_type_ids=(),
        backend_tax_ids=(26,),
        notes="消费税当前接入两张表：消费税及附加税费申报表、消费税附加税费计算表。",
    ),
    TaxTypeDefinition(
        tax_type="CBJ_PERSONAL",
        tax_type_name="个税残保金",
        form_ids=("cbj_personal",),
        backend_tax_type_ids=(26, 31),
        backend_tax_ids=(39,),
        coverage_statuses=(DECLARATION_ANY,),
        notes="个税残保金只校验后台字段 snzzzgrs_cbj、snzzzggzze_cbj 是否返回。",
    ),
    TaxTypeDefinition(
        tax_type="CBJ_ANNUAL",
        tax_type_name="汇算清缴残保金",
        form_ids=("cbj_annual_settlement",),
        backend_tax_type_ids=(26, 31),
        backend_tax_ids=(39,),
        coverage_statuses=(DECLARATION_ANY,),
        notes="汇算清缴残保金需要进入税局年度企业所得税申报表核对 A000000、A105050。",
    ),
)


def supported_tax_types() -> list[TaxTypeDefinition]:
    return list(SUPPORTED_TAX_TYPES)


def normalize_tax_type_keys(values: list[str] | tuple[str, ...] | None = None) -> list[str]:
    if not values:
        return []
    valid = {definition.tax_type for definition in SUPPORTED_TAX_TYPES}
    name_aliases = {definition.tax_type_name: definition.tax_type for definition in SUPPORTED_TAX_TYPES}
    aliases = {
        "VAT_GENERAL": "VAT_GENERAL",
        "VAT_SMALL": "VAT_SMALL",
        "CIT_A": "CIT_A",
        "CIT": "CIT_A",
        "CULTURE_FEE": "CULTURE_FEE",
        "CONSUMPTION_TAX": "CONSUMPTION_TAX",
        "CBJ": "CBJ_PERSONAL",
        "CBJ_PERSONAL": "CBJ_PERSONAL",
        "CBJ_ANNUAL": "CBJ_ANNUAL",
    }
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        raw = str(value or "").strip()
        if not raw:
            continue
        key = aliases.get(raw.upper()) or name_aliases.get(raw) or raw.upper()
        if key not in valid or key in seen:
            continue
        seen.add(key)
        result.append(key)
    return result


def normalize_collect_status_keys(values: list[str] | tuple[str, ...] | None = None) -> list[str]:
    if not values:
        return []
    aliases = {
        "COLLECTED": COVERAGE_COLLECT_STATUS_COLLECTED,
        "FILED": COVERAGE_COLLECT_STATUS_COLLECTED,
        "SUCCESS": COVERAGE_COLLECT_STATUS_COLLECTED,
        "已取数": COVERAGE_COLLECT_STATUS_COLLECTED,
        "已申报": COVERAGE_COLLECT_STATUS_COLLECTED,
        "NOT_COLLECTED": COVERAGE_COLLECT_STATUS_NOT_COLLECTED,
        "NOT-COLLECTED": COVERAGE_COLLECT_STATUS_NOT_COLLECTED,
        "UNFILED": COVERAGE_COLLECT_STATUS_NOT_COLLECTED,
        "NO_NEED": COVERAGE_COLLECT_STATUS_NOT_COLLECTED,
        "未取数": COVERAGE_COLLECT_STATUS_NOT_COLLECTED,
        "未申报": COVERAGE_COLLECT_STATUS_NOT_COLLECTED,
    }
    result: list[str] = []
    seen: set[str] = set()
    valid = set(DEFAULT_COVERAGE_COLLECT_STATUSES)
    for value in values:
        raw = str(value or "").strip()
        if not raw:
            continue
        key = aliases.get(raw.upper()) or aliases.get(raw) or raw.lower()
        if key not in valid or key in seen:
            continue
        seen.add(key)
        result.append(key)
    return result


def declaration_statuses_for_collect_statuses(values: list[str] | tuple[str, ...] | None = None) -> tuple[str, ...]:
    selected = normalize_collect_status_keys(values) or list(DEFAULT_COVERAGE_COLLECT_STATUSES)
    statuses: list[str] = []
    seen: set[str] = set()
    for value in selected:
        status = COVERAGE_COLLECT_STATUS_TO_DECLARATION[value]
        if status in seen:
            continue
        seen.add(status)
        statuses.append(status)
    return tuple(statuses)


def build_coverage_targets(
    declaration_statuses: tuple[str, ...] = (DECLARATION_FILED, DECLARATION_UNFILED),
    tax_types: list[str] | tuple[str, ...] | None = None,
) -> list[CoverageTarget]:
    targets: list[CoverageTarget] = []
    allowed = set(normalize_tax_type_keys(tax_types))
    for definition in SUPPORTED_TAX_TYPES:
        if allowed and definition.tax_type not in allowed:
            continue
        statuses = definition.coverage_statuses or declaration_statuses
        for status in statuses:
            status_name = DECLARATION_STATUS_LABELS.get(status, status)
            targets.append(
                CoverageTarget(
                    tax_type=definition.tax_type,
                    tax_type_name=definition.tax_type_name,
                    declaration_status=status,
                    declaration_status_name=status_name,
                    form_ids=definition.form_ids,
                    backend_tax_type_ids=definition.backend_tax_type_ids,
                    backend_tax_ids=definition.backend_tax_ids,
                    backend_taxpayer_type=definition.backend_taxpayer_type,
                    requires_tax_bureau=True,
                    notes=definition.notes,
                )
            )
    return targets


def tax_type_from_form_id(form_id: str) -> str:
    text = str(form_id or "").lower()
    if text.startswith("vat_general"):
        return "VAT_GENERAL"
    if text.startswith("vat_small"):
        return "VAT_SMALL"
    if text.startswith("cit_a"):
        return "CIT_A"
    if text.startswith("culture_fee"):
        return "CULTURE_FEE"
    if text.startswith("consumption_tax"):
        return "CONSUMPTION_TAX"
    if text.startswith("cbj_personal"):
        return "CBJ_PERSONAL"
    if text.startswith("cbj_annual"):
        return "CBJ_ANNUAL"
    if text.startswith("cbj_"):
        return "CBJ_PERSONAL"
    return str(form_id or "")


def normalize_tax_type(value: object, form_id: str = "") -> str:
    text = str(value or "").strip()
    upper = text.upper()
    inferred = tax_type_from_form_id(form_id)
    if upper == "CBJ" and inferred in {"CBJ_PERSONAL", "CBJ_ANNUAL"}:
        return inferred
    aliases = {
        "VAT_GENERAL": "VAT_GENERAL",
        "VAT_SMALL": "VAT_SMALL",
        "CIT_A": "CIT_A",
        "CIT": "CIT_A",
        "CULTURE_FEE": "CULTURE_FEE",
        "CONSUMPTION_TAX": "CONSUMPTION_TAX",
        "CBJ": "CBJ_PERSONAL",
        "CBJ_PERSONAL": "CBJ_PERSONAL",
        "CBJ_ANNUAL": "CBJ_ANNUAL",
    }
    if upper in aliases:
        return aliases[upper]
    return inferred or upper


def target_lookup() -> dict[tuple[str, str], CoverageTarget]:
    return {(target.tax_type, target.declaration_status): target for target in build_coverage_targets()}
