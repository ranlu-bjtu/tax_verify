from decimal import Decimal, InvalidOperation
from typing import Optional, Any
from dataclasses import dataclass

from src.models.field_mapping import DataType


@dataclass
class NormalizedValue:
    value: Optional[Any]
    original: Optional[Any]
    is_empty: bool = False
    error: bool = False

    @property
    def is_missing(self) -> bool:
        return self.value is None and not self.is_empty and not self.error


DASH_VALUES = frozenset({"——", "—", "-", "／", "/"})
EMPTY_VALUES = frozenset({"", "0.00", "0"})


class AmountNormalizer:
    """金额 → Decimal 两位小数"""

    def normalize(self, raw_value: Optional[Any]) -> NormalizedValue:
        if raw_value is None or (isinstance(raw_value, str) and raw_value.strip() == ""):
            return NormalizedValue(value=None, original=raw_value, is_empty=True)

        s = str(raw_value).replace(",", "").replace("￥", "").replace("¥", "").strip()
        s = "".join(s.split())
        if s in DASH_VALUES:
            return NormalizedValue(value=None, original=raw_value, is_empty=True)

        try:
            val = Decimal(s).quantize(Decimal("0.01"))
            return NormalizedValue(value=val, original=raw_value, is_empty=False)
        except (InvalidOperation, ValueError):
            return NormalizedValue(value=None, original=raw_value, is_empty=False, error=True)


class RateNormalizer:
    """税率 → Decimal 四位小数"""

    def normalize(self, raw_value: Optional[Any]) -> NormalizedValue:
        if raw_value is None or (isinstance(raw_value, str) and raw_value.strip() == ""):
            return NormalizedValue(value=None, original=raw_value, is_empty=True)

        s = str(raw_value).strip()
        if s in DASH_VALUES:
            return NormalizedValue(value=None, original=raw_value, is_empty=True)

        if "%" in s:
            try:
                val = Decimal(s.replace("%", "")) / Decimal("100")
                return NormalizedValue(
                    value=val.quantize(Decimal("0.0001")),
                    original=raw_value, is_empty=False,
                )
            except (InvalidOperation, ValueError):
                return NormalizedValue(value=None, original=raw_value, error=True)

        try:
            val = Decimal(s).quantize(Decimal("0.0001"))
            return NormalizedValue(value=val, original=raw_value, is_empty=False)
        except (InvalidOperation, ValueError):
            return NormalizedValue(value=None, original=raw_value, error=True)


class TextNormalizer:
    """文本 → strip"""

    def normalize(self, raw_value: Optional[Any]) -> NormalizedValue:
        if raw_value is None:
            return NormalizedValue(value=None, original=raw_value, is_empty=True)
        s = str(raw_value).strip()
        if s == "" or s in DASH_VALUES:
            return NormalizedValue(value=None, original=raw_value, is_empty=True)
        return NormalizedValue(value=s, original=raw_value)


class DateNormalizer:
    """日期 → YYYY-MM-DD"""

    DATE_FORMATS = ["%Y-%m-%d", "%Y/%m/%d", "%Y%m%d", "%Y年%m月%d日"]

    def normalize(self, raw_value: Optional[Any]) -> NormalizedValue:
        if raw_value is None or (isinstance(raw_value, str) and raw_value.strip() == ""):
            return NormalizedValue(value=None, original=raw_value, is_empty=True)

        s = str(raw_value).strip()
        if s in DASH_VALUES:
            return NormalizedValue(value=None, original=raw_value, is_empty=True)

        from datetime import datetime as dt
        for fmt in self.DATE_FORMATS:
            try:
                parsed = dt.strptime(s, fmt)
                return NormalizedValue(
                    value=parsed.strftime("%Y-%m-%d"),
                    original=raw_value, is_empty=False,
                )
            except ValueError:
                continue

        return NormalizedValue(value=None, original=raw_value, error=True)


class IntegerNormalizer:
    """整数 → int"""

    def normalize(self, raw_value: Optional[Any]) -> NormalizedValue:
        if raw_value is None or (isinstance(raw_value, str) and raw_value.strip() == ""):
            return NormalizedValue(value=None, original=raw_value, is_empty=True)

        s = str(raw_value).strip()
        if s in DASH_VALUES:
            return NormalizedValue(value=None, original=raw_value, is_empty=True)

        try:
            return NormalizedValue(value=int(float(s)), original=raw_value, is_empty=False)
        except (ValueError, TypeError):
            return NormalizedValue(value=None, original=raw_value, error=True)


class EmptyOrDashNormalizer:
    """空值/横线归一化"""

    EQUIVALENT = frozenset({"——", "—", "", "0.00", "0", None})

    def normalize(self, raw_value: Optional[Any]) -> NormalizedValue:
        if raw_value is None:
            return NormalizedValue(value=None, original=raw_value, is_empty=True)
        s = str(raw_value).strip()
        is_equiv = s in self.EQUIVALENT
        return NormalizedValue(
            value=None if is_equiv else raw_value,
            original=raw_value,
            is_empty=is_equiv,
        )


_NORMALIZERS = {
    DataType.AMOUNT: AmountNormalizer(),
    DataType.RATE: RateNormalizer(),
    DataType.TEXT: TextNormalizer(),
    DataType.DATE: DateNormalizer(),
    DataType.INTEGER: IntegerNormalizer(),
    DataType.EMPTY_OR_DASH: EmptyOrDashNormalizer(),
}


def get_normalizer(data_type: DataType) -> AmountNormalizer | RateNormalizer | TextNormalizer | DateNormalizer | IntegerNormalizer | EmptyOrDashNormalizer:
    normalizer = _NORMALIZERS.get(data_type)
    if normalizer is None:
        raise ValueError(f"No normalizer for data_type: {data_type}")
    return normalizer
