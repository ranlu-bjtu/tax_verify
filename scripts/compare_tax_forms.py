"""Compare configured tax declaration forms by outer taskId.

This is the extensible version of the small VAT main-table smoke script.  A
new form comparison should normally be added as one CompareTarget entry: API
tax code/table, ID workbook/sheet, query-result keywords, optional detail form
keywords, and an extraction strategy.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import html
import json
import logging
import re
import sys
import time
import urllib.parse
import urllib.parse
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

import requests
from openpyxl import load_workbook
from openpyxl.cell.cell import MergedCell
from openpyxl.comments import Comment
from openpyxl.styles import PatternFill

sys.path.insert(0, ".")

from src.api.api_client import APIClient
from src.chanjet_admin.task_execution_log import fetch_current_period_flag as fetch_task_current_period_flag
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
WECHAT_FILE_ROOT = Path.home() / "xwechat_files" / "wxid_ok3uvjq21ydu22_098f" / "msg" / "file"
LOCAL_WORKBOOK_ROOT = Path("mappings") / "id_workbooks"
VAT_WORKBOOK = "增值税小规模纳税人ID定义-5.16增加附列资料二ok-8.27增加发票归集统计表ok-12.29ok-1.16ok-2.10ok菁菁开发提供主表附加明细ID修改.xlsx"
VAT_GENERAL_WORKBOOK = "增值税一般纳税人.xlsx"
CIT_WORKBOOK = "企业所得税主表.xlsx"
CULTURE_FEE_WORKBOOK = "文化事业建设费ID-9.16ok-9.30ok-1.7ok.xlsx"
CONSUMPTION_TAX_MAIN_WORKBOOK = "消费税及附加税费申报表-2026-05-28 09_50_52.xlsx(1).xlsx"
CONSUMPTION_TAX_SURCHARGE_WORKBOOK = "消费税附加税费计算表-2026-05-28 09_50_58.xlsx(1).xlsx"
WORKBOOK_CACHE_ROOT = Path("runtime") / "workbook_cache"
UNSUPPORTED_SHEET_PROTECTION_ATTRS = ("allowResizeRows", "allowResizeColumns")

FIELD_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
TEXT_FIELDS = {"nsrsbh", "nsrmc", "nsrxm", "nsssq", "djxh", "sbpm"}
CONSUMPTION_TAX_TEXT_PREFIXES = (
    "nsrsbh",
    "nsrmc",
    "nsrxm",
    "skssq",
    "ysxfpmc",
    "jldw",
    "jmxzdm",
    "bqsfsy",
    "jmzc",
    "syjmzc",
    "jbr",
    "jbrsfzh",
    "dlr",
    "dljg",
    "slswjg",
    "blrysfz",
    "lxfs",
)
CONSUMPTION_TAX_RATE_PREFIXES = ("desl", "blsl", "sfl", "jzbl")
CONSUMPTION_TAX_NON_API_PREFIXES = (
    "nsrsbh",
    "nsrmc",
    "nsrxm",
    "skssq",
    "bqsfsy",
    "jmzc",
    "syjmzc",
    "jbr",
    "jbrsfzh",
    "dlr",
    "dljg",
    "slswjg",
    "blrysfz",
    "lxfs",
)
DASH_ZERO_VALUES = {"——", "—", "-", "/", "－"}
PROBLEM_STATUSES = {"mismatch", "api_missing", "web_missing", "parse_error", "mapping_error"}
QUALITY_WARNING_STATUSES = PROBLEM_STATUSES | {"both_missing"}
QUERY_URL_HINTS = ("sbxxcx", "sbxx/sbxxcx", "zhcx/sbxx")
TAX_DIGITAL_ACCOUNT_HINTS = (
    "\u7a0e\u52a1\u6570\u5b57\u8d26\u6237",
    "\u8d26\u6237\u67e5\u8be2",
    "\u53d1\u7968\u4e1a\u52a1",
    "\u5408\u89c4\u7406\u7a0e",
)
TAX_PORTAL_HINTS = (
    "\u6211\u8981\u67e5\u8be2",
    "\u6211\u8981\u529e\u7a0e",
    "\u7533\u62a5\u4fe1\u606f\u67e5\u8be2",
    "\u672c\u671f\u5e94\u7533\u62a5",
    "\u7edf\u4e00\u793e\u4f1a\u4fe1\u7528\u4ee3\u7801",
    "\u7eb3\u7a0e\u4eba\u8bc6\u522b\u53f7",
)
API_EXCEL_VALUE_FILL = PatternFill("solid", fgColor="E2F0D9")
API_EXCEL_MISSING_FILL = PatternFill("solid", fgColor="FFF2CC")
UNDECLARED_VAT_GENERAL_PATH = "/sbzx/view/lzsfjssb/#/declare/zzsybnsrsb?jyjkId=10"
VAT_APPENDIX5_ROW_LABELS = {
    "_cjs": "城市维护建设税",
    "_jyfj": "教育费附加",
    "_jyf": "教育费附加",
    "_dfjyfj": "地方教育附加",
    "_hj": "合计",
}
VAT_APPENDIX5_GRID_BASE_COL = 3
VAT_APPENDIX5_GRID_WIDTH = 14
VAT_APPENDIX5_SINGLE_VALUE_LABELS = {
    "dqxztze": "当期新增投资额",
    "sqldkdmje": "上期留抵可抵免金额",
    "jzxqkdmje": "结转下期可抵免金额",
    "dqxzkyykcdldtse": "当期新增可用于扣除的留抵退税额",
    "sqjckyykcdldtse": "上期结存可用于扣除的留抵退税额",
    "jzxqkyykcdldtse": "结转下期可用于扣除的留抵退税额",
}
VAT_APPENDIX5_TEXT_FIELDS = {
    "bqsfsyxwqylslfjmzc",
    "jmzcsyzt",
    "syjmzcqsj",
    "syjmzczsj",
    "bqsfsysdjspycjrhxqydmzc",
    "jbr",
    "jbrsfzhm",
    "lxfs",
}
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
        detail_form_keywords=("增值税及附加税费申报表", "一般纳税人适用"),
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
    "culture_fee_main": CompareTarget(
        target_id="culture_fee_main",
        tax_type="CULTURE_FEE",
        tax_code="sz_whsyjsf",
        api_table="",
        workbook_name=CULTURE_FEE_WORKBOOK,
        sheet_name="文化事业建设费申报表",
        form_code="CULTURE_FEE_MAIN",
        form_name="文化事业建设费申报表",
        query_keywords=("文化事业建设费",),
        detail_form_keywords=("文化事业建设费申报表",),
    ),
    "culture_fee_deduction": CompareTarget(
        target_id="culture_fee_deduction",
        tax_type="CULTURE_FEE",
        tax_code="sz_whsyjsf",
        api_table="",
        workbook_name=CULTURE_FEE_WORKBOOK,
        sheet_name="应税服务减除项目清单",
        form_code="CULTURE_FEE_DEDUCTION",
        form_name="应税服务减除项目清单",
        query_keywords=("文化事业建设费",),
        detail_form_keywords=("应税服务减除项目清单",),
    ),
    "consumption_tax_main": CompareTarget(
        target_id="consumption_tax_main",
        tax_type="CONSUMPTION_TAX",
        tax_code="sz_xfs",
        api_table="xfszb_qc",
        workbook_name=CONSUMPTION_TAX_MAIN_WORKBOOK,
        sheet_name="Sheet1",
        form_code="CONSUMPTION_TAX_MAIN",
        form_name="消费税及附加税费申报表",
        query_keywords=("消费税及附加税费申报表",),
        detail_form_keywords=("消费税及附加税费申报表",),
    ),
    "consumption_tax_surcharge": CompareTarget(
        target_id="consumption_tax_surcharge",
        tax_type="CONSUMPTION_TAX",
        tax_code="sz_xfs",
        api_table="xfsfb1_qc",
        workbook_name=CONSUMPTION_TAX_SURCHARGE_WORKBOOK,
        sheet_name="Sheet1",
        form_code="CONSUMPTION_TAX_SURCHARGE",
        form_name="消费税附加税费计算表",
        query_keywords=("消费税及附加税费申报表",),
        detail_form_keywords=("消费税附加税费计算表",),
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
    parser.add_argument("--tax-timeout", type=int, default=600)
    parser.add_argument("--tax-login-strategy", choices=["direct_first", "plugin_first"], default="direct_first")
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

    for target_id in ("culture_fee_main", "culture_fee_deduction"):
        if target_api_coverage(api_by_tax, TARGETS[target_id], mappings_by_target[target_id]) > 0:
            selected_ids.append(target_id)

    for target_id in ("consumption_tax_main", "consumption_tax_surcharge"):
        if target_api_coverage(api_by_tax, TARGETS[target_id], mappings_by_target[target_id]) > 0:
            selected_ids.append(target_id)

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


def filter_targets_with_api_data(
    api_by_tax: dict[str, Any],
    targets: list[CompareTarget],
    mappings_by_target: dict[str, list[FieldMapping]],
) -> list[CompareTarget]:
    selected = []
    for target in targets:
        mappings = mappings_by_target.get(target.target_id, [])
        coverage = target_api_coverage(api_by_tax, target, mappings)
        if coverage <= 0:
            LOGGER.info(
                "Skipping target %s because API field coverage is 0/%s; tax_code=%s",
                target.target_id,
                len(mappings),
                target.tax_code,
            )
            continue
        selected.append(target)
    return selected


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
    if not matches and WECHAT_FILE_ROOT.exists():
        direct_candidates = [WECHAT_FILE_ROOT / name]
        direct_candidates.extend(
            child / name for child in WECHAT_FILE_ROOT.iterdir() if child.is_dir()
        )
        matches = [p for p in direct_candidates if p.exists() and not p.name.startswith("~$")]
    if not matches:
        raise FileNotFoundError(f"Workbook not found: {name}; searched={search_roots + [WECHAT_FILE_ROOT]}")
    return matches[0]


def workbook_has_unsupported_protection_attrs(workbook: Path) -> bool:
    try:
        with ZipFile(workbook) as archive:
            for name in archive.namelist():
                if not name.startswith("xl/worksheets/") or not name.endswith(".xml"):
                    continue
                data = archive.read(name)
                if any(attr.encode("utf-8") in data for attr in UNSUPPORTED_SHEET_PROTECTION_ATTRS):
                    return True
    except Exception:
        return False
    return False


def sanitized_workbook_path(workbook: Path) -> Path:
    stat = workbook.stat()
    key = hashlib.sha1(
        f"{workbook.resolve()}|{stat.st_mtime_ns}|{stat.st_size}".encode("utf-8")
    ).hexdigest()[:16]
    WORKBOOK_CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    cache_path = WORKBOOK_CACHE_ROOT / f"{workbook.stem}_{key}.xlsx"
    if cache_path.exists():
        return cache_path

    with ZipFile(workbook, "r") as source, ZipFile(cache_path, "w", ZIP_DEFLATED) as target:
        for info in source.infolist():
            data = source.read(info.filename)
            if info.filename.startswith("xl/worksheets/") and info.filename.endswith(".xml"):
                text = data.decode("utf-8")
                for attr in UNSUPPORTED_SHEET_PROTECTION_ATTRS:
                    text = re.sub(rf'\s{re.escape(attr)}="[^"]*"', "", text)
                data = text.encode("utf-8")
            target.writestr(info, data)
    LOGGER.info("Sanitized workbook protection attributes for openpyxl: %s -> %s", workbook, cache_path)
    return cache_path


def load_workbook_compat(workbook: Path, *, data_only: bool, read_only: bool = False):
    source = sanitized_workbook_path(workbook) if workbook_has_unsupported_protection_attrs(workbook) else workbook
    return load_workbook(source, data_only=data_only, read_only=read_only)


def load_mappings(target: CompareTarget) -> list[FieldMapping]:
    workbook = find_workbook(target.workbook_name)
    if target.loader == "vat_main":
        mappings = load_vat_main_mappings(target, workbook)
    else:
        mappings = load_layout_scan_mappings(target, workbook)
    LOGGER.info("Loaded %s field IDs for %s from %s/%s", len(mappings), target.target_id, workbook, target.sheet_name)
    return mappings


def load_auto_mappings() -> dict[str, list[FieldMapping]]:
    mappings_by_target: dict[str, list[FieldMapping]] = {}
    for target in TARGETS.values():
        try:
            mappings_by_target[target.target_id] = load_mappings(target)
        except FileNotFoundError as exc:
            mappings_by_target[target.target_id] = []
            LOGGER.warning(
                "Skipping auto candidate %s because its mapping workbook is unavailable: %s",
                target.target_id,
                exc,
            )
    return mappings_by_target


def load_vat_main_mappings(target: CompareTarget, workbook: Path) -> list[FieldMapping]:
    wb = load_workbook_compat(workbook, data_only=True, read_only=True)
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
    wb = load_workbook_compat(workbook, data_only=True, read_only=True)
    if target.sheet_name not in wb.sheetnames:
        raise ValueError(f"Sheet not found: {target.sheet_name}; available={wb.sheetnames}")
    ws = wb[target.sheet_name]
    mappings: list[FieldMapping] = []
    seen: set[str] = set()
    for row_idx, row in enumerate(ws.iter_rows(values_only=True), start=1):
        for col_idx, value in enumerate(row, start=1):
            field_id = str(value).strip() if value is not None else ""
            if not FIELD_ID_RE.match(field_id) or field_id in seen or not should_include_mapping_field(target, field_id):
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
        if re.fullmatch(r"(FZ)?\d+[A-Za-z]?(\.\d+)?([=＝（(].*)?", text):
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


def should_include_mapping_field(target: CompareTarget, field_id: str) -> bool:
    if target.tax_type != "CONSUMPTION_TAX":
        return True
    lower = field_id.lower()
    if lower in {"a", "b", "c"}:
        return False
    return not lower.startswith(CONSUMPTION_TAX_NON_API_PREFIXES)


def infer_data_type(field_id: str) -> DataType:
    lower = field_id.lower()
    if lower.startswith(CONSUMPTION_TAX_TEXT_PREFIXES):
        return DataType.TEXT
    if lower.startswith(CONSUMPTION_TAX_RATE_PREFIXES):
        return DataType.RATE
    if lower in TEXT_FIELDS or re.fullmatch(r"(kpfnsrsbh|kpfdwmc|fwxmmc|pzzl|pzhm)(_\d+)?", lower):
        return DataType.TEXT
    if lower.startswith("fl") or lower.endswith("sl") or "taxrate" in lower or lower.endswith("_rate"):
        return DataType.RATE
    if "cyrs" in lower or lower.endswith("rs") or lower.endswith("count"):
        return DataType.INTEGER
    return DataType.AMOUNT


def data_type_for_target_field(target: CompareTarget, field_id: str, data_type: DataType) -> DataType:
    if target.target_id == "vat_general_appendix5" and field_id in VAT_APPENDIX5_TEXT_FIELDS:
        return DataType.TEXT
    return data_type


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
        data_type=data_type_for_target_field(target, field_id, data_type),
        web_cell_id=field_id,
        web_row_index=row_idx,
        web_col_index=col_idx,
        api_json_path=f"$.data.{target.tax_code}.{target.api_table}.{field_id}",
    )


def fetch_api_payload(task_id: str) -> dict[str, Any]:
    response = APIClient().fetch_by_task_id(task_id)
    if response.get("error"):
        raise RuntimeError(f"API fetch failed: {response.get('error')}")
    return response


def fetch_api(task_id: str) -> tuple[dict[str, Any], str]:
    response = fetch_api_payload(task_id)
    return response.get("data", {}), response.get("province", "")


def extract_expected_tax_no(api_response: dict[str, Any]) -> str:
    param_json = api_response.get("paramJson") or {}
    if isinstance(param_json, str):
        try:
            param_json = json.loads(param_json)
        except (json.JSONDecodeError, TypeError):
            param_json = {}
    if not isinstance(param_json, dict):
        return ""
    direct_tax_no = str(param_json.get("taxNo") or "").strip()
    if direct_tax_no:
        return direct_tax_no
    cookies = param_json.get("cookies") or {}
    if isinstance(cookies, dict):
        user_info = cookies.get("user_info") or {}
        if isinstance(user_info, dict):
            for key in ("tax_no", "taxNo", "creditCode", "taxpayer_id"):
                value = str(user_info.get(key) or "").strip()
                if value:
                    return value
    return ""


def fetch_current_period_flag(task_id: str) -> bool | None:
    """Return latest '成功保存数据-是否是当期' logInfo as bool.

    None means the task log does not contain this marker, so callers should keep
    the normal declared-query flow.
    """
    try:
        flag = fetch_task_current_period_flag(task_id, tax_code="sz_zzs", timeout=20)
    except Exception as exc:
        LOGGER.warning("Could not read VAT current-period marker from task logs; continuing normal flow: %s", exc)
        return None
    if flag is None:
        LOGGER.info("No VAT current-period marker found in task execution logs")
    else:
        LOGGER.info("Task VAT current-period marker parsed=%s", flag)
    return flag


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


def find_existing_tax_page(bm: BrowserManager, province: str, expected_tax_no: str = ""):
    if not province:
        return None
    expected_tax_no = (expected_tax_no or "").strip()
    if not expected_tax_no:
        LOGGER.info("Skipping existing tax bureau page reuse: expected taxpayer id is unavailable")
        return None
    host = f"etax.{province}.chinatax.gov.cn"
    scored_candidates = []
    for page in bm.get_all_pages():
        try:
            if urllib.parse.urlparse(page.url or "").hostname != host:
                continue
            text = page.evaluate("document.body ? document.body.innerText.slice(0, 5000) : ''")
            if expected_tax_no not in text:
                LOGGER.info(
                    "Skipping existing tax bureau page because taxpayer id does not match: expected=%s url=%s",
                    expected_tax_no,
                    page.url,
                )
                continue
            url = page.url or ""
            lower_url = url.lower()
            detail_context = (
                "sbxxcx/detail" in lower_url
                or "sbxxcxxq" in lower_url
                or ("申报信息查询详情" in text and "主附表表单" in text)
            )
            if any(hint in lower_url for hint in QUERY_URL_HINTS) and not detail_context:
                LOGGER.info(
                    "Skipping existing declaration query list page; task login is required to confirm taxpayer context: %s",
                    url,
                )
                continue
            logged_in_hints = (
                "\u6211\u8981\u67e5\u8be2",
                "\u6211\u8981\u529e\u7a0e",
                "\u672c\u671f\u5e94\u7533\u62a5",
                "\u6211\u7684\u5f85\u529e",
                "\u7edf\u4e00\u793e\u4f1a\u4fe1\u7528\u4ee3\u7801",
                "\u7eb3\u7a0e\u4eba\u8bc6\u522b\u53f7",
                "\u8ddd\u672c\u6708\u5f81\u671f\u7ed3\u675f",
                "\u7533\u62a5\u4fe1\u606f\u67e5\u8be2",
                "\u7533\u62a5\u4fe1\u606f\u67e5\u8be2\u8be6\u60c5",
                "\u8fd4\u56de",
                "\u589e\u503c\u7a0e",
                "\u63d0\u4ea4\u7533\u62a5",
                "\u7a0e\u52a1\u6570\u5b57\u8d26\u6237",
                "\u8d26\u6237\u67e5\u8be2",
            )
            if not any(hint in text for hint in logged_in_hints):
                continue
            score = 0
            if detail_context:
                score += 100
            if "\u7533\u62a5\u4fe1\u606f\u67e5\u8be2" in text:
                score += 80
            if "\u6211\u8981\u67e5\u8be2" in text:
                score += 40
            if "\u672c\u671f\u5e94\u7533\u62a5" in text:
                score += 30
            if "\u7a0e\u52a1\u6570\u5b57\u8d26\u6237" in text or "\u8d26\u6237\u67e5\u8be2" in text:
                score += 25
            if "\u7edf\u4e00\u793e\u4f1a\u4fe1\u7528\u4ee3\u7801" in text or "\u7eb3\u7a0e\u4eba\u8bc6\u522b\u53f7" in text:
                score += 20
            if "loginb" in url.lower():
                score -= 5
            scored_candidates.append((score, page))
        except Exception:
            continue
    if scored_candidates:
        scored_candidates.sort(key=lambda item: item[0], reverse=True)
        return scored_candidates[0][1]
    candidates = []
    for page in bm.get_all_pages():
        try:
            url = page.url or ""
            if urllib.parse.urlparse(url).hostname != host:
                continue
            text = page.evaluate("document.body ? document.body.innerText.slice(0, 3000) : ''")
            if expected_tax_no not in text:
                continue
            lower_url = url.lower()
            detail_context = (
                "sbxxcx/detail" in lower_url
                or "sbxxcxxq" in lower_url
                or ("申报信息查询详情" in text and "主附表表单" in text)
            )
            if any(hint in lower_url for hint in QUERY_URL_HINTS) and not detail_context:
                continue
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
                    "税务数字账户",
                    "账户查询",
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
    if is_declaration_detail_page(page):
        return False
    return any(hint in url for hint in QUERY_URL_HINTS)


def is_declaration_detail_page(page) -> bool:
    url = (page.url or "").lower()
    if "sbxxcx/detail" in url or "sbxxcxxq" in url:
        return True
    try:
        text = page.evaluate("document.body ? document.body.innerText.slice(0, 1000) : ''")
    except Exception:
        return False
    return "申报信息查询详情" in text and "主附表表单" in text


def declaration_detail_matches_target(page, target: CompareTarget) -> bool:
    try:
        text = page.evaluate("document.body ? document.body.innerText.slice(0, 5000) : ''")
    except Exception:
        return False
    normalized = re.sub(r"\s+", "", text)
    keyword_sets = [target.query_keywords, target.detail_form_keywords, (target.form_name,)]
    for keywords in keyword_sets:
        clean_keywords = [re.sub(r"\s+", "", str(keyword)) for keyword in keywords if str(keyword).strip()]
        if clean_keywords and all(keyword in normalized for keyword in clean_keywords):
            return True
    return False


def ensure_target_page(
    page,
    target: CompareTarget,
    mappings: list[FieldMapping],
    web_config,
    prefer_detail_form_switch: bool = False,
):
    tried_detail_form_switch = False
    if not is_target_detail_page(page, target, mappings):
        if is_declaration_detail_page(page):
            if declaration_detail_matches_target(page, target):
                LOGGER.info("Reusing current declaration detail page for %s", target.target_id)
            elif prefer_detail_form_switch and target.detail_form_keywords:
                tried_detail_form_switch = True
                LOGGER.info("Trying in-detail form switch for %s before returning to declaration query", target.target_id)
            else:
                LOGGER.info("Current declaration detail does not match %s; returning to declaration query", target.target_id)
                page = navigate_to_query_page_robust(page, web_config)
        elif not is_query_page(page):
            LOGGER.info("Navigating to declaration information query page")
            page = navigate_to_query_page_robust(page, web_config)
        if not is_declaration_detail_page(page) and not is_target_detail_page(page, target, mappings):
            if not is_ready_declaration_query_page(page):
                host = extract_etax_host(page.url or "")
                recovered_page = wait_for_declaration_query_page(page, host, timeout=45) if host else None
                if recovered_page:
                    page = recovered_page
                else:
                    raise RuntimeError(f"Could not navigate to declaration query page before opening target={target.target_id}; url={page.url}")
            LOGGER.info("Opening declaration row for %s", target.target_id)
            opened_page = click_declaration_row(page, target.query_keywords)
            if opened_page:
                page = opened_page

    page.wait_for_load_state("domcontentloaded", timeout=15000)
    time.sleep(2)
    if target.detail_form_keywords:
        select_result = select_detail_form(page, target.detail_form_keywords)
        if select_result == "not_found":
            if tried_detail_form_switch:
                LOGGER.info("In-detail form switch did not find %s; reopening from declaration query", target.target_id)
                page = navigate_to_query_page_robust(page, web_config)
                if not is_ready_declaration_query_page(page):
                    raise RuntimeError(f"Could not recover declaration query page for target={target.target_id}; url={page.url}")
                opened_page = click_declaration_row(page, target.query_keywords)
                if opened_page:
                    page = opened_page
                page.wait_for_load_state("domcontentloaded", timeout=15000)
                time.sleep(2)
                select_result = select_detail_form(page, target.detail_form_keywords)
                if select_result != "not_found":
                    deadline = time.time() + 30
                    while time.time() < deadline:
                        if is_target_detail_page(page, target, mappings):
                            return page
                        time.sleep(1)
            if is_target_detail_page(page, target, mappings):
                LOGGER.info(
                    "Detail form selector was not found for %s, but current page already matches target",
                    target.target_id,
                )
                return page
            raise RuntimeError(
                f"Detail form was not found for target={target.target_id}, "
                f"keywords={target.detail_form_keywords}"
            )
        deadline = time.time() + 30
        while time.time() < deadline:
            if is_target_detail_page(page, target, mappings):
                return page
            time.sleep(1)
        raise RuntimeError(
            f"Detail form was selected but target page was not confirmed for "
            f"target={target.target_id}, keywords={target.detail_form_keywords}, result={select_result}"
        )
    if not is_target_detail_page(page, target, mappings):
        LOGGER.warning("Target detail page was not positively detected for %s; continuing extraction anyway", target.target_id)
    return page


def can_switch_detail_form_between(previous: CompareTarget | None, current: CompareTarget) -> bool:
    if previous is None:
        return False
    if not current.detail_form_keywords:
        return False
    return (
        previous.tax_code == current.tax_code
        and previous.tax_type == current.tax_type
        and previous.query_keywords == current.query_keywords
    )


def find_context_tax_page(page, required_hints: tuple[str, ...]):
    try:
        current_host = urllib.parse.urlparse(page.url or "").hostname
    except Exception:
        current_host = ""
    if not current_host:
        return None
    for candidate in list(page.context.pages):
        try:
            url = candidate.url or ""
            if urllib.parse.urlparse(url).hostname != current_host:
                continue
            if "loading" in url.lower():
                continue
            text = candidate.evaluate("document.body ? document.body.innerText.slice(0, 5000) : ''")
            if all(hint in text for hint in required_hints):
                candidate.bring_to_front()
                return candidate
        except Exception:
            continue
    return None


def wait_for_context_tax_page(page, required_hints: tuple[str, ...], timeout: int = 20):
    deadline = time.time() + timeout
    while time.time() < deadline:
        candidate = find_context_tax_page(page, required_hints)
        if candidate:
            return candidate
        time.sleep(1)
    return None


def find_context_query_page(page):
    try:
        current_host = urllib.parse.urlparse(page.url or "").hostname
    except Exception:
        current_host = ""
    if not current_host:
        return None
    for candidate in list(page.context.pages):
        try:
            if urllib.parse.urlparse(candidate.url or "").hostname != current_host:
                continue
            if is_query_page(candidate):
                candidate.bring_to_front()
                return candidate
        except Exception:
            continue
    return None


def find_context_digital_account_page(page):
    try:
        current_host = urllib.parse.urlparse(page.url or "").hostname
    except Exception:
        current_host = ""
    if not current_host:
        return None
    for candidate in list(page.context.pages):
        try:
            url = candidate.url or ""
            lower_url = url.lower()
            if urllib.parse.urlparse(url).hostname != current_host:
                continue
            if "loading" in lower_url:
                continue
            if "/szzh/" not in lower_url and "/szzh/?" not in lower_url:
                continue
            if "/szzh/?" in lower_url:
                candidate.bring_to_front()
                return candidate
            text = candidate.evaluate("document.body ? document.body.innerText.slice(0, 2000) : ''")
            if "账户查询" in text or "税务数字账户" in text:
                candidate.bring_to_front()
                return candidate
        except Exception:
            continue
    return None


def wait_for_context_digital_account_page(page, timeout: int = 30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        candidate = find_context_digital_account_page(page)
        if candidate:
            return candidate
        time.sleep(1)
    return None


def find_context_page_by_url_fragment(page, fragment: str):
    for candidate in list(page.context.pages):
        try:
            if fragment in (candidate.url or ""):
                candidate.bring_to_front()
                return candidate
        except Exception:
            continue
    return None


def wait_for_context_page_by_url_fragment(page, fragment: str, timeout: int = 30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        candidate = find_context_page_by_url_fragment(page, fragment)
        if candidate:
            return candidate
        time.sleep(1)
    return None


def wait_for_context_query_page(page, timeout: int = 30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if is_query_page(page):
            return page
        candidate = find_context_query_page(page)
        if candidate:
            return candidate
        time.sleep(1)
    return None


def page_contains_hints(page, hints: tuple[str, ...]) -> bool:
    try:
        text = page.evaluate("document.body ? document.body.innerText.slice(0, 5000) : ''")
    except Exception:
        return False
    return all(hint in text for hint in hints)


def open_declaration_query_direct(page, host: str, timeout: int = 30):
    target_url = f"https://{host}/szzh/zhcx/sbxx/sbxxcx"
    LOGGER.info("Opening declaration query page directly: %s", target_url)
    try:
        page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
    except Exception as exc:
        if "interrupted by another navigation" not in str(exc):
            LOGGER.info("Direct declaration query navigation failed: %s", exc)
        else:
            LOGGER.info("Direct declaration query navigation was interrupted; waiting for redirected page")
    try:
        page.wait_for_url("**/szzh/zhcx/sbxx/sbxxcx**", timeout=timeout * 1000)
    except Exception:
        pass
    query_page = wait_for_context_query_page(page, timeout=5)
    if query_page:
        return query_page
    if "loading" in (page.url or "").lower():
        LOGGER.info("Declaration query is still on loading page; waiting for redirect: %s", page.url)
        return wait_for_context_query_page(page, timeout=timeout)
    return None


def navigate_to_query_page(page, web_config):
    url = page.url or ""
    host_match = re.search(r"https://(etax\.[^/]+)", url)
    if host_match:
        host = host_match.group(1)
        province_match = re.search(r"etax\.([^.]+)\.chinatax\.gov\.cn", host)
        province = province_match.group(1) if province_match else ""
        if province == "sichuan":
            query_page = open_declaration_query_direct(page, host, timeout=45)
            if query_page:
                return query_page
            LOGGER.info("Sichuan direct declaration query did not become usable; falling back to tax digital account")
        if "/szzh/" not in (page.url or ""):
            szzh_url = f"https://{host}/szc/szzh/sjswszzh/spHandler?cdlj=/szzh/szzh/"
            for attempt in range(1, 3):
                szzh_page = wait_for_context_digital_account_page(page, timeout=1)
                if szzh_page:
                    page = szzh_page
                    break
                LOGGER.info("Opening tax digital account before declaration query: %s (attempt %s/2)", szzh_url, attempt)
                try:
                    page.goto(szzh_url, wait_until="domcontentloaded", timeout=30000)
                except Exception as exc:
                    if "interrupted by another navigation" not in str(exc) and attempt == 2:
                        raise
                    LOGGER.info("Tax digital account navigation was interrupted; waiting for a usable account page")
                szzh_page = wait_for_context_digital_account_page(page, timeout=12)
                if szzh_page:
                    page = szzh_page
                    break
                LOGGER.warning("Tax digital account page did not become usable after attempt %s", attempt)
                continue
                portal_page = wait_for_context_tax_page(page, ("税务数字账户",), timeout=15)
                if portal_page:
                    page = portal_page
                LOGGER.info("Opening tax digital account before declaration query: %s (attempt %s/3)", szzh_url, attempt)
                try:
                    page.goto(szzh_url, wait_until="domcontentloaded", timeout=30000)
                except Exception as exc:
                    if "interrupted by another navigation" not in str(exc) and attempt == 3:
                        raise
                    LOGGER.info("Tax digital account navigation was interrupted; waiting for a usable account page")
                szzh_page = wait_for_context_digital_account_page(page, timeout=12)
                if szzh_page:
                    page = szzh_page
                    break
                LOGGER.warning("Tax digital account page did not become usable after attempt %s", attempt)
            else:
                szzh_page = wait_for_context_digital_account_page(page, timeout=15)
                if szzh_page:
                    page = szzh_page
                else:
                    raise RuntimeError(f"Could not open tax digital account page; current url={page.url}")
        target_url = f"https://{host}/szzh/zhcx/sbxx/sbxxcx"
        LOGGER.info("Opening declaration query page directly: %s", target_url)
        last_nav_error = None
        for attempt in range(1, 4):
            try:
                page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
                last_nav_error = None
            except Exception as exc:
                last_nav_error = exc
                if "interrupted by another navigation" not in str(exc) or attempt == 3:
                    raise
                LOGGER.info("Declaration query navigation was interrupted; retrying after root page settles")
                query_page = wait_for_context_query_page(page, timeout=8)
                if query_page:
                    return query_page
                settled_page = wait_for_context_digital_account_page(page, timeout=10)
                if settled_page:
                    page = settled_page
                continue
            query_page = wait_for_context_query_page(page, timeout=30)
            if query_page:
                return query_page
            settled_page = wait_for_context_digital_account_page(page, timeout=5)
            if settled_page:
                page = settled_page
        if last_nav_error:
            raise last_nav_error
        if "loading" in (page.url or "").lower():
            query_page = open_declaration_query_direct(page, host, timeout=45)
            if query_page:
                return query_page
            raise RuntimeError(f"Declaration query page did not open; still on loading page: {page.url}")
    portal_page = find_context_tax_page(page, ("我要查询",))
    if portal_page:
        page = portal_page
    NavigationEngine(page).navigate_to_form(web_config)
    time.sleep(3)
    if is_query_page(page):
        return page
    query_page = find_context_query_page(page)
    if query_page:
        return query_page
    return page


def extract_etax_host(url: str) -> str:
    match = re.search(r"https://(etax\.[^/]+)", url or "")
    return match.group(1) if match else ""


def is_undeclared_vat_page_url(url: str) -> bool:
    return UNDECLARED_VAT_GENERAL_PATH.split("#", 1)[0] in (url or "")


def is_loading_page_url(url: str) -> bool:
    return "/loading" in (url or "").lower()


def is_tpass_login_page_url(url: str) -> bool:
    lower_url = (url or "").lower()
    return "tpass." in lower_url and "#/login" in lower_url


def etax_hostname(host_or_url: str) -> str:
    if not host_or_url:
        return ""
    value = host_or_url
    if "://" not in value:
        value = f"https://{value}"
    try:
        return urllib.parse.urlparse(value).hostname or ""
    except Exception:
        return ""


def context_pages_for_etax_host(page, host: str):
    expected_hostname = etax_hostname(host)
    if not expected_hostname:
        return []
    pages = []
    for candidate in list(page.context.pages):
        try:
            candidate_url = candidate.url or ""
            if etax_hostname(candidate_url) == expected_hostname:
                pages.append(candidate)
        except Exception:
            continue
    return pages


def find_context_query_page_for_host(page, host: str):
    for candidate in context_pages_for_etax_host(page, host):
        try:
            if is_ready_declaration_query_page(candidate):
                candidate.bring_to_front()
                return candidate
        except Exception:
            continue
    return None


def find_context_digital_account_page_for_host(page, host: str):
    for candidate in context_pages_for_etax_host(page, host):
        try:
            url = candidate.url or ""
            lower_url = url.lower()
            if "loading" in lower_url:
                continue
            if "/szzh/" not in lower_url and "/szzh/?" not in lower_url:
                continue
            if "/szc/szzh/" in lower_url and not page_has_visible_loading(candidate):
                candidate.bring_to_front()
                return candidate
            if lower_url.rstrip("/").endswith("/szzh") or "/szzh/?" in lower_url:
                candidate.bring_to_front()
                return candidate
            text = candidate.evaluate("document.body ? document.body.innerText.slice(0, 3000) : ''")
            if any(hint in text for hint in TAX_DIGITAL_ACCOUNT_HINTS):
                candidate.bring_to_front()
                return candidate
        except Exception:
            continue
    return None


def page_has_visible_loading(page) -> bool:
    try:
        return bool(
            page.evaluate(
                """() => {
                    const visible = (el) => !!(el && (el.offsetWidth || el.offsetHeight || el.getClientRects().length));
                    const loadingSelectors = [
                        '.el-loading-mask',
                        '.ant-spin-spinning',
                        '.t-loading',
                        '.vxe-loading',
                        '[class*="loading"]',
                        '[class*="Loading"]'
                    ];
                    for (const selector of loadingSelectors) {
                        if (Array.from(document.querySelectorAll(selector)).some(visible)) return true;
                    }
                    const text = String(document.body && document.body.innerText || '').replace(/\\s+/g, '');
                    return text === '加载中' || text.includes('正在加载') || text.includes('请稍候');
                }"""
            )
        )
    except Exception:
        return False


def wait_for_declaration_query_page(page, host: str, timeout: int = 60):
    deadline = time.time() + timeout
    last_logged_url = ""
    last_log_at = 0.0
    while time.time() < deadline:
        try:
            if is_ready_declaration_query_page(page):
                return page
        except Exception:
            pass
        candidate = find_context_query_page_for_host(page, host)
        if candidate:
            return candidate
        try:
            current_url = page.url or ""
        except Exception:
            current_url = ""
        if is_tpass_login_page_url(current_url):
            LOGGER.info("Declaration query wait stopped on tpass login page: %s", current_url)
            return None
        now = time.time()
        if current_url and ("loading" in current_url.lower() or current_url != last_logged_url) and now - last_log_at >= 5:
            LOGGER.info("Waiting for declaration query page; current url=%s", current_url)
            last_logged_url = current_url
            last_log_at = now
        time.sleep(1)
    return None


def is_ready_declaration_query_page(page) -> bool:
    if not is_query_page(page):
        return False
    try:
        url = page.url or ""
    except Exception:
        return False
    if "loading" in url.lower():
        return False
    try:
        text = page.evaluate("document.body ? document.body.innerText.slice(0, 5000) : ''")
    except Exception:
        return False
    if not text.strip():
        return False
    ready_hints = (
        "\u7533\u62a5\u4fe1\u606f\u67e5\u8be2",
        "\u7a0e\u6b3e\u6240\u5c5e\u671f",
        "\u5f81\u6536\u9879\u76ee",
        "\u7533\u62a5\u8868",
        "\u67e5\u8be2",
    )
    return any(hint in text for hint in ready_hints)


def wait_for_digital_account_page_for_host(page, host: str, timeout: int = 30, soft_timeout: int = 12):
    start = time.time()
    deadline = time.time() + timeout
    while time.time() < deadline:
        query_page = find_context_query_page_for_host(page, host)
        if query_page:
            LOGGER.info("Declaration query became ready while waiting for tax digital account: %.1fs", time.time() - start)
            return query_page
        candidate = find_context_digital_account_page_for_host(page, host)
        if candidate:
            LOGGER.info("Tax digital account became usable: %.1fs", time.time() - start)
            return candidate
        elapsed = time.time() - start
        if elapsed >= soft_timeout:
            LOGGER.info(
                "Tax digital account readiness not detected after %.1fs; continuing with direct declaration query",
                elapsed,
            )
            return None
        time.sleep(0.35)
    LOGGER.info("Tax digital account wait timed out after %.1fs", time.time() - start)
    return None


def open_declaration_query_with_wait(page, host: str, timeout: int = 60):
    target_url = f"https://{host}/szzh/zhcx/sbxx/sbxxcx"
    LOGGER.info("Opening declaration query page directly: %s", target_url)
    try:
        page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
    except Exception as exc:
        message = str(exc)
        if "interrupted by another navigation" in message:
            LOGGER.info("Declaration query navigation was interrupted; waiting for redirected page")
        else:
            LOGGER.info("Declaration query navigation did not settle immediately: %s", exc)
    return wait_for_declaration_query_page(page, host, timeout=timeout)


def open_digital_account_with_wait(page, host: str, timeout: int = 30):
    existing_query_page = find_context_query_page_for_host(page, host)
    if existing_query_page:
        return existing_query_page
    existing_page = find_context_digital_account_page_for_host(page, host)
    if existing_page:
        return existing_page
    szzh_url = f"https://{host}/szc/szzh/sjswszzh/spHandler?cdlj=/szzh/szzh/"
    LOGGER.info("Opening tax digital account before declaration query: %s", szzh_url)
    try:
        page.goto(szzh_url, wait_until="domcontentloaded", timeout=30000)
    except Exception as exc:
        message = str(exc)
        if "interrupted by another navigation" in message:
            LOGGER.info("Tax digital account navigation was interrupted; waiting for redirected page")
        else:
            LOGGER.info("Tax digital account navigation did not settle immediately: %s", exc)
    return wait_for_digital_account_page_for_host(page, host, timeout=timeout)


def is_tax_portal_page(page) -> bool:
    try:
        url = page.url or ""
    except Exception:
        return False
    if is_loading_page_url(url) or is_tpass_login_page_url(url):
        return False
    try:
        text = page.evaluate("document.body ? document.body.innerText.slice(0, 5000) : ''")
    except Exception:
        return False
    return any(hint in text for hint in TAX_PORTAL_HINTS)


def wait_for_tax_portal_page(page, host: str, timeout: int = 30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            current_url = page.url or ""
        except Exception:
            current_url = ""
        if is_tpass_login_page_url(current_url):
            LOGGER.info("Tax portal wait stopped on tpass login page: %s", current_url)
            return None
        if extract_etax_host(current_url) == host and is_tax_portal_page(page):
            return page
        time.sleep(1)
    return page if is_tax_portal_page(page) else None


def find_context_tax_portal_page_for_host(page, host: str):
    for candidate in context_pages_for_etax_host(page, host):
        try:
            if is_tax_portal_page(candidate):
                candidate.bring_to_front()
                return candidate
        except Exception:
            continue
    return None


def reset_tax_bureau_tab_to_loginb(page, host: str, timeout: int = 30):
    login_url = f"https://{host}/loginb/"
    LOGGER.info("Resetting current tax-bureau tab before declaration query recovery: %s", login_url)
    try:
        page.goto(login_url, wait_until="domcontentloaded", timeout=30000)
    except Exception as exc:
        message = str(exc)
        if "interrupted by another navigation" in message:
            LOGGER.info("Tax-bureau reset navigation was interrupted; waiting for redirected page")
        else:
            LOGGER.info("Tax-bureau reset navigation did not settle immediately: %s", exc)
    return wait_for_tax_portal_page(page, host, timeout=timeout)


def navigate_to_query_from_tax_portal(page, host: str, timeout: int = 60):
    if not is_tax_portal_page(page):
        return None
    LOGGER.info("Navigating to declaration query from tax-bureau portal menu")
    try:
        result = page.evaluate(
            """async () => {
                const normalize = (value) => String(value || '').replace(/\\s+/g, '');
                const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
                const visible = (el) => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
                const dispatchPointer = (el) => {
                    for (const type of ['mouseover', 'mouseenter', 'mousemove']) {
                        el.dispatchEvent(new MouseEvent(type, { bubbles: true, cancelable: true, view: window }));
                    }
                };
                const clickByLabels = (labels) => {
                    const wanted = labels.map(normalize);
                    const nodes = Array.from(document.querySelectorAll(
                        'a, button, li, span, div, [role=button], [role=menuitem], .el-menu-item, .ant-menu-item'
                    )).filter((el) => {
                        if (!visible(el)) return false;
                        const text = normalize(el.innerText || el.textContent || el.getAttribute('title'));
                        return text && text.length <= 120;
                    });
                    const exact = nodes.find((el) => wanted.includes(normalize(el.innerText || el.textContent || el.getAttribute('title'))));
                    const partial = exact || nodes.find((el) => {
                        const text = normalize(el.innerText || el.textContent || el.getAttribute('title'));
                        return wanted.some((label) => text.includes(label));
                    });
                    if (!partial) return '';
                    partial.scrollIntoView({ block: 'center', inline: 'center' });
                    dispatchPointer(partial);
                    partial.click();
                    return normalize(partial.innerText || partial.textContent || partial.getAttribute('title'));
                };

                const clicked = [];
                const first = clickByLabels(['我要查询']);
                if (first) clicked.push(first);
                await wait(1000);
                const second = clickByLabels(['一户式查询', '申报信息查询']);
                if (second) clicked.push(second);
                await wait(1000);
                if (!clicked.some((item) => item.includes('申报信息查询'))) {
                    const third = clickByLabels(['申报信息查询']);
                    if (third) clicked.push(third);
                }
                await wait(5000);
                return clicked.join('>');
            }"""
        )
        LOGGER.info("Tax portal declaration query menu result: %s", result or "not_clicked")
    except Exception as exc:
        LOGGER.info("Tax portal declaration query menu navigation failed: %s", exc)
        return None
    return wait_for_declaration_query_page(page, host, timeout=timeout)


def open_declaration_query_via_sp_handler(page, host: str, timeout: int = 60):
    target_url = f"https://{host}/szc/szzh/sjswszzh/spHandler?cdlj=/szzh/zhcx/sbxx/sbxxcx"
    LOGGER.info("Opening declaration query through tax digital account handler: %s", target_url)
    try:
        page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
    except Exception as exc:
        message = str(exc)
        if "interrupted by another navigation" in message:
            LOGGER.info("Declaration query handler navigation was interrupted; waiting for redirected page")
        else:
            LOGGER.info("Declaration query handler navigation did not settle immediately: %s", exc)
    if is_tpass_login_page_url(page.url or ""):
        LOGGER.info("Declaration query handler reached tpass login page; recovery path is not authenticated")
        return None
    return wait_for_declaration_query_page(page, host, timeout=timeout)


def recover_declaration_query_in_current_tab(page, host: str, timeout: int = 60):
    portal_page = find_context_tax_portal_page_for_host(page, host)
    if not portal_page:
        portal_page = reset_tax_bureau_tab_to_loginb(page, host, timeout=30)
    if not portal_page:
        return None

    query_page = navigate_to_query_from_tax_portal(portal_page, host, timeout=timeout)
    if query_page:
        return query_page

    query_page = open_declaration_query_with_wait(portal_page, host, timeout=timeout)
    if query_page:
        return query_page

    query_page = open_declaration_query_via_sp_handler(portal_page, host, timeout=timeout)
    if query_page:
        return query_page
    return None


def open_fresh_tax_bureau_tab(page, host: str):
    try:
        fresh_page = page.context.new_page()
    except Exception as exc:
        LOGGER.info("Could not open a fresh tax-bureau tab for recovery: %s", exc)
        return None

    login_url = f"https://{host}/loginb/"
    LOGGER.info("Opening fresh tax-bureau tab for declaration query recovery: %s", login_url)
    try:
        fresh_page.goto(login_url, wait_until="domcontentloaded", timeout=30000)
    except Exception as exc:
        message = str(exc)
        if "interrupted by another navigation" in message:
            LOGGER.info("Fresh tax-bureau tab navigation was interrupted; continuing with redirected page")
        else:
            LOGGER.info("Fresh tax-bureau tab navigation did not settle immediately: %s", exc)
    return fresh_page


def recover_declaration_query_in_fresh_tab(page, host: str, timeout: int = 60):
    fresh_page = open_fresh_tax_bureau_tab(page, host)
    if not fresh_page:
        return None

    try:
        query_page = open_declaration_query_via_sp_handler(fresh_page, host, timeout=timeout)
        if query_page:
            return query_page

        query_page = open_declaration_query_with_wait(fresh_page, host, timeout=timeout)
        if query_page:
            return query_page

        szzh_page = open_digital_account_with_wait(fresh_page, host, timeout=30)
        if szzh_page:
            if is_ready_declaration_query_page(szzh_page):
                return szzh_page
            fresh_page = szzh_page
        query_page = open_declaration_query_with_wait(fresh_page, host, timeout=timeout)
        if query_page:
            return query_page
    except Exception as exc:
        LOGGER.info("Fresh-tab declaration query recovery failed: %s", exc)
    return None


def find_any_context_etax_host(page) -> str:
    for candidate in list(page.context.pages):
        try:
            host = extract_etax_host(candidate.url or "")
        except Exception:
            host = ""
        if host:
            return host
    return ""


def navigate_to_query_page_robust(page, web_config):
    host = extract_etax_host(page.url or "") or find_any_context_etax_host(page)
    if host:
        query_page = wait_for_declaration_query_page(page, host, timeout=3)
        if query_page:
            return query_page

        current_url = page.url or ""
        if is_undeclared_vat_page_url(current_url) or is_loading_page_url(current_url):
            query_page = recover_declaration_query_in_current_tab(page, host, timeout=60)
            if query_page:
                return query_page
            query_page = recover_declaration_query_in_fresh_tab(page, host, timeout=60)
            if query_page:
                return query_page

        szzh_page = open_digital_account_with_wait(page, host, timeout=30)
        if szzh_page:
            if is_ready_declaration_query_page(szzh_page):
                return szzh_page
            page = szzh_page
            query_page = open_declaration_query_with_wait(page, host, timeout=60)
            if query_page:
                return query_page

        query_page = open_declaration_query_with_wait(page, host, timeout=60)
        if query_page:
            return query_page

        if is_loading_page_url(page.url or ""):
            query_page = recover_declaration_query_in_current_tab(page, host, timeout=60)
            if query_page:
                return query_page
            query_page = recover_declaration_query_in_fresh_tab(page, host, timeout=60)
            if query_page:
                return query_page

        for attempt in range(1, 3):
            LOGGER.info("Declaration query was not ready; retrying through tax digital account (attempt %s/2)", attempt)
            szzh_page = open_digital_account_with_wait(page, host, timeout=30)
            if szzh_page:
                if is_ready_declaration_query_page(szzh_page):
                    return szzh_page
                page = szzh_page
            query_page = open_declaration_query_with_wait(page, host, timeout=60)
            if query_page:
                return query_page

        query_page = wait_for_declaration_query_page(page, host, timeout=45)
        if query_page:
            return query_page
        return page

    portal_page = find_context_tax_page(page, ("鎴戣鏌ヨ",))
    if portal_page:
        page = portal_page
    NavigationEngine(page).navigate_to_form(web_config)
    time.sleep(3)
    if is_query_page(page):
        return page
    query_page = find_context_query_page(page)
    if query_page:
        return query_page
    return page


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
    url = (page.url or "").lower()
    detail_context = (
        "sbxxcx/detail" in url
        or "sbxxcxxq" in url
        or ("申报信息查询详情" in body_text and "主附表表单" in body_text)
        or "报表列表" in body_text
    )
    if any(hint in url for hint in QUERY_URL_HINTS) and not detail_context:
        return False
    if target.detail_form_keywords:
        if all(keyword in body_text for keyword in target.detail_form_keywords):
            return detail_context
        if target.tax_type in {"CULTURE_FEE", "CIT_A_PREPAY"}:
            return False
    if not detail_context:
        return False
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


def refresh_declaration_query_results(page) -> str:
    """Reset stale query filters and run the declaration query again."""

    try:
        result = page.evaluate(
            """async () => {
                const normalize = (value) => String(value || '').replace(/\\s+/g, '');
                const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
                const visible = (el) => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
                const clickByLabels = (labels) => {
                    const wanted = labels.map(normalize);
                    const nodes = Array.from(document.querySelectorAll(
                        'button, a, [role=button], .el-button, .ant-btn, .t-button'
                    )).filter(visible);
                    const exact = nodes.find((el) => {
                        const text = normalize(el.innerText || el.textContent || el.getAttribute('aria-label'));
                        return wanted.includes(text);
                    });
                    const partial = exact || nodes.find((el) => {
                        const text = normalize(el.innerText || el.textContent || el.getAttribute('aria-label'));
                        return wanted.some((label) => text.includes(label));
                    });
                    if (!partial) return '';
                    partial.scrollIntoView({ block: 'center', inline: 'center' });
                    partial.click();
                    return normalize(partial.innerText || partial.textContent || partial.getAttribute('aria-label'));
                };

                const reset = clickByLabels(['重置', '清空']);
                if (reset) await wait(1000);
                const query = clickByLabels(['查询', '搜索']);
                if (query) await wait(5000);
                return `reset=${reset || 'none'};query=${query || 'none'}`;
            }"""
        )
        LOGGER.info("Declaration query refresh result: %s", result)
        return str(result)
    except Exception as exc:
        LOGGER.warning("Declaration query refresh failed: %s", exc)
        return f"error:{exc}"


def wait_for_declaration_detail_page(page, before_pages: set[Any], timeout: int = 30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        candidates = list(page.context.pages)
        for candidate in candidates:
            try:
                if candidate in before_pages:
                    continue
                if is_declaration_detail_page(candidate):
                    candidate.bring_to_front()
                    return candidate
            except Exception:
                continue
        for candidate in candidates:
            try:
                if is_declaration_detail_page(candidate):
                    candidate.bring_to_front()
                    return candidate
            except Exception:
                continue
        time.sleep(1)
    return page


def click_declaration_row_once(page, keywords: tuple[str, ...]) -> str:
    result = page.evaluate(
        """(keywords) => {
            const normalize = (value) => String(value || '')
                .replace(/\\s+/g, '')
                .replace(/[（）()《》]/g, '');
            const wanted = keywords.map(normalize);
            const includesWanted = (value) => {
                const text = normalize(value);
                return wanted.every((kw) => text.includes(kw));
            };

            function findComponents(el, out = []) {
                if (el.__vue__) out.push(el.__vue__);
                for (const child of el.children || []) findComponents(child, out);
                return out;
            }
            const comp = findComponents(document.body).find((v) => v.$options && v.$options.name === 'sbxxcx');
            if (comp && comp.$data && Array.isArray(comp.$data.data)) {
                const rowIndex = comp.$data.data.findIndex((row) => {
                    const text = Object.values(row || {}).map((v) => String(v ?? '')).join('');
                    return includesWanted(text);
                });
                if (rowIndex >= 0 && typeof comp.rehandleClickOp === 'function') {
                    comp.rehandleClickOp(comp.$data.data[rowIndex], rowIndex);
                    return 'clicked_vue';
                }
            }
            const nodes = Array.from(document.querySelectorAll('tr, .el-table__row, li, div'));
            const hit = nodes.find((el) => {
                const text = el.innerText || el.textContent || '';
                return text && text.length < 1000 && includesWanted(text);
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
    return str(result)


def click_declaration_row(page, keywords: tuple[str, ...]):
    before_pages = set(page.context.pages)
    result = click_declaration_row_once(page, keywords)
    if result == "not_found" and is_query_page(page):
        refresh_declaration_query_results(page)
        result = click_declaration_row_once(page, keywords)
    if not str(result).startswith("clicked"):
        raise RuntimeError(f"Declaration row was not found for keywords={keywords}; result={result}")
    time.sleep(5)
    detail_page = wait_for_declaration_detail_page(page, before_pages)
    if not is_declaration_detail_page(detail_page):
        raise RuntimeError(f"Declaration row was clicked but detail page did not open; keywords={keywords}; result={result}")
    return detail_page


def select_detail_form(page, keywords: tuple[str, ...]) -> str:
    result = page.evaluate(
        """async (keywords) => {
            const normalize = (value) => String(value || '')
                .replace(/\\s+/g, '')
                .replace(/[（）()《》]/g, '');
            const wanted = keywords.map(normalize);
            const includesWanted = (value) => {
                const text = normalize(value);
                return wanted.every((kw) => text.includes(kw));
            };

            const body = document.body ? document.body.innerText : '';
            const detailContext = location.href.includes('sbxxcx/detail')
                || location.href.includes('sbxxcxxq')
                || (body.includes('申报信息查询详情') && body.includes('主附表表单'))
                || body.includes('报表列表');
            if (detailContext && includesWanted(body)) return 'already_visible';

            function findVueComponents(el, out = []) {
                if (el.__vue__) out.push(el.__vue__);
                if (el.__vueParentComponent) out.push(el.__vueParentComponent);
                for (const child of el.children || []) findVueComponents(child, out);
                return out;
            }
            const components = findVueComponents(document.body);
            const detailComp = components.find((comp) => {
                const tree = comp && comp.sbmxxqzfbTree;
                return Array.isArray(tree) && typeof comp.selectChange === 'function';
            });
            if (detailComp) {
                const option = detailComp.sbmxxqzfbTree.find((item) => includesWanted(item && item.label));
                if (option) {
                    const beforeHtml = String(detailComp.sbxxcxDetail || '');
                    const ret = detailComp.selectChange(option.value, { option });
                    if (ret && typeof ret.then === 'function') await ret;
                    const deadline = Date.now() + 30000;
                    while (Date.now() < deadline) {
                        await new Promise((resolve) => setTimeout(resolve, 500));
                        const bodyNow = document.body ? document.body.innerText : '';
                        const htmlNow = String(detailComp.sbxxcxDetail || '');
                        if (includesWanted(bodyNow) || (htmlNow !== beforeHtml && includesWanted(htmlNow))) {
                            return `tdesign_vue_select:${option.value}`;
                        }
                    }
                    return `tdesign_vue_select_unconfirmed:${option.value}`;
                }
            }

            const all = Array.from(document.querySelectorAll('*')).filter((el) => el.offsetParent !== null);
            const exact = all.find((el) => {
                if (['HTML', 'BODY'].includes(el.tagName)) return false;
                const text = el.innerText || el.textContent || '';
                if (!text || text.length > 300) return false;
                return includesWanted(text);
            });
            if (exact) {
                exact.click();
                return 'clicked_visible_text';
            }

            const labels = all.filter((el) => /主附表表单|附表|附列资料/.test(el.innerText || el.textContent || ''));
            for (const label of labels) {
                const container = label.closest('.el-form-item, .ant-form-item, tr, div') || label.parentElement;
                const trigger = container && Array.from(container.querySelectorAll('input, .el-select, .ant-select, .t-select, .t-select-input, button, [role=combobox]'))
                    .find((el) => el.offsetParent !== null);
                if (trigger) {
                    trigger.click();
                    break;
                }
            }

            const options = Array.from(document.querySelectorAll('.el-select-dropdown__item, .ant-select-item, .t-select-option, .t-option, li, [role=option]'))
                .filter((el) => el.offsetParent !== null);
            const option = options.find((el) => {
                return includesWanted(el.innerText || el.textContent || '');
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
    return str(result)


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
                        if (idx > 4) return false;
                        const m = text.match(/^(FZ\\d+|\\d+(?:\\.\\d+)?)(.*)$/);
                        if (!m || m[1] !== wantedLine) return false;
                        const rest = (m[2] || '').trim();
                        return rest === '' || /^[()（）=+\\-×\\\\\\s]/.test(rest);
                    });
                    if (lineIndex < 0) continue;
                    const offset = Number(mapping.web_col_index);
                    const looksAmount = (value) => {
                        const text = String(value || '').trim().replace(/[,\s]/g, '');
                        return text === ''
                            || text === '——'
                            || text === '-'
                            || /^-?\d+(\.\d+)?%?$/.test(text);
                    };
                    const mainSuffix = fieldId.match(/_(ybxm_bys|ybxm_bnlj|jzjtxm_bys|jzjtxm_bnlj)$/);
                    if (mapping.form_code === 'VAT_GENERAL_MAIN' && mainSuffix) {
                        const relativeOffset = {
                            ybxm_bys: 1,
                            ybxm_bnlj: 2,
                            jzjtxm_bys: 3,
                            jzjtxm_bnlj: 4,
                        }[mainSuffix[1]];
                        const mainIndex = lineIndex + relativeOffset;
                        if (mainIndex >= 0 && mainIndex < cells.length) {
                            const value = (cells[mainIndex].innerText || cells[mainIndex].textContent || '').trim();
                            if (looksAmount(value)) return value;
                        }
                    }
                    const appendix2Field = fieldId.match(/^(fs|je|se)_/);
                    if (appendix2Field) {
                        const relativeOffset = { fs: 1, je: 2, se: 3 }[appendix2Field[1]];
                        const appendix2Index = lineIndex + relativeOffset;
                        if (appendix2Index >= 0 && appendix2Index < cells.length) {
                            const value = (cells[appendix2Index].innerText || cells[appendix2Index].textContent || '').trim();
                            if (looksAmount(value)) return value;
                        }
                    }
                    if (mapping.form_code === 'CULTURE_FEE_MAIN') {
                        const cultureFeeSuffix = fieldId.match(/_(bys|bnlj)$/);
                        if (cultureFeeSuffix) {
                            const relativeOffset = { bys: 1, bnlj: 2 }[cultureFeeSuffix[1]];
                            const cultureFeeIndex = lineIndex + relativeOffset;
                            if (cultureFeeIndex >= 0 && cultureFeeIndex < cells.length) {
                                const value = (cells[cultureFeeIndex].innerText || cells[cultureFeeIndex].textContent || '').trim();
                                if (mapping.data_type !== 'amount' || looksAmount(value)) return value;
                            }
                        }
                    }
                    if (mapping.form_code === 'VAT_GENERAL_APPENDIX1') {
                        const appendix1Index = lineIndex + offset - 5;
                        if (appendix1Index >= 0 && appendix1Index < cells.length) {
                            const value = (cells[appendix1Index].innerText || cells[appendix1Index].textContent || '').trim();
                            if (looksAmount(value)) return value;
                        }
                    }
                    const candidateIndexes = [
                        offset - 1,
                        lineIndex + offset - 1,
                        lineIndex + 1 + Math.max(0, offset - 4),
                        offset - 2,
                        cells.length - 1,
                    ];
                    const seenIndexes = new Set();
                    for (const index of candidateIndexes) {
                        if (index < 0 || index >= cells.length || seenIndexes.has(index)) continue;
                        seenIndexes.add(index);
                        const cell = cells[index];
                        const value = (cell.innerText || cell.textContent || '').trim();
                        if (mapping.data_type !== 'amount' || looksAmount(value)) return value;
                    }
                }
                const mainSuffix = fieldId.match(/_(ybxm_bys|ybxm_bnlj|jzjtxm_bys|jzjtxm_bnlj)$/);
                if (mapping.form_code === 'VAT_GENERAL_MAIN' && mainSuffix && wantedLine) {
                    const looksAmount = (value) => {
                        const text = String(value || '').trim().replace(/[,\s]/g, '');
                        return text === ''
                            || text === '——'
                            || text === '-'
                            || /^-?\d+(\.\d+)?%?$/.test(text);
                    };
                    const relativeOffset = {
                        ybxm_bys: 1,
                        ybxm_bnlj: 2,
                        jzjtxm_bys: 3,
                        jzjtxm_bnlj: 4,
                    }[mainSuffix[1]];
                    const linePattern = new RegExp(`^${wantedLine}(?!\\\\d)`);
                    for (const tr of rows) {
                        const cells = Array.from(tr.querySelectorAll('th,td'));
                        const texts = cells.map((td) => (td.innerText || td.textContent || '').trim());
                        const lineIndex = texts.findIndex((text, idx) => idx <= 2 && linePattern.test(normalizeLabel(text)));
                        if (lineIndex < 0) continue;
                        const mainIndex = lineIndex + relativeOffset;
                        if (mainIndex >= 0 && mainIndex < cells.length) {
                            const value = (cells[mainIndex].innerText || cells[mainIndex].textContent || '').trim();
                            if (looksAmount(value)) return value;
                        }
                    }
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


VAT_GENERAL_MAIN_WEB_VALUE_ALIASES = {
    "qmwjse_ybxm_bys": "qcwjse_ybxm_bys",
}


def apply_target_web_value_rules(target: CompareTarget, web_raw: dict[str, Any]) -> dict[str, Any]:
    if target.target_id != "vat_general_main":
        return web_raw
    for target_field, source_field in VAT_GENERAL_MAIN_WEB_VALUE_ALIASES.items():
        if target_field in web_raw:
            web_raw[target_field] = web_raw.get(source_field)
    return web_raw


def extract_web_data_for_target(page, target: CompareTarget, mappings: list[FieldMapping]) -> dict[str, Any]:
    if target.target_id in {"consumption_tax_main", "consumption_tax_surcharge"}:
        data = extract_consumption_tax_data(page, target, mappings)
        found = sum(1 for value in data.values() if value not in (None, ""))
        if found:
            LOGGER.info("Extracted %s/%s web fields with consumption-tax parser", found, len(mappings))
            return apply_target_web_value_rules(target, data)
        LOGGER.warning("Consumption-tax parser found no fields; falling back to generic extraction")
    if target.target_id == "vat_general_appendix3":
        data = extract_vat_general_appendix3_data(page, mappings)
        found = sum(1 for value in data.values() if value not in (None, ""))
        if found:
            LOGGER.info("Extracted %s/%s web fields with appendix3 parser", found, len(mappings))
            return apply_target_web_value_rules(target, data)
        LOGGER.warning("Appendix3 parser found no fields; falling back to generic extraction")
    if target.target_id == "vat_general_appendix5":
        data = extract_vat_general_appendix5_data(page, mappings)
        found = sum(1 for value in data.values() if value not in (None, ""))
        if found:
            LOGGER.info("Extracted %s/%s web fields with appendix5 parser", found, len(mappings))
            return apply_target_web_value_rules(target, data)
        LOGGER.warning("Appendix5 parser found no fields; falling back to generic extraction")
    return apply_target_web_value_rules(target, extract_web_data(page, mappings))


def extract_consumption_tax_data(page, target: CompareTarget, mappings: list[FieldMapping]) -> dict[str, Any]:
    rows = page.evaluate(
        """() => Array.from(document.querySelectorAll('table tr')).map((tr) =>
            Array.from(tr.querySelectorAll('th,td')).map((td) =>
                (td.innerText || td.textContent || '').trim()
            )
        )"""
    )
    if target.target_id == "consumption_tax_main":
        parsed = parse_consumption_tax_main_rows(rows)
    else:
        parsed = parse_consumption_tax_surcharge_rows(rows)
    return {mapping.field_id: parsed.get(mapping.field_id) for mapping in mappings}


def parse_consumption_tax_main_rows(rows: list[list[Any]]) -> dict[str, Any]:
    data: dict[str, Any] = {}
    normalized_rows = [[str(cell or "").strip() for cell in row] for row in rows]
    product_start = -1
    for idx, row in enumerate(normalized_rows):
        joined = "".join(row)
        if "6=1" in joined and "2" in joined and "5" in joined:
            product_start = idx + 1
            break
    if product_start >= 0:
        product_no = 1
        for row in normalized_rows[product_start:]:
            if not row:
                continue
            first_cell = normalize_form_text(row[0])
            if "合计" in first_cell:
                if len(row) >= 10:
                    data["bqynse6_xfsjfjsfsbb"] = row[8]
                    data["bnynse6_xfsjfjsfsbb"] = row[9]
                break
            if product_no > 5:
                break
            if len(row) >= 10:
                prefix_to_index = {
                    "ysxfpmc": 0,
                    "desl": 1,
                    "blsl": 2,
                    "jldw": 3,
                    "bqxssl": 4,
                    "bnxssl": 5,
                    "bqxse": 6,
                    "bnxse": 7,
                    "bqynse": 8,
                    "bnynse": 9,
                }
                for prefix, cell_index in prefix_to_index.items():
                    value = normalize_form_text(row[cell_index]) if prefix in {"ysxfpmc", "jldw"} else row[cell_index]
                    data[f"{prefix}{product_no}_xfsjfjsfsbb"] = value
                product_no += 1

    summary_fields = {
        "本期减免税额": ("bqsjmse_xfsjfjsfsbb", "bnljjmse_xfsjfjsfsbb"),
        "期初留抵税额": ("bqqcldse_xfsjfjsfsbb", None),
        "本期准予扣除税额": ("bqzydkse_xfsjfjsfsbb", "bnljzydkse_xfsjfjsfsbb"),
        "本期应扣除税额": ("bqykcse_xfsjfjsfsbb", None),
        "本期实际扣除税额": ("bqsjkcse_xfsjfjsfsbb", "bnljsjkcse_xfsjfjsfsbb"),
        "期末留抵税额": ("bqqmlqse_xfsjfjsfsbb", None),
        "本期预缴税额": ("bqyjse_xfsjfjsfsbb", None),
        "本期应补退税额": ("bqybtse_xfsjfjsfsbb", "bnljybtse_xfsjfjsfsbb"),
        "城市维护建设税本期应补退税额": ("bqcswhjssybtse_xfsjfjsfsbb", "bnljcswhjssybtse_xfsjfjsfsbb"),
        "教育费附加本期应补退费额": ("bqjyffjybtse_xfsjfjsfsbb", "bnljjyffjybtse_xfsjfjsfsbb"),
        "地方教育附加本期应补退费额": ("bqdfjyfjybtse_xfsjfjsfsbb", "bnljdfjyfjybtse_xfsjfjsfsbb"),
    }
    for row in normalized_rows:
        if len(row) < 3:
            continue
        row_label = normalize_form_text(row[0])
        for label, (current_field, cumulative_field) in summary_fields.items():
            if row_label.startswith(label):
                data[current_field] = row[2] if len(row) > 2 else None
                if cumulative_field:
                    data[cumulative_field] = row[3] if len(row) > 3 else None
                break
    return data


def parse_consumption_tax_surcharge_rows(rows: list[list[Any]]) -> dict[str, Any]:
    data: dict[str, Any] = {}
    row_labels = {
        "城市维护建设税": 1,
        "教育费附加": 2,
        "地方教育附加": 3,
        "合计": 4,
    }
    normal_rows = [[str(cell or "").strip() for cell in row] for row in rows]
    for row in normal_rows:
        if len(row) < 5:
            continue
        normalized_label = normalize_form_text(row[0])
        row_no = next((value for label, value in row_labels.items() if label in normalized_label), None)
        if row_no is None:
            continue
        if row_no in (1, 2, 3) and len(row) >= 12:
            prefix_to_index = {
                "jsyjsfsse": 2,
                "sfl": 3,
                "bqynsfe": 4,
                "jmxzdm": 5,
                "jmsfe": 6,
                "jzbl": 8,
                "jze": 9,
                "bqyjsfe": 10,
                "bqybtsfe": 11,
            }
            for prefix, cell_index in prefix_to_index.items():
                value = row[cell_index]
                if prefix == "jzbl":
                    value = normalize_percent_ratio(value)
                data[f"{prefix}{row_no}_xfsfjsfjsb"] = value
        elif row_no == 4 and len(row) >= 12:
            data["bqynsfe4_xfsfjsfjsb"] = row[4]
            data["jmsfe4_xfsfjsfjsb"] = row[6]
            data["jze4_xfsfjsfjsb"] = row[9]
            data["bqyjsfe4_xfsfjsfjsb"] = row[10]
            data["bqybtsfe4_xfsfjsfjsb"] = row[11]
    return data


def normalize_percent_ratio(value: Any) -> str:
    amount = parse_amount(value)
    if amount is None:
        return str(value or "")
    if abs(amount) > Decimal("1"):
        amount = amount / Decimal("100")
    text = format(amount, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def normalize_form_text(value: Any) -> str:
    return (
        str(value or "")
        .replace("\u2002", "")
        .replace("\xa0", "")
        .replace("\n", "")
        .replace("\r", "")
        .replace(" ", "")
        .replace("（", "")
        .replace("）", "")
        .replace("(", "")
        .replace(")", "")
    )


def extract_vat_general_appendix3_data(page, mappings: list[FieldMapping]) -> dict[str, Any]:
    rows = page.evaluate(
        """() => {
            const clean = (value) => String(value ?? '')
                .replace(/\\u00a0/g, ' ')
                .replace(/\\u3000/g, ' ')
                .trim();
            const valueOf = (cell) => {
                const input = cell.querySelector('input, textarea, select');
                if (input) return clean(input.value);
                const value = cell.getAttribute('value');
                if (value !== null && value !== '') return clean(value);
                return clean(cell.innerText || cell.textContent || '');
            };
            const tables = Array.from(document.querySelectorAll('table'));
            const table = tables.find((item) => {
                const text = item.innerText || item.textContent || '';
                return text.includes('附列资料（三）') || text.includes('扣除项目明细');
            }) || tables.find((item) => {
                const text = item.innerText || item.textContent || '';
                return text.includes('13%税率的项目') && text.includes('期末余额');
            });
            if (!table) return [];
            return Array.from(table.querySelectorAll('tr')).map((tr) =>
                Array.from(tr.querySelectorAll('th,td')).map(valueOf)
            );
        }"""
    )
    return parse_vat_general_appendix3_rows(rows or [], mappings)


def parse_vat_general_appendix3_rows(rows: list[list[Any]], mappings: list[FieldMapping]) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for mapping in mappings:
        if mapping.data_type != DataType.AMOUNT:
            continue
        if not mapping.line_no or mapping.web_col_index is None:
            continue
        value = appendix3_value_from_rows(rows, mapping)
        if value is not None:
            data[mapping.field_id] = value
    return {mapping.field_id: data.get(mapping.field_id) for mapping in mappings}


def appendix3_value_from_rows(rows: list[list[Any]], mapping: FieldMapping) -> str | None:
    wanted_line = first_line_number(mapping.line_no)
    wanted_name = compact_appendix3_label(mapping.row_name)
    if not wanted_line or not wanted_name:
        return None

    for row in rows:
        cells = [str(value or "").strip() for value in row]
        if not cells:
            continue
        compact_cells = [compact_appendix3_label(cell) for cell in cells]
        line_index = appendix3_line_index(compact_cells, wanted_line)
        if line_index < 0:
            continue
        row_text = compact_appendix3_label("".join(cells))
        if wanted_name and wanted_name not in row_text:
            continue
        label_index = appendix3_label_index(compact_cells, wanted_name)
        value_start = max(line_index, label_index) + 1
        value_index = value_start + int(mapping.web_col_index) - 3
        if value_index < 0 or value_index >= len(cells):
            return None
        return normalize_appendix3_amount_cell(cells[value_index])
    return None


def compact_appendix3_label(value: Any) -> str:
    return (
        compact_label(value)
        .replace("（", "(")
        .replace("）", ")")
        .replace("，", ",")
        .replace("：", ":")
    )


def first_line_number(value: Any) -> str:
    match = re.search(r"\d+(?:\.\d+)?", str(value or ""))
    return match.group(0) if match else ""


def appendix3_line_index(cells: list[str], wanted_line: str) -> int:
    for index, cell in enumerate(cells[:4]):
        if cell == wanted_line:
            return index
    line_pattern = re.compile(rf"^{re.escape(wanted_line)}(?!\d)")
    for index, cell in enumerate(cells[:4]):
        if line_pattern.match(cell):
            return index
    return -1


def appendix3_label_index(cells: list[str], wanted_name: str) -> int:
    for index, cell in enumerate(cells[:4]):
        if wanted_name and wanted_name in cell:
            return index
    return -1


def normalize_appendix3_amount_cell(value: Any) -> str:
    text = str(value or "").strip()
    text = (
        text.replace("\u00a0", "")
        .replace("\u3000", "")
        .replace(",", "")
        .replace("￥", "")
        .replace("¥", "")
    )
    text = re.sub(r"\s+", "", text)
    if not text or text in DASH_ZERO_VALUES:
        return "0.00"
    return text


def extract_vat_general_appendix5_data(page, mappings: list[FieldMapping]) -> dict[str, Any]:
    text = page.evaluate("document.body ? document.body.innerText : ''")
    parsed = parse_vat_general_appendix5_text(str(text or ""), mappings)
    fallback = extract_web_data(page, [mapping for mapping in mappings if mapping.field_id not in parsed])
    fallback.update({field_id: value for field_id, value in parsed.items() if value not in (None, "")})
    return {mapping.field_id: fallback.get(mapping.field_id) for mapping in mappings}


def parse_vat_general_appendix5_text(text: str, mappings: list[FieldMapping]) -> dict[str, Any]:
    lines = normalize_page_text_lines(text)
    data: dict[str, Any] = {}
    rows = extract_vat_appendix5_grid_rows(lines)

    for mapping in mappings:
        field_id = mapping.field_id
        row_label = vat_appendix5_row_label_for_field(field_id)
        if row_label and row_label in rows and mapping.web_col_index is not None:
            index = int(mapping.web_col_index) - VAT_APPENDIX5_GRID_BASE_COL
            values = rows[row_label]
            if 0 <= index < len(values):
                data[field_id] = values[index]
            continue

        if field_id == "nsrmc":
            data[field_id] = value_after_label(lines, "纳税人名称")
        elif field_id == "nsssq":
            start = value_after_label(lines, "税（费）款所属期起")
            end = value_after_label(lines, "税（费）款所属期止")
            data[field_id] = f"{start}至{end}" if start and end else start or end
        elif field_id == "bqsfsyxwqylslfjmzc":
            data[field_id] = checked_option_after_label(lines, "本期是否适用小微企业")
        elif field_id == "jmzcsyzt":
            data[field_id] = checked_option_after_label(lines, "减征政策适用主体")
        elif field_id == "syjmzcqsj":
            data[field_id] = value_after_label(lines, "适用减免政策日期起")
        elif field_id == "syjmzczsj":
            data[field_id] = value_after_label(lines, "适用减免政策日期止")
        elif field_id == "bqsfsysdjspycjrhxqydmzc":
            data[field_id] = checked_option_after_label(lines, "本期是否适用试点建设培育产教融合型企业抵免政策")
        elif field_id in VAT_APPENDIX5_SINGLE_VALUE_LABELS:
            data[field_id] = numeric_value_after_label(lines, VAT_APPENDIX5_SINGLE_VALUE_LABELS[field_id], mapping.line_no)
    return data


def normalize_page_text_lines(text: str) -> list[str]:
    normalized = (
        str(text or "")
        .replace("\u2002", " ")
        .replace("\xa0", " ")
        .replace("\u3000", " ")
    )
    return [line.strip() for line in normalized.splitlines() if line.strip()]


def extract_vat_appendix5_grid_rows(lines: list[str]) -> dict[str, list[str]]:
    rows: dict[str, list[str]] = {}
    row_labels = set(VAT_APPENDIX5_ROW_LABELS.values())
    stop_labels = row_labels | {
        "本期是否适用试点建设培育产教融合型企业抵免政策",
        "可用于扣除的增值税留抵退税额使用情况",
        "当期新增投资额",
    }
    for index, line in enumerate(lines):
        label, value_start, inline_values = find_appendix5_row_label(lines, index, row_labels)
        if not label or label in rows:
            continue
        values = list(inline_values)
        if len(values) < VAT_APPENDIX5_GRID_WIDTH:
            values.extend(collect_appendix5_row_values(lines, value_start, stop_labels))
        values = align_appendix5_grid_values(values)
        if len(values) >= VAT_APPENDIX5_GRID_WIDTH:
            rows[label] = values[:VAT_APPENDIX5_GRID_WIDTH]
    return rows


def find_appendix5_row_label(lines: list[str], index: int, row_labels: set[str]) -> tuple[str, int, list[str]]:
    line = lines[index]
    cells = split_appendix5_cells(line, preserve_empty=True)
    for label in row_labels:
        wanted = compact_label(label)
        for cell_index, cell in enumerate(cells):
            current_cell = compact_label(cell)
            if wanted == current_cell or wanted in current_cell:
                return label, index + 1, appendix5_value_tokens(cells[cell_index + 1 :], preserve_empty=True)

    current = compact_label(line)
    next_cells = split_appendix5_cells(lines[index + 1], preserve_empty=True) if index + 1 < len(lines) else []
    next_first = compact_label(next_cells[0]) if next_cells else ""
    for label in row_labels:
        wanted = compact_label(label)
        if wanted == current or wanted in current:
            return label, index + 1, []
        if current and (current + next_first).startswith(wanted):
            return label, index + 2, appendix5_value_tokens(next_cells[1:], preserve_empty=True)
    return "", index + 1, []


def split_appendix5_cells(line: Any, preserve_empty: bool = False) -> list[str]:
    text = (
        str(line or "")
        .replace("\u2002", " ")
        .replace("\xa0", " ")
        .replace("\u3000", " ")
        .strip()
    )
    if not text:
        return []
    if "\t" not in text:
        return [text]
    cells = [cell.strip() for cell in text.split("\t")]
    if preserve_empty:
        while cells and not cells[0]:
            cells.pop(0)
        while cells and not cells[-1]:
            cells.pop()
        return cells
    return [cell for cell in cells if cell]


def compact_label(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or ""))


def align_appendix5_grid_values(values: list[str]) -> list[str]:
    if len(values) == VAT_APPENDIX5_GRID_WIDTH - 1:
        aligned = list(values)
        aligned.insert(7, "")
        return aligned
    return values


def collect_appendix5_row_values(lines: list[str], start: int, stop_labels: set[str]) -> list[str]:
    values: list[str] = []
    for line in lines[start:]:
        compact_line = compact_label(line)
        if values and any(compact_label(label) in compact_line for label in stop_labels):
            break
        values.extend(appendix5_value_tokens(split_appendix5_cells(line, preserve_empty=True), preserve_empty="\t" in line))
        if len(values) >= VAT_APPENDIX5_GRID_WIDTH:
            break
    return strip_leading_row_number(values)


def strip_leading_row_number(values: list[str]) -> list[str]:
    if len(values) > VAT_APPENDIX5_GRID_WIDTH and values[0] in {"1", "2", "3", "4"}:
        return values[1:]
    return values


def normalize_appendix5_value_token(value: Any) -> str | None:
    text = str(value or "").strip()
    text = text.replace("\u2002", " ").replace("\xa0", " ")
    text = re.sub(r"\s+", "", text)
    if not text:
        return None
    if text in {"|", "｜"}:
        return ""
    if text in {"—", "——", "--", "-", "－"}:
        return "0.00"
    if re.fullmatch(r"-?\d+(?:,\d{3})*(?:\.\d+)?%?", text) or re.fullmatch(r"-?\d+(?:\.\d+)?%?", text):
        return text
    return None


def appendix5_value_tokens(values: list[Any], preserve_empty: bool = False) -> list[str]:
    tokens: list[str] = []
    for value in values:
        if preserve_empty and str(value or "").strip() == "":
            tokens.append("")
            continue
        token = normalize_appendix5_value_token(value)
        if token is not None:
            tokens.append(token)
    return tokens


def vat_appendix5_row_label_for_field(field_id: str) -> str:
    for suffix, label in VAT_APPENDIX5_ROW_LABELS.items():
        if field_id.endswith(suffix):
            return label
    return ""


def value_after_label(lines: list[str], label: str) -> str:
    for index, line in enumerate(lines):
        cells = split_appendix5_cells(line)
        for cell_index, cell in enumerate(cells):
            if label not in cell:
                continue
            inline = cell.split(label, 1)[1].strip(" ：:")
            if inline:
                return inline
            if cell_index + 1 < len(cells):
                return cells[cell_index + 1]
            for candidate in lines[index + 1 : index + 5]:
                if candidate and candidate not in {":", "："}:
                    return candidate
    return ""


def numeric_value_after_label(lines: list[str], label: str, line_no: Any = "") -> str:
    skip_line_no = str(line_no or "").strip()
    for index, line in enumerate(lines):
        cells = split_appendix5_cells(line, preserve_empty=True)
        inline_candidates: list[Any] = []
        for cell_index, cell in enumerate(cells):
            if label in cell:
                inline = cell.split(label, 1)[1].strip(" ：:")
                if inline:
                    inline_candidates.append(inline)
                inline_candidates.extend(cells[cell_index + 1 :])
                break
        if inline_candidates:
            for candidate in inline_candidates:
                token = normalize_appendix5_value_token(candidate)
                if token is None:
                    continue
                if skip_line_no and token == skip_line_no:
                    continue
                return token
            continue
        if label not in line:
            continue
        for candidate in lines[index + 1 : index + 8]:
            token = normalize_appendix5_value_token(candidate)
            if token is None:
                continue
            if skip_line_no and token == skip_line_no:
                continue
            return token
    return ""


def checked_option_after_label(lines: list[str], label: str) -> str:
    for index, line in enumerate(lines):
        cells = split_appendix5_cells(line)
        search_windows: list[str] = []
        for cell_index, cell in enumerate(cells):
            if label not in cell:
                continue
            inline = cell.split(label, 1)[1].strip(" ：:")
            if inline and contains_checked_option_marker(inline):
                search_windows.append(inline)
            search_windows.extend(cells[cell_index + 1 : cell_index + 3])
            break
        if label in line and not any(contains_checked_option_marker(window) for window in search_windows):
            search_windows.extend(lines[index + 1 : index + 4])
        for window in search_windows:
            options = re.findall(r"([■☑√●])\s*([^□■☑√●]+)", window)
            for marker, option in options:
                if marker:
                    return option.strip()
    return ""


def contains_checked_option_marker(value: Any) -> bool:
    return any(marker in str(value or "") for marker in ("■", "☑", "√", "●"))


def web_extraction_coverage(web_raw: dict[str, Any], mappings: list[FieldMapping]) -> tuple[int, int, float]:
    comparable = [mapping for mapping in mappings if mapping.compare and mapping.field_id not in TEXT_FIELDS]
    total = len(comparable)
    if total <= 0:
        return 0, 0, 1.0
    found = sum(1 for mapping in comparable if web_raw.get(mapping.field_id) not in (None, ""))
    return found, total, found / total


def is_low_web_extraction_coverage(target: CompareTarget, web_raw: dict[str, Any], mappings: list[FieldMapping]) -> bool:
    found, total, ratio = web_extraction_coverage(web_raw, mappings)
    if total <= 0:
        return False
    if found == 0:
        return True
    threshold = 0.2 if target.target_id.endswith("appendix5") else 0.1
    return ratio < threshold


def web_extraction_coverage(web_raw: dict[str, Any], mappings: list[FieldMapping]) -> tuple[int, int, float]:
    comparable = [mapping for mapping in mappings if mapping.compare and mapping.field_id not in TEXT_FIELDS]
    total = len(comparable)
    if total <= 0:
        return 0, 0, 1.0
    found = sum(1 for mapping in comparable if web_raw.get(mapping.field_id) not in (None, ""))
    return found, total, found / total


def is_low_web_extraction_coverage(target: CompareTarget, web_raw: dict[str, Any], mappings: list[FieldMapping]) -> bool:
    found, total, ratio = web_extraction_coverage(web_raw, mappings)
    if total <= 0:
        return False
    if found == 0:
        return True
    threshold = 0.6 if target.target_id == "vat_general_appendix5" else 0.1
    return ratio < threshold


def comparison_quality_issues(target: CompareTarget, result, low_web_coverage: bool) -> list[str]:
    summary = result.summary
    issues: list[str] = []
    if summary.mismatch_count:
        issues.append(f"mismatch={summary.mismatch_count}")
    if summary.api_missing_count:
        issues.append(f"api_missing={summary.api_missing_count}")
    if summary.web_missing_count:
        issues.append(f"web_missing={summary.web_missing_count}")
    if summary.parse_error_count:
        issues.append(f"parse_error={summary.parse_error_count}")
    if summary.mapping_error_count:
        issues.append(f"mapping_error={summary.mapping_error_count}")
    if low_web_coverage:
        issues.append("low_web_extraction_coverage")

    both_missing_ratio = summary.both_missing_count / summary.total_fields if summary.total_fields else 0
    if target.target_id == "vat_general_appendix5":
        both_missing_threshold = 0.3
    elif target.tax_type == "CONSUMPTION_TAX":
        both_missing_threshold = 0.8
    else:
        both_missing_threshold = 0.5
    if both_missing_ratio >= both_missing_threshold and summary.both_missing_count:
        issues.append(f"both_missing_ratio={both_missing_ratio:.2%}")
    return issues


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
    if isinstance(value, str) and value.strip() in DASH_ZERO_VALUES | {""}:
        return value

    monthly_field_id = mapping.field_id.removesuffix("_ybxm_bnlj") + "_ybxm_bys"
    cumulative = parse_amount(value)
    current_month = parse_amount(web_raw.get(monthly_field_id))
    if cumulative is None or current_month is None:
        return value
    if cumulative < current_month:
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
    text = re.sub(r"\s+", "", text)
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


def save_result(
    task_id: str,
    target: CompareTarget,
    result,
    province: str = "",
    current_period_flag: bool | None = None,
    quality_issues: list[str] | None = None,
) -> Path:
    output_dir = task_output_dir(task_id)
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = output_dir / f"{target.target_id}_compare_{task_id}_{ts}.json"
    payload = json.loads(result.model_dump_json())
    payload["province"] = province
    payload["current_period_flag"] = current_period_flag
    payload["declaration_status"] = declaration_status_for_target(target, current_period_flag)
    payload["quality_issues"] = quality_issues or []
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def declaration_status_for_target(target: CompareTarget, current_period_flag: bool | None) -> str:
    if current_period_flag is False and target.tax_type == "VAT_GENERAL":
        return "未申报"
    if current_period_flag is True:
        return "已申报"
    return "未知"


def save_api_filled_workbook(
    task_id: str,
    target: CompareTarget,
    mappings: list[FieldMapping],
    api_by_tax: dict[str, Any],
    output_dir: Path,
) -> Path | None:
    """Write API values back into the ID workbook layout for human review."""

    workbook = find_workbook(target.workbook_name)
    wb = load_workbook_compat(workbook, data_only=False)
    try:
        if target.sheet_name not in wb.sheetnames:
            raise ValueError(f"Sheet not found: {target.sheet_name}; available={wb.sheetnames}")
        ws = wb[target.sheet_name]
        for sheet in list(wb.worksheets):
            if sheet.title != target.sheet_name:
                wb.remove(sheet)
        ws.title = safe_excel_sheet_title(target.sheet_name)

        filled = 0
        missing = 0
        for mapping in mappings:
            cell = find_mapping_cell(ws, mapping)
            if cell is None:
                continue
            raw_value = api_value(api_by_tax, target, mapping.field_id)
            value = api_excel_value(raw_value, mapping)
            cell.value = value
            cell.fill = API_EXCEL_MISSING_FILL if value == "" else API_EXCEL_VALUE_FILL
            cell.comment = Comment(
                f"field_id: {mapping.field_id}\napi_path: {mapping.api_json_path}\napi_raw_value: {raw_value if raw_value is not None else ''}",
                "Codex",
            )
            if value == "":
                missing += 1
            else:
                filled += 1

        excel_dir = output_dir / "excel"
        excel_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        excel_path = excel_dir / f"{safe_filename(target.form_name)}_{target.target_id}_{task_id}_{ts}_api_filled.xlsx"
        wb.save(excel_path)
        LOGGER.info(
            "Saved API-filled Excel for %s: %s (filled=%s missing=%s)",
            target.target_id,
            excel_path,
            filled,
            missing,
        )
        return excel_path
    finally:
        wb.close()


def safe_excel_sheet_title(value: str) -> str:
    text = re.sub(r"[\[\]\:\*\?\/\\]", "_", str(value or "Sheet")).strip()
    return (text or "Sheet")[:31]


def api_excel_value(value: Any, mapping: FieldMapping) -> Any:
    if value is None:
        return ""
    value = clean_value(value, mapping)
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return value


def find_mapping_cell(ws, mapping: FieldMapping):
    row_idx = mapping.web_row_index
    col_idx = mapping.web_col_index
    if row_idx and col_idx:
        cell = writable_cell(ws, row_idx, col_idx)
        if cell is not None and str(cell.value or "").strip() == mapping.field_id:
            return cell

    for row in ws.iter_rows():
        for cell in row:
            if str(cell.value or "").strip() == mapping.field_id:
                return writable_cell(ws, cell.row, cell.column)
    return None


def writable_cell(ws, row_idx: int, col_idx: int):
    cell = ws.cell(row=row_idx, column=col_idx)
    if not isinstance(cell, MergedCell):
        return cell
    for merged_range in ws.merged_cells.ranges:
        if cell.coordinate in merged_range:
            return ws.cell(row=merged_range.min_row, column=merged_range.min_col)
    return None


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
        quality_issues = item.get("quality_issues") or report.get("quality_issues") or []
        quality_html = "<br>".join(escape_html(issue) for issue in quality_issues) if quality_issues else '<span class="quiet">-</span>'
        form_name = str(report.get("form_name") or report.get("form_code") or item.get("target_id") or "")
        anchor = f"form-{index}"
        report_link = relative_report_link(output_path, item.get("report_path"))
        pdf_link = relative_report_link(output_path, item.get("pdf_path"))
        api_excel_link = relative_report_link(output_path, item.get("api_excel_path"))
        pdf_html = f'<a href="{html.escape(pdf_link)}">PDF</a>' if pdf_link else '<span class="quiet">未生成</span>'
        api_excel_html = (
            f'<a href="{html.escape(api_excel_link)}">接口Excel</a>'
            if api_excel_link
            else '<span class="quiet">未生成</span>'
        )
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
              <td>{quality_html}</td>
              <td><a href="{html.escape(report_link)}">JSON</a> / {api_excel_html} / {pdf_html}</td>
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
              {f'<div class="quiet">质量风险：{quality_html}</div>' if quality_issues else ''}
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
          <th>表单</th><th>问题字段</th><th>有效通过率</th><th>原始通过率</th><th>不一致</th><th>接口缺失</th><th>网页缺失</th><th>双方为空</th><th>质量风险</th><th>文件</th>
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

    api_response = fetch_api_payload(args.task_id)
    api_by_tax = api_response.get("data", {})
    province = api_response.get("province", "")
    expected_tax_no = extract_expected_tax_no(api_response)
    LOGGER.info("Fetched API data: province=%s tax_codes=%s", province, ", ".join(api_by_tax.keys()))
    if is_auto_targets(args.targets):
        mappings_by_target = load_auto_mappings()
        targets = resolve_auto_targets(api_by_tax, mappings_by_target)
    else:
        targets = resolve_targets(args.targets)
        mappings_by_target = {target.target_id: load_mappings(target) for target in targets}
    if not targets:
        LOGGER.warning("No compare targets selected for task_id=%s", args.task_id)
        return 2
    targets = filter_targets_with_api_data(api_by_tax, targets, mappings_by_target)
    if not targets:
        LOGGER.warning("No compare targets have API field coverage for task_id=%s", args.task_id)
        return 2
    current_period_flag = fetch_current_period_flag(args.task_id) if any(target.tax_code == "sz_zzs" for target in targets) else None

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

        tax_page = find_existing_tax_page(bm, province, expected_tax_no)
        if tax_page:
            LOGGER.info(
                "Reusing existing tax bureau page: province=%s tax_no=%s url=%s",
                province,
                expected_tax_no,
                tax_page.url,
            )
        else:
            flow = TaskLoginFlow(bm, timeout=args.tax_timeout, login_strategy=getattr(args, "tax_login_strategy", "direct_first"))
            tax_page, info = flow.login(chanjet_page, args.task_id)
            LOGGER.info("Logged into tax bureau: province=%s inner_task_id=%s url=%s", info.province, info.inner_task_id, tax_page.url)
            if expected_tax_no and info.tax_no and expected_tax_no != info.tax_no:
                LOGGER.warning(
                    "Task login taxpayer id differs from API paramJson: api=%s login=%s",
                    expected_tax_no,
                    info.tax_no,
                )

        exit_code = 0
        run_outputs: list[dict[str, Any]] = []
        previous_declared_target: CompareTarget | None = None
        for target in targets:
            mappings = mappings_by_target[target.target_id]
            web_config = get_web_config(args.config_root, target.tax_type)
            if current_period_flag is False and target.tax_type == "VAT_GENERAL":
                tax_page = navigate_to_undeclared_vat_page(tax_page, province)
                prepare_undeclared_page_for_target(tax_page, target)
                previous_declared_target = None
            else:
                tax_page = ensure_target_page(
                    tax_page,
                    target,
                    mappings,
                    web_config,
                    prefer_detail_form_switch=can_switch_detail_form_between(previous_declared_target, target),
                )
                previous_declared_target = target if is_declaration_detail_page(tax_page) else None
            web_data = extract_web_data_for_target(tax_page, target, mappings)
            low_web_coverage = is_low_web_extraction_coverage(target, web_data, mappings)
            if low_web_coverage:
                found, total, ratio = web_extraction_coverage(web_data, mappings)
                LOGGER.warning(
                    "%s low web extraction coverage: %s/%s (%.2f%%)",
                    target.target_id,
                    found,
                    total,
                    ratio * 100,
                )
            result = compare_target(target, mappings, api_by_tax, web_data)
            quality_issues = comparison_quality_issues(target, result, low_web_coverage)
            if quality_issues:
                LOGGER.warning("%s quality issues: %s", target.target_id, "; ".join(quality_issues))
            output_path = save_result(
                args.task_id,
                target,
                result,
                province=province,
                current_period_flag=current_period_flag,
                quality_issues=quality_issues,
            )
            api_excel_path = save_api_filled_workbook(args.task_id, target, mappings, api_by_tax, output_path.parent)
            pdf_path = None
            if not args.skip_pdf:
                pdf_path = save_web_pdf(tax_page, args.task_id, target, output_path.parent)
            run_outputs.append(
                {
                    "target_id": target.target_id,
                    "form_name": target.form_name,
                    "report_path": str(output_path),
                    "api_excel_path": str(api_excel_path) if api_excel_path else "",
                    "pdf_path": str(pdf_path) if pdf_path else "",
                    "quality_issues": quality_issues,
                }
            )
            summary = result.summary
            LOGGER.info(
                "%s complete: total=%s match=%s mismatch=%s api_missing=%s web_missing=%s match_rate=%s%% report=%s api_excel=%s pdf=%s",
                target.target_id,
                summary.total_fields,
                summary.match_count + summary.tolerance_match_count,
                summary.mismatch_count,
                summary.api_missing_count,
                summary.web_missing_count,
                summary.match_rate,
                output_path,
                api_excel_path or "",
                pdf_path or "",
            )
            if quality_issues:
                exit_code = 1
        combined_path = render_task_summary_report(args.task_id, run_outputs)
        if combined_path:
            LOGGER.info("Combined compare report: %s", combined_path)
        return exit_code
    finally:
        bm.close()


if __name__ == "__main__":
    raise SystemExit(main())
