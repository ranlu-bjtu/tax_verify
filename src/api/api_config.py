import logging
from typing import Any, Optional

from src.models.tax_type import APIConfig

logger = logging.getLogger(__name__)


class ResponseStore:
    """Stores raw API responses for auditing and debugging."""

    def __init__(self, output_dir: str = "./output/api_responses"):
        self.output_dir = output_dir

    def save(self, response: dict[str, Any], form_code: str, batch_id: str = "") -> str:
        import json
        from pathlib import Path
        from datetime import datetime

        Path(self.output_dir).mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{batch_id}_{form_code}_{timestamp}.json"
        filepath = Path(self.output_dir) / filename

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(response, f, indent=2, ensure_ascii=False)

        logger.info(f"API response saved: {filepath}")
        return str(filepath)