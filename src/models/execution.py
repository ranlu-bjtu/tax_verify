from enum import Enum
from typing import Optional, Any
from datetime import datetime

from pydantic import BaseModel, Field

from src.models.field_mapping import FieldMapping
from src.models.compare_result import CompareResult


class StepStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    PARTIAL = "partial"


class StepResult(BaseModel):
    step_name: str
    status: StepStatus
    duration_ms: int = 0
    error_message: Optional[str] = None
    output_data: Optional[dict[str, Any]] = None


class PipelineContext(BaseModel):
    tax_type: str
    period: str
    company_id: str
    task_id: str = ""
    province: str = ""
    config_root: str = ""
    steps: list[StepResult] = Field(default_factory=list)
    api_data: Optional[dict[str, Any]] = None
    web_data: Optional[dict[str, Any]] = None
    pdf_data: Optional[dict[str, Any]] = None
    mappings: Optional[list[FieldMapping]] = None
    compare_result: Optional[CompareResult] = None
    output_data: Optional[dict[str, Any]] = None


class ExecutionBatch(BaseModel):
    batch_id: str
    created_at: datetime = Field(default_factory=datetime.now)
    companies: list[str] = Field(default_factory=list)
    tax_types: list[str] = Field(default_factory=list)
    periods: list[str] = Field(default_factory=list)
    contexts: list[PipelineContext] = Field(default_factory=list)