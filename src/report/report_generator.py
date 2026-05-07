from abc import ABC, abstractmethod
from pathlib import Path

from src.models.compare_result import CompareResult


class BaseReportGenerator(ABC):
    """Base interface for report generators."""

    def __init__(self, output_dir: str = "./output/reports"):
        self.output_dir = Path(output_dir)

    @abstractmethod
    def generate(self, result: CompareResult) -> str:
        """Generate report and return the output file path."""
        ...