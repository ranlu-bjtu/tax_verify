"""Unit tests for ValueNormalizer and Comparator."""

import sys
from pathlib import Path
from decimal import Decimal

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.compare.value_normalizer import (
    get_normalizer, DataType, NormalizedValue,
    AmountNormalizer, RateNormalizer, TextNormalizer,
    DateNormalizer, IntegerNormalizer, EmptyOrDashNormalizer,
)
from src.compare.comparator import Comparator
from src.models.field_mapping import FieldMapping
from src.models.compare_result import CompareStatus
from src.models.tax_type import CompareRules


# ── Normalizer tests ──

def test_amount_normalizer():
    n = get_normalizer(DataType.AMOUNT)
    # Exact value
    r = n.normalize("1,234.56")
    assert r.value == Decimal("1234.56")
    assert not r.is_empty
    # Dash
    r = n.normalize("——")
    assert r.is_empty
    # None
    r = n.normalize(None)
    assert r.is_empty
    # Zero
    r = n.normalize("0.00")
    assert r.value == Decimal("0.00")
    # Currency symbol
    r = n.normalize("￥5,000.00")
    assert r.value == Decimal("5000.00")


def test_rate_normalizer():
    n = get_normalizer(DataType.RATE)
    # Percentage
    r = n.normalize("5%")
    assert r.value == Decimal("0.0500")
    # Decimal
    r = n.normalize("0.05")
    assert r.value == Decimal("0.0500")
    # 0.03 vs 3% should be equal
    r1 = n.normalize("3%")
    r2 = n.normalize("0.03")
    assert r1.value == r2.value


def test_text_normalizer():
    n = get_normalizer(DataType.TEXT)
    r = n.normalize("  abc  ")
    assert r.value == "abc"
    r = n.normalize("")
    assert r.is_empty
    r = n.normalize("——")
    assert r.is_empty


def test_date_normalizer():
    n = get_normalizer(DataType.DATE)
    r = n.normalize("2026-01-15")
    assert r.value == "2026-01-15"
    r = n.normalize("2026年01月15日")
    assert r.value == "2026-01-15"


def test_integer_normalizer():
    n = get_normalizer(DataType.INTEGER)
    r = n.normalize("42")
    assert r.value == 42
    r = n.normalize("3.7")
    assert r.value == 3


def test_empty_or_dash_normalizer():
    n = get_normalizer(DataType.EMPTY_OR_DASH)
    r = n.normalize("——")
    assert r.is_empty
    r = n.normalize("")
    assert r.is_empty
    r = n.normalize("0.00")
    assert r.is_empty


# ── Comparator tests ──

def test_compare_exact_match():
    comp = Comparator()
    n = get_normalizer(DataType.AMOUNT)
    m = FieldMapping(field_id="test", display_name="test", data_type=DataType.AMOUNT)
    r = comp.compare_field(m, n.normalize("100.00"), n.normalize("100.00"))
    assert r.status == CompareStatus.MATCH


def test_compare_tolerance_match():
    comp = Comparator()
    n = get_normalizer(DataType.AMOUNT)
    m = FieldMapping(field_id="test", display_name="test", data_type=DataType.AMOUNT)
    r = comp.compare_field(m, n.normalize("100.01"), n.normalize("100.00"))
    assert r.status == CompareStatus.TOLERANCE_MATCH


def test_compare_mismatch():
    comp = Comparator(CompareRules(default_tolerance_amount=0.01))
    n = get_normalizer(DataType.AMOUNT)
    m = FieldMapping(field_id="test", display_name="test", data_type=DataType.AMOUNT)
    r = comp.compare_field(m, n.normalize("100.10"), n.normalize("100.00"))
    assert r.status == CompareStatus.MISMATCH


def test_compare_api_missing():
    comp = Comparator()
    n = get_normalizer(DataType.AMOUNT)
    m = FieldMapping(field_id="test", display_name="test", data_type=DataType.AMOUNT)
    r = comp.compare_field(m, NormalizedValue(value=None, original=None), n.normalize("100"))
    assert r.status == CompareStatus.API_MISSING


def test_compare_rate_match():
    comp = Comparator()
    n = get_normalizer(DataType.RATE)
    m = FieldMapping(field_id="test", display_name="test", data_type=DataType.RATE)
    r = comp.compare_field(m, n.normalize("3%"), n.normalize("0.03"))
    assert r.status == CompareStatus.MATCH


def test_compare_text_match():
    comp = Comparator()
    n = get_normalizer(DataType.TEXT)
    m = FieldMapping(field_id="test", display_name="test", data_type=DataType.TEXT)
    r = comp.compare_field(m, n.normalize("abc"), n.normalize("abc"))
    assert r.status == CompareStatus.MATCH


def test_compare_date_match():
    comp = Comparator()
    n = get_normalizer(DataType.DATE)
    m = FieldMapping(field_id="test", display_name="test", data_type=DataType.DATE)
    r = comp.compare_field(m, n.normalize("2026-01-15"), n.normalize("2026年01月15日"))
    assert r.status == CompareStatus.MATCH


def test_compare_calculated_skip():
    comp = Comparator()
    n = get_normalizer(DataType.AMOUNT)
    m = FieldMapping(field_id="calc", display_name="计算项", data_type=DataType.AMOUNT, is_calculated=True)
    r = comp.compare_field(m, n.normalize("100"), n.normalize("100"))
    assert r.status == CompareStatus.SKIP


def test_compare_all():
    comp = Comparator()
    n_amt = get_normalizer(DataType.AMOUNT)
    n_rate = get_normalizer(DataType.RATE)

    mappings = [
        FieldMapping(field_id="amt1", display_name="金额1", data_type=DataType.AMOUNT, tax_type="VAT", form_code="MAIN", form_name="主表"),
        FieldMapping(field_id="rate1", display_name="税率1", data_type=DataType.RATE, tax_type="VAT", form_code="MAIN", form_name="主表"),
    ]

    api_data = {"amt1": n_amt.normalize("100.00"), "rate1": n_rate.normalize("3%")}
    web_data = {"amt1": n_amt.normalize("100.01"), "rate1": n_rate.normalize("0.03")}

    result = comp.compare_all(mappings, api_data, web_data, batch_id="test", period="2026Q1")
    assert result.summary.total_fields == 2
    assert result.summary.match_count + result.summary.tolerance_match_count >= 1


if __name__ == "__main__":
    test_amount_normalizer()
    test_rate_normalizer()
    test_text_normalizer()
    test_date_normalizer()
    test_integer_normalizer()
    test_empty_or_dash_normalizer()
    test_compare_exact_match()
    test_compare_tolerance_match()
    test_compare_mismatch()
    test_compare_api_missing()
    test_compare_rate_match()
    test_compare_text_match()
    test_compare_date_match()
    test_compare_calculated_skip()
    test_compare_all()
    print("All normalizer/comparator tests passed!")