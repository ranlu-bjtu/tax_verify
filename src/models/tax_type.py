from typing import Optional

from pydantic import BaseModel, Field

from src.models.field_mapping import MappingSource, DataType


class NavigationStep(BaseModel):
    action: str
    selector: Optional[str] = None
    value: Optional[str] = None
    wait_until: str = "networkidle"
    timeout: int = 30000
    description: Optional[str] = None


class WebConfig(BaseModel):
    url_template: str = ""
    login_required: bool = True
    navigation_steps: list[NavigationStep] = Field(default_factory=list)
    result_list: Optional[dict] = None
    table_selector: Optional[str] = None
    row_selector: Optional[str] = None
    cell_selector: Optional[str] = None


class TableRegion(BaseModel):
    name: str
    page: int = 1
    bbox: Optional[list[float]] = None


class CoordinateRegion(BaseModel):
    x0: float
    y0: float
    x1: float
    y1: float
    page: int = 1


class PDFConfig(BaseModel):
    url_template: Optional[str] = None
    parser_strategy: str = "table_extract"
    table_regions: list[TableRegion] = Field(default_factory=list)
    coordinate_regions: Optional[dict[str, CoordinateRegion]] = None
    page_count: int = 1
    template_file: Optional[str] = None


class APIConfig(BaseModel):
    base_url: str = ""
    endpoint_template: str = ""
    method: str = "GET"
    headers: Optional[dict[str, str]] = None
    params_template: Optional[dict[str, str]] = None
    body_template: Optional[dict[str, str]] = None
    auth_type: Optional[str] = None
    response_json_path: str = "$.data"
    timeout_seconds: int = 30
    retry_count: int = 3
    retry_delay_seconds: int = 5


class CompareRules(BaseModel):
    default_tolerance_amount: float = 0.01
    default_tolerance_rate: float = 0.0001
    treat_dash_as_zero: bool = True
    treat_empty_as_zero: bool = False
    empty_equivalent_values: list[str] = Field(
        default_factory=lambda: ["——", "", "0.00", "0"]
    )
    date_format_api: str = "%Y-%m-%d"
    date_format_web: str = "%Y年%m月%d日"


class FormTemplate(BaseModel):
    form_code: str
    form_name: str
    form_version: str = "2026"
    pages: int = 1

    mapping_source: MappingSource = MappingSource.WEB
    mapping_file: Optional[str] = None
    mapping_sheet: Optional[str] = None
    mapping_header_row: int = 1
    mapping_data_start_row: int = 2

    web_config: Optional[WebConfig] = None
    pdf_config: Optional[PDFConfig] = None
    api_config: Optional[APIConfig] = None
    compare_rules: CompareRules = Field(default_factory=CompareRules)


class TaxTypeConfig(BaseModel):
    tax_type_id: str
    tax_type_name: str
    forms: list[FormTemplate] = Field(default_factory=list)
    enabled: bool = True