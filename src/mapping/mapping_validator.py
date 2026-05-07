import logging
from typing import Optional

from src.models.field_mapping import FieldMapping, DataType

logger = logging.getLogger(__name__)


class MappingValidator:
    """Validates cleaned mapping dicts and reports issues."""

    def validate(self, mappings: list[dict]) -> list[FieldMapping]:
        valid = []
        seen_ids = set()
        warnings = []

        for i, raw in enumerate(mappings):
            issues = []

            if not raw.get("field_id"):
                issues.append("missing field_id")
                raw["field_id"] = f"auto_field_{i+1}"

            if raw["field_id"] in seen_ids:
                issues.append(f"duplicate field_id: {raw['field_id']}")

            seen_ids.add(raw["field_id"])

            if not raw.get("data_type"):
                issues.append("missing data_type, defaulting to 'text'")
                raw["data_type"] = "text"

            try:
                DataType(raw["data_type"])
            except ValueError:
                issues.append(f"invalid data_type: {raw['data_type']}")
                raw["data_type"] = "text"

            if not raw.get("display_name"):
                raw["display_name"] = raw.get("field_id", f"field_{i+1}")

            if raw.get("compare") is None:
                raw["compare"] = True
            if raw.get("required") is None:
                raw["required"] = True
            if raw.get("is_calculated") is None:
                raw["is_calculated"] = False

            if issues:
                logger.warning(f"Mapping row {i+1} issues: {', '.join(issues)}")
                warnings.append({"row": i + 1, "issues": issues})

            try:
                mapping = FieldMapping(**raw)
                valid.append(mapping)
            except Exception as e:
                logger.error(f"Mapping row {i+1} failed to create FieldMapping: {e}")
                warnings.append({"row": i + 1, "issues": [str(e)]})

        if warnings:
            logger.warning(f"Mapping validation: {len(warnings)} rows with issues")

        return valid