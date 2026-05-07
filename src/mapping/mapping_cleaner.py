import re
from typing import Optional

# Common Chinese column name variants → standard field names
COLUMN_NAME_MAP = {
    "税种": "tax_type",
    "表单编码": "form_code",
    "表单名称": "form_name",
    "表单版本": "form_version",
    "页码": "page",
    "sheet名": "sheet_name",
    "sheet名称": "sheet_name",
    "行名称": "row_name",
    "行名": "row_name",
    "栏次": "line_no",
    "行号": "line_no",
    "列名称": "column_name",
    "列名": "column_name",
    "字段ID": "field_id",
    "接口字段ID": "field_id",
    "接口字段": "api_json_path",
    "接口字段中文名": "api_field_name_cn",
    "字段中文名": "api_field_name_cn",
    "JSONPath": "api_json_path",
    "json_path": "api_json_path",
    "jsonpath": "api_json_path",
    "数据类型": "data_type",
    "类型": "data_type",
    "是否比对": "compare",
    "参与比对": "compare",
    "是否必填": "required",
    "必填": "required",
    "是否计算项": "is_calculated",
    "计算项": "is_calculated",
    "网页selector": "web_selector",
    "web_selector": "web_selector",
    "网页定位": "web_selector",
    "PDF区域": "pdf_region_key",
    "pdf区域key": "pdf_region_key",
    "容差": "tolerance",
    "误差": "tolerance",
    "备注": "remarks",
}

BOOL_TRUE_VALUES = {"是", "yes", "true", "True", "1", "Y", "y"}
BOOL_FALSE_VALUES = {"否", "no", "false", "False", "0", "N", "n", "—"}


def normalize_column_name(raw: str) -> str:
    raw = raw.strip()
    if raw in COLUMN_NAME_MAP:
        return COLUMN_NAME_MAP[raw]

    for cn_key, std_key in COLUMN_NAME_MAP.items():
        if cn_key in raw or raw in cn_key:
            return std_key

    # fallback: convert to snake_case
    s = re.sub(r"[\s\-]+", "_", raw)
    s = re.sub(r"[^\w]", "", s)
    return s.lower()


def normalize_value(raw: Optional[str], target_field: str) -> Optional[object]:
    if raw is None or (isinstance(raw, str) and raw.strip() == ""):
        return None

    if target_field in ("compare", "required", "is_calculated"):
        raw_str = str(raw).strip()
        if raw_str in BOOL_TRUE_VALUES:
            return True
        if raw_str in BOOL_FALSE_VALUES:
            return False
        return None

    if target_field == "page":
        try:
            return int(raw)
        except (ValueError, TypeError):
            return 1

    if target_field == "tolerance":
        try:
            return float(raw)
        except (ValueError, TypeError):
            return None

    return str(raw).strip() if raw is not None else None


class MappingCleaner:
    """Cleans raw Excel mapping rows into standard FieldMapping dicts."""

    def clean_rows(
        self,
        raw_rows: list[dict],
        column_map: Optional[dict[str, str]] = None,
    ) -> list[dict]:
        if column_map is None:
            column_map = {
                normalize_column_name(k): k for k in raw_rows[0].keys()
            } if raw_rows else {}

        cleaned = []
        for row in raw_rows:
            cleaned_row = {}
            for raw_col, value in row.items():
                std_name = normalize_column_name(raw_col)
                cleaned_row[std_name] = normalize_value(value, std_name)
            cleaned.append(cleaned_row)

        return cleaned