from decimal import Decimal
from typing import Optional

from src.models.field_mapping import DataType, FieldMapping
from src.models.compare_result import (
    CompareStatus, FieldCompareResult, CompareResult, CompareSummary,
)
from src.models.tax_type import CompareRules
from src.compare.value_normalizer import NormalizedValue, get_normalizer


class Comparator:
    """Compares normalized API values vs web/PDF values per data_type."""

    def __init__(self, rules: Optional[CompareRules] = None):
        self.rules = rules or CompareRules()

    def compare_field(
        self,
        mapping: FieldMapping,
        api_normalized: NormalizedValue,
        web_normalized: NormalizedValue,
    ) -> FieldCompareResult:
        data_type = mapping.data_type

        if mapping.is_calculated:
            return FieldCompareResult(
                field_id=mapping.field_id,
                display_name=mapping.display_name,
                data_type=data_type,
                row_name=mapping.row_name,
                line_no=mapping.line_no,
                column_name=mapping.column_name,
                api_raw_value=api_normalized.original,
                web_raw_value=web_normalized.original,
                api_normalized=str(api_normalized.value) if api_normalized.value else None,
                web_normalized=str(web_normalized.value) if web_normalized.value else None,
                status=CompareStatus.SKIP,
                detail="计算项，暂不比对",
            )

        if not mapping.compare:
            return FieldCompareResult(
                field_id=mapping.field_id,
                display_name=mapping.display_name,
                data_type=data_type,
                api_raw_value=api_normalized.original,
                web_raw_value=web_normalized.original,
                status=CompareStatus.SKIP,
                detail="配置为不比对",
            )

        # Missing value handling — treat as missing if original was never provided
        if mapping.form_code != "VAT_GENERAL_APPENDIX5" and self._zero_empty_equivalent(data_type, api_normalized, web_normalized):
            return self._make_result(mapping, api_normalized, web_normalized,
                                     CompareStatus.MATCH, "zero_empty_equivalent")

        api_is_missing = api_normalized.original is None or api_normalized.is_missing or api_normalized.is_empty
        web_is_missing = web_normalized.original is None or web_normalized.is_missing or web_normalized.is_empty

        if api_is_missing and web_is_missing:
            return self._make_result(mapping, api_normalized, web_normalized,
                                     CompareStatus.BOTH_MISSING, "both_missing")

        if api_is_missing:
            return self._make_result(mapping, api_normalized, web_normalized,
                                     CompareStatus.API_MISSING, "api_missing")

        if web_is_missing:
            return self._make_result(mapping, api_normalized, web_normalized,
                                     CompareStatus.WEB_MISSING, "web_missing")

        # Error handling
        if api_normalized.error or web_normalized.error:
            return self._make_result(mapping, api_normalized, web_normalized,
                                     CompareStatus.PARSE_ERROR, "parse_error")

        # Empty-equivalent check
        if api_normalized.is_empty and web_normalized.is_empty:
            if self._empty_equivalent(data_type):
                return self._make_result(mapping, api_normalized, web_normalized,
                                         CompareStatus.MATCH, "empty_equivalent")
            return self._make_result(mapping, api_normalized, web_normalized,
                                     CompareStatus.BOTH_MISSING, "both_empty_not_equivalent")

        # Numeric comparison (amount, rate, integer)
        if data_type in (DataType.AMOUNT, DataType.RATE, DataType.INTEGER):
            return self._compare_numeric(mapping, api_normalized, web_normalized)

        # Text comparison
        if data_type in (DataType.TEXT, DataType.ENUM):
            return self._compare_text(mapping, api_normalized, web_normalized)

        # Date comparison
        if data_type == DataType.DATE:
            return self._compare_text(mapping, api_normalized, web_normalized)

        # Empty or dash
        if data_type == DataType.EMPTY_OR_DASH:
            if api_normalized.is_empty and web_normalized.is_empty:
                return self._make_result(mapping, api_normalized, web_normalized,
                                         CompareStatus.MATCH, "empty_equivalent")
            return self._make_result(mapping, api_normalized, web_normalized,
                                     CompareStatus.MISMATCH, "not_empty_equivalent")

        return self._make_result(mapping, api_normalized, web_normalized,
                                 CompareStatus.SKIP, f"unsupported_data_type:{data_type}")

    def compare_all(
        self,
        mappings: list[FieldMapping],
        api_data: dict[str, NormalizedValue],
        web_data: dict[str, NormalizedValue],
        batch_id: str = "",
        company_name: str = "",
        taxpayer_id: str = "",
        period: str = "",
    ) -> CompareResult:
        field_results = []
        for mapping in mappings:
            api_norm = api_data.get(mapping.field_id, NormalizedValue(value=None, original=None))
            web_norm = web_data.get(mapping.field_id, NormalizedValue(value=None, original=None))
            result = self.compare_field(mapping, api_norm, web_norm)
            field_results.append(result)

        summary = self._compute_summary(field_results)
        return CompareResult(
            batch_id=batch_id,
            company_name=company_name,
            taxpayer_id=taxpayer_id,
            tax_type=mappings[0].tax_type if mappings else "",
            form_code=mappings[0].form_code if mappings else "",
            form_name=mappings[0].form_name if mappings else "",
            period=period,
            field_results=field_results,
            summary=summary,
        )

    # ── Private helpers ──────────────────────────────────────────

    def _compare_numeric(
        self, mapping: FieldMapping,
        api: NormalizedValue, web: NormalizedValue,
    ) -> FieldCompareResult:
        tolerance = self._get_tolerance(mapping)
        diff = abs(Decimal(str(api.value)) - Decimal(str(web.value)))

        if diff == 0:
            return self._make_result(mapping, api, web, CompareStatus.MATCH, "exact_match")
        if diff <= tolerance:
            return self._make_result(
                mapping, api, web, CompareStatus.TOLERANCE_MATCH,
                f"tolerance_match: diff={diff}, tol={tolerance}",
                diff_type=f"{mapping.data_type.value}_diff",
                diff_value=str(diff),
                tolerance=tolerance,
            )
        return self._make_result(
            mapping, api, web, CompareStatus.MISMATCH,
            f"mismatch: diff={diff}, tol={tolerance}",
            diff_type=f"{mapping.data_type.value}_diff",
            diff_value=str(diff),
            tolerance=tolerance,
        )

    def _compare_text(
        self, mapping: FieldMapping,
        api: NormalizedValue, web: NormalizedValue,
    ) -> FieldCompareResult:
        if api.value == web.value:
            return self._make_result(mapping, api, web, CompareStatus.MATCH, "text_match")
        return self._make_result(mapping, api, web, CompareStatus.MISMATCH, "text_mismatch")

    def _make_result(
        self, mapping: FieldMapping,
        api: NormalizedValue, web: NormalizedValue,
        status: CompareStatus, detail: str,
        diff_type: Optional[str] = None,
        diff_value: Optional[str] = None,
        tolerance: Optional[float] = None,
    ) -> FieldCompareResult:
        return FieldCompareResult(
            field_id=mapping.field_id,
            display_name=mapping.display_name,
            data_type=mapping.data_type,
            row_name=mapping.row_name,
            line_no=mapping.line_no,
            column_name=mapping.column_name,
            api_raw_value=api.original,
            web_raw_value=web.original,
            api_normalized=str(api.value) if api.value is not None else None,
            web_normalized=str(web.value) if web.value is not None else None,
            status=status,
            diff_type=diff_type,
            diff_value=diff_value,
            detail=detail,
            tolerance=tolerance,
        )

    def _get_tolerance(self, mapping: FieldMapping) -> Decimal:
        if mapping.tolerance is not None:
            return Decimal(str(mapping.tolerance))
        if mapping.data_type == DataType.AMOUNT:
            return Decimal(str(self.rules.default_tolerance_amount))
        if mapping.data_type == DataType.RATE:
            return Decimal(str(self.rules.default_tolerance_rate))
        return Decimal("0")

    def _empty_equivalent(self, data_type: DataType) -> bool:
        if data_type == DataType.EMPTY_OR_DASH:
            return True
        if data_type in (DataType.AMOUNT, DataType.INTEGER):
            return self.rules.treat_dash_as_zero and self.rules.treat_empty_as_zero
        return False

    def _zero_empty_equivalent(
        self,
        data_type: DataType,
        api: NormalizedValue,
        web: NormalizedValue,
    ) -> bool:
        if data_type not in (DataType.AMOUNT, DataType.RATE, DataType.INTEGER):
            return False

        def is_empty_like(value: NormalizedValue) -> bool:
            return value.original is None or value.is_empty or value.is_missing

        def is_zero(value: NormalizedValue) -> bool:
            if value.value is None or value.error:
                return False
            return Decimal(str(value.value)) == Decimal("0")

        return (is_empty_like(api) and is_zero(web)) or (is_empty_like(web) and is_zero(api))

    def _compute_summary(self, results: list[FieldCompareResult]) -> CompareSummary:
        total = len(results)
        counts = {s: 0 for s in CompareStatus}
        for r in results:
            counts[r.status] += 1

        match_total = counts[CompareStatus.MATCH] + counts[CompareStatus.TOLERANCE_MATCH]
        rate = (match_total / total * 100) if total > 0 else 0.0

        return CompareSummary(
            total_fields=total,
            match_count=counts[CompareStatus.MATCH],
            tolerance_match_count=counts[CompareStatus.TOLERANCE_MATCH],
            mismatch_count=counts[CompareStatus.MISMATCH],
            api_missing_count=counts[CompareStatus.API_MISSING],
            web_missing_count=counts[CompareStatus.WEB_MISSING],
            both_missing_count=counts[CompareStatus.BOTH_MISSING],
            parse_error_count=counts[CompareStatus.PARSE_ERROR],
            mapping_error_count=counts[CompareStatus.MAPPING_ERROR],
            skip_count=counts[CompareStatus.SKIP],
            match_rate=round(rate, 2),
        )
