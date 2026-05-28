import json
import logging
import shutil
import subprocess
import time
from typing import Any, Optional

import requests

from src.models.tax_type import APIConfig

logger = logging.getLogger(__name__)

API_BASE_URL = "https://data-task-management.chanapp.chanjet.com/pub-tax-management/api/admin/task/getListByTaskId"


class APIClient:
    """Fetches tax data from the task management API by taskId.

    Calls GET /getListByTaskId/{taskId}, extracts resultJson from
    the response, and flattens the nested structure for comparison.
    """

    def __init__(self, config: Optional[APIConfig] = None):
        self.config = config or APIConfig()
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})
        if self.config.headers:
            self.session.headers.update(self.config.headers)

    def fetch_by_task_id(self, task_id: str) -> dict[str, Any]:
        """Fetch data from the real API using a taskId.

        Response structure:
          {flag, code, success, msg, message, data: [{resultJson: {<tax_code>: {code, data, status}}}], errorInfo}

        resultJson.data is nested by form table (e.g. final_settment_001_qc),
        each containing flat field key-value pairs.
        """
        url = f"{API_BASE_URL}/{task_id}"
        timeout = self.config.timeout_seconds
        retries = self.config.retry_count
        delay = self.config.retry_delay_seconds

        for attempt in range(1, retries + 1):
            try:
                logger.info(f"API fetch attempt {attempt}/{retries}: task_id={task_id}")
                resp = self.session.get(url, timeout=timeout)
                resp.raise_for_status()
                body = resp.json()
                parsed = self._parse_task_body(body)
                if parsed.get("retryable") and attempt < retries:
                    time.sleep(delay)
                    continue
                return parsed

            except requests.RequestException as e:
                logger.error(f"API request failed (attempt {attempt}): {e}")
                if self._should_try_curl_fallback(e):
                    fallback = self._fetch_by_curl(url, timeout)
                    if fallback is not None:
                        return fallback
                if attempt < retries:
                    time.sleep(delay)
                else:
                    fallback = self._fetch_by_curl(url, timeout)
                    if fallback is not None:
                        return fallback
                    return {"error": str(e)}

    def _parse_task_body(self, body: dict[str, Any]) -> dict[str, Any]:
        if not body.get("success"):
            logger.warning(f"API returned unsuccessful response: {body.get('msg')}")
            return {"error": body.get("msg", "Unknown error"), "raw": body, "retryable": True}

        data_list = body.get("data", [])
        if not data_list:
            logger.warning("API returned empty data list")
            return {"error": "empty_data", "raw": body}

        result_json = data_list[0].get("resultJson", {})
        if not result_json:
            logger.warning("No resultJson in first data item")
            return {"error": "no_resultJson", "raw": body}

        # Extract province from paramJson (for province-based routing)
        param_json = data_list[0].get("paramJson", {})
        province = ""
        if isinstance(param_json, dict):
            province = param_json.get("province", "")
        elif isinstance(param_json, str):
            try:
                province = json.loads(param_json).get("province", "")
            except (json.JSONDecodeError, TypeError):
                pass

        # Flatten resultJson: {tax_code: {code, data: {table: {field: val}}}}
        # into {tax_code: {table.field: val}}
        flattened = self._flatten_result_json(result_json)
        return {
            "data": flattened,
            "raw_resultJson": result_json,
            "province": province,
            "paramJson": param_json,
        }

    def _fetch_by_curl(self, url: str, timeout: int) -> dict[str, Any] | None:
        curl_path = shutil.which("curl.exe") or shutil.which("curl")
        if not curl_path:
            return None
        try:
            logger.warning("Requests failed; retrying task API with curl fallback")
            completed = subprocess.run(
                [
                    curl_path,
                    "-L",
                    "--silent",
                    "--show-error",
                    "--max-time",
                    str(timeout),
                    url,
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout + 5,
                check=False,
            )
            if completed.returncode != 0:
                logger.error("curl fallback failed: %s", completed.stderr.strip())
                return None
            return self._parse_task_body(json.loads(completed.stdout))
        except Exception as exc:
            logger.error("curl fallback raised error: %s", exc)
            return None

    @staticmethod
    def _should_try_curl_fallback(exc: Exception) -> bool:
        text = str(exc)
        return "SSLEOFError" in text or "UNEXPECTED_EOF_WHILE_READING" in text

    def fetch(
        self,
        taxpayer_id: str = "",
        tax_period: str = "",
        tax_type: str = "",
        form_code: str = "",
        task_id: str = "",
    ) -> dict[str, Any]:
        """Compatibility wrapper: delegates to fetch_by_task_id if task_id is provided,
        otherwise returns mock data for dry-run mode."""
        if task_id:
            return self.fetch_by_task_id(task_id)

        logger.info(
            f"API fetch (mock fallback): taxpayer_id={taxpayer_id}, "
            f"period={tax_period}, tax_type={tax_type}"
        )
        return {
            "data": {
                "salesGoods3Percent": 10000.50,
                "salesService3Percent": 5000.25,
                "salesGoods5Percent": 3000.00,
                "taxPeriod": "2026-01-01至2026-03-31",
                "taxDueCurrent": 450.15,
                "taxRate": 0.03,
                "declareDate": "2026-04-15",
                "taxExemptSales": "——",
            }
        }

    def _flatten_result_json(self, result_json: dict[str, Any]) -> dict[str, Any]:
        """Flatten nested resultJson structure into {tax_code: {field: value}}.

        Input: {sz_hsqj: {code: "sz_hsqj", data: {final_settment_001_qc: {field1: val1, ...}}, status: "SUCCESS"}}
        Output: {sz_hsqj: {final_settment_001_qc.field1: val1, ...}}
        """
        flattened = {}
        for tax_code, entry in result_json.items():
            if not isinstance(entry, dict) or "data" not in entry:
                flattened[tax_code] = entry
                continue

            entry_data = entry.get("data", {})
            flat_fields = {}
            for table_name, fields in entry_data.items():
                if isinstance(fields, dict):
                    for field_key, value in fields.items():
                        # Use table_name.field_key as composite key
                        # Also keep plain field_key for direct lookup
                        flat_fields[field_key] = value
                        flat_fields[f"{table_name}.{field_key}"] = value
                else:
                    flat_fields[table_name] = fields

            flattened[tax_code] = flat_fields

        return flattened
