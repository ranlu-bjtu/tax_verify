"""Compare configured tax declaration forms by outer taskId.

This is the extensible version of the small VAT main-table smoke script.  A
new form comparison should normally be added as one CompareTarget entry: API
tax code/table, ID workbook/sheet, query-result keywords, optional detail form
keywords, and an extraction strategy.
"""

from __future__ import annotations

import argparse
import base64
import html
import json
import logging
import re
import sys
import time
import urllib.parse
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import requests
from openpyxl import load_workbook

sys.path.insert(0, ".")

from src.api.api_client import APIClient
from src.compare.comparator import Comparator
from src.compare.value_normalizer import get_normalizer
from src.login.auto_tax_login import CHANJET_TASK_URL
from src.login.browser_manager import BrowserManager
from src.login.task_login_flow import TaskLoginFlow
from src.models.field_mapping import DataType, FieldMapping
from src.navigation.navigation_engine import NavigationEngine
from src.registry.tax_type_registry import TaxTypeRegistry


LOGGER = logging.getLogger("compare_tax_forms")

WORKBOOK_ROOT = (
    Path.home()
    / "xwechat_files"
    / "wxid_ok3uvjq21ydu22_098f"
    / "msg"
    / "file"
    / "2026-04"
)
LOCAL_WORKBOOK_ROOT = Path("mappings") / "id_workbooks"
VAT_WORKBOOK = "增值税小规模纳税人ID定义-5.16增加附列资料二ok-8.27增加发票归集统计表ok-12.29ok-1.16ok-2.10ok菁菁开发提供主表附加明细ID修改.xlsx"
VAT_GENERAL_WORKBOOK = "增值税一般纳税人.xlsx"
CIT_WORKBOOK = "企业所得税主表.xlsx"

FIELD_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
TEXT_FIELDS = {"nsrsbh", "nsrmc", "nsssq", "djxh"}
DASH_ZERO_VALUES = {"——", "—", "-", "/", "－"}
PROBLEM_STATUSES = {"mismatch", "api_missing", "web_missing", "parse_error", "mapping_error"}
QUERY_URL_HINTS = ("sbxxcx", "sbxx/sbxxcx", "zhcx/sbxx")
TASK_EXECUTION_LOG_URL = (
    "https://data-task-management.chanapp.chanjet.com/"
    "pub-tax-management/tTaskExecutionLog/getPageListByTaskId"
)
CURRENT_PERIOD_LOG_KEYWORDS = ("成功保存数据", "是否是当期")
UNDECLARED_VAT_GENERAL_PATH = "/sbzx/view/lzsfjssb/#/declare/zzsybnsrsb?jyjkId=10"
UNDECLARED_VAT_MENU_KEYWORDS = {
    "vat_general_main": ("主表", "增值税及附加税费申报表"),
    "vat_general_appendix1": ("附列资料一", "本期销售情况明细"),
    "vat_general_appendix2": ("附列资料二", "本期进项税额明细"),
    "vat_general_appendix3": ("附列资料三", "扣除项目明细"),
    "vat_general_appendix4": ("附列资料四", "税额抵减情况表"),
    "vat_general_appendix5": ("附列资料五", "附加税费情况表"),
}


@dataclass(frozen=True)
class CompareTarget:
    target_id: str
    tax_type: str
    tax_code: str
    api_table: str
    workbook_name: str
    sheet_name: str
    form_code: str
    form_name: str
    query_keywords: tuple[str, ...]
    detail_form_keywords: tuple[str, ...] = ()
    loader: str = "layout_scan"
    extractor: str = "layout_scan"


TARGETS: dict[str, CompareTarget] = {
    "vat_small_main": CompareTarget(
        target_id="vat_small_main",
        tax_type="VAT_SMALL_SCALE",
        tax_code="sz_zzs",
        api_table="zzszb_qc",
        workbook_name=VAT_WORKBOOK,
        sheet_name="主表",
        form_code="VAT_SMALL_SCALE_MAIN",
        form_name="增值税及附加税费申报表（小规模纳税人适用）",
        query_keywords=("增值税及附加税费申报表", "小规模纳税人适用"),
        loader="vat_main",
        extractor="line_table",
    ),
    "vat_small_appendix1": CompareTarget(
        target_id="vat_small_appendix1",
        tax_type="VAT_SMALL_SCALE",
        tax_code="sz_zzs",
        api_table="zzsflzl_qc",
        workbook_name=VAT_WORKBOOK,
        sheet_name="附列资料一",
        form_code="VAT_SMALL_SCALE_APPENDIX1",
        form_name="增值税及附加税费申报表（小规模纳税人适用）附列资料（一）（服务、不动产和无形资产扣除项目明细）",
        query_keywords=("增值税及附加税费申报表", "小规模纳税人适用"),
        detail_form_keywords=("附列资料（一）", "服务、不动产和无形资产扣除项目明细"),
    ),
    "vat_small_appendix2": CompareTarget(
        target_id="vat_small_appendix2",
        tax_type="VAT_SMALL_SCALE",
        tax_code="sz_zzs",
        api_table="zzsflzl2_qc",
        workbook_name=VAT_WORKBOOK,
        sheet_name="附列资料二",
        form_code="VAT_SMALL_SCALE_APPENDIX2",
        form_name="增值税及附加税费申报表（小规模纳税人适用）附列资料（二）（附加税费情况表）",
        query_keywords=("增值税及附加税费申报表", "小规模纳税人适用"),
        detail_form_keywords=("附列资料（二）", "附加税费情况表"),
    ),
    "cit_a_main": CompareTarget(
        target_id="cit_a_main",
        tax_type="CIT_A_PREPAY",
        tax_code="sz_qysds",
        api_table="qysds_zb_qc",
        workbook_name=CIT_WORKBOOK,
        sheet_name="主表",
        form_code="CIT_A_MAIN",
        form_name="A200000 中华人民共和国企业所得税月（季）度预缴纳税申报表（A类）",
        query_keywords=("A200000", "企业所得税月（季）度预缴纳税申报表", "A类"),
        detail_form_keywords=("A200000", "企业所得税月（季）度预缴纳税申报表（A类）"),
    ),
    "vat_general_main": CompareTarget(
        target_id="vat_general_main",
        tax_type="VAT_GENERAL",
        tax_code="sz_zzs",
        api_table="zzszb_qc",
        workbook_name=VAT_GENERAL_WORKBOOK,
        sheet_name="主表",
        form_code="VAT_GENERAL_MAIN",
        form_name="增值税纳税申报表（一般纳税人适用）",
        query_keywords=("增值税", "一般纳税人适用"),
        detail_form_keywords=("增值税纳税申报表", "一般纳税人适用"),
    ),
    "vat_general_appendix1": CompareTarget(
        target_id="vat_general_appendix1",
        tax_type="VAT_GENERAL",
        tax_code="sz_zzs",
        api_table="zzsfb1_qc",
        workbook_name=VAT_GENERAL_WORKBOOK,
        sheet_name="附表1",
        form_code="VAT_GENERAL_APPENDIX1",
        form_name="增值税纳税申报表附列资料（一）（本期销售情况明细）",
        query_keywords=("增值税", "一般纳税人适用"),
        detail_form_keywords=("附列资料（一）", "本期销售情况明细"),
    ),
    "vat_general_appendix2": CompareTarget(
        target_id="vat_general_appendix2",
        tax_type="VAT_GENERAL",
        tax_code="sz_zzs",
        api_table="zzsfb2_qc",
        workbook_name=VAT_GENERAL_WORKBOOK,
        sheet_name="附表2",
        form_code="VAT_GENERAL_APPENDIX2",
        form_name="增值税纳税申报表附列资料（二）（本期进项税额明细）",
        query_keywords=("增值税", "一般纳税人适用"),
        detail_form_keywords=("附列资料（二）", "本期进项税额明细"),
    ),
    "vat_general_appendix3": CompareTarget(
        target_id="vat_general_appendix3",
        tax_type="VAT_GENERAL",
        tax_code="sz_zzs",
        api_table="zzsfb3_qc",
        workbook_name=VAT_GENERAL_WORKBOOK,
        sheet_name="附表3",
        form_code="VAT_GENERAL_APPENDIX3",
        form_name="增值税纳税申报表附列资料（三）（服务、不动产和无形资产扣除项目明细）",
        query_keywords=("增值税", "一般纳税人适用"),
        detail_form_keywords=("附列资料（三）", "扣除项目明细"),
    ),
    "vat_general_appendix4": CompareTarget(
        target_id="vat_general_appendix4",
        tax_type="VAT_GENERAL",
        tax_code="sz_zzs",
        api_table="zzsfb4_qc",
        workbook_name=VAT_GENERAL_WORKBOOK,
        sheet_name="附表4",
        form_code="VAT_GENERAL_APPENDIX4",
        form_name="增值税纳税申报表附列资料（四）（税额抵减情况表）",
        query_keywords=("增值税", "一般纳税人适用"),
        detail_form_keywords=("附列资料（四）", "税额抵减情况表"),
    ),
    "vat_general_appendix5": CompareTarget(
        target_id="vat_general_appendix5",
        tax_type="VAT_GENERAL",
        tax_code="sz_zzs",
        api_table="zzsfb5_qc",
        workbook_name=VAT_GENERAL_WORKBOOK,
        sheet_name="附表5",
        form_code="VAT_GENERAL_APPENDIX5",
        form_name="增值税及附加税费申报表附列资料（五）（附加税费情况表）",
        query_keywords=("增值税", "一般纳税人适用"),
        detail_form_keywords=("附列资料（五）", "附加税费情况表"),
    ),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare configured tax forms by taskId.")
    parser.add_argument("--task-id", required=True, help="Outer Chanjet taskId.")
    parser.add_argument(
        "--targets",
        default="auto",
        help=f"Comma-separated target ids, 'auto', or 'all'. Available: {', '.join(TARGETS)}",
    )
    parser.add_argument("--config-root", default="config")
    parser.add_argument("--cdp-port", type=int, default=9222)
    parser.add_argument("--mode", choices=["auto", "connect", "launch"], default="auto")
    parser.add_argument("--user-data-dir", default="./browser_profile/etax_compare_forms")
    parser.add_argument("--plugin-path", default=r"C:\Users\Administrator\Downloads\EtaxPlugin")
    parser.add_argument("--chanjet-timeout", type=int, default=300)
    parser.add_argument("--tax-timeout", type=int, default=180)
    parser.add_argument("--skip-api", action="store_true", help="Only load workbook mappings; do not call Chanjet API.")
    parser.add_argument("--skip-browser", action="store_true", help="Only load API/workbook mapping; do not open tax pages.")
    parser.add_argument("--skip-pdf", action="store_true", help="Do not save a PDF copy of the compared tax page.")
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args()


def setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def resolve_targets(value: str) -> list[CompareTarget]:
    if value.strip().lower() == "auto":
        raise ValueError("'auto' targets require API data; call resolve_auto_targets after fetch_api")
    if value.strip().lower() == "all":
        return list(TARGETS.values())
    resolved = []
    for raw_id in value.split(","):
        target_id = raw_id.strip()
        if not target_id:
            continue
        if target_id not in TARGETS:
            raise KeyError(f"Unknown target '{target_id}'. Available: {', '.join(TARGETS)}")
        resolved.append(TARGETS[target_id])
    return resolved


def is_auto_targets(value: str) -> bool:
    return value.strip().lower() == "auto"


def resolve_auto_targets(api_by_tax: dict[str, Any], mappings_by_target: dict[str, list[FieldMapping]]) -> list[CompareTarget]:
    selected_ids: list[str] = []

    # CIT is independent and can be selected directly from its configured API table.
    if target_api_coverage(api_by_tax, TARGETS["cit_a_main"], mappings_by_target["cit_a_main"]) > 0:
        selected_ids.append("cit_a_main")

    vat_ids = resolve_auto_vat_targets(api_by_tax, mappings_by_target)
    selected_ids.extend(vat_ids)

    selected = [TARGETS[target_id] for target_id in TARGETS if target_id in selected_ids]
    LOGGER.info("Auto-selected targets: %s", ", ".join(target.target_id for target in selected) or "(none)")
    return selected


def resolve_auto_vat_targets(api_by_tax: dict[str, Any], mappings_by_target: dict[str, list[FieldMapping]]) -> list[str]:
    general_ids = [
        "vat_general_main",
        "vat_general_appendix1",
        "vat_general_appendix2",
        "vat_general_appendix3",
        "vat_general_appendix4",
        "vat_general_appendix5",
    ]
    small_ids = ["vat_small_main", "vat_small_appendix1", "vat_small_appendix2"]

    general_appendices = [
        target_id
        for target_id in general_ids[1:]
        if target_has_prefixed_table(api_by_tax, TARGETS[target_id])
        and target_api_coverage(api_by_tax, TARGETS[target_id], mappings_by_target[target_id]) > 0
    ]
    small_appendices = [
        target_id
        for target_id in small_ids[1:]
        if target_has_prefixed_table(api_by_tax, TARGETS[target_id])
        and target_api_coverage(api_by_tax, TARGETS[target_id], mappings_by_target[target_id]) > 0
    ]

    if general_appendices:
        return [target_id for target_id in general_ids if target_id == "vat_general_main" or target_id in general_appendices]
    if small_appendices:
        return [target_id for target_id in small_ids if target_id == "vat_small_main" or target_id in small_appendices]

    general_main_coverage = target_api_coverage(api_by_tax, TARGETS["vat_general_main"], mappings_by_target["vat_general_main"])
    small_main_coverage = target_api_coverage(api_by_tax, TARGETS["vat_small_main"], mappings_by_target["vat_small_main"])
    if general_main_coverage <= 0 and small_main_coverage <= 0:
        return []
    if general_main_coverage >= small_main_coverage:
        return ["vat_general_main"]
    return ["vat_small_main"]


def target_has_prefixed_table(api_by_tax: dict[str, Any], target: CompareTarget) -> bool:
    tax_data = api_by_tax.get(target.tax_code, {})
    if not isinstance(tax_data, dict):
        return False
    if target.api_table in tax_data and tax_data.get(target.api_table) not in (None, "", {}, []):
        return True
    prefix = f"{target.api_table}."
    return any(str(key).startswith(prefix) for key in tax_data)


def target_api_coverage(api_by_tax: dict[str, Any], target: CompareTarget, mappings: list[FieldMapping]) -> int:
    return sum(1 for mapping in mappings if is_effective_api_value(api_value(api_by_tax, target, mapping.field_id)))


def is_effective_api_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str) and value.strip() == "":
        return False
    return True


def find_workbook(name: str) -> Path:
    search_roots = [LOCAL_WORKBOOK_ROOT, WORKBOOK_ROOT]
    matches = [
        p
        for root in search_roots
        if root.exists()
        for p in root.rglob(name)
        if not p.name.startswith("~$")
    ]
    if not matches:
        raise FileNotFoundError(f"Workbook not found: {name}; searched={search_roots}")
    return matches[0]


def load_mappings(target: CompareTarget) -> list[FieldMapping]:
    workbook = find_workbook(target.workbook_name)
    if target.loader == "vat_main":
        mappings = load_vat_main_mappings(target, workbook)
    else:
        mappings = load_layout_scan_mappings(target, workbook)
    LOGGER.info("Loaded %s field IDs for %s from %s/%s", len(mappings), target.target_id, workbook, target.sheet_name)
    return mappings


def load_vat_main_mappings(target: CompareTarget, workbook: Path) -> list[FieldMapping]:
    wb = load_workbook(workbook, data_only=True, read_only=True)
    ws = wb[target.sheet_name]
    mappings: list[FieldMapping] = []
    seen: set[str] = set()
    for row_idx, row in enumerate(ws.iter_rows(values_only=True), start=1):
        if row_idx in (2, 3, 4):
            for value in row:
                field_id = str(value).strip() if value is not None else ""
                if field_id in TEXT_FIELDS and field_id not in seen:
                    seen.add(field_id)
                    mappings.append(make_mapping(target, field_id, DataType.TEXT, row_idx=row_idx))

        line_no = str(row[2]).strip() if len(row) > 2 and row[2] is not None else ""
        if not line_no:
            continue
        for ordinal, value in enumerate(row[3:7]):
            field_id = str(value).strip() if value is not None else ""
            if FIELD_ID_RE.match(field_id) and field_id not in seen:
                seen.add(field_id)
                mappings.append(
                    make_mapping(
                        target,
                        field_id,
                        infer_data_type(field_id),
                        line_no=line_no,
                        row_idx=row_idx,
                        col_idx=ordinal,
                    )
                )
    wb.close()
    return mappings


def load_layout_scan_mappings(target: CompareTarget, workbook: Path) -> list[FieldMapping]:
    wb = load_workbook(workbook, data_only=True, read_only=True)
    if target.sheet_name not in wb.sheetnames:
        raise ValueError(f"Sheet not found: {target.sheet_name}; available={wb.sheetnames}")
    ws = wb[target.sheet_name]
    mappings: list[FieldMapping] = []
    seen: set[str] = set()
    for row_idx, row in enumerate(ws.iter_rows(values_only=True), start=1):
        for col_idx, value in enumerate(row, start=1):
            field_id = str(value).strip() if value is not None else ""
            if not FIELD_ID_RE.match(field_id) or field_id in seen:
                continue
            seen.add(field_id)
            mappings.append(
                make_mapping(
                    target,
                    field_id,
                    infer_data_type(field_id),
                    line_no=find_line_no(row, col_idx),
                    row_name=find_row_name(row, col_idx),
                    row_idx=row_idx,
                    col_idx=col_idx,
                )
            )
    wb.close()
    return mappings


def find_line_no(row: tuple[Any, ...], col_idx: int | None = None) -> str:
    search_values = row[: max(col_idx - 1, 0)] if col_idx is not None else row[:4]
    for value in reversed(search_values):
        text = str(value).strip() if value is not None else ""
        if re.fullmatch(r"(FZ)?\d+[A-Za-z]?(\.\d+)?([=（(].*)?", text):
            return text
    return ""


def find_row_name(row: tuple[Any, ...], col_idx: int) -> str:
    candidates = []
    for value in row[: max(col_idx - 1, 0)]:
        text = str(value).strip() if value is not None else ""
        if not text or FIELD_ID_RE.match(text) or re.fullmatch(r"\d+(\.\d+)?", text):
            continue
        candidates.append(text)
    return candidates[-1] if candidates else ""


def infer_data_type(field_id: str) -> DataType:
    lower = field_id.lower()
    if lower in TEXT_FIELDS:
        return DataType.TEXT
    if lower.endswith("sl") or "taxrate" in lower or lower.endswith("_rate"):
        return DataType.RATE
    if "cyrs" in lower or lower.endswith("rs") or lower.endswith("count"):
        return DataType.INTEGER
    return DataType.AMOUNT


def make_mapping(
    target: CompareTarget,
    field_id: str,
    data_type: DataType,
    line_no: str = "",
    row_name: str = "",
    row_idx: int | None = None,
    col_idx: int | None = None,
) -> FieldMapping:
    return FieldMapping(
        tax_type=target.tax_type,
        form_code=target.form_code,
        form_name=target.form_name,
        sheet_name=target.sheet_name,
        field_id=field_id,
        display_name=field_id,
        row_name=row_name,
        line_no=line_no,
        data_type=data_type,
        web_cell_id=field_id,
        web_row_index=row_idx,
        web_col_index=col_idx,
        api_json_path=f"$.data.{target.tax_code}.{target.api_table}.{field_id}",
    )


def fetch_api(task_id: str) -> tuple[dict[str, Any], str]:
    response = APIClient().fetch_by_task_id(task_id)
    if response.get("error"):
        raise RuntimeError(f"API fetch failed: {response.get('error')}")
    return response.get("data", {}), response.get("province", "")


def fetch_current_period_flag(task_id: str) -> bool | None:
    """Return latest '成功保存数据-是否是当期' logInfo as bool.

    None means the task log does not contain this marker, so callers should keep
    the normal declared-query flow.
    """
    resp = requests.get(TASK_EXECUTION_LOG_URL, params={"taskId": task_id}, timeout=20)
    resp.raise_for_status()
    body = resp.json()
    logs = body.get("data") or []
    matched = [
        item
        for item in logs
        if all(keyword in str(item.get("logType", "")) for keyword in CURRENT_PERIOD_LOG_KEYWORDS)
    ]
    if not matched:
        LOGGER.info("No current-period marker found in task execution logs")
        return None

    latest = sorted(
        enumerate(matched),
        key=lambda pair: (pair[1].get("createdStamp") or 0, pair[0]),
    )[-1][1]
    raw_value = latest.get("logInfo")
    flag = parse_bool(raw_value)
    LOGGER.info(
        "Task current-period marker: logInfo=%s parsed=%s createdStamp=%s",
        raw_value,
        flag,
        latest.get("createdStamp"),
    )
    return flag


def parse_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text == "true":
        return True
    if text == "false":
        return False
    return None


def api_value(api_by_tax: dict[str, Any], target: CompareTarget, field_id: str) -> Any:
    tax_data = api_by_tax.get(target.tax_code, {})
    if not isinstance(tax_data, dict):
        return None
    table_key = f"{target.api_table}.{field_id}" if target.api_table else field_id
    if table_key in tax_data:
        return tax_data[table_key]
    return tax_data.get(field_id)


def connect_browser(args: argparse.Namespace) -> BrowserManager:
    bm = BrowserManager()
    if args.mode in {"auto", "connect"}:
        try:
            bm.connect_cdp(args.cdp_port)
            return bm
        except Exception as exc:
            if args.mode == "connect":
                raise
            LOGGER.info("CDP connect failed, launching Chrome instead: %s", exc)
    bm.launch_with_extension(
        {
            "user_data_dir": args.user_data_dir,
            "cdp_port": args.cdp_port,
            "plugin_path": args.plugin_path,
        }
    )
    return bm


def wait_for_chanjet_login(bm: BrowserManager, timeout: int) -> Any:
    start = time.time()
    while time.time() - start < timeout:
        page = bm.find_page_by_url("chanjet.com")
        if page:
            title = page.title()
            if title and "登录" not in title and "Login" not in title:
                return page
        time.sleep(3)
    raise TimeoutError("Chanjet login was not detected before timeout")


def get_web_config(config_root: str, tax_type: str):
    registry = TaxTypeRegistry()
    registry.load_all_from_dir(config_root)
    if tax_type in registry.list_all():
        return registry.get(tax_type).forms[0].web_config
    return registry.get("VAT_SMALL_SCALE").forms[0].web_config


def find_existing_tax_page(bm: BrowserManager, province: str):
    if not province:
        return None
    host = f"etax.{province}.chinatax.gov.cn"
    candidates = []
    for page in bm.get_all_pages():
        try:
            if urllib.parse.urlparse(page.url or "").hostname != host:
                continue
            text = page.evaluate("document.body ? document.body.innerText.slice(0, 3000) : ''")
            if any(
                hint in text
                for hint in (
                    "我要查询",
                    "我要办税",
                    "纳税人识别号",
                    "统一社会信用代码",
                    "申报信息查询",
                    "申报信息查询详情",
                    "首页",
                    "返回",
                    "增值税",
                    "提交申报",
                )
            ):
                candidates.append(page)
        except Exception:
            try:
                page.keyboard.press("Escape")
            except Exception:
                pass
            continue
    for page in candidates:
        if "sbxxcxxq" in (page.url or ""):
            return page
    if candidates:
        return candidates[0]
    return None


def is_query_page(page) -> bool:
    url = (page.url or "").lower()
    return any(hint in url for hint in QUERY_URL_HINTS)


def ensure_target_page(page, target: CompareTarget, mappings: list[FieldMapping], web_config):
    if not is_target_detail_page(page, target, mappings):
        if not is_query_page(page):
            LOGGER.info("Navigating to declaration information query page")
            navigate_to_query_page(page, web_config)
        if not is_target_detail_page(page, target, mappings):
            LOGGER.info("Opening declaration row for %s", target.target_id)
            opened_page = click_declaration_row(page, target.query_keywords)
            if opened_page:
                page = opened_page

    page.wait_for_load_state("domcontentloaded", timeout=15000)
    time.sleep(2)
    if target.detail_form_keywords:
        select_detail_form(page, target.detail_form_keywords)
    if not is_target_detail_page(page, target, mappings):
        LOGGER.warning("Target detail page was not positively detected for %s; continuing extraction anyway", target.target_id)
    return page


def navigate_to_query_page(page, web_config) -> None:
    url = page.url or ""
    host_match = re.search(r"https://(etax\.[^/]+)", url)
    if host_match:
        target_url = f"https://{host_match.group(1)}/szc/szzh/sjswszzh/spHandler?cdlj=/szzh/zhcx/sbxx/sbxxcx"
        page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
        time.sleep(5)
        if is_query_page(page):
            return
    NavigationEngine(page).navigate_to_form(web_config)


def navigate_to_undeclared_vat_page(page, province: str):
    """Open the province-specific undeclared VAT declaration page."""
    current_url = page.url or ""
    if UNDECLARED_VAT_GENERAL_PATH.split("#", 1)[0] in current_url:
        LOGGER.info("Already on undeclared declaration page: %s", current_url)
        time.sleep(5)
        return page
    origin_match = re.match(r"(https://etax\.[^/]+)", current_url)
    fallback_origin = origin_match.group(1) if origin_match else ""
    target_urls = []
    if fallback_origin:
        target_urls.append(f"{fallback_origin}{UNDECLARED_VAT_GENERAL_PATH}")
    target_urls.append(f"https://etax.{province}.chinatax.gov.cn:8443{UNDECLARED_VAT_GENERAL_PATH}")
    target_urls = list(dict.fromkeys(target_urls))

    last_error = None
    for target_url in target_urls:
        LOGGER.info("Current-period marker is false; opening undeclared declaration URL: %s", target_url)
        try:
            page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
            break
        except Exception as exc:
            last_error = exc
            LOGGER.warning("Undeclared URL failed: %s", exc)
            time.sleep(1)
    else:
        raise last_error
    time.sleep(5)
    return page


def prepare_undeclared_page_for_target(page, target: CompareTarget) -> None:
    """On undeclared VAT pages, open the editable declaration form before extraction."""
    result = "fill_button_not_found"
    deadline = time.time() + 45
    while time.time() < deadline:
        try:
            result = page.evaluate(
                """(targetId) => {
                    const body = document.body ? document.body.innerText : '';
                    if (body.includes('\\u62a5\\u8868\\u5217\\u8868')) return 'already_form_view';

                    const label = '\\u6211\\u8981\\u586b\\u8868';
                    const buttons = Array.from(document.querySelectorAll('button'))
                        .filter((el) => el.offsetParent !== null);
                    const button = buttons.find((el) => (el.innerText || el.textContent || '').trim() === label);
                    if (!button) return 'fill_button_not_found';
                    button.scrollIntoView({ block: 'center' });
                    button.click();
                    return `clicked_${targetId}`;
                }""",
                target.target_id,
            )
        except Exception as exc:
            LOGGER.info("Waiting for undeclared page to settle for %s: %s", target.target_id, exc)
            time.sleep(2)
            continue
        if result != "fill_button_not_found":
            break
        time.sleep(2)
    LOGGER.info("Undeclared form prepare result for %s: %s", target.target_id, result)
    time.sleep(5)

    menu_keywords = UNDECLARED_VAT_MENU_KEYWORDS.get(target.target_id)
    if menu_keywords:
        menu_result = page.evaluate(
            """(keywords) => {
                const normalize = (value) => String(value || '')
                    .replace(/\\s+/g, '')
                    .replace(/[（）()]/g, '');
                const wanted = keywords.map(normalize);
                const items = Array.from(document.querySelectorAll(
                    '.gt-collapse-menu-sidebar-content li, .gt-collapse-menu-sidebar-content [class*=menu__item]'
                )).filter((el) => el.offsetParent !== null);
                const item = items.find((el) => {
                    const text = normalize(el.innerText || el.textContent || '');
                    return wanted.every((kw) => text.includes(kw));
                });
                if (!item) return 'menu_item_not_found';
                if (String(item.className || '').includes('t-is-active')) return 'already_selected';
                item.scrollIntoView({ block: 'center' });
                item.click();
                return 'clicked_menu_item';
            }""",
            list(menu_keywords),
        )
        LOGGER.info("Undeclared menu select result for %s: %s", target.target_id, menu_result)
        wait_for_undeclared_target_visible(page, target, menu_keywords)
        return

    if target.detail_form_keywords:
        select_detail_form(page, target.detail_form_keywords)


def wait_for_undeclared_target_visible(page, target: CompareTarget, menu_keywords: tuple[str, ...]) -> None:
    expected = target_title_keywords(target, menu_keywords)
    deadline = time.time() + 30
    while time.time() < deadline:
        visible = page.evaluate(
            """(keywords) => {
                const normalize = (value) => String(value || '')
                    .replace(/\\s+/g, '')
                    .replace(/[（）()]/g, '');
                const wanted = keywords.map(normalize);
                const activeItems = Array.from(document.querySelectorAll(
                    '.gt-collapse-menu-sidebar-content .t-is-active, .gt-collapse-menu-sidebar-content [class*=active]'
                )).filter((el) => el.offsetParent !== null);
                return activeItems.some((el) => {
                    const text = normalize(el.innerText || el.textContent || '');
                    return wanted.every((kw) => text.includes(kw));
                });
            }""",
            list(expected),
        )
        if visible:
            LOGGER.info("Undeclared target visible for %s: %s", target.target_id, expected)
            time.sleep(4)
            return
        time.sleep(1)
    LOGGER.warning("Timed out waiting for undeclared target content: %s keywords=%s", target.target_id, expected)


def target_title_keywords(target: CompareTarget, menu_keywords: tuple[str, ...]) -> tuple[str, ...]:
    if target.target_id == "vat_general_main":
        return ("增值税及附加税费申报表",)
    if "appendix" in target.target_id:
        return menu_keywords
    return target.detail_form_keywords or menu_keywords


def is_target_detail_page(page, target: CompareTarget, mappings: list[FieldMapping]) -> bool:
    try:
        body_text = page.evaluate("document.body ? document.body.innerText.slice(0, 5000) : ''")
    except Exception:
        body_text = ""
    if target.detail_form_keywords and all(keyword in body_text for keyword in target.detail_form_keywords):
        return True
    return count_business_fields(page, mappings) >= max(5, min(12, len(mappings) // 4))


def has_any_field(page, mappings: list[FieldMapping]) -> bool:
    for mapping in mappings[:30]:
        if extract_field_value(page, mapping) not in (None, ""):
            return True
    return False


def count_business_fields(page, mappings: list[FieldMapping]) -> int:
    count = 0
    for mapping in mappings:
        if mapping.field_id in TEXT_FIELDS:
            continue
        if extract_field_value(page, mapping) not in (None, ""):
            count += 1
    return count


def click_declaration_row(page, keywords: tuple[str, ...]):
    before_pages = set(page.context.pages)
    result = page.evaluate(
        """(keywords) => {
            function findComponents(el, out = []) {
                if (el.__vue__) out.push(el.__vue__);
                for (const child of el.children || []) findComponents(child, out);
                return out;
            }
            const comp = findComponents(document.body).find((v) => v.$options && v.$options.name === 'sbxxcx');
            if (comp && comp.$data && Array.isArray(comp.$data.data)) {
                const rowIndex = comp.$data.data.findIndex((row) => {
                    const text = Object.values(row || {}).map((v) => String(v ?? '')).join('');
                    return keywords.every((kw) => text.includes(kw));
                });
                if (rowIndex >= 0 && typeof comp.rehandleClickOp === 'function') {
                    comp.rehandleClickOp(comp.$data.data[rowIndex], rowIndex);
                    return 'clicked_vue';
                }
            }
            const nodes = Array.from(document.querySelectorAll('tr, .el-table__row, li, div'));
            const hit = nodes.find((el) => {
                const text = (el.innerText || el.textContent || '').replace(/\\s+/g, '');
                return keywords.every((kw) => text.includes(kw));
            });
            if (!hit) return 'not_found';
            const row = hit.closest('tr, .el-table__row, li, [class*=row]') || hit;
            const buttons = Array.from(row.querySelectorAll('a, button, [role=button], .ant-btn, .el-button'))
                .filter((el) => el.offsetParent !== null);
            const detail = buttons.find((el) => /(查看|详情|申报|查询|打开)/.test(el.innerText || el.textContent || ''));
            (detail || buttons[buttons.length - 1] || hit).click();
            return 'clicked_dom';
        }""",
        list(keywords),
    )
    if not str(result).startswith("clicked"):
        raise RuntimeError(f"Declaration row was not found for keywords={keywords}; result={result}")
    time.sleep(5)
    for candidate in page.context.pages:
        if candidate not in before_pages and "sbxxcxxq" in (candidate.url or ""):
            candidate.bring_to_front()
            return candidate
    for candidate in page.context.pages:
        if "sbxxcxxq" in (candidate.url or ""):
            candidate.bring_to_front()
            return candidate
    return page


def select_detail_form(page, keywords: tuple[str, ...]) -> None:
    result = page.evaluate(
        """(keywords) => {
            const body = document.body ? document.body.innerText : '';
            if (keywords.every((kw) => body.includes(kw))) return 'already_visible';

            const all = Array.from(document.querySelectorAll('*')).filter((el) => el.offsetParent !== null);
            const exact = all.find((el) => {
                const text = (el.innerText || el.textContent || '').replace(/\\s+/g, '');
                return keywords.every((kw) => text.includes(kw));
            });
            if (exact) {
                exact.click();
                return 'clicked_visible_text';
            }

            const labels = all.filter((el) => /主附表表单|附表|附列资料/.test(el.innerText || el.textContent || ''));
            for (const label of labels) {
                const container = label.closest('.el-form-item, .ant-form-item, tr, div') || label.parentElement;
                const trigger = container && Array.from(container.querySelectorAll('input, .el-select, .ant-select, button, [role=combobox]'))
                    .find((el) => el.offsetParent !== null);
                if (trigger) {
                    trigger.click();
                    break;
                }
            }

            const options = Array.from(document.querySelectorAll('.el-select-dropdown__item, .ant-select-item, li, [role=option]'))
                .filter((el) => el.offsetParent !== null);
            const option = options.find((el) => {
                const text = (el.innerText || el.textContent || '').replace(/\\s+/g, '');
                return keywords.every((kw) => text.includes(kw));
            });
            if (option) {
                option.click();
                return 'selected_option';
            }
            return 'not_found';
        }""",
        list(keywords),
    )
    LOGGER.info("Detail form select result for %s: %s", keywords, result)
    time.sleep(2)


def extract_field_value(page, mapping: FieldMapping) -> Any:
    return page.evaluate(
        """(mapping) => {
            const fieldId = mapping.field_id;
            const cssEscape = window.CSS && CSS.escape ? CSS.escape(fieldId) : fieldId.replace(/([:.\\[\\],=])/g, '\\\\$1');
            const selectors = [
                `#${cssEscape}`,
                `[name="${fieldId}"]`,
                `[data-cell-id="${fieldId}"]`,
                `[data-field-id="${fieldId}"]`,
                `[data-field="${fieldId}"]`,
                `[id$="${fieldId}"]`
            ];
            for (const selector of selectors) {
                const el = document.querySelector(selector);
                if (!el) continue;
                const tag = el.tagName.toLowerCase();
                if (tag === 'input' || tag === 'textarea' || tag === 'select') return el.value ?? '';
                const value = el.getAttribute('value');
                if (value !== null && value !== '') return value;
                const text = (el.innerText || el.textContent || '').trim();
                if (text !== '') return text;
            }

            const vueVatValue = (() => {
                const match = fieldId.match(/^(.*)_(ybxm_bys|ybxm_bnlj|jzjtxm_bys|jzjtxm_bnlj)$/);
                if (!match) return null;
                const suffixToLine = { ybxm_bys: '1', ybxm_bnlj: '2', jzjtxm_bys: '3', jzjtxm_bnlj: '4' };
                const alias = {
                    cswhjssbqybtse: 'bqybtsecjs',
                    jyffjbqybtse: 'bqybtsejyfj',
                    dfjyfjbqybtse: 'bqybtsedfjyfj',
                };
                const property = alias[match[1]] || match[1];
                const line = suffixToLine[match[2]];

                function findComponents(el, out = []) {
                    if (el.__vue__) out.push(el.__vue__);
                    for (const child of el.children || []) findComponents(child, out);
                    return out;
                }
                function findKey(obj, key, depth = 0, seen = new Set()) {
                    try {
                        if (!obj || typeof obj !== 'object' || depth > 6 || seen.has(obj)) return undefined;
                        seen.add(obj);
                        if (Object.prototype.hasOwnProperty.call(obj, key)) return obj[key];
                        for (const k of Object.keys(obj).slice(0, 120)) {
                            let value;
                            try { value = obj[k]; } catch (_) { continue; }
                            const found = findKey(value, key, depth + 1, seen);
                            if (found !== undefined) return found;
                        }
                    } catch (_) {
                        return undefined;
                    }
                    return undefined;
                }

                for (const comp of findComponents(document.body)) {
                    const rows = findKey(comp.$data, 'sbZzsYbnsr') || findKey(comp, 'sbZzsYbnsr');
                    if (!Array.isArray(rows)) continue;
                    const row = rows.find((item) => String(item && item.ewblxh) === line);
                    if (!row || row[property] === undefined || row[property] === null) continue;
                    return String(row[property]);
                }
                return null;
            })();
            if (vueVatValue !== null) return vueVatValue;

            if (mapping.line_no !== '' && mapping.web_col_index !== null && mapping.web_col_index !== undefined) {
                const wantedLine = String(mapping.line_no).match(/^\\d+/)?.[0];
                const normalizeLabel = (value) => String(value || '')
                    .replace(/\\s+/g, '')
                    .replace(/^其中[:：]?/, '')
                    .replace(/[（]/g, '(')
                    .replace(/[）]/g, ')')
                    .replace(/[，]/g, ',')
                    .replace(/[＝]/g, '=');
                const wantedName = normalizeLabel(mapping.row_name);
                const rows = Array.from(document.querySelectorAll('table tr'));
                for (const tr of rows) {
                    const cells = Array.from(tr.querySelectorAll('th,td'));
                    const texts = cells.map((td) => (td.innerText || td.textContent || '').trim());
                    const rowText = normalizeLabel(texts.join(''));
                    if (wantedName && !rowText.includes(wantedName)) continue;
                    const lineIndex = texts.findIndex((text, idx) => {
                        if (idx > 2) return false;
                        const m = text.match(/^(FZ\\d+|\\d+(?:\\.\\d+)?)(.*)$/);
                        if (!m || m[1] !== wantedLine) return false;
                        const rest = (m[2] || '').trim();
                        return rest === '' || /^[()=+\\-×\\\\\\s]/.test(rest);
                    });
                    if (lineIndex < 0) continue;
                    const offset = Number(mapping.web_col_index);
                    const valueIndex = lineIndex + 1 + Math.max(0, offset - 4);
                    const valueCell = cells[valueIndex] || cells[offset - 2] || cells[cells.length - 1];
                    if (valueCell) return (valueCell.innerText || valueCell.textContent || '').trim();
                }
            }
            return null;
        }""",
        mapping.model_dump(mode="json"),
    )


def extract_web_data(page, mappings: list[FieldMapping]) -> dict[str, Any]:
    data = {mapping.field_id: extract_field_value(page, mapping) for mapping in mappings}
    found = sum(1 for value in data.values() if value not in (None, ""))
    LOGGER.info("Extracted %s/%s web fields", found, len(mappings))
    return data


def compare_target(target: CompareTarget, mappings: list[FieldMapping], api_by_tax: dict[str, Any], web_raw: dict[str, Any]):
    api_norm = {}
    web_norm = {}
    for mapping in mappings:
        normalizer = get_normalizer(mapping.data_type)
        api_norm[mapping.field_id] = normalizer.normalize(clean_value(api_value(api_by_tax, target, mapping.field_id), mapping))
        web_value = adjusted_web_value_for_compare(target, mapping, web_raw)
        web_norm[mapping.field_id] = normalizer.normalize(clean_value(web_value, mapping))
    return Comparator().compare_all(
        mappings=mappings,
        api_data=api_norm,
        web_data=web_norm,
        batch_id=target.target_id,
        company_name="",
        taxpayer_id="",
        period="",
    )


def adjusted_web_value_for_compare(target: CompareTarget, mapping: FieldMapping, web_raw: dict[str, Any]) -> Any:
    value = web_raw.get(mapping.field_id)
    if not should_subtract_current_month_for_vat(target, mapping):
        return value

    monthly_field_id = mapping.field_id.removesuffix("_ybxm_bnlj") + "_ybxm_bys"
    cumulative = parse_amount(value)
    current_month = parse_amount(web_raw.get(monthly_field_id))
    if cumulative is None or current_month is None:
        return value
    adjusted = cumulative - current_month
    return f"{adjusted.quantize(Decimal('0.01'))}"


def should_subtract_current_month_for_vat(target: CompareTarget, mapping: FieldMapping) -> bool:
    return (
        target.tax_code == "sz_zzs"
        and mapping.data_type == DataType.AMOUNT
        and mapping.field_id.endswith("_ybxm_bnlj")
    )


def parse_amount(value: Any) -> Decimal | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text in DASH_ZERO_VALUES:
        return Decimal("0")
    text = text.replace(",", "").replace("￥", "").replace("¥", "")
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


def clean_value(value: Any, mapping: FieldMapping) -> Any:
    if mapping.data_type == DataType.AMOUNT and isinstance(value, str) and value.strip() in DASH_ZERO_VALUES:
        return "0.00"
    return value


def task_output_dir(task_id: str) -> Path:
    return Path("./output/reports") / str(task_id)


def save_result(task_id: str, target: CompareTarget, result) -> Path:
    output_dir = task_output_dir(task_id)
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = output_dir / f"{target.target_id}_compare_{task_id}_{ts}.json"
    path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    return path


def save_web_pdf(page, task_id: str, target: CompareTarget, output_dir: Path) -> Path | None:
    """Save a PDF copy of the currently compared tax page for later verification."""
    pdf_dir = output_dir / "pdf"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    pdf_path = pdf_dir / f"{safe_filename(target.form_name)}_{target.target_id}_{task_id}_{ts}.pdf"

    prepared = False
    try:
        try:
            prepare_page_for_pdf_snapshot(page)
            prepared = True
            page.emulate_media(media="print")
            page.pdf(
                path=str(pdf_path),
                format="A4",
                landscape=True,
                scale=0.72,
                print_background=True,
                prefer_css_page_size=False,
                margin={"top": "8mm", "right": "8mm", "bottom": "8mm", "left": "8mm"},
            )
            LOGGER.info("Saved tax page PDF snapshot for %s: %s", target.target_id, pdf_path)
            cleanup_page_pdf_snapshot(page)
            prepared = False
            return pdf_path
        except Exception as exc:
            LOGGER.warning("page.pdf failed for %s: %s", target.target_id, exc)

        try:
            session = page.context.new_cdp_session(page)
            result = session.send(
                "Page.printToPDF",
                {
                    "printBackground": True,
                    "preferCSSPageSize": False,
                    "paperWidth": 11.69,
                    "paperHeight": 8.27,
                    "scale": 0.72,
                    "marginTop": 0.31,
                    "marginRight": 0.31,
                    "marginBottom": 0.31,
                    "marginLeft": 0.31,
                },
            )
            pdf_path.write_bytes(base64.b64decode(result["data"]))
            try:
                session.detach()
            except Exception:
                pass
            LOGGER.info("Saved tax page PDF via CDP for %s: %s", target.target_id, pdf_path)
            return pdf_path
        except Exception as exc:
            LOGGER.warning("Could not save PDF for %s: %s", target.target_id, exc)

        downloaded = try_download_pdf_from_page(page, pdf_path)
        if downloaded:
            LOGGER.info("Saved tax PDF by page download for %s: %s", target.target_id, downloaded)
            return downloaded
        return None
    finally:
        if prepared:
            cleanup_page_pdf_snapshot(page)


def prepare_page_for_pdf_snapshot(page) -> None:
    page.evaluate(
        """() => {
            const root = document.documentElement;
            root.classList.add('codex-pdf-export');
            let style = document.getElementById('codex-pdf-export-style');
            if (!style) {
                style = document.createElement('style');
                style.id = 'codex-pdf-export-style';
                style.textContent = `
html.codex-pdf-export,
html.codex-pdf-export body,
html.codex-pdf-export #app,
html.codex-pdf-export [id="app"],
html.codex-pdf-export .page-container,
html.codex-pdf-export .g-layout,
html.codex-pdf-export .g-layout--main,
html.codex-pdf-export .g-main,
html.codex-pdf-export .t-layout,
html.codex-pdf-export .t-layout__content,
html.codex-pdf-export main,
html.codex-pdf-export .page-content,
html.codex-pdf-export .wrapper,
html.codex-pdf-export .report-template,
html.codex-pdf-export .is-scroll-panel,
html.codex-pdf-export .gov-tax-report-container,
html.codex-pdf-export .tax-report,
html.codex-pdf-export .gt-collapse-menu,
html.codex-pdf-export .gt-collapse-menu-content,
html.codex-pdf-export .gt-collapse-menu-content_box,
html.codex-pdf-export .gt-collapse-menu-main,
html.codex-pdf-export .gt-collapse-menu-panel,
html.codex-pdf-export .t-table,
html.codex-pdf-export .t-table__content,
html.codex-pdf-export .t-table__body,
html.codex-pdf-export .t-table__body-wrapper,
html.codex-pdf-export .el-table,
html.codex-pdf-export .el-table__body-wrapper,
html.codex-pdf-export .ant-table,
html.codex-pdf-export .ant-table-body {
  height: auto !important;
  max-height: none !important;
  min-height: 0 !important;
  overflow: visible !important;
}
html.codex-pdf-export .page-content,
html.codex-pdf-export .wrapper,
html.codex-pdf-export .report-template,
html.codex-pdf-export .gt-collapse-menu-content,
html.codex-pdf-export .gt-collapse-menu-main {
  width: auto !important;
  max-width: none !important;
}
html.codex-pdf-export .gt-collapse-menu-sidebar,
html.codex-pdf-export .gt-layout-footerbar,
html.codex-pdf-export .gt-layout-footerbar_fix,
html.codex-pdf-export .t-layout__sider,
html.codex-pdf-export .t-affix,
html.codex-pdf-export [class*="footerbar"],
html.codex-pdf-export [class*="countdown"],
html.codex-pdf-export [class*="operation"] {
  display: none !important;
}
html.codex-pdf-export table {
  page-break-inside: auto;
}
html.codex-pdf-export thead {
  display: table-header-group;
}
html.codex-pdf-export tr,
html.codex-pdf-export img,
html.codex-pdf-export svg {
  page-break-inside: avoid;
}
html.codex-pdf-export * {
  -webkit-print-color-adjust: exact !important;
  print-color-adjust: exact !important;
}
`;
                document.head.appendChild(style);
            }
            const scrollables = Array.from(document.querySelectorAll('*')).filter((el) => {
                const style = getComputedStyle(el);
                return /(auto|scroll)/.test(style.overflow + style.overflowY + style.overflowX)
                    && (el.scrollHeight > el.clientHeight || el.scrollWidth > el.clientWidth);
            });
            for (const el of scrollables) {
                el.scrollTop = el.scrollHeight;
                el.scrollLeft = 0;
            }
            window.scrollTo(0, document.body.scrollHeight);
            for (const el of scrollables) {
                el.scrollTop = 0;
                el.scrollLeft = 0;
            }
            window.scrollTo(0, 0);
        }"""
    )
    time.sleep(1)


def cleanup_page_pdf_snapshot(page) -> None:
    try:
        page.evaluate("document.documentElement.classList.remove('codex-pdf-export')")
    except Exception:
        pass
    try:
        page.emulate_media(media="screen")
    except Exception:
        pass


def safe_filename(value: str, max_length: int = 120) -> str:
    invalid = set('<>:"/\\|?*')
    text = "".join("_" if char in invalid or ord(char) < 32 else char for char in str(value or "").strip())
    text = re.sub(r"\s+", "", text).strip("._ ")
    return (text or "税表")[:max_length]


def escape_html(value: Any) -> str:
    if value is None or value == "":
        return '<span class="empty">空</span>'
    return html.escape(str(value))


def relative_report_link(base_path: Path, target_path: str | Path | None) -> str:
    if not target_path:
        return ""
    path = Path(target_path)
    try:
        return path.resolve().relative_to(base_path.parent.resolve()).as_posix()
    except ValueError:
        try:
            return Path(urllib.parse.quote(str(path))).as_posix()
        except Exception:
            return str(path)


def status_label(status: str) -> str:
    labels = {
        "mismatch": ("不一致", "bad"),
        "api_missing": ("接口缺失", "warn"),
        "web_missing": ("网页缺失", "warn"),
        "parse_error": ("解析失败", "bad"),
        "mapping_error": ("映射错误", "bad"),
        "both_missing": ("双方为空", "muted"),
        "tolerance_match": ("容差通过", "ok"),
        "match": ("一致", "ok"),
        "skip": ("跳过", "muted"),
    }
    label, cls = labels.get(status, (status, "muted"))
    return f'<span class="pill {cls}">{html.escape(label)}</span>'


def problem_fields(fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
    status_order = {
        "mismatch": 0,
        "parse_error": 1,
        "mapping_error": 2,
        "api_missing": 3,
        "web_missing": 4,
    }
    return [
        item
        for item in sorted(
            fields,
            key=lambda x: (
                status_order.get(str(x.get("status", "")), 99),
                str(x.get("line_no") or ""),
                str(x.get("field_id") or ""),
            ),
        )
        if str(item.get("status")) in PROBLEM_STATUSES
    ]


def effective_pass_rate(summary: dict[str, Any], fields: list[dict[str, Any]]) -> tuple[int, int, float]:
    total = int(summary.get("total_fields", len(fields)) or 0)
    both_missing = int(summary.get("both_missing_count", 0) or 0)
    skip = int(summary.get("skip_count", 0) or 0)
    denominator = max(0, total - both_missing - skip)
    passed = int(summary.get("match_count", 0) or 0) + int(summary.get("tolerance_match_count", 0) or 0)
    rate = round(passed / denominator * 100, 2) if denominator else 100.0
    return passed, denominator, rate


def render_problem_table(fields: list[dict[str, Any]]) -> str:
    problems = problem_fields(fields)
    if not problems:
        return '<p class="quiet">没有发现需要优先处理的问题字段。</p>'
    rows = []
    for item in problems:
        business_name = item.get("business_name") or item.get("row_name") or item.get("column_name") or item.get("display_name")
        rows.append(
            f"""
            <tr>
              <td>{status_label(str(item.get("status", "")))}</td>
              <td>{escape_html(item.get("line_no"))}</td>
              <td>{escape_html(business_name)}</td>
              <td><code>{escape_html(item.get("field_id"))}</code></td>
              <td>{escape_html(item.get("api_raw_value"))}</td>
              <td>{escape_html(item.get("web_raw_value"))}</td>
              <td>{escape_html(item.get("diff_value"))}</td>
              <td>{escape_html(item.get("detail"))}</td>
            </tr>
            """
        )
    return f"""
    <table>
      <thead>
        <tr>
          <th>状态</th><th>行次</th><th>项目</th><th>字段</th><th>接口值</th><th>网页值</th><th>差异</th><th>说明</th>
        </tr>
      </thead>
      <tbody>{''.join(rows)}</tbody>
    </table>
    """


def render_task_summary_report(task_id: str, outputs: list[dict[str, Any]]) -> Path | None:
    reports = []
    output_dir = task_output_dir(task_id)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"compare_summary_{task_id}_{ts}.html"

    for item in outputs:
        report_path = Path(str(item.get("report_path", "")))
        if not report_path.exists():
            continue
        report = json.loads(report_path.read_text(encoding="utf-8"))
        reports.append({**item, "report": report})

    if not reports:
        return None

    summary_rows = []
    detail_sections = []
    total_problems = 0
    for index, item in enumerate(reports, start=1):
        report = item["report"]
        summary = report.get("summary", {})
        fields = report.get("field_results", [])
        problems = problem_fields(fields)
        total_problems += len(problems)
        passed, denominator, effective_rate = effective_pass_rate(summary, fields)
        form_name = str(report.get("form_name") or report.get("form_code") or item.get("target_id") or "")
        anchor = f"form-{index}"
        report_link = relative_report_link(output_path, item.get("report_path"))
        pdf_link = relative_report_link(output_path, item.get("pdf_path"))
        pdf_html = f'<a href="{html.escape(pdf_link)}">PDF</a>' if pdf_link else '<span class="quiet">未生成</span>'
        summary_rows.append(
            f"""
            <tr>
              <td><a href="#{anchor}">{html.escape(form_name)}</a></td>
              <td>{len(problems)}</td>
              <td>{effective_rate}% <span class="quiet">({passed}/{denominator})</span></td>
              <td>{escape_html(summary.get("match_rate"))}%</td>
              <td>{escape_html(summary.get("mismatch_count"))}</td>
              <td>{escape_html(summary.get("api_missing_count"))}</td>
              <td>{escape_html(summary.get("web_missing_count"))}</td>
              <td>{escape_html(summary.get("both_missing_count"))}</td>
              <td><a href="{html.escape(report_link)}">JSON</a> / {pdf_html}</td>
            </tr>
            """
        )
        detail_sections.append(
            f"""
            <section id="{anchor}" class="form-block">
              <div class="section-title">
                <h2>{html.escape(form_name)}</h2>
                <div class="quiet">有效通过率 {effective_rate}% ({passed}/{denominator})，原始通过率 {escape_html(summary.get("match_rate"))}%</div>
              </div>
              {render_problem_table(fields)}
            </section>
            """
        )

    title = f"taskId {task_id} 对比汇总"
    output_path.write_text(
        f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    :root {{
      color-scheme: light;
      --text: #172033;
      --muted: #667085;
      --line: #d8dee8;
      --bg: #f5f7fb;
      --surface: #ffffff;
      --bad: #b42318;
      --warn: #b54708;
      --ok: #067647;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: "Microsoft YaHei", "Segoe UI", Arial, sans-serif; color: var(--text); background: var(--bg); }}
    main {{ max-width: 1280px; margin: 0 auto; padding: 28px 24px 48px; }}
    h1 {{ margin: 0 0 8px; font-size: 24px; }}
    h2 {{ margin: 0; font-size: 18px; }}
    a {{ color: #175cd3; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    .quiet {{ color: var(--muted); font-size: 13px; }}
    .topline {{ display: flex; justify-content: space-between; gap: 16px; align-items: flex-end; margin-bottom: 20px; }}
    .metric-strip {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; margin: 18px 0 20px; }}
    .metric {{ background: var(--surface); border: 1px solid var(--line); border-radius: 8px; padding: 14px 16px; }}
    .metric-label {{ color: var(--muted); font-size: 13px; }}
    .metric-value {{ font-size: 24px; font-weight: 700; margin-top: 4px; }}
    table {{ width: 100%; border-collapse: collapse; background: var(--surface); border: 1px solid var(--line); border-radius: 8px; overflow: hidden; }}
    th, td {{ border-bottom: 1px solid var(--line); padding: 10px 12px; text-align: left; vertical-align: top; font-size: 13px; }}
    th {{ background: #eef2f7; color: #344054; font-weight: 700; white-space: nowrap; }}
    tr:last-child td {{ border-bottom: 0; }}
    code {{ font-family: Consolas, monospace; font-size: 12px; }}
    .form-block {{ margin-top: 22px; }}
    .section-title {{ display: flex; justify-content: space-between; gap: 12px; align-items: baseline; margin: 0 0 10px; }}
    .pill {{ display: inline-block; min-width: 56px; text-align: center; border-radius: 999px; padding: 2px 8px; font-size: 12px; font-weight: 700; }}
    .pill.bad {{ color: var(--bad); background: #fee4e2; }}
    .pill.warn {{ color: var(--warn); background: #fef0c7; }}
    .pill.ok {{ color: var(--ok); background: #dcfae6; }}
    .pill.muted {{ color: #475467; background: #eaecf0; }}
    .empty {{ color: var(--muted); }}
    @media (max-width: 820px) {{
      main {{ padding: 20px 14px 36px; }}
      .topline, .section-title {{ display: block; }}
      .metric-strip {{ grid-template-columns: 1fr; }}
      table {{ display: block; overflow-x: auto; }}
    }}
  </style>
</head>
<body>
  <main>
    <div class="topline">
      <div>
        <h1>{html.escape(title)}</h1>
        <div class="quiet">生成时间：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}；所有主表和附表结果集中在本页。</div>
      </div>
    </div>
    <section class="metric-strip">
      <div class="metric"><div class="metric-label">表单数量</div><div class="metric-value">{len(reports)}</div></div>
      <div class="metric"><div class="metric-label">需要优先处理的问题字段</div><div class="metric-value">{total_problems}</div></div>
      <div class="metric"><div class="metric-label">结果目录</div><div class="metric-value" style="font-size:16px;">{html.escape(str(output_dir))}</div></div>
    </section>
    <table>
      <thead>
        <tr>
          <th>表单</th><th>问题字段</th><th>有效通过率</th><th>原始通过率</th><th>不一致</th><th>接口缺失</th><th>网页缺失</th><th>双方为空</th><th>文件</th>
        </tr>
      </thead>
      <tbody>{''.join(summary_rows)}</tbody>
    </table>
    {''.join(detail_sections)}
  </main>
</body>
</html>
""",
        encoding="utf-8",
    )
    LOGGER.info("Saved combined task report: %s", output_path)
    return output_path


def try_download_pdf_from_page(page, pdf_path: Path) -> Path | None:
    labels = ("下载PDF", "PDF下载", "下载", "导出PDF", "导出")
    for label in labels:
        try:
            exists = page.evaluate(
                """(label) => {
                    const nodes = Array.from(document.querySelectorAll('a, button, [role=button]'))
                        .filter((el) => el.offsetParent !== null);
                    return nodes.some((el) => (el.innerText || el.textContent || '').replace(/\\s+/g, '').includes(label));
                }""",
                label,
            )
            if not exists:
                continue
            with page.expect_download(timeout=8000) as download_info:
                page.evaluate(
                    """(label) => {
                        const nodes = Array.from(document.querySelectorAll('a, button, [role=button]'))
                            .filter((el) => el.offsetParent !== null);
                        const node = nodes.find((el) => (el.innerText || el.textContent || '').replace(/\\s+/g, '').includes(label));
                        if (!node) return false;
                        node.scrollIntoView({ block: 'center' });
                        node.click();
                        return true;
                    }""",
                    label,
                )
            download = download_info.value
            download.save_as(str(pdf_path))
            return pdf_path
        except Exception:
            continue
    return None


def main() -> int:
    args = parse_args()
    setup_logging(args.log_level)
    return run_compare(args)


def run_compare(args: argparse.Namespace) -> int:
    """Run the taskId-driven comparison flow.

    This function is intentionally importable so the repository has one
    real comparison implementation while multiple CLI wrappers can call it.
    Prefer invoking it through ``main.py`` for day-to-day use.
    """

    if args.skip_api:
        if is_auto_targets(args.targets):
            raise ValueError("--targets auto cannot be used with --skip-api")
        targets = resolve_targets(args.targets)
        mappings_by_target = {target.target_id: load_mappings(target) for target in targets}
        return 0

    api_by_tax, province = fetch_api(args.task_id)
    LOGGER.info("Fetched API data: province=%s tax_codes=%s", province, ", ".join(api_by_tax.keys()))
    current_period_flag = fetch_current_period_flag(args.task_id)
    if is_auto_targets(args.targets):
        mappings_by_target = {target.target_id: load_mappings(target) for target in TARGETS.values()}
        targets = resolve_auto_targets(api_by_tax, mappings_by_target)
    else:
        targets = resolve_targets(args.targets)
        mappings_by_target = {target.target_id: load_mappings(target) for target in targets}
    if not targets:
        LOGGER.warning("No compare targets selected for task_id=%s", args.task_id)
        return 0

    if args.skip_browser:
        for target in targets:
            present = sum(1 for mapping in mappings_by_target[target.target_id] if api_value(api_by_tax, target, mapping.field_id) is not None)
            LOGGER.info("%s API field coverage: %s/%s", target.target_id, present, len(mappings_by_target[target.target_id]))
        if current_period_flag is not None:
            LOGGER.info("Task current-period flag: %s", current_period_flag)
        return 0

    bm = connect_browser(args)
    try:
        page = bm.find_page_by_url("chanjet.com") or bm.get_page()
        page.goto(CHANJET_TASK_URL, wait_until="domcontentloaded", timeout=30000)
        chanjet_page = wait_for_chanjet_login(bm, args.chanjet_timeout)

        tax_page = find_existing_tax_page(bm, province)
        if tax_page:
            LOGGER.info("Reusing existing tax bureau page: province=%s url=%s", province, tax_page.url)
        else:
            flow = TaskLoginFlow(bm, timeout=args.tax_timeout)
            tax_page, info = flow.login(chanjet_page, args.task_id)
            LOGGER.info("Logged into tax bureau: province=%s inner_task_id=%s url=%s", info.province, info.inner_task_id, tax_page.url)

        exit_code = 0
        run_outputs: list[dict[str, Any]] = []
        for target in targets:
            mappings = mappings_by_target[target.target_id]
            web_config = get_web_config(args.config_root, target.tax_type)
            if current_period_flag is False and target.tax_type == "VAT_GENERAL":
                tax_page = navigate_to_undeclared_vat_page(tax_page, province)
                prepare_undeclared_page_for_target(tax_page, target)
            else:
                tax_page = ensure_target_page(tax_page, target, mappings, web_config)
            web_data = extract_web_data(tax_page, mappings)
            result = compare_target(target, mappings, api_by_tax, web_data)
            output_path = save_result(args.task_id, target, result)
            pdf_path = None
            if not args.skip_pdf:
                pdf_path = save_web_pdf(tax_page, args.task_id, target, output_path.parent)
            run_outputs.append(
                {
                    "target_id": target.target_id,
                    "form_name": target.form_name,
                    "report_path": str(output_path),
                    "pdf_path": str(pdf_path) if pdf_path else "",
                }
            )
            summary = result.summary
            LOGGER.info(
                "%s complete: total=%s match=%s mismatch=%s api_missing=%s web_missing=%s match_rate=%s%% report=%s pdf=%s",
                target.target_id,
                summary.total_fields,
                summary.match_count + summary.tolerance_match_count,
                summary.mismatch_count,
                summary.api_missing_count,
                summary.web_missing_count,
                summary.match_rate,
                output_path,
                pdf_path or "",
            )
            if summary.mismatch_count or summary.web_missing_count:
                exit_code = 1
        combined_path = render_task_summary_report(args.task_id, run_outputs)
        if combined_path:
            LOGGER.info("Combined compare report: %s", combined_path)
        return exit_code
    finally:
        bm.close()


if __name__ == "__main__":
    raise SystemExit(main())
