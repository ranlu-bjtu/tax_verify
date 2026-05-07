import json
from pathlib import Path
from datetime import datetime

from src.models.compare_result import CompareResult
from src.report.report_generator import BaseReportGenerator


class JSONReport(BaseReportGenerator):

    def generate(self, result: CompareResult) -> str:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"compare_{result.batch_id}_{result.tax_type}_{result.period}_{timestamp}.json"
        filepath = self.output_dir / filename

        data = result.model_dump(mode="json")
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        return str(filepath)