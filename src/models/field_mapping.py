from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class DataType(str, Enum):
    AMOUNT = "amount"
    RATE = "rate"
    TEXT = "text"
    DATE = "date"
    INTEGER = "integer"
    EMPTY_OR_DASH = "empty_or_dash"
    FORMULA = "formula"
    ENUM = "enum"


class MappingSource(str, Enum):
    WEB = "web"
    PDF = "pdf"


class FieldMapping(BaseModel):
    tax_type: str = ""
    form_code: str = ""
    form_name: str = ""
    form_version: str = ""
    page: int = 1
    sheet_name: str = ""

    field_id: str
    display_name: str
    row_name: str = ""
    line_no: str = ""
    column_name: str = ""
    data_type: DataType
    group: Optional[str] = None

    api_json_path: Optional[str] = None
    api_field_name_cn: Optional[str] = None

    web_selector: Optional[str] = None
    web_cell_id: Optional[str] = None
    web_row_index: Optional[int] = None
    web_col_index: Optional[int] = None

    pdf_region_key: Optional[str] = None
    pdf_page: Optional[int] = None
    pdf_table_region: Optional[str] = None

    compare: bool = True
    required: bool = True
    is_calculated: bool = False
    tolerance: Optional[float] = None
    normalize_rule: Optional[str] = None

    remarks: Optional[str] = None


class FieldMappingGroup(BaseModel):
    group_id: str
    group_name: str
    fields: list[FieldMapping] = Field(default_factory=list)