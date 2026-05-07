import json
from typing import Any, Optional

from jsonpath_ng import parse as jp_parse


class JSONPathExtractor:
    """Extracts values from JSON data using JSONPath expressions."""

    def extract(self, data: dict[str, Any], json_path: str) -> Optional[Any]:
        if not json_path:
            return None

        try:
            expr = jp_parse(json_path)
            matches = expr.find(data)
            if not matches:
                return None
            if len(matches) == 1:
                return matches[0].value
            return [m.value for m in matches]
        except Exception:
            return None

    def extract_all(
        self,
        data: dict[str, Any],
        field_paths: dict[str, str],
    ) -> dict[str, Any]:
        result = {}
        for field_id, json_path in field_paths.items():
            result[field_id] = self.extract(data, json_path)
        return result