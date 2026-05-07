import json
from pathlib import Path


SCHEMA_FILE = Path(__file__).parent.parent.parent / "mappings" / "_standard_schema.json"

STANDARD_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "FieldMapping Standard Schema",
    "description": "Standard structure for tax form field mappings after cleaning",
    "type": "object",
    "required": ["field_id", "display_name", "data_type"],
    "properties": {
        "tax_type": {"type": "string"},
        "form_code": {"type": "string"},
        "form_name": {"type": "string"},
        "form_version": {"type": "string"},
        "page": {"type": "integer"},
        "sheet_name": {"type": "string"},
        "field_id": {"type": "string"},
        "display_name": {"type": "string"},
        "row_name": {"type": "string"},
        "line_no": {"type": "string"},
        "column_name": {"type": "string"},
        "data_type": {
            "type": "string",
            "enum": ["amount", "rate", "text", "date", "integer",
                     "empty_or_dash", "formula", "enum"],
        },
        "group": {"type": ["string", "null"]},
        "api_json_path": {"type": ["string", "null"]},
        "api_field_name_cn": {"type": ["string", "null"]},
        "web_selector": {"type": ["string", "null"]},
        "web_cell_id": {"type": ["string", "null"]},
        "web_row_index": {"type": ["integer", "null"]},
        "web_col_index": {"type": ["integer", "null"]},
        "pdf_region_key": {"type": ["string", "null"]},
        "pdf_page": {"type": ["integer", "null"]},
        "pdf_table_region": {"type": ["string", "null"]},
        "compare": {"type": "boolean"},
        "required": {"type": "boolean"},
        "is_calculated": {"type": "boolean"},
        "tolerance": {"type": ["number", "null"]},
        "normalize_rule": {"type": ["string", "null"]},
        "remarks": {"type": ["string", "null"]},
    },
}


def save_schema() -> None:
    SCHEMA_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(SCHEMA_FILE, "w", encoding="utf-8") as f:
        json.dump(STANDARD_SCHEMA, f, indent=2, ensure_ascii=False)