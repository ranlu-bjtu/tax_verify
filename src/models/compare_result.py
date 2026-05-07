from enum import Enum
from typing import Optional, Any
from datetime import datetime

from pydantic import BaseModel, Field

from src.models.field_mapping import DataType


class CompareStatus(str, Enum):
    MATCH = "match"
    MISMATCH = "mismatch"
    TOLERANCE_MATCH = "tolerance_match"
    API_MISSING = "api_missing"
    WEB_MISSING = "web_missing"
    BOTH_MISSING = "both_missing"
    PARSE_ERROR = "parse_error"
    MAPPING_ERROR = "mapping_error"
    SKIP = "skip"
    UNSUPPORTED_TAX_TYPE = "unsupported_tax_type"
    UNSUPPORTED_FORM_TEMPLATE = "unsupported_form_template"


class FieldCompareResult(BaseModel):
    field_id: str
    display_name: str
    data_type: DataType
    row_name: str = ""
    line_no: str = ""
    column_name: str = ""

    api_raw_value: Optional[Any] = None
    web_raw_value: Optional[Any] = None
    pdf_raw_value: Optional[Any] = None

    api_normalized: Optional[str] = None
    web_normalized: Optional[str] = None

    status: CompareStatus
    diff_type: Optional[str] = None
    diff_value: Optional[str] = None
    detail: Optional[str] = None
    tolerance: Optional[float] = None


class CompareSummary(BaseModel):
    total_fields: int = 0
    match_count: int = 0
    tolerance_match_count: int = 0
    mismatch_count: int = 0
    api_missing_count: int = 0
    web_missing_count: int = 0
    both_missing_count: int = 0
    parse_error_count: int = 0
    mapping_error_count: int = 0
    skip_count: int = 0
    match_rate: float = 0.0


class CompareResult(BaseModel):
    batch_id: str = ""
    company_name: str = ""
    taxpayer_id: str = ""
    tax_type: str = ""
    form_code: str = ""
    form_name: str = ""
    form_version: str = ""
    period: str = ""
    field_results: list[FieldCompareResult] = Field(default_factory=list)
    summary: CompareSummary = Field(default_factory=CompareSummary)
    timestamp: datetime = Field(default_factory=datetime.now)