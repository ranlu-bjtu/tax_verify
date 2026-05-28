"""Coverage planning for supported tax verification scenarios."""

from .analyzer import analyze_run_coverage, write_coverage_status
from .registry import build_coverage_targets, supported_tax_types

__all__ = [
    "analyze_run_coverage",
    "build_coverage_targets",
    "supported_tax_types",
    "write_coverage_status",
]
