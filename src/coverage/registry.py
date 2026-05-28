from __future__ import annotations

from .models import (
    DECLARATION_FILED,
    DECLARATION_STATUS_LABELS,
    DECLARATION_UNFILED,
    CoverageTarget,
    TaxTypeDefinition,
)


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
        backend_tax_type_ids=(1,),
        notes="后台税种 ID 只能定位增值税，是否一般纳税人需结合任务结果或表单结果判断。",
    ),
    TaxTypeDefinition(
        tax_type="VAT_SMALL",
        tax_type_name="增值税（小规模纳税人）",
        form_ids=("vat_small_main", "vat_small_appendix1", "vat_small_appendix2"),
        backend_tax_type_ids=(1,),
        notes="后台税种 ID 只能定位增值税，是否小规模需结合任务结果或表单结果判断。",
    ),
    TaxTypeDefinition(
        tax_type="CIT_A",
        tax_type_name="企业所得税（A类）",
        form_ids=("cit_a_main",),
        backend_tax_type_ids=(2,),
    ),
    TaxTypeDefinition(
        tax_type="CULTURE_FEE",
        tax_type_name="文化事业建设费",
        form_ids=("culture_fee_main", "culture_fee_deduction"),
        backend_tax_type_ids=(3,),
    ),
    TaxTypeDefinition(
        tax_type="CONSUMPTION_TAX",
        tax_type_name="消费税",
        form_ids=("consumption_tax_main", "consumption_tax_surcharge"),
        backend_tax_type_ids=(29,),
        notes="消费税当前接入两张表：消费税及附加税费申报表、消费税附加税费计算表。",
    ),
    TaxTypeDefinition(
        tax_type="CBJ_PERSONAL",
        tax_type_name="个税残保金",
        form_ids=("cbj_personal",),
        backend_tax_type_ids=(26,),
        notes="个税残保金只校验后台字段 snzzzgrs_cbj、snzzzggzze_cbj 是否返回。",
    ),
    TaxTypeDefinition(
        tax_type="CBJ_ANNUAL",
        tax_type_name="汇算清缴残保金",
        form_ids=("cbj_annual_settlement",),
        backend_tax_type_ids=(31,),
        notes="汇算清缴残保金需要进入税局年度企业所得税申报表核对 A000000、A105050。",
    ),
)


def supported_tax_types() -> list[TaxTypeDefinition]:
    return list(SUPPORTED_TAX_TYPES)


def build_coverage_targets(
    declaration_statuses: tuple[str, ...] = (DECLARATION_FILED, DECLARATION_UNFILED),
) -> list[CoverageTarget]:
    targets: list[CoverageTarget] = []
    for definition in SUPPORTED_TAX_TYPES:
        for status in declaration_statuses:
            targets.append(
                CoverageTarget(
                    tax_type=definition.tax_type,
                    tax_type_name=definition.tax_type_name,
                    declaration_status=status,
                    declaration_status_name=DECLARATION_STATUS_LABELS.get(status, status),
                    form_ids=definition.form_ids,
                    backend_tax_type_ids=definition.backend_tax_type_ids,
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
