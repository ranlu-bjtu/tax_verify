#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import logging
import os
import re
import secrets
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

LOGGER = logging.getLogger(__name__)

PUBLIC_MANAGE_URL = "https://public-manage.chanjet.com/taxserver/#/taskManage/taxTaskList"
PUBLIC_MANAGE_MARKER = "public-manage.chanjet.com/taxserver"
PUBLIC_MANAGE_TOKEN_URL = "https://public-manage.chanjet.com/token"
PUBLIC_MANAGE_CLIENT_ID = "f5b78222-5ade-465b-b080-cc31abc0f2b8"
TASK_LIST_URL = (
    "https://data-task-management.chanapp.chanjet.com/"
    "pub-tax-management/api/admin/task/getTaskListInternal"
)
PROD_PRIVACY_PHONE_API_BASE = "https://data-task-management.chanapp.chanjet.com/pub-tax-management/api/privatePhone"
INTE_PRIVACY_PHONE_API_BASE = "https://data-task-management-chanapp.inte.chanjet.com/pub-tax-management/api/privatePhone"
PRIVACY_PHONE_SUMMARY_URL = f"{PROD_PRIVACY_PHONE_API_BASE}/summary"
PRIVACY_PHONE_DETAIL_URL = f"{PROD_PRIVACY_PHONE_API_BASE}/ref/getDetail"
PRIVACY_PHONE_COPY_URL = f"{PROD_PRIVACY_PHONE_API_BASE}/copyDataByPrivatePhone"
INTE_PRIVACY_PHONE_SUMMARY_URL = f"{INTE_PRIVACY_PHONE_API_BASE}/summary"
INTE_PRIVACY_PHONE_PULL_URL = f"{INTE_PRIVACY_PHONE_API_BASE}/pullPrivateDataByPrivatePhone"
DEFAULT_CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
DEFAULT_PROFILE_DIR = str(Path.home() / ".ydz-create-accountset" / "browser_profile")
CDP_FALLBACK_PORTS = (9333, 9444, 9555, 9666)
CHROME_AUTOMATION_STEALTH_ARGS = ["--enable-automation", "--disable-blink-features=AutomationControlled"]
MANUAL_VERIFICATION_REQUIRED_MARKER = "MANUAL_VERIFICATION_REQUIRED"
CHANJET_LOGIN_CLIENT_ID = "4cb832be-e503-4075-9903-6aa8d9e29104"
CHANJET_LOGIN_RSA_MODULUS = (
    "D57B6EB2728B0377BBB94CD50EEC11902FF0BC5F2EBCA49AC2AA081621D28859A"
    "5272009C053BF1DDF765D831F88717869A7DC23F6AE2BBB92BF4ABEA487C5B44B5"
    "C9A108FE4B34994E03815F83D52584DAB454659B2A1AAC68006FA411747F8E7596"
    "7D060CC04EDCF3F5984B7D16D871A391D12BAA269C74E1B6B3E5A78B3E7"
)
CHANJET_LOGIN_RSA_EXPONENT = 0x10001
PASSWORD_LOGIN_TOKEN_READY = "TOKEN_READY"
PASSWORD_LOGIN_SSO_READY_TOKEN_UNAVAILABLE = "SSO_READY_TOKEN_UNAVAILABLE"
PASSWORD_LOGIN_MANUAL_VERIFICATION_REQUIRED = "MANUAL_VERIFICATION_REQUIRED"
PASSWORD_LOGIN_PASSWORD_CHANGE_REQUIRED = "PASSWORD_CHANGE_REQUIRED"
PASSWORD_LOGIN_BIND_PHONE_REQUIRED = "BIND_PHONE_REQUIRED"
PASSWORD_LOGIN_FAILED = "FAILED"
ADMIN_AUTH_READY = "TOKEN_READY"
ADMIN_AUTH_MANUAL_VERIFICATION_REQUIRED = "MANUAL_VERIFICATION_REQUIRED"
ADMIN_AUTH_FAILED = "FAILED"
CHALLENGE_ERROR_CODES = {"400", "800", "900", "访问拒绝", "璁块棶鎷掔粷"}
PASSWORD_CHANGE_ERROR_CODES = {"20154", "10012", "10013"}
BIND_PHONE_ERROR_CODES = {"20115"}
DEFAULT_OPENING_PERIOD = "202501"
DEFAULT_TAXPAYER_TYPE = "SMALL_TAXPAYER"
DEFAULT_TAX_INDUSTRY_ID = "11079"
DEFAULT_ACCTG_SYSTEM_ID = "10001"
DEFAULT_SERVICE_TYPE = "ACCOUTING"
BACKEND_LOGIN_TASK_CATEGORYS = "2,3"
ACCOUNTSET_LOGIN_TYPE_FILTER = "YSHDL,DLYW-YSHDL,SDSRDX,DLYW-SDSRDX"
MOCK_FLAG_NO = 0
NO_PASSWORD_LOGIN_METHODS = {"SBZMDL"}
PROXY_LOGIN_PREFIX = "DLYW-"
PRIVACY_LOGIN_METHODS = {"YSHDL", "DLYW-YSHDL"}
MANUAL_CAPTCHA_LOGIN_METHODS = {"SDSRDX", "DLYW-SDSRDX"}
LOGIN_ACCOUNT_METHODS = PRIVACY_LOGIN_METHODS | MANUAL_CAPTCHA_LOGIN_METHODS
SUPPORTED_LOGIN_METHODS = LOGIN_ACCOUNT_METHODS | NO_PASSWORD_LOGIN_METHODS
MAX_BACKEND_QUERY_WINDOW_DAYS = 39
TRANSIENT_PAGE_ERROR_MARKERS = (
    "Execution context was destroyed",
    "most likely because of a navigation",
    "Cannot find context with specified id",
)
DEFAULT_ENTERPRISE_HINTS = {"inte": "7793uB6A", "prod": "蓝天之爱"}
WORKBENCH_APP_LIST_URL = "https://workbench.chanjet.com/v2/myapp/list"
PLAYWRIGHT_INSTALL_HINT = (
    "Playwright is only required for browser/CDP login fallback. "
    "Install the Python package only if you need browser login or an existing Chrome CDP session: "
    "python -m pip install playwright. "
    "Do not run 'playwright install chromium' unless your host has no local Chrome; this CLI normally uses local Chrome CDP."
)

AREA_NAME_TO_CODE = {
    "北京": "11",
    "天津": "12",
    "河北": "13",
    "山西": "14",
    "内蒙古": "15",
    "辽宁": "21",
    "大连": "2102",
    "吉林": "22",
    "黑龙江": "23",
    "上海": "31",
    "江苏": "32",
    "浙江": "33",
    "宁波": "3302",
    "安徽": "34",
    "福建": "35",
    "厦门": "3502",
    "江西": "36",
    "山东": "37",
    "青岛": "3702",
    "河南": "41",
    "湖北": "42",
    "湖南": "43",
    "广东": "44",
    "深圳": "4403",
    "广西": "45",
    "海南": "46",
    "重庆": "50",
    "四川": "51",
    "贵州": "52",
    "云南": "53",
    "西藏": "54",
    "陕西": "61",
    "甘肃": "62",
    "青海": "63",
    "宁夏": "64",
    "新疆": "65",
}


@dataclass(frozen=True)
class YdzEnvironment:
    name: str
    cloud_marker: str
    public_url: str
    default_work_url: str
    org_id: str
    user_id: str
    accountant_id: str
    accountant_name: str


@dataclass(frozen=True)
class YdzAuthContext:
    href: str
    origin: str
    base: str
    iframe_token: str
    cia_token: str
    org_id: str
    user_id: str
    org_name: str = ""
    user_mobile: str = ""
    user_name: str = ""

    def as_api_dict(self) -> dict[str, str]:
        return {
            "href": self.href,
            "origin": self.origin,
            "base": self.base,
            "iframeToken": self.iframe_token,
            "ciaToken": self.cia_token,
            "orgId": self.org_id,
            "userId": self.user_id,
            "orgName": self.org_name,
            "userMobile": self.user_mobile,
            "userName": self.user_name,
        }


YDZ_ENVIRONMENTS = {
    "inte": YdzEnvironment(
        name="inte",
        cloud_marker="inte-cloud.chanjet.com/ydzee/",
        public_url="https://ydz.inte.chanjet.com/",
        default_work_url="https://inte-cloud.chanjet.com/ydzee/ujsoz429myw4/a41vioa2em/work.html#/customer-list",
        org_id="90001204213",
        user_id="61000431181",
        accountant_id="61000431181",
        accountant_name="user7793",
    ),
    "prod": YdzEnvironment(
        name="prod",
        cloud_marker="cloud.chanjet.com/ydzee/",
        public_url="https://ydz.chanjet.com/",
        default_work_url="https://cloud.chanjet.com/ydzee/u7anoc8y5p7p/49le0svcsa/work.html#/customer-list",
        org_id="90011827608",
        user_id="60009603684",
        accountant_id="60009603684",
        accountant_name="user-yAfUZb",
    ),
}


def build_ydz_auth_context(
    env: YdzEnvironment,
    *,
    iframe_token: str,
    cia_token: str,
    work_url: str | None = None,
    org_id: str | None = None,
    user_id: str | None = None,
    org_name: str | None = None,
    user_mobile: str | None = None,
    user_name: str | None = None,
) -> YdzAuthContext:
    href = str(work_url or env.default_work_url or "").strip()
    parsed = urllib.parse.urlparse(href)
    if not parsed.scheme or not parsed.netloc or "/work.html" not in parsed.path:
        raise AccountSetError("Yidaizhang token auth requires a full work.html URL.")
    context = YdzAuthContext(
        href=href,
        origin=f"{parsed.scheme}://{parsed.netloc}",
        base=parsed.path.split("/work.html", 1)[0],
        iframe_token=str(iframe_token or "").strip(),
        cia_token=str(cia_token or "").strip(),
        org_id=str(org_id or env.org_id),
        user_id=str(user_id or env.user_id),
        org_name=str(org_name or ""),
        user_mobile=str(user_mobile or ""),
        user_name=str(user_name or ""),
    )
    _validate_ydz_context(context.as_api_dict(), env)
    return context


def _normalize_ydz_context(data: Any, env: YdzEnvironment) -> dict[str, str]:
    if isinstance(data, YdzAuthContext):
        normalized = data.as_api_dict()
    elif isinstance(data, dict):
        normalized = {
            "href": data.get("href") or data.get("workUrl") or data.get("work_url") or "",
            "origin": data.get("origin") or "",
            "base": data.get("base") or "",
            "iframeToken": data.get("iframeToken") or data.get("iframe_token") or "",
            "ciaToken": data.get("ciaToken") or data.get("cia_token") or "",
            "orgId": data.get("orgId") or data.get("org_id") or "",
            "userId": data.get("userId") or data.get("user_id") or "",
            "orgName": data.get("orgName") or data.get("org_name") or "",
            "userMobile": data.get("userMobile") or data.get("user_mobile") or data.get("mobile") or "",
            "userName": data.get("userName") or data.get("user_name") or data.get("name") or "",
        }
    else:
        raise AccountSetError("Yidaizhang auth context is invalid.")
    normalized = {key: str(value or "") for key, value in normalized.items()}
    _validate_ydz_context(normalized, env)
    return normalized


def _validate_ydz_context(data: dict[str, str], env: YdzEnvironment) -> None:
    href = str(data.get("href") or "")
    if env.cloud_marker not in href or "/work.html" not in href:
        raise AccountSetError(f"Yidaizhang auth context is not ready for {env.name}; current_url={href}")
    if not data.get("origin") or not data.get("base"):
        raise AccountSetError("Yidaizhang API base path is missing.")
    if not data.get("iframeToken") or not data.get("ciaToken"):
        raise AccountSetError("Yidaizhang login token is missing. Log in and select the enterprise first.")
    if str(data.get("orgId") or "") != env.org_id:
        raise AccountSetError(f"Yidaizhang org mismatch: current={data.get('orgId')} expected={env.org_id}.")


@dataclass
class YdzDefaults:
    opening_period: str = DEFAULT_OPENING_PERIOD
    taxpayer_type: str = DEFAULT_TAXPAYER_TYPE
    tax_industry_id: str = DEFAULT_TAX_INDUSTRY_ID
    acctg_system_id: str = DEFAULT_ACCTG_SYSTEM_ID
    service_type: str = DEFAULT_SERVICE_TYPE


@dataclass
class BackendSource:
    tax_no: str
    name: str
    area_code: str
    area_name: str
    login_method: str
    proxy_tax_no: str = ""
    privacy_no: str = ""
    password: str = ""
    backend_task_id: str = ""

    def public_dict(self) -> dict[str, Any]:
        return {
            "taxNo": self.tax_no,
            "name": self.name,
            "areaCode": self.area_code,
            "areaName": self.area_name,
            "loginMethod": self.login_method,
            "hasProxyTaxNo": bool(self.proxy_tax_no),
            "hasPrivacyNo": bool(self.privacy_no),
            "hasLoginAccount": bool(self.privacy_no),
            "hasPassword": bool(self.password),
            "backendTaskId": self.backend_task_id,
        }


@dataclass
class ExistingCustomer:
    cust_id: str
    assoc_tenant_id: str
    name: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AssignedAccountant:
    employee_id: str
    name: str = ""
    mobile: str = ""
    source: str = "env_default"

    @classmethod
    def from_environment(cls, env: YdzEnvironment, source: str = "env_default") -> "AssignedAccountant":
        return cls(employee_id=env.accountant_id, name=env.accountant_name, source=source)


@dataclass
class CreateResult:
    tax_no: str
    status: str
    action: str = ""
    name: str = ""
    cust_id: str = ""
    assoc_tenant_id: str = ""
    area_code: str = ""
    area_name: str = ""
    login_method: str = ""
    has_password: bool = False
    save_ok: bool = False
    verify_ok: bool = False
    customer_verify_ok: bool = False
    tax_info_verify_ok: bool = False
    backend_task_id: str = ""
    accountant_id: str = ""
    accountant_name: str = ""
    accountant_mobile: str = ""
    accountant_source: str = ""
    privacy_phone_status: str = ""
    privacy_phone_message: str = ""
    errors: list[str] = field(default_factory=list)

    def public_dict(self) -> dict[str, Any]:
        return {
            "taxNo": self.tax_no,
            "status": self.status,
            "action": self.action,
            "name": self.name,
            "custId": self.cust_id,
            "assocTenantId": self.assoc_tenant_id,
            "areaCode": self.area_code,
            "areaName": self.area_name,
            "loginMethod": self.login_method,
            "hasPassword": self.has_password,
            "saveOk": self.save_ok,
            "verifyOk": self.verify_ok,
            "customerVerifyOk": self.customer_verify_ok,
            "taxInfoVerifyOk": self.tax_info_verify_ok,
            "backendTaskId": self.backend_task_id,
            "accountantId": self.accountant_id,
            "accountantName": self.accountant_name,
            "accountantMobile": self.accountant_mobile,
            "accountantSource": self.accountant_source,
            "privacyPhoneStatus": self.privacy_phone_status,
            "privacyPhoneMessage": self.privacy_phone_message,
            "errors": list(self.errors),
        }


@dataclass
class PrivacyPhonePrepareResult:
    private_phone: str
    status: str
    inte_summary_count: int = 0
    online_summary_count: int = 0
    online_detail_count: int = 0
    copy_success: bool = False
    pull_success: bool = False
    copy_message: str | None = None
    pull_message: str | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status in {"EXISTS", "PULLED", "DRY_RUN_EXISTS", "DRY_RUN_MISSING", "SKIPPED"}


class AccountSetError(RuntimeError):
    pass


def load_env_file(path: str | None) -> None:
    if not path:
        return
    env_path = Path(path)
    if not env_path.exists():
        raise SystemExit(f"Env file does not exist: {env_path}")
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def strip_operator_prefix(name: str | None) -> str:
    return re.sub(r"^\[[^\]]+\]", "", name or "").strip()


def normalize_login_json(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def normalize_login_method(value: str | None) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    upper = text.upper()
    if upper in SUPPORTED_LOGIN_METHODS:
        return upper
    compact = "".join(text.split())
    has_proxy = "代理" in compact or upper.startswith(PROXY_LOGIN_PREFIX)
    has_privacy = "隐私" in compact
    has_manual_captcha = (
        "SDSRDX" in upper
        or "手工录入验证码" in compact
        or "手动录入验证码" in compact
        or ("验证码" in compact and ("手工" in compact or "手动" in compact))
    )
    if has_manual_captcha:
        return "DLYW-SDSRDX" if has_proxy else "SDSRDX"
    if has_proxy and has_privacy:
        return "DLYW-YSHDL"
    if has_privacy:
        return "YSHDL"
    return upper


def backend_row_login_method(row: dict[str, Any]) -> str:
    login_json = normalize_login_json(row.get("loginJson"))
    return normalize_login_method(
        login_json.get("cLoginMethodEnum")
        or row.get("loginMethod")
        or row.get("cloginMethodEnum")
        or row.get("loginMethodText")
        or ""
    )


def backend_row_has_supported_login(row: dict[str, Any]) -> bool:
    login_json = normalize_login_json(row.get("loginJson"))
    login_method = backend_row_login_method(row)
    if not login_json or login_method not in LOGIN_ACCOUNT_METHODS:
        return False
    if not str(login_json.get("cTaxPreparerName") or "").strip():
        return False
    if not str(login_json.get("cTaxPreparerPwd") or "").strip():
        return False
    if login_method.startswith(PROXY_LOGIN_PREFIX) and not str(login_json.get("cSiteLoginName") or "").strip():
        return False
    return True


def login_method_requires_password(login_method: str) -> bool:
    return bool(login_method) and login_method not in NO_PASSWORD_LOGIN_METHODS


def expected_site_login_name(login_method: str, proxy_tax_no: str) -> str:
    return proxy_tax_no if str(login_method or "").startswith(PROXY_LOGIN_PREFIX) else ""


def normalize_phone(value: Any) -> str:
    return "".join(re.findall(r"\d+", str(value or "")))


def is_transient_page_error(exc: Exception) -> bool:
    text = str(exc)
    return any(marker in text for marker in TRANSIENT_PAGE_ERROR_MARKERS)


def fallback_area_code(area_name: str, tax_no: str) -> str:
    text = str(area_name or "")
    for name, code in AREA_NAME_TO_CODE.items():
        if name in text:
            return code
    if len(tax_no) >= 4 and tax_no[2:4].isdigit():
        return tax_no[2:4]
    return ""


def split_tax_numbers(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        for chunk in str(value or "").replace(",", "\n").replace("，", "\n").split():
            tax_no = chunk.strip().lstrip("\ufeff").upper()
            if not tax_no or tax_no in seen:
                continue
            seen.add(tax_no)
            result.append(tax_no)
    return result


def parse_lookback_days(value: str) -> list[int]:
    days = [int(chunk.strip()) for chunk in value.split(",") if chunk.strip()]
    return days or [30, 180, 730, 1460]


def build_customer_create_payload(
    source: BackendSource,
    env: YdzEnvironment,
    defaults: YdzDefaults,
    accountant_employee_id: str | None = None,
) -> dict[str, Any]:
    user_name = source.proxy_tax_no if source.login_method.startswith(PROXY_LOGIN_PREFIX) else source.privacy_no
    resolved_accountant_id = str(accountant_employee_id or env.accountant_id)
    return {
        "accountBook": {
            "name": source.name,
            "openingPeriod": defaults.opening_period,
            "taxpayerTypeEnum": defaults.taxpayer_type,
            "glAccountTaxpayerTypeEnum": defaults.taxpayer_type,
            "acctgSystemId": defaults.acctg_system_id,
            "bookkeeperName": "",
            "casherName": "",
        },
        "orgId": int(env.org_id),
        "custName": source.name,
        "corpName": source.name,
        "taxNo": source.tax_no,
        "taxIndustryId": defaults.tax_industry_id,
        "enterpriseFormEnum": "CORPORATION",
        "taxiationArea": source.area_code,
        "taxClaimMethodEnum": "TAX_DECLARATION",
        "accountTypeEnum": "COPY_LAST",
        "code": "",
        "businessAnnualPsw": "",
        "businessStatusEnum": "EMPLOYED",
        "establishmentDate": "",
        "labelIds": "",
        "label": "",
        "corpAddress": "",
        "legalRepresentative": "",
        "legalRepresentativeSsn": "",
        "legalRepresentativeTel": "",
        "contactName": "",
        "contactIdentificationNo": "",
        "contactTel": "",
        "registerAddress": "",
        "bizScope": "",
        "taxClaimTypeEnum": "NATIONAL",
        "emailAddress": "",
        "aiIndustry": "SOFTWARE_AND_INFO_TECH_SERVICES",
        "accountantEmployeeId": resolved_accountant_id,
        "isBuild": True,
        "centralTaxVerficationModeEnum": "SYSTEM",
        "centralTaxPswStateEnum": "UN_AUTHORIZED",
        "taxDep": "",
        "taxManager": "",
        "hasTaxCtrl": True,
        "taxPhone": "",
        "individualTaxVerficationModeEnum": "SYSTEM",
        "individualTaxPswStateEnum": "UN_AUTHORIZED",
        "comments": "",
        "serviceTypeEnum": defaults.service_type,
        "isTaxControlTrust": False,
        "isIndustryCommerceAnnals": False,
        "isOperationManagement": False,
        "isIncomeTaxSettlement": False,
        "insuranceFlag": False,
        "otherSpecialServices": "",
        "taxLoginMethodEnum": source.login_method,
        "taxSystemUserName": user_name,
        "realAccount": source.privacy_no,
        "realPwd": source.password,
    }


def build_tax_info_payload(source: BackendSource, cust_id: str, assoc_tenant_id: str) -> dict[str, Any]:
    return {
        "taxInfoDTO": {
            "areaCode": source.area_code,
            "easyacctgCustId": str(cust_id),
            "assocTenantId": str(assoc_tenant_id or ""),
            "cLoginMethodEnum": source.login_method,
            "cSiteLoginName": expected_site_login_name(source.login_method, source.proxy_tax_no),
            "cTaxPreparerName": source.privacy_no,
            "cTaxPreparerPwd": source.password,
            "cVerificationMethod": "SYSTEM",
            "iVerificationMethod": "SYSTEM",
            "isRpa": True,
            "isAuth": True,
        },
        "busiInfoDTO": {
            "assocTenantId": str(assoc_tenant_id or ""),
            "easyacctgCustId": str(cust_id),
        },
    }


def extract_first_dict_with_keys(payload: Any, keys: Iterable[str]) -> dict[str, Any]:
    key_set = set(keys)
    if isinstance(payload, dict):
        if key_set.intersection(payload):
            return payload
        for value in payload.values():
            found = extract_first_dict_with_keys(value, key_set)
            if found:
                return found
    elif isinstance(payload, list):
        for value in payload:
            found = extract_first_dict_with_keys(value, key_set)
            if found:
                return found
    return {}


def extract_tax_info(payload: Any) -> dict[str, Any]:
    return extract_first_dict_with_keys(
        payload,
        ("cLoginMethodEnum", "cSiteLoginName", "cTaxPreparerName", "cTaxPreparerPwd"),
    )


def extract_customer_info(payload: Any, tax_no: str = "") -> dict[str, Any]:
    if isinstance(payload, dict):
        data = payload.get("data", payload)
        if isinstance(data, dict) and (not tax_no or str(data.get("taxNo") or "") == tax_no):
            if data.get("taxNo") or data.get("custName") or data.get("accountBook"):
                return data
        if isinstance(data, dict):
            for value in data.values():
                found = extract_customer_info(value, tax_no)
                if found:
                    return found
        elif isinstance(data, list):
            for item in data:
                found = extract_customer_info(item, tax_no)
                if found:
                    return found
    elif isinstance(payload, list):
        for value in payload:
            found = extract_customer_info(value, tax_no)
            if found:
                return found
    return {}


def extract_employee_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("data", "list", "rows", "employeeList", "accountantEmployeeList"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            rows = extract_employee_rows(value)
            if rows:
                return rows
    return []


def find_ids(payload: Any) -> tuple[str, str]:
    if isinstance(payload, dict):
        data = payload.get("data", payload)
        if isinstance(data, dict):
            cust_id = data.get("custId") or data.get("id") or data.get("easyacctgCustId")
            assoc_tenant_id = (
                data.get("assocTenantId")
                or data.get("tenantId")
                or data.get("assocTenant")
                or data.get("tId")
                or data.get("thId")
            )
            if cust_id:
                return str(cust_id), str(assoc_tenant_id or "")
            for value in data.values():
                found = find_ids(value)
                if found[0]:
                    return found
        elif isinstance(data, list):
            for value in data:
                found = find_ids(value)
                if found[0]:
                    return found
    elif isinstance(payload, list):
        for value in payload:
            found = find_ids(value)
            if found[0]:
                return found
    return "", ""


def api_success(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    if payload.get("success") is True:
        return True
    code = str(payload.get("code") or payload.get("resultCode") or "").lower()
    return code in {"200", "0", "success"}


def verify_tax_info(source: BackendSource, tax_info: dict[str, Any]) -> bool:
    return (
        str(tax_info.get("cLoginMethodEnum") or "") == source.login_method
        and str(tax_info.get("cSiteLoginName") or "") == expected_site_login_name(source.login_method, source.proxy_tax_no)
        and str(tax_info.get("cTaxPreparerName") or "") == source.privacy_no
        and str(tax_info.get("cTaxPreparerPwd") or "") == source.password
    )


def verify_customer_info(
    customer: dict[str, Any],
    source: BackendSource,
    env: YdzEnvironment,
    defaults: YdzDefaults,
    accountant_employee_id: str | None = None,
) -> bool:
    account_book = customer.get("accountBook") if isinstance(customer.get("accountBook"), dict) else {}
    opening_period = account_book.get("openingPeriod") or customer.get("openingPeriod") or customer.get("lastBookPeriod")
    resolved_accountant_id = str(accountant_employee_id or env.accountant_id)
    return (
        str(customer.get("taxNo") or "") == source.tax_no
        and str(customer.get("custName") or "") == source.name
        and str(customer.get("corpName") or "") == source.name
        and str(customer.get("taxIndustryId") or "") == defaults.tax_industry_id
        and str(customer.get("taxpayerTypeEnum") or "") == defaults.taxpayer_type
        and str(opening_period or "") == defaults.opening_period
        and str(customer.get("accountantEmployeeId") or "") == resolved_accountant_id
    )


def is_cdp_alive(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=2):
            return True
    except Exception:
        return False


def remember_cdp_request(args: argparse.Namespace) -> None:
    if not hasattr(args, "_requested_cdp_port"):
        setattr(args, "_requested_cdp_port", int(args.cdp_port))
    if not hasattr(args, "_requested_user_data_dir"):
        setattr(args, "_requested_user_data_dir", str(args.user_data_dir))


def cdp_candidate_ports(preferred_port: int) -> list[int]:
    ports: list[int] = []
    for port in (preferred_port, *CDP_FALLBACK_PORTS):
        if port not in ports:
            ports.append(port)
    return ports


def cdp_profile_dir_for_port(base_dir: str, requested_port: int, port: int) -> str:
    if int(port) == int(requested_port):
        return str(base_dir)
    path = Path(base_dir)
    return str(path.with_name(f"{path.name}_{port}"))


def set_runtime_cdp_port(args: argparse.Namespace, port: int) -> None:
    remember_cdp_request(args)
    requested_port = int(getattr(args, "_requested_cdp_port"))
    base_user_data_dir = str(getattr(args, "_requested_user_data_dir"))
    args.cdp_port = int(port)
    args.user_data_dir = cdp_profile_dir_for_port(base_user_data_dir, requested_port, int(port))


def cdp_connect_requires_isolated_browser(exc: Exception) -> bool:
    text = str(exc).lower()
    return "enable-automation" in text


def launch_chrome_if_needed(args: argparse.Namespace, env: YdzEnvironment) -> None:
    if is_cdp_alive(args.cdp_port):
        LOGGER.info(
            "Reusing existing Chrome CDP on port %s; startup flags cannot be changed for an already-running browser.",
            args.cdp_port,
        )
        return
    if getattr(args, "no_launch_chrome", False):
        raise SystemExit(f"Chrome CDP is not available on port {args.cdp_port}.")
    Path(args.user_data_dir).mkdir(parents=True, exist_ok=True)
    work_url = args.ydz_work_url or env.default_work_url or env.public_url
    command = [
        args.chrome_path,
        f"--remote-debugging-port={args.cdp_port}",
        f"--user-data-dir={args.user_data_dir}",
        "--no-first-run",
        "--disable-popup-blocking",
        *CHROME_AUTOMATION_STEALTH_ARGS,
        work_url,
        PUBLIC_MANAGE_URL,
    ]
    LOGGER.info(
        "Launching Chrome CDP on port %s with startup flags: %s.",
        args.cdp_port,
        " ".join(CHROME_AUTOMATION_STEALTH_ARGS),
    )
    subprocess.Popen(command, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    deadline = time.time() + 20
    while time.time() < deadline:
        if is_cdp_alive(args.cdp_port):
            return
        time.sleep(0.5)
    raise SystemExit(f"Chrome CDP did not become available on port {args.cdp_port}.")


def connect_chrome_over_cdp(playwright: Any, args: argparse.Namespace, env: YdzEnvironment) -> Any:
    remember_cdp_request(args)
    requested_port = int(getattr(args, "_requested_cdp_port"))
    last_error: BaseException | None = None
    for port in cdp_candidate_ports(requested_port):
        set_runtime_cdp_port(args, port)
        try:
            launch_chrome_if_needed(args, env)
        except SystemExit as exc:
            last_error = exc
            if getattr(args, "no_launch_chrome", False):
                raise
            LOGGER.warning("Chrome CDP on port %s could not be launched; trying another port. %s", args.cdp_port, exc)
            continue
        try:
            return playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{args.cdp_port}")
        except Exception as exc:
            last_error = exc
            if cdp_connect_requires_isolated_browser(exc):
                LOGGER.warning(
                    "Chrome CDP on port %s is incompatible with Playwright automation; trying another port.",
                    args.cdp_port,
                )
                continue
            raise
    raise SystemExit(
        "Chrome CDP could not be connected on any candidate port "
        f"{cdp_candidate_ports(requested_port)}. Last error: {last_error}"
    )


def load_sync_playwright() -> Any:
    try:
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError as exc:
        if str(getattr(exc, "name", "")).split(".")[0] == "playwright":
            raise SystemExit(PLAYWRIGHT_INSTALL_HINT) from exc
        raise
    return sync_playwright


@dataclass(frozen=True)
class AdminAuthTokens:
    authorization: str
    token: str
    user_id: str = ""
    source: str = ""

    def as_dict(self) -> dict[str, str]:
        return {"authorization": self.authorization, "token": self.token}


@dataclass
class AdminPasswordLoginResult:
    status: str
    message: str = ""
    error_code: str = ""
    tokens: AdminAuthTokens | None = None
    raw_keys: list[str] = field(default_factory=list)

    def public_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "message": self.message,
            "errorCode": self.error_code,
            "hasTokens": self.tokens is not None,
            "rawKeys": list(self.raw_keys),
        }


class StaticAdminAuthProvider:
    def __init__(self, tokens: AdminAuthTokens) -> None:
        self.tokens = tokens

    def get_tokens(self, force_refresh: bool = False) -> AdminAuthTokens:
        return self.tokens


class ChanjetAdminPasswordAuthClient:
    def __init__(
        self,
        username: str,
        password: str,
        *,
        public_manage_url: str = PUBLIC_MANAGE_URL,
        timeout: int = 30,
        session: Any | None = None,
    ) -> None:
        import requests

        self.username = str(username or "")
        self.password = str(password or "")
        self.public_manage_url = str(public_manage_url or PUBLIC_MANAGE_URL)
        self.timeout = timeout
        self.session = session or requests.Session()

    def login(self) -> AdminPasswordLoginResult:
        if not self.username or not self.password:
            return AdminPasswordLoginResult(
                status=ADMIN_AUTH_FAILED,
                message="Public management username/password is not configured.",
            )
        try:
            self._open_login_page()
            auth_code = self._get_auth_code()
            login_response = self._account_login(auth_code)
        except Exception as exc:
            return AdminPasswordLoginResult(
                status=ADMIN_AUTH_FAILED,
                message=f"Public management password login request failed: {exc}",
            )

        classified = self._classify_login_response(login_response)
        if classified.status != ADMIN_AUTH_READY:
            return classified
        return self._exchange_public_manage_tokens()

    def _classify_login_response(self, response: dict[str, Any]) -> AdminPasswordLoginResult:
        raw_keys = sorted(str(key) for key in response.keys())
        if response.get("result") is True:
            self._try_get_ticket()
            return AdminPasswordLoginResult(status=ADMIN_AUTH_READY, raw_keys=raw_keys)
        error_code = str(response.get("errorCode") or (response.get("error") or {}).get("code") or "")
        message = str(
            response.get("errorMessage")
            or response.get("msg")
            or (response.get("error") or {}).get("msg")
            or error_code
            or "Public management password login did not succeed."
        )
        if error_code in CHALLENGE_ERROR_CODES or response.get("captchaResult") is False:
            return AdminPasswordLoginResult(
                status=ADMIN_AUTH_MANUAL_VERIFICATION_REQUIRED,
                message=message,
                error_code=error_code,
                raw_keys=raw_keys,
            )
        return AdminPasswordLoginResult(
            status=ADMIN_AUTH_FAILED,
            message=message,
            error_code=error_code,
            raw_keys=raw_keys,
        )

    def _exchange_public_manage_tokens(self) -> AdminPasswordLoginResult:
        try:
            code_response = self._authorize_public_manage()
            if code_response.get("auth_code") and not code_response.get("code"):
                return AdminPasswordLoginResult(
                    status=ADMIN_AUTH_FAILED,
                    message="Chanjet SSO login did not authorize public-manage.",
                    raw_keys=sorted(str(key) for key in code_response.keys()),
                )
            code = str(code_response.get("code") or "").strip()
            if not code:
                return AdminPasswordLoginResult(
                    status=ADMIN_AUTH_FAILED,
                    message="public-manage authorizeByJsonp did not return code.",
                    raw_keys=sorted(str(key) for key in code_response.keys()),
                )
            response = self.session.get(
                PUBLIC_MANAGE_TOKEN_URL,
                params={"code": code},
                headers=self._headers(self.public_manage_url),
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
            tokens = self._tokens_from_token_response(data)
            if tokens is None:
                return AdminPasswordLoginResult(
                    status=ADMIN_AUTH_FAILED,
                    message="public-manage token exchange did not return usable tokens.",
                    raw_keys=sorted(str(key) for key in data.keys()),
                )
            return AdminPasswordLoginResult(
                status=ADMIN_AUTH_READY,
                message="Public management password auth produced API tokens.",
                tokens=tokens,
                raw_keys=sorted(str(key) for key in data.keys()),
            )
        except Exception as exc:
            return AdminPasswordLoginResult(
                status=ADMIN_AUTH_FAILED,
                message=f"Public management token exchange failed: {exc}",
            )

    def _tokens_from_token_response(self, data: dict[str, Any]) -> AdminAuthTokens | None:
        payload = data.get("data") if isinstance(data.get("data"), dict) else {}
        authorization = str(data.get("token") or data.get("Authorization") or "").strip()
        access_token = str(payload.get("access_token") or data.get("access_token") or "").strip()
        if not authorization or not access_token:
            return None
        return AdminAuthTokens(
            authorization=authorization,
            token=access_token,
            user_id=str(payload.get("user_id") or data.get("user_id") or ""),
            source="password",
        )

    def _open_login_page(self) -> None:
        self.session.get(self.login_page_url, headers=self._headers(self.login_page_url), timeout=self.timeout)

    def _get_auth_code(self) -> str:
        callback = f"jsonp_{int(time.time() * 1000)}_{secrets.randbelow(900) + 100}"
        response = self.session.get(
            f"{self.cia_base_url}/internal_api/getAuthCodeByJsonp",
            params={"client_id": CHANJET_LOGIN_CLIENT_ID, "callback": callback},
            headers=self._headers(self.login_page_url),
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = _parse_json_or_jsonp(response.text)
        auth_code = str(data.get("auth_code") or data.get("code") or "")
        if not auth_code:
            raise AccountSetError("Chanjet CIA auth_code was not returned.")
        return auth_code

    def _authorize_public_manage(self) -> dict[str, Any]:
        callback = f"callback_{int(time.time() * 1000)}_{secrets.randbelow(900) + 100}"
        response = self.session.get(
            f"{self.cia_base_url}/internal_api/authorizeByJsonp",
            params={"client_id": PUBLIC_MANAGE_CLIENT_ID, "callback": callback},
            headers=self._headers("https://public-manage.chanjet.com/"),
            timeout=self.timeout,
        )
        response.raise_for_status()
        return _parse_json_or_jsonp(response.text)

    def _account_login(self, auth_code: str) -> dict[str, Any]:
        payload = {
            "auth_username": chanjet_rsa_encrypt(self.username),
            "passwordEncrypted": chanjet_rsa_encrypt(self.password),
            "auth_code": auth_code,
            "verifyToken": "",
            "jsonp": "0",
        }
        response = self.session.post(
            f"{self.login_api_base_url}/loginV2/accountLogin",
            data=payload,
            headers=self._headers(self.login_page_url, content_type=True),
            timeout=self.timeout,
        )
        response.raise_for_status()
        return _parse_json_or_jsonp(response.text)

    def _try_get_ticket(self) -> dict[str, Any] | None:
        try:
            response = self.session.post(
                f"{self.login_api_base_url}/loginV2/getTicket",
                headers=self._headers(self.login_page_url, content_type=True),
                timeout=self.timeout,
            )
            response.raise_for_status()
            return _parse_json_or_jsonp(response.text)
        except Exception:
            return None

    def _headers(self, referer: str, *, content_type: bool = False) -> dict[str, str]:
        headers = {
            "Accept": "application/json, text/plain, */*",
            "User-Agent": "Mozilla/5.0",
            "Referer": referer,
            "Domain": urllib.parse.urlparse(self.login_page_url).hostname or "",
            "Chanjet-Client-Language": "zh-CN",
            "Chanjet-Client-TimeZone": "Asia/Shanghai",
        }
        if content_type:
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        return headers

    @property
    def login_page_url(self) -> str:
        return f"{self.login_base_url}/?callback={urllib.parse.quote(self.public_manage_url, safe='')}"

    @property
    def is_integration(self) -> bool:
        host = urllib.parse.urlparse(self.public_manage_url).hostname or ""
        return ".inte." in host or host.startswith("inte-")

    @property
    def login_base_url(self) -> str:
        return "https://ydz-login.inte.chanjet.com" if self.is_integration else "https://login.chanjet.com"

    @property
    def login_api_base_url(self) -> str:
        return "https://passport.inte.chanjet.com" if self.is_integration else "https://login.chanjet.com"

    @property
    def cia_base_url(self) -> str:
        return "https://inte-cia.chanapp.chanjet.com" if self.is_integration else "https://cia.chanapp.chanjet.com"


class AdminTaskQuery:
    def __init__(self, context: Any | None = None, timeout: int = 20, token_provider: Any | None = None) -> None:
        self.context = context
        self.timeout = timeout
        self.token_provider = token_provider
        self._token_cache: dict[str, str] | None = None

    def query_tasks(
        self,
        start_time: datetime,
        end_time: datetime,
        tax_no: str,
        task_status: str = "SUCCESS",
        page_size: int = 20,
    ) -> list[dict[str, Any]]:
        page = None if self.token_provider is not None else self._ensure_page()
        tokens = self._read_tokens(page)
        payload = {
            "pageNo": 1,
            "pageSize": page_size,
            "sortField": "createTime",
            "sortBy": "desc",
            "taskCategorys": BACKEND_LOGIN_TASK_CATEGORYS,
            "startTime": start_time.strftime("%Y-%m-%d %H:%M:%S"),
            "endTime": end_time.strftime("%Y-%m-%d %H:%M:%S"),
            "mockFlag": MOCK_FLAG_NO,
            "taxNo": tax_no,
            "status": task_status,
            "taskStatus": task_status,
            "loginType": ACCOUNTSET_LOGIN_TYPE_FILTER,
        }
        data, _ = self._post_task_query(payload, tokens, page)
        if str(data.get("code")) != "200" or not data.get("success", False):
            raise AccountSetError(f"Public task query failed: code={data.get('code')} msg={data.get('msg') or data.get('message')}")
        rows = ((data.get("data") or {}).get("content") or []) if isinstance(data, dict) else []
        return [row for row in rows if str(row.get("taxNo") or "") == tax_no]

    def _post_task_query(self, payload: dict[str, Any], tokens: dict[str, str], page: Any | None) -> tuple[dict[str, Any], dict[str, str]]:
        import requests

        current_tokens = tokens
        data: dict[str, Any] = {}
        for attempt in range(2):
            response = requests.post(
                TASK_LIST_URL,
                headers=self._headers(current_tokens),
                json=payload,
                timeout=self.timeout,
            )
            if response.status_code in {401, 403} and attempt == 0:
                current_tokens = self._read_tokens(page, force_refresh=True)
                continue
            response.raise_for_status()
            data = response.json()
            if self._is_auth_failure_response(data) and attempt == 0:
                current_tokens = self._read_tokens(page, force_refresh=True)
                continue
            return data, current_tokens
        return data, current_tokens

    def _ensure_page(self) -> Any:
        if self.context is None:
            raise AccountSetError("Public management browser context is not configured.")
        for page in self.context.pages:
            if page.is_closed():
                continue
            if PUBLIC_MANAGE_MARKER in page.url:
                self._wait_for_page_ready(page)
                return page
        page = self.context.new_page()
        page.goto(PUBLIC_MANAGE_URL, wait_until="domcontentloaded", timeout=60_000)
        self._wait_for_page_ready(page)
        return page

    def _read_tokens(self, page: Any | None = None, force_refresh: bool = False) -> dict[str, str]:
        if self.token_provider is not None:
            tokens = self.token_provider.get_tokens(force_refresh=force_refresh)
            if not tokens.authorization or not tokens.token:
                raise AccountSetError("Public management token provider returned incomplete tokens.")
            self._token_cache = tokens.as_dict()
            return dict(self._token_cache)
        if self._token_cache and not force_refresh:
            return dict(self._token_cache)
        last_exc: Exception | None = None
        current_page = page or self._ensure_page()
        for attempt in range(5):
            try:
                if current_page.is_closed():
                    current_page = self._ensure_page()
                if PUBLIC_MANAGE_MARKER not in current_page.url:
                    current_page.goto(PUBLIC_MANAGE_URL, wait_until="domcontentloaded", timeout=60_000)
                self._wait_for_page_ready(current_page)
                tokens = current_page.evaluate(
                    """() => {
                        const read = (store, key) => {
                            try { return store.getItem(key) || ''; } catch (_err) { return ''; }
                        };
                        return {
                            authorization:
                                read(sessionStorage, 'Authorization') ||
                                read(localStorage, 'Authorization') ||
                                read(sessionStorage, 'authorization') ||
                                read(localStorage, 'authorization'),
                            token:
                                read(sessionStorage, 'access_token') ||
                                read(localStorage, 'access_token') ||
                                read(sessionStorage, 'token') ||
                                read(localStorage, 'token')
                        };
                    }"""
                )
                if tokens.get("authorization") and tokens.get("token"):
                    self._token_cache = {
                        "authorization": str(tokens.get("authorization") or ""),
                        "token": str(tokens.get("token") or ""),
                    }
                    return dict(self._token_cache)
                last_exc = RuntimeError("Public management login token is missing.")
            except Exception as exc:
                last_exc = exc
            if attempt < 4:
                try:
                    current_page.wait_for_timeout(1000)
                except Exception:
                    pass
        raise AccountSetError("Public management login token is missing. Open public-manage and login first.") from last_exc

    def _headers(self, tokens: dict[str, str]) -> dict[str, str]:
        return {
            "accept": "application/json, text/plain, */*",
            "content-type": "application/json",
            "authorization": tokens["authorization"],
            "token": tokens["token"],
            "referer": "https://public-manage.chanjet.com/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome Safari/537.36",
        }

    def _is_auth_failure_response(self, data: dict[str, Any]) -> bool:
        code = str(data.get("code") or "").strip().lower()
        message = str(data.get("msg") or data.get("message") or "").strip().lower()
        if code in {"401", "403", "unauthorized", "forbidden"}:
            return True
        if str(data.get("success", "")).lower() == "true":
            return False
        return any(marker in message for marker in ("token", "authorization", "unauthorized", "forbidden", "登录", "未登录"))

    def _wait_for_page_ready(self, page: Any) -> None:
        try:
            page.wait_for_load_state("domcontentloaded", timeout=10_000)
        except Exception:
            pass
        try:
            page.wait_for_timeout(500)
        except Exception:
            pass


def normalize_private_phone(value: str) -> str:
    phone = str(value or "").strip()
    if not phone:
        raise AccountSetError("private phone is required")
    return phone


def build_privacy_summary_payload(private_phone: str, page_no: int = 1, page_size: int = 10) -> dict[str, Any]:
    return {
        "customerDingSettingId": None,
        "phone": None,
        "privatePhone": normalize_private_phone(private_phone),
        "username": None,
        "yshIdCard": None,
        "accountingAgencyName": None,
        "mailbox": None,
        "isTaxBureauConfiguration": None,
        "orgId": None,
        "orgName": None,
        "orderStatus": None,
        "isSoonExpire": None,
        "exceedFlag": None,
        "phoneExpiredFlag": None,
        "pageSize": page_size,
        "pageNo": page_no,
    }


def build_inte_privacy_summary_payload(private_phone: str) -> dict[str, Any]:
    return {"privatePhone": normalize_private_phone(private_phone)}


def build_privacy_detail_payload(private_phone: str, org_id: str) -> dict[str, Any]:
    return {
        "privatePhone": normalize_private_phone(private_phone),
        "phone": None,
        "isException": None,
        "orgId": str(org_id or "").strip(),
        "pageSize": 20,
        "pageNo": 1,
    }


class PrivacyPhoneClient:
    def __init__(
        self,
        context: Any | None,
        api_base_url: str,
        timeout: int = 20,
        token_provider: Any | None = None,
    ) -> None:
        self.context = context
        self.api_base_url = api_base_url.rstrip("/")
        self.timeout = timeout
        self.admin_query = AdminTaskQuery(context, timeout=timeout, token_provider=token_provider)

    def query_summary_rows(self, private_phone: str) -> list[dict[str, Any]]:
        phone = normalize_private_phone(private_phone)
        page = None if self.admin_query.token_provider is not None else self.admin_query._ensure_page()
        tokens = self.admin_query._read_tokens(page)
        data, _ = self._post_json(self._endpoint("summary"), self._summary_payload(phone), tokens, page)
        return self._content_rows(data)

    def sync_online_private_phone(self, private_phone: str) -> tuple[bool, int, int, str]:
        phone = normalize_private_phone(private_phone)
        page = None if self.admin_query.token_provider is not None else self.admin_query._ensure_page()
        tokens = self.admin_query._read_tokens(page)
        summary_data, tokens = self._post_json(self._endpoint("summary"), self._summary_payload(phone), tokens, page)
        summary_rows = self._content_rows(summary_data)
        if not summary_rows:
            return False, 0, 0, f"private phone {phone} was not found in online summary"
        detail_rows: list[dict[str, Any]] = []
        for summary in summary_rows:
            org_id = str(summary.get("orgId") or "").strip()
            if not org_id:
                continue
            detail_data, tokens = self._post_json(
                self._endpoint("ref/getDetail"),
                build_privacy_detail_payload(phone, org_id),
                tokens,
                page,
            )
            detail_rows.extend(
                row for row in self._content_rows(detail_data) if str(row.get("privatePhone") or "").strip() == phone
            )
        if not detail_rows:
            return False, len(summary_rows), 0, f"private phone {phone} was not found in online detail"
        copy_data, _ = self._get_json(self._endpoint("copyDataByPrivatePhone"), {"privatePhone": phone}, tokens, page)
        ok = str(copy_data.get("code")) == "200" and bool(copy_data.get("success", False))
        message = str(copy_data.get("msg") or copy_data.get("message") or "")
        return ok, len(summary_rows), len(detail_rows), message

    def pull_private_phone(self, private_phone: str) -> tuple[bool, str]:
        phone = normalize_private_phone(private_phone)
        page = None if self.admin_query.token_provider is not None else self.admin_query._ensure_page()
        tokens = self.admin_query._read_tokens(page)
        data, _ = self._get_json(self._endpoint("pullPrivateDataByPrivatePhone"), {"privatePhone": phone}, tokens, page)
        ok = str(data.get("code")) == "200" and bool(data.get("success", False))
        return ok, str(data.get("msg") or data.get("message") or "")

    def _endpoint(self, path: str) -> str:
        return f"{self.api_base_url}/{path.lstrip('/')}"

    def _summary_payload(self, private_phone: str) -> dict[str, Any]:
        if self.api_base_url == INTE_PRIVACY_PHONE_API_BASE:
            return build_inte_privacy_summary_payload(private_phone)
        return build_privacy_summary_payload(private_phone)

    def _headers(self, tokens: dict[str, str]) -> dict[str, str]:
        headers = self.admin_query._headers(tokens)
        if self.api_base_url == INTE_PRIVACY_PHONE_API_BASE:
            headers.pop("token", None)
        return headers

    def _post_json(self, url: str, payload: dict[str, Any], tokens: dict[str, str], page: Any | None) -> tuple[dict[str, Any], dict[str, str]]:
        import requests

        current_tokens = tokens
        data: dict[str, Any] = {}
        for attempt in range(2):
            response = requests.post(url, headers=self._headers(current_tokens), json=payload, timeout=self.timeout)
            if response.status_code in {401, 403} and attempt == 0:
                current_tokens = self.admin_query._read_tokens(page, force_refresh=True)
                continue
            response.raise_for_status()
            data = response.json()
            if self.admin_query._is_auth_failure_response(data) and attempt == 0:
                current_tokens = self.admin_query._read_tokens(page, force_refresh=True)
                continue
            self._raise_if_failed(data, url)
            return data, current_tokens
        self._raise_if_failed(data, url)
        return data, current_tokens

    def _get_json(self, url: str, params: dict[str, Any], tokens: dict[str, str], page: Any | None) -> tuple[dict[str, Any], dict[str, str]]:
        import requests

        current_tokens = tokens
        data: dict[str, Any] = {}
        for attempt in range(2):
            response = requests.get(url, headers=self._headers(current_tokens), params=params, timeout=self.timeout)
            if response.status_code in {401, 403} and attempt == 0:
                current_tokens = self.admin_query._read_tokens(page, force_refresh=True)
                continue
            response.raise_for_status()
            data = response.json()
            if self.admin_query._is_auth_failure_response(data) and attempt == 0:
                current_tokens = self.admin_query._read_tokens(page, force_refresh=True)
                continue
            self._raise_if_failed(data, url)
            return data, current_tokens
        self._raise_if_failed(data, url)
        return data, current_tokens

    def _raise_if_failed(self, data: dict[str, Any], url: str) -> None:
        if str(data.get("code")) == "200" and bool(data.get("success", False)):
            return
        raise AccountSetError(f"privacy phone API failed: {url}: {data.get('msg') or data.get('message') or 'unknown error'}")

    def _content_rows(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        payload = data.get("data") or {}
        if isinstance(payload, list):
            rows = payload
        elif isinstance(payload, dict):
            rows = payload.get("content") or payload.get("records") or payload.get("list") or []
        else:
            rows = []
        return [row for row in (rows or []) if isinstance(row, dict)]


class PrivacyPhoneBridge:
    def __init__(self, context: Any | None = None, timeout: int = 20, token_provider: Any | None = None) -> None:
        self.online = PrivacyPhoneClient(
            context,
            PROD_PRIVACY_PHONE_API_BASE,
            timeout=timeout,
            token_provider=token_provider,
        )
        self.integration = PrivacyPhoneClient(
            context,
            INTE_PRIVACY_PHONE_API_BASE,
            timeout=timeout,
            token_provider=token_provider,
        )

    def ensure_integration_private_phone(self, private_phone: str, dry_run: bool = False) -> PrivacyPhonePrepareResult:
        phone = normalize_private_phone(private_phone)
        inte_rows = self.integration.query_summary_rows(phone)
        if inte_rows:
            return PrivacyPhonePrepareResult(phone, "DRY_RUN_EXISTS" if dry_run else "EXISTS", inte_summary_count=len(inte_rows))
        if dry_run:
            return PrivacyPhonePrepareResult(
                phone,
                "DRY_RUN_MISSING",
                errors=[f"private phone {phone} is not present in integration backend"],
            )
        copy_ok, online_summary_count, online_detail_count, copy_message = self.online.sync_online_private_phone(phone)
        if not copy_ok:
            return PrivacyPhonePrepareResult(
                phone,
                "FAILED",
                online_summary_count=online_summary_count,
                online_detail_count=online_detail_count,
                copy_success=False,
                copy_message=copy_message,
                errors=[copy_message or "online privacy phone sync failed"],
            )
        pull_ok, pull_message = self.integration.pull_private_phone(phone)
        if not pull_ok:
            return PrivacyPhonePrepareResult(
                phone,
                "FAILED",
                online_summary_count=online_summary_count,
                online_detail_count=online_detail_count,
                copy_success=True,
                pull_success=False,
                copy_message=copy_message,
                pull_message=pull_message,
                errors=[pull_message or "integration privacy phone pull failed"],
            )
        refreshed_rows = self.integration.query_summary_rows(phone)
        if not refreshed_rows:
            return PrivacyPhonePrepareResult(
                phone,
                "FAILED",
                online_summary_count=online_summary_count,
                online_detail_count=online_detail_count,
                copy_success=True,
                pull_success=True,
                copy_message=copy_message,
                pull_message=pull_message,
                errors=["integration privacy phone pull returned success, but summary is still empty"],
            )
        return PrivacyPhonePrepareResult(
            phone,
            "PULLED",
            inte_summary_count=len(refreshed_rows),
            online_summary_count=online_summary_count,
            online_detail_count=online_detail_count,
            copy_success=True,
            pull_success=True,
            copy_message=copy_message,
            pull_message=pull_message,
        )


class YdzApi:
    def __init__(
        self,
        page: Any | None,
        env: YdzEnvironment,
        timeout: int = 60,
        auth_context: YdzAuthContext | dict[str, Any] | None = None,
    ) -> None:
        if page is None and auth_context is None:
            raise AccountSetError("Yidaizhang API requires either a browser page or a token auth context.")
        self.page = page
        self.env = env
        self.timeout = timeout
        self._static_context = _normalize_ydz_context(auth_context, env) if auth_context is not None else None
        self._context_cache: dict[str, str] | None = None

    def context(self, force_refresh: bool = False) -> dict[str, str]:
        if self._context_cache is not None and not force_refresh:
            return dict(self._context_cache)
        if self._static_context is not None:
            self._context_cache = dict(self._static_context)
            return dict(self._context_cache)
        if self.page is None:
            raise AccountSetError("Yidaizhang browser page is not configured.")
        data = self.page.evaluate(
            """() => ({
                href: location.href,
                origin: location.origin,
                base: location.pathname.split('/work.html')[0],
                iframeToken: sessionStorage.getItem('iframeToken') || '',
                ciaToken: localStorage.getItem('ciaToken') || '',
                orgId: String((window.APP && window.APP.orgId) || ''),
                userId: String((window.APP && window.APP.user && window.APP.user.id) || ''),
                orgName: (window.APP && window.APP.orgName) || '',
                userMobile: String(
                    (window.APP && window.APP.user && (
                        window.APP.user.mobile ||
                        window.APP.user.phone ||
                        window.APP.user.account ||
                        window.APP.user.accountNumber
                    )) || ''
                ),
                userName: String(
                    (window.APP && window.APP.user && (
                        window.APP.user.name ||
                        window.APP.user.userName ||
                        window.APP.user.username
                    )) || ''
                )
            })"""
        )
        self._context_cache = _normalize_ydz_context(data, self.env)
        return dict(self._context_cache)

    def query_tax_geo(self, tax_no: str) -> tuple[str, str]:
        data = self.get_json(f"/trans/easyacctg/customer/queryTaxGeoByTaxNo?taxNo={tax_no}&orgId={self.env.org_id}")
        node = data.get("data") if isinstance(data.get("data"), dict) else data
        return str(node.get("geoCode") or node.get("taxiationArea") or ""), str(node.get("geoName") or node.get("areaName") or "")

    def query_accountant_employees(self) -> list[dict[str, Any]]:
        data = self.get_json("/trans/easyacctg/employee/getChildEmpListByUserId")
        return [
            row
            for row in extract_employee_rows(data)
            if str(row.get("roleTypeEnum") or "") != "EASYACCTG_ADMIN"
        ]

    def resolve_assigned_accountant(self, login_account: str | None = None) -> AssignedAccountant:
        fallback = AssignedAccountant.from_environment(self.env)
        try:
            rows = self.query_accountant_employees()
        except Exception as exc:
            LOGGER.warning("Yidaizhang accountant employee lookup failed; using env default accountant: %s", exc)
            return fallback
        if not rows:
            return fallback

        try:
            ctx = self.context()
        except Exception as exc:
            LOGGER.warning("Yidaizhang context lookup failed during accountant resolution; using available fallback: %s", exc)
            ctx = {}
        login_mobile = normalize_phone(login_account) or normalize_phone(ctx.get("userMobile"))
        current_user_id = str(ctx.get("userId") or "")

        def build(row: dict[str, Any], source: str) -> AssignedAccountant:
            return AssignedAccountant(
                employee_id=str(row.get("userId") or row.get("id") or row.get("employeeId") or ""),
                name=str(row.get("name") or row.get("userName") or row.get("employeeName") or ""),
                mobile=str(row.get("mobile") or row.get("phone") or row.get("account") or ""),
                source=source,
            )

        if login_mobile:
            for row in rows:
                if normalize_phone(row.get("mobile") or row.get("phone") or row.get("account")) == login_mobile:
                    resolved = build(row, "login_mobile")
                    if resolved.employee_id:
                        return resolved
        if current_user_id:
            for row in rows:
                row_user_id = str(row.get("userId") or row.get("id") or row.get("employeeId") or "")
                if row_user_id == current_user_id:
                    resolved = build(row, "current_user_id")
                    if resolved.employee_id:
                        return resolved
        for row in rows:
            row_user_id = str(row.get("userId") or row.get("id") or row.get("employeeId") or "")
            if row_user_id == self.env.accountant_id:
                resolved = build(row, "env_default_in_list")
                if resolved.employee_id:
                    return resolved
        return fallback

    def query_existing_customer(self, tax_no: str) -> ExistingCustomer | None:
        data = self.post_json("/trans/easyacctg/custWorkbench/queryPageList", {"pageNo": 1, "pageSize": 20, "keyword": tax_no})
        rows = ((data.get("data") or {}).get("custList") or []) if isinstance(data, dict) else []
        for row in rows:
            if str(row.get("taxNo") or row.get("tenantTaxNo") or "") != tax_no:
                continue
            return ExistingCustomer(
                cust_id=str(row.get("id") or ""),
                assoc_tenant_id=str(row.get("assocTenantId") or row.get("tId") or row.get("thId") or ""),
                name=str(row.get("custName") or row.get("corpName") or ""),
                raw=row,
            )
        return None

    def create_customer(
        self,
        source: BackendSource,
        defaults: YdzDefaults,
        accountant: AssignedAccountant | None = None,
    ) -> ExistingCustomer:
        data = self.post_json(
            "/trans/easyacctg/customer/create",
            build_customer_create_payload(
                source,
                self.env,
                defaults,
                accountant_employee_id=(accountant.employee_id if accountant else None),
            ),
        )
        cust_id, assoc_tenant_id = find_ids(data)
        if not cust_id:
            message = data.get("message") or data.get("msg") or data.get("errorMsg") or "create response has no customer id"
            raise AccountSetError(f"Yidaizhang create customer failed: {message}")
        return ExistingCustomer(cust_id=cust_id, assoc_tenant_id=assoc_tenant_id, name=source.name, raw=data)

    def save_tax_info(self, source: BackendSource, customer: ExistingCustomer) -> dict[str, Any]:
        return self.post_json("/trans/easyacctg/taxInfo/saveCustTaxAndBusiInfo", build_tax_info_payload(source, customer.cust_id, customer.assoc_tenant_id))

    def query_customer(self, cust_id: str) -> dict[str, Any]:
        return self.get_json(f"/trans/easyacctg/customer/query?custId={cust_id}&assocTenantId=&orgId={self.env.org_id}&hasSecret=1")

    def query_tax_info(self, cust_id: str) -> dict[str, Any]:
        return self.post_json("/trans/easyacctg/taxInfo/queryEasyacctgCustTaxInfo", [{"easyacctgCustId": str(cust_id)}])

    def post_json(self, endpoint: str, payload: Any) -> dict[str, Any]:
        return self._request_json("POST", endpoint, payload)

    def get_json(self, endpoint: str) -> dict[str, Any]:
        return self._request_json("GET", endpoint, None)

    def _request_json(self, method: str, endpoint: str, payload: Any) -> dict[str, Any]:
        import requests

        ctx = self.context()
        url = self._absolute_url(endpoint, ctx)
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Authorization": "Bearer " + ctx["iframeToken"],
            "token": ctx["ciaToken"],
            "Content-Type": "application/json;charset=UTF-8",
            "Referer": ctx["origin"] + ctx["base"] + "/work.html",
        }
        response = requests.get(url, headers=headers, timeout=self.timeout) if method == "GET" else requests.post(url, headers=headers, json=payload, timeout=self.timeout)
        if response.status_code >= 400:
            raise AccountSetError(f"Yidaizhang API failed: endpoint={endpoint} http={response.status_code}")
        try:
            data = response.json()
        except ValueError as exc:
            raise AccountSetError(f"Yidaizhang API returned non-json response: endpoint={endpoint}") from exc
        if isinstance(data, dict):
            code = str(data.get("code") or "")
            if code in {"500", "701"}:
                message = data.get("msg") or data.get("message") or data.get("rootCause") or "Yidaizhang API failed"
                raise AccountSetError(f"Yidaizhang API failed: endpoint={endpoint} code={code} msg={message}")
        return data

    def _absolute_url(self, endpoint: str, ctx: dict[str, str]) -> str:
        separator = "&" if "?" in endpoint else "?"
        req = (
            f"{separator}user_req_id=ydz-accountset-{int(time.time() * 1000)}"
            f"&user_req_userid={ctx.get('userId') or self.env.user_id}"
            f"&user_req_orgid={ctx.get('orgId') or self.env.org_id}"
        )
        return ctx["origin"] + ctx["base"] + endpoint + req


class SourceResolver:
    def __init__(self, admin_query: AdminTaskQuery, lookback_days: list[int] | None = None) -> None:
        self.admin_query = admin_query
        self.lookback_days = lookback_days or [30, 180, 730, 1460]

    def resolve(self, tax_no: str, ydz_api: YdzApi) -> BackendSource:
        row = self._latest_backend_row(tax_no)
        if not row:
            raise AccountSetError("No successful backend task with login info was found.")
        area_code, area_name = ydz_api.query_tax_geo(tax_no)
        backend_area_name = str(row.get("taxAreaName") or row.get("areaName") or "")
        if not area_code:
            area_code = fallback_area_code(backend_area_name, tax_no)
        if not area_name:
            area_name = backend_area_name
        login_json = normalize_login_json(row.get("loginJson"))
        login_method = backend_row_login_method(row)
        source = BackendSource(
            tax_no=tax_no,
            name=strip_operator_prefix(str(row.get("orgName") or row.get("enterpriseName") or row.get("taxName") or "")),
            area_code=area_code,
            area_name=area_name,
            login_method=login_method,
            proxy_tax_no=str(login_json.get("cSiteLoginName") or ""),
            privacy_no=str(login_json.get("cTaxPreparerName") or ""),
            password=str(login_json.get("cTaxPreparerPwd") or ""),
            backend_task_id=str(row.get("id") or ""),
        )
        self._validate_source(source)
        return source

    def _latest_backend_row(self, tax_no: str) -> dict[str, Any] | None:
        now = datetime.now()
        for days in self.lookback_days:
            for start_time, end_time in self._iter_backend_query_windows(now, days):
                tasks = self.admin_query.query_tasks(
                    start_time=start_time,
                    end_time=end_time,
                    tax_no=tax_no,
                    task_status="SUCCESS",
                    page_size=20,
                )
                candidates = [task for task in tasks if backend_row_has_supported_login(task)]
                if candidates:
                    return sorted(candidates, key=lambda item: int(item.get("createdStamp") or 0), reverse=True)[0]
        return None

    def _iter_backend_query_windows(self, now: datetime, days: int) -> Iterable[tuple[datetime, datetime]]:
        total_days = max(int(days or 0), 1)
        covered_days = 0
        while covered_days < total_days:
            span_days = min(MAX_BACKEND_QUERY_WINDOW_DAYS, total_days - covered_days)
            start_time = now - timedelta(days=covered_days + span_days)
            end_time = now + timedelta(minutes=5) if covered_days == 0 else now - timedelta(days=covered_days)
            yield start_time, end_time
            covered_days += span_days

    def _validate_source(self, source: BackendSource) -> None:
        missing = []
        if not source.name:
            missing.append("name")
        if not source.area_code:
            missing.append("areaCode")
        if not source.login_method:
            missing.append("loginMethod")
        if source.login_method and source.login_method not in SUPPORTED_LOGIN_METHODS:
            missing.append("supportedLoginMethod")
        if source.login_method in PRIVACY_LOGIN_METHODS and not source.privacy_no:
            missing.append("privacyNo")
        if source.login_method in MANUAL_CAPTCHA_LOGIN_METHODS and not source.privacy_no:
            missing.append("phone")
        if login_method_requires_password(source.login_method) and not source.password:
            missing.append("password")
        if source.login_method.startswith(PROXY_LOGIN_PREFIX) and not source.proxy_tax_no:
            missing.append("proxyTaxNo")
        if missing:
            raise AccountSetError("Backend source is incomplete: " + ", ".join(missing))


class Creator:
    def __init__(
        self,
        ydz_api: YdzApi,
        resolver: SourceResolver,
        env: YdzEnvironment,
        defaults: YdzDefaults,
        privacy_phone_bridge: PrivacyPhoneBridge | None = None,
        prepare_privacy_phone: bool = True,
        login_account: str | None = None,
    ) -> None:
        self.ydz_api = ydz_api
        self.resolver = resolver
        self.env = env
        self.defaults = defaults
        self.privacy_phone_bridge = privacy_phone_bridge
        self.prepare_privacy_phone = prepare_privacy_phone
        self.login_account = login_account or ""

    def process_tax_no(self, tax_no: str, dry_run: bool = False) -> CreateResult:
        result: CreateResult | None = None
        try:
            source = self.resolver.resolve(tax_no, self.ydz_api)
            result = CreateResult(
                tax_no=tax_no,
                status="DRY_RUN" if dry_run else "PENDING",
                name=source.name,
                area_code=source.area_code,
                area_name=source.area_name,
                login_method=source.login_method,
                has_password=bool(source.password),
                backend_task_id=source.backend_task_id,
            )
            accountant = self.ydz_api.resolve_assigned_accountant(self.login_account)
            result.accountant_id = accountant.employee_id
            result.accountant_name = accountant.name
            result.accountant_mobile = accountant.mobile
            result.accountant_source = accountant.source
            privacy_prepare = self._prepare_privacy_phone(source, dry_run=dry_run)
            if privacy_prepare is not None:
                result.privacy_phone_status = privacy_prepare.status
                result.privacy_phone_message = self._privacy_prepare_message(privacy_prepare)
                if not privacy_prepare.ok:
                    raise AccountSetError(result.privacy_phone_message)
            existing = self.ydz_api.query_existing_customer(tax_no)
            if dry_run:
                result.action = "existing" if existing else "would_create"
                if existing:
                    result.cust_id = existing.cust_id
                    result.assoc_tenant_id = existing.assoc_tenant_id
                return result
            customer = existing
            if customer is None:
                customer = self.ydz_api.create_customer(source, self.defaults, accountant=accountant)
                result.action = "created"
            else:
                result.action = "existing"
            result.cust_id = customer.cust_id
            result.assoc_tenant_id = customer.assoc_tenant_id
            result.save_ok = api_success(self.ydz_api.save_tax_info(source, customer))
            customer_info = extract_customer_info(self.ydz_api.query_customer(customer.cust_id), tax_no=tax_no)
            tax_info = extract_tax_info(self.ydz_api.query_tax_info(customer.cust_id))
            result.customer_verify_ok = verify_customer_info(
                customer_info,
                source,
                self.env,
                self.defaults,
                accountant_employee_id=accountant.employee_id,
            )
            result.tax_info_verify_ok = verify_tax_info(source, tax_info)
            result.verify_ok = result.customer_verify_ok and result.tax_info_verify_ok
            result.status = "OK" if result.verify_ok else "PARTIAL"
            if not result.customer_verify_ok:
                result.errors.append("customer fields did not match expected defaults")
            if not result.tax_info_verify_ok:
                result.errors.append("dynamic tax info did not match backend source")
            return result
        except Exception as exc:
            if result is None:
                return CreateResult(tax_no=tax_no, status="FAILED", errors=[str(exc)])
            result.status = "FAILED"
            result.errors.append(str(exc))
            return result

    def _prepare_privacy_phone(self, source: BackendSource, dry_run: bool = False) -> PrivacyPhonePrepareResult | None:
        if not self.prepare_privacy_phone:
            return None
        if self.env.name != "inte" or source.login_method not in PRIVACY_LOGIN_METHODS or not source.privacy_no:
            return None
        if self.privacy_phone_bridge is None:
            raise AccountSetError("Integration privacy phone bridge is not configured.")
        return self.privacy_phone_bridge.ensure_integration_private_phone(source.privacy_no, dry_run=dry_run)

    def _privacy_prepare_message(self, prepare: PrivacyPhonePrepareResult) -> str:
        if prepare.status in {"EXISTS", "DRY_RUN_EXISTS"}:
            return f"integration privacy phone exists: count={prepare.inte_summary_count}"
        if prepare.status == "DRY_RUN_MISSING":
            return "integration privacy phone is missing; online sync and integration pull would be required"
        if prepare.status == "PULLED":
            return "integration privacy phone was pulled after online sync"
        return "; ".join(prepare.errors) or prepare.pull_message or prepare.copy_message or prepare.status


def find_ydz_page(context: Any, env: YdzEnvironment) -> Any | None:
    for page in context.pages:
        if page.is_closed():
            continue
        if env.cloud_marker in page.url and "/work.html" in page.url:
            return page
    return None


def wait_for_ydz_page(context: Any, env: YdzEnvironment, timeout: int) -> Any | None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        page = find_ydz_page(context, env)
        if page is not None:
            try:
                YdzApi(page, env).context()
                return page
            except AccountSetError:
                pass
            except Exception as exc:
                if not is_transient_page_error(exc):
                    raise
        time.sleep(1)
    return None


def ensure_pages_open(context: Any, env: YdzEnvironment, ydz_work_url: str | None, include_backend: bool = True) -> None:
    if find_ydz_page(context, env) is None:
        page = context.new_page()
        page.goto(ydz_work_url or env.default_work_url or env.public_url, wait_until="domcontentloaded", timeout=60_000)
    if not include_backend:
        return
    if not any(PUBLIC_MANAGE_MARKER in page.url for page in context.pages if not page.is_closed()):
        page = context.new_page()
        page.goto(PUBLIC_MANAGE_URL, wait_until="domcontentloaded", timeout=60_000)


def wait_for_backend_session(context: Any, timeout: int) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        for page in context.pages:
            if page.is_closed() or PUBLIC_MANAGE_MARKER not in page.url:
                continue
            if backend_page_forbidden(page):
                continue
            try:
                tokens = page.evaluate(
                    """() => ({
                        authorization:
                            sessionStorage.getItem('Authorization') ||
                            localStorage.getItem('Authorization') ||
                            sessionStorage.getItem('authorization') ||
                            localStorage.getItem('authorization') || '',
                        token:
                            sessionStorage.getItem('access_token') ||
                            localStorage.getItem('access_token') ||
                            sessionStorage.getItem('token') ||
                            localStorage.getItem('token') || ''
                    })"""
                )
            except Exception:
                continue
            if tokens.get("authorization") and tokens.get("token"):
                return True
        time.sleep(1)
    return False


def backend_page_forbidden(page: Any) -> bool:
    try:
        text = page.evaluate("() => String(document.body && document.body.innerText || '')")
    except Exception:
        return False
    lower_text = text.lower()
    forbidden_markers = (
        "\u65e0\u6743",
        "\u65e0\u6743\u8bbf\u95ee",
        "\u6ca1\u6709\u6743\u9650",
        "\u7121\u6b0a",
        "\u7121\u6b0a\u8a2a\u554f",
        "forbidden",
        "鏃犳潈",
    )
    if ("403" in text or "forbidden" in lower_text) and any(
        marker in text or marker in lower_text for marker in forbidden_markers
    ):
        return True
    return "403" in text and ("无权访问" in text or "無權訪問" in text)


def clear_page_storage(page: Any) -> None:
    try:
        page.evaluate("() => { try { localStorage.clear(); } catch(e) {} try { sessionStorage.clear(); } catch(e) {} }")
    except Exception:
        pass


def env_prefix(env_name: str) -> str:
    return "YDZ_INTE" if env_name == "inte" else "YDZ_PROD"


def backend_login_url(callback_url: str | None = None) -> str:
    callback = urllib.parse.quote(callback_url or PUBLIC_MANAGE_URL, safe="")
    return f"https://login.chanjet.com/?callback={callback}"


def ydz_login_url(env: YdzEnvironment) -> str:
    callback = urllib.parse.quote(env.public_url, safe="")
    if env.name == "inte":
        return f"https://ydz-login.inte.chanjet.com/?callback={callback}"
    return f"https://login.chanjet.com/?callback={callback}"


def configured_ydz_credentials(env: YdzEnvironment) -> dict[str, str]:
    prefix = env_prefix(env.name)
    return {
        "url": os.environ.get(f"{prefix}_URL") or env.public_url,
        "workUrl": os.environ.get(f"{prefix}_WORK_URL") or env.default_work_url,
        "username": os.environ.get(f"{prefix}_USERNAME") or "",
        "password": os.environ.get(f"{prefix}_PASSWORD") or "",
        "enterprise": os.environ.get(f"{prefix}_ENTERPRISE") or DEFAULT_ENTERPRISE_HINTS.get(env.name, ""),
    }


def first_env_value(*keys: str) -> str:
    for key in keys:
        value = os.environ.get(key)
        if value:
            return value
    return ""


def configured_ydz_login_captcha(env: YdzEnvironment) -> str:
    prefix = env_prefix(env.name)
    explicit = first_env_value(
        f"{prefix}_LOGIN_CAPTCHA",
        f"{prefix}_CAPTCHA",
        f"{prefix}_VERIFY_CODE",
        "YDZ_LOGIN_CAPTCHA",
        "YDZ_CAPTCHA",
        "YDZ_VERIFY_CODE",
    )
    if explicit:
        return explicit
    return "666666" if env.name == "inte" else ""


def resolved_ydz_auth_mode(args: argparse.Namespace) -> str:
    return str(getattr(args, "ydz_auth_mode", None) or os.environ.get("YDZ_AUTH_MODE") or "auto").strip().lower()


def resolved_backend_auth_mode(args: argparse.Namespace) -> str:
    return str(getattr(args, "backend_auth_mode", None) or os.environ.get("TAX_BACKEND_AUTH_MODE") or "auto").strip().lower()


def configured_ydz_token_context(env: YdzEnvironment, ydz_work_url: str | None = None) -> dict[str, str] | None:
    prefix = env_prefix(env.name)
    iframe_token = first_env_value(f"{prefix}_IFRAME_TOKEN", "YDZ_IFRAME_TOKEN")
    cia_token = first_env_value(f"{prefix}_CIA_TOKEN", "YDZ_CIA_TOKEN")
    if not iframe_token or not cia_token:
        return None
    return build_ydz_auth_context(
        env,
        iframe_token=iframe_token,
        cia_token=cia_token,
        work_url=ydz_work_url or first_env_value(f"{prefix}_WORK_URL", "YDZ_WORK_URL") or env.default_work_url,
        org_id=first_env_value(f"{prefix}_ORG_ID", "YDZ_ORG_ID") or env.org_id,
        user_id=first_env_value(f"{prefix}_USER_ID", "YDZ_USER_ID") or env.user_id,
        org_name=first_env_value(f"{prefix}_ORG_NAME", "YDZ_ORG_NAME"),
        user_mobile=first_env_value(f"{prefix}_USER_MOBILE", f"{prefix}_MOBILE", "YDZ_USER_MOBILE", "YDZ_MOBILE"),
        user_name=first_env_value(f"{prefix}_USER_NAME", "YDZ_USER_NAME"),
    ).as_api_dict()


@dataclass
class PasswordLoginResult:
    env: str
    status: str
    message: str = ""
    error_code: str = ""
    sso_ready: bool = False
    has_ticket: bool = False
    auth_context: YdzAuthContext | None = None
    raw_keys: list[str] = field(default_factory=list)

    def public_dict(self) -> dict[str, Any]:
        return {
            "env": self.env,
            "status": self.status,
            "message": self.message,
            "errorCode": self.error_code,
            "ssoReady": self.sso_ready,
            "hasTicket": self.has_ticket,
            "hasAuthContext": self.auth_context is not None,
            "rawKeys": list(self.raw_keys),
        }


def chanjet_rsa_encrypt(value: str) -> str:
    message = str(value or "").encode("utf-8")
    modulus = int(CHANJET_LOGIN_RSA_MODULUS, 16)
    key_len = (modulus.bit_length() + 7) // 8
    if len(message) > key_len - 11:
        raise ValueError("Chanjet login value is too long for RSA encryption.")
    padding_len = key_len - len(message) - 3
    padding = bytearray()
    while len(padding) < padding_len:
        chunk = secrets.token_bytes(padding_len - len(padding))
        padding.extend(byte for byte in chunk if byte != 0)
    encoded = b"\x00\x02" + bytes(padding[:padding_len]) + b"\x00" + message
    encrypted = pow(int.from_bytes(encoded, "big"), CHANJET_LOGIN_RSA_EXPONENT, modulus)
    return base64.b64encode(encrypted.to_bytes(key_len, "big")).decode("ascii")


def parse_json_or_jsonp(text: str) -> dict[str, Any]:
    stripped = str(text or "").strip()
    if not stripped:
        return {}
    if stripped.startswith("{"):
        return json.loads(stripped)
    match = re.match(r"^[^(]+\((.*)\);?$", stripped, flags=re.S)
    if not match:
        raise ValueError("Response is neither JSON nor JSONP.")
    return json.loads(match.group(1))


class ChanjetPasswordAuthClient:
    """Best-effort direct Chanjet account-password login.

    This submits the normal login endpoints and reports slider, SMS, phone
    binding, and password-change blockers. It does not solve or bypass CAPTCHA.
    """

    def __init__(self, env: YdzEnvironment, session: Any | None = None, timeout: int = 30) -> None:
        import requests

        self.env = env
        self.session = session or requests.Session()
        self.timeout = timeout

    def login(
        self,
        username: str,
        password: str,
        *,
        work_url: str | None = None,
        verify_token: str | None = None,
        captcha_code: str | None = None,
    ) -> PasswordLoginResult:
        if not username or not password:
            return PasswordLoginResult(
                env=self.env.name,
                status=PASSWORD_LOGIN_FAILED,
                message="Yidaizhang username/password is not configured.",
            )
        try:
            self._open_login_page()
            auth_code = self._get_auth_code()
            effective_verify_token = verify_token or ""
            if not effective_verify_token and captcha_code:
                verify_response = self._account_verify(username, password, captcha_code)
                if not verify_response.get("result"):
                    return self._classify_login_response(verify_response, work_url=work_url)
                effective_verify_token = str(verify_response.get("verifyToken") or "").strip()
                if not effective_verify_token:
                    return PasswordLoginResult(
                        env=self.env.name,
                        status=PASSWORD_LOGIN_FAILED,
                        message="Yidaizhang captcha verification did not return a verifyToken.",
                        raw_keys=sorted(str(key) for key in verify_response.keys()),
                    )
            response = self._account_login(username, password, auth_code, effective_verify_token)
        except Exception as exc:
            LOGGER.debug("Direct Yidaizhang password login failed before response classification.", exc_info=True)
            return PasswordLoginResult(
                env=self.env.name,
                status=PASSWORD_LOGIN_FAILED,
                message=f"Direct password login request failed: {exc}",
            )
        return self._classify_login_response(response, work_url=work_url)

    def _classify_login_response(self, response: dict[str, Any], *, work_url: str | None) -> PasswordLoginResult:
        raw_keys = sorted(str(key) for key in response.keys())
        if response.get("result") is True:
            ticket_response = self._try_get_ticket()
            auth_context = self._try_extract_token_context(work_url or self.env.default_work_url)
            if auth_context is not None:
                return PasswordLoginResult(
                    env=self.env.name,
                    status=PASSWORD_LOGIN_TOKEN_READY,
                    message="Direct password login produced a Yidaizhang API token context.",
                    sso_ready=True,
                    has_ticket=bool(ticket_response),
                    auth_context=auth_context,
                    raw_keys=raw_keys,
                )
            return PasswordLoginResult(
                env=self.env.name,
                status=PASSWORD_LOGIN_SSO_READY_TOKEN_UNAVAILABLE,
                message=(
                    "Chanjet SSO login succeeded, but Yidaizhang business tokens were not exposed "
                    "through HTTP responses. Use browser mode to let work.html initialize tokens, "
                    "or provide token mode variables."
                ),
                sso_ready=True,
                has_ticket=bool(ticket_response),
                raw_keys=raw_keys,
            )

        error_code = str(response.get("errorCode") or (response.get("error") or {}).get("code") or "")
        message = str(
            response.get("errorMessage")
            or response.get("msg")
            or (response.get("error") or {}).get("msg")
            or error_code
            or "Direct password login did not succeed."
        )
        if error_code in CHALLENGE_ERROR_CODES or response.get("captchaResult") is False:
            return PasswordLoginResult(
                env=self.env.name,
                status=PASSWORD_LOGIN_MANUAL_VERIFICATION_REQUIRED,
                message=message or "Yidaizhang password login requires manual verification.",
                error_code=error_code,
                raw_keys=raw_keys,
            )
        if error_code in PASSWORD_CHANGE_ERROR_CODES:
            return PasswordLoginResult(
                env=self.env.name,
                status=PASSWORD_LOGIN_PASSWORD_CHANGE_REQUIRED,
                message=message,
                error_code=error_code,
                raw_keys=raw_keys,
            )
        if error_code in BIND_PHONE_ERROR_CODES:
            return PasswordLoginResult(
                env=self.env.name,
                status=PASSWORD_LOGIN_BIND_PHONE_REQUIRED,
                message=message,
                error_code=error_code,
                raw_keys=raw_keys,
            )
        return PasswordLoginResult(
            env=self.env.name,
            status=PASSWORD_LOGIN_FAILED,
            message=message,
            error_code=error_code,
            raw_keys=raw_keys,
        )

    def _open_login_page(self) -> None:
        self.session.get(self.login_page_url, headers=self._headers(content_type=False), timeout=self.timeout)

    def _get_auth_code(self) -> str:
        callback = f"jsonp_{int(time.time() * 1000)}_{secrets.randbelow(900) + 100}"
        response = self.session.get(
            f"{self.cia_base_url}/internal_api/getAuthCodeByJsonp",
            params={"client_id": CHANJET_LOGIN_CLIENT_ID, "callback": callback},
            headers=self._headers(content_type=False),
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = parse_json_or_jsonp(response.text)
        auth_code = str(data.get("auth_code") or data.get("code") or "")
        if not auth_code:
            raise RuntimeError("Chanjet CIA auth_code was not returned.")
        return auth_code

    def _account_login(self, username: str, password: str, auth_code: str, verify_token: str) -> dict[str, Any]:
        payload = {
            "auth_username": chanjet_rsa_encrypt(username),
            "passwordEncrypted": chanjet_rsa_encrypt(password),
            "auth_code": auth_code,
            "verifyToken": verify_token,
            "jsonp": "0",
        }
        response = self.session.post(
            f"{self.api_base_url}/loginV2/accountLogin",
            data=payload,
            headers=self._headers(content_type=True),
            timeout=self.timeout,
        )
        response.raise_for_status()
        return parse_json_or_jsonp(response.text)

    def _account_verify(self, username: str, password: str, captcha_code: str) -> dict[str, Any]:
        payload = {
            "authUsername": chanjet_rsa_encrypt(username),
            "passwordEncrypted": chanjet_rsa_encrypt(password),
            "captcha": str(captcha_code or "").strip(),
        }
        response = self.session.post(
            f"{self.api_base_url}/loginV2/accountVerify",
            data=payload,
            headers=self._headers(content_type=True),
            timeout=self.timeout,
        )
        response.raise_for_status()
        return parse_json_or_jsonp(response.text)

    def _try_get_ticket(self) -> dict[str, Any] | None:
        try:
            response = self.session.post(
                f"{self.api_base_url}/loginV2/getTicket",
                headers=self._headers(content_type=True),
                timeout=self.timeout,
            )
            response.raise_for_status()
            return parse_json_or_jsonp(response.text)
        except Exception:
            LOGGER.debug("Direct password login could not read getTicket.", exc_info=True)
            return None

    def _try_extract_token_context(self, work_url: str) -> YdzAuthContext | None:
        try:
            response = self.session.get(work_url, headers=self._headers(content_type=False), timeout=self.timeout)
            response.raise_for_status()
        except Exception:
            LOGGER.debug("Direct password login could not fetch Yidaizhang work URL.", exc_info=True)
            return None
        text = response.text or ""
        iframe_token = self._extract_token_string(text, "iframeToken")
        cia_token = self._extract_token_string(text, "ciaToken")
        if not iframe_token or not cia_token:
            return None
        try:
            return build_ydz_auth_context(self.env, iframe_token=iframe_token, cia_token=cia_token, work_url=work_url)
        except Exception:
            LOGGER.debug("Direct password login found token strings but context validation failed.", exc_info=True)
            return None

    @staticmethod
    def _extract_token_string(text: str, key: str) -> str:
        patterns = (
            rf"{re.escape(key)}['\"]?\s*[:=]\s*['\"]([^'\"]+)['\"]",
            rf"['\"]{re.escape(key)}['\"]\s*,\s*['\"]([^'\"]+)['\"]",
        )
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1).strip()
        return ""

    def _headers(self, *, content_type: bool) -> dict[str, str]:
        headers = {
            "Accept": "application/json, text/plain, */*",
            "User-Agent": "Mozilla/5.0",
            "Referer": self.login_page_url,
            "Domain": urllib.parse.urlparse(self.login_page_url).hostname or "",
            "Chanjet-Client-Language": "zh-CN",
            "Chanjet-Client-TimeZone": "Asia/Shanghai",
        }
        if content_type:
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        return headers

    @property
    def login_page_url(self) -> str:
        callback = urllib.parse.quote(self.env.public_url, safe="")
        if self.env.name == "inte":
            return f"https://ydz-login.inte.chanjet.com/?callback={callback}"
        return f"https://login.chanjet.com/?callback={callback}"

    @property
    def api_base_url(self) -> str:
        if self.env.name == "inte":
            return "https://passport.inte.chanjet.com"
        return "https://login.chanjet.com"

    @property
    def cia_base_url(self) -> str:
        if self.env.name == "inte":
            return "https://inte-cia.chanapp.chanjet.com"
        return "https://cia.chanapp.chanjet.com"


def configured_ydz_password_context(
    env: YdzEnvironment,
    ydz_work_url: str | None = None,
    timeout: int = 30,
) -> tuple[dict[str, str] | None, dict[str, Any]]:
    creds = configured_ydz_credentials(env)
    status: dict[str, Any] = {
        "env": env.name,
        "status": PASSWORD_LOGIN_FAILED,
        "message": "",
        "hasAuthContext": False,
    }
    if not creds["username"] or not creds["password"]:
        status["message"] = "Yidaizhang username/password is not configured."
        return None, status
    prefix = env_prefix(env.name)
    result = ChanjetPasswordAuthClient(env, timeout=timeout).login(
        creds["username"],
        creds["password"],
        work_url=ydz_work_url or creds["workUrl"] or env.default_work_url,
        verify_token=first_env_value(f"{prefix}_VERIFY_TOKEN", "YDZ_VERIFY_TOKEN"),
        captcha_code=configured_ydz_login_captcha(env),
    )
    public = result.public_dict()
    if result.status in {
        PASSWORD_LOGIN_MANUAL_VERIFICATION_REQUIRED,
        PASSWORD_LOGIN_PASSWORD_CHANGE_REQUIRED,
        PASSWORD_LOGIN_BIND_PHONE_REQUIRED,
    }:
        LOGGER.warning(
            "%s ydz env=%s status=%s code=%s message=%s",
            MANUAL_VERIFICATION_REQUIRED_MARKER,
            env.name,
            result.status,
            result.error_code or "-",
            result.message,
        )
    status.update(public)
    return (result.auth_context.as_api_dict() if result.auth_context else None), status


def configured_backend_credentials() -> dict[str, str]:
    return {
        "url": os.environ.get("TAX_BACKEND_URL") or PUBLIC_MANAGE_URL,
        "username": os.environ.get("TAX_BACKEND_USERNAME") or "",
        "password": os.environ.get("TAX_BACKEND_PASSWORD") or "",
    }


def configured_backend_token_provider() -> tuple[StaticAdminAuthProvider | None, dict[str, Any]]:
    authorization = first_env_value("TAX_BACKEND_AUTHORIZATION", "TAX_BACKEND_AUTH")
    access_token = first_env_value("TAX_BACKEND_TOKEN", "TAX_BACKEND_ACCESS_TOKEN")
    user_id = first_env_value("TAX_BACKEND_USER_ID")
    status = {"mode": "token", "status": ADMIN_AUTH_FAILED, "hasTokens": bool(authorization and access_token)}
    if not authorization or not access_token:
        status["message"] = "TAX_BACKEND_AUTHORIZATION and TAX_BACKEND_TOKEN/TAX_BACKEND_ACCESS_TOKEN are not configured."
        return None, status
    provider = StaticAdminAuthProvider(
        AdminAuthTokens(
            authorization=str(authorization).strip(),
            token=str(access_token).strip(),
            user_id=str(user_id or ""),
            source="env_token",
        )
    )
    status.update({"status": ADMIN_AUTH_READY, "message": "Backend token variables are configured.", "hasTokens": True})
    return provider, status


def configured_backend_password_provider(timeout: int = 30) -> tuple[StaticAdminAuthProvider | None, dict[str, Any]]:
    creds = configured_backend_credentials()
    result = ChanjetAdminPasswordAuthClient(
        creds["username"],
        creds["password"],
        public_manage_url=creds["url"] or PUBLIC_MANAGE_URL,
        timeout=timeout,
    ).login()
    status = {"mode": "password", **result.public_dict()}
    if result.status == ADMIN_AUTH_MANUAL_VERIFICATION_REQUIRED:
        LOGGER.warning(
            "%s backend status=%s code=%s message=%s",
            MANUAL_VERIFICATION_REQUIRED_MARKER,
            result.status,
            result.error_code or "-",
            result.message,
        )
    if result.tokens is None:
        return None, status
    return StaticAdminAuthProvider(result.tokens), status


def resolve_backend_token_provider(args: argparse.Namespace) -> tuple[StaticAdminAuthProvider | None, str, dict[str, Any]]:
    mode = resolved_backend_auth_mode(args)
    if mode not in {"auto", "browser", "token", "password"}:
        raise SystemExit("TAX_BACKEND_AUTH_MODE must be auto, browser, token, or password.")
    if mode in {"auto", "token"}:
        provider, status = configured_backend_token_provider()
        if provider is not None or mode == "token":
            return provider, "token" if provider is not None else mode, status
    if mode in {"auto", "password"}:
        provider, status = configured_backend_password_provider(timeout=args.session_timeout)
        if provider is not None or mode == "password":
            return provider, "password" if provider is not None else mode, status
        LOGGER.info(
            "Public-manage password auth did not produce usable tokens; falling back to browser login. status=%s",
            status.get("status"),
        )
    return None, "browser", {"mode": mode, "status": "BROWSER_FALLBACK"}


def visible_text_click(page: Any, text: str, contains: bool = False) -> bool:
    try:
        return bool(
            page.evaluate(
                """({text, contains}) => {
                    const vis = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
                    const norm = value => String(value || '').trim().replace(/\\s+/g, '');
                    const target = norm(text);
                    const nodes = Array.from(document.querySelectorAll('button,a,div,span,label,li')).filter(vis);
                    const hit = nodes.find(el => {
                        const current = norm(el.innerText || el.textContent || '');
                        return contains ? current.includes(target) : current === target;
                    });
                    if (!hit) return false;
                    hit.dispatchEvent(new MouseEvent('mousedown', {bubbles: true}));
                    hit.click();
                    hit.dispatchEvent(new MouseEvent('mouseup', {bubbles: true}));
                    return true;
                }""",
                {"text": text, "contains": contains},
            )
        )
    except Exception:
        return False


def page_body_text(page: Any) -> str:
    try:
        return str(page.evaluate("() => String(document.body && document.body.innerText || '')") or "")
    except Exception:
        return ""


def ydz_login_requires_manual_verification(page: Any) -> bool:
    text = page_body_text(page)
    compact = "".join(text.split())
    return "请按住滑块" in compact or ("滑块" in compact and "登录" in compact)


def log_manual_verification_required(env: YdzEnvironment, reason: str) -> None:
    LOGGER.warning(
        "%s ydz env=%s reason=%s action=complete_slider_in_browser message=Please complete the Yidaizhang slider in Chrome; the script will continue after the workbench session is ready.",
        MANUAL_VERIFICATION_REQUIRED_MARKER,
        env.name,
        reason,
    )


def ydz_public_entry_available(page: Any) -> bool:
    text = page_body_text(page)
    return "进入易代账" in text and ("用户" in text or "登录" not in text)


def click_ydz_public_entry(context: Any, env: YdzEnvironment) -> bool:
    clicked = False
    for page in context.pages:
        if page.is_closed():
            continue
        try:
            if env.public_url not in page.url:
                continue
            if ydz_public_entry_available(page):
                clicked = visible_text_click(page, "进入易代账", contains=True) or clicked
        except Exception:
            continue
    return clicked


def is_ydz_redirect_vm_page(page: Any, env: YdzEnvironment) -> bool:
    try:
        url = str(page.url or "")
    except Exception:
        return False
    return (
        "/vm/redirectVM" in url
        and "passport" in url
        and ("appName=ydzee" in url or "productId=260" in url or env.name == "inte")
    )


def open_ydz_redirect_vm_workbench(context: Any, env: YdzEnvironment, work_url: str) -> bool:
    for page in context.pages:
        if page.is_closed():
            continue
        if not is_ydz_redirect_vm_page(page, env):
            continue
        try:
            page.evaluate(
                """() => {
                    const vis = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
                    const nodes = Array.from(document.querySelectorAll('button,a,[role=button],.ant-btn,.btn')).filter(vis);
                    const target = nodes.find(el => !/cancel|close|back/i.test(String(el.innerText || el.textContent || el.className || '')))
                        || nodes[0];
                    if (!target) return false;
                    target.dispatchEvent(new MouseEvent('mousedown', {bubbles: true}));
                    target.click();
                    target.dispatchEvent(new MouseEvent('mouseup', {bubbles: true}));
                    return true;
                }"""
            )
            page.wait_for_timeout(1500)
            if wait_for_ydz_page(context, env, timeout=3) is not None:
                return True
        except Exception:
            pass
        try:
            page.goto(work_url, wait_until="domcontentloaded", timeout=60_000)
            return True
        except Exception:
            return False
    return False


def has_visible_login_form(page: Any) -> bool:
    try:
        return bool(
            page.evaluate(
                """() => {
                    const vis = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
                    const inputs = Array.from(document.querySelectorAll('input')).filter(vis);
                    return inputs.some(el => el.type === 'password' || (el.placeholder || '').includes('密码'))
                        && inputs.some(el => (el.placeholder || '').includes('账号') || (el.placeholder || '').includes('手机') || el.type === 'text');
                }"""
            )
        )
    except Exception:
        return False


def fill_chanjet_login_form(page: Any, username: str, password: str, captcha_code: str = "") -> bool:
    if not username or not password:
        return False
    try:
        return bool(
            page.evaluate(
                """({username, password, captchaCode}) => {
                    const vis = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
                    const setValue = (el, value) => {
                        const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
                        setter.call(el, value);
                        el.dispatchEvent(new Event('input', {bubbles: true, composed: true}));
                        el.dispatchEvent(new Event('change', {bubbles: true, composed: true}));
                        el.dispatchEvent(new KeyboardEvent('keyup', {bubbles: true, composed: true, key: '1'}));
                        el.blur();
                    };
                    const roots = Array.from(document.querySelectorAll('.login-wrapper, .login-main, .account-wrapper, body')).filter(vis);
                    const root = roots.find(el => (el.innerText || el.textContent || '').includes('账号密码登录')) || roots[0] || document;
                    const inputs = Array.from(root.querySelectorAll('input')).filter(vis);
                    const userInput = inputs.find(el => (el.placeholder || '').includes('账号'))
                        || inputs.find(el => (el.placeholder || '').includes('手机'))
                        || inputs.find(el => el.type === 'text')
                        || inputs[0];
                    const passInput = inputs.find(el => el.type === 'password')
                        || inputs.find(el => (el.placeholder || '').includes('密码'));
                    if (!userInput || !passInput) return false;
                    setValue(userInput, username);
                    setValue(passInput, password);
                    const captchaInput = inputs.find(el => {
                        if (el === userInput || el === passInput) return false;
                        const text = `${el.placeholder || ''} ${el.name || ''} ${el.id || ''} ${el.className || ''}`.toLowerCase();
                        return text.includes('captcha')
                            || text.includes('verify')
                            || text.includes('valid')
                            || text.includes('code')
                            || text.includes('\u9a8c\u8bc1\u7801')
                            || text.includes('\u6821\u9a8c\u7801');
                    }) || inputs.find(el => captchaCode && el !== userInput && el !== passInput && el.type !== 'password');
                    if (captchaInput && captchaCode) setValue(captchaInput, captchaCode);
                    for (const cb of Array.from(document.querySelectorAll('input[type=checkbox]')).filter(vis)) {
                        if (!cb.checked) cb.click();
                    }
                    const agree = Array.from(document.querySelectorAll('.login-common-checkbox, .check-box-wrapper, .check-box, .check-box-border'))
                        .find(el => vis(el));
                    const activeBox = document.querySelector('.check-box.active');
                    if (agree && !activeBox) agree.click();
                    const buttons = Array.from(document.querySelectorAll('button')).filter(vis);
                    const submit = buttons.find(el => String(el.className || '').includes('login-button'))
                        || buttons.find(el => String(el.innerText || el.textContent || '').trim().replace(/\\s+/g, '') === '登录');
                    if (!submit) return false;
                    submit.dispatchEvent(new MouseEvent('mousedown', {bubbles: true}));
                    submit.click();
                    submit.dispatchEvent(new MouseEvent('mouseup', {bubbles: true}));
                    return true;
                }""",
                {"username": username, "password": password, "captchaCode": captcha_code},
            )
        )
    except Exception:
        return False


def submit_chanjet_login_form(page: Any) -> bool:
    try:
        return bool(
            page.evaluate(
                """() => {
                    const vis = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
                    const buttons = Array.from(document.querySelectorAll('button')).filter(vis);
                    const submit = buttons.find(el => String(el.className || '').includes('login-button'))
                        || buttons.find(el => String(el.innerText || el.textContent || '').trim().replace(/\\s+/g, '') === '登录');
                    if (!submit) return false;
                    submit.focus();
                    submit.dispatchEvent(new MouseEvent('mousedown', {bubbles: true}));
                    submit.click();
                    submit.dispatchEvent(new MouseEvent('mouseup', {bubbles: true}));
                    return true;
                }"""
            )
        )
    except Exception:
        return False


def find_page_by_url(context: Any, markers: Iterable[str]) -> Any | None:
    marker_list = list(markers)
    for page in context.pages:
        if page.is_closed():
            continue
        try:
            if any(marker in page.url for marker in marker_list):
                return page
        except Exception:
            continue
    return None


def workbench_app_list_url(env: YdzEnvironment) -> str:
    query = urllib.parse.urlencode({"orgId": str(env.org_id or "")})
    return f"{WORKBENCH_APP_LIST_URL}?{query}"


def click_workbench_ydz_entry(page: Any) -> bool:
    try:
        result = page.evaluate(
            r"""() => {
                const ydzText = '\u6613\u4ee3\u8d26';
                const enterText = '\u8fdb\u5165\u5e94\u7528';
                const blocked = [
                    '\u5c0f\u7545e\u7968',
                    '\u5e93\u5b58',
                    '\u4e00\u952e\u62a5\u7a0e',
                    '\u4e2a\u7a0e',
                    '\u4f01\u5fae'
                ];
                const vis = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
                const clean = value => String(value || '').replace(/\s+/g, '').trim();
                const nodes = Array.from(document.querySelectorAll('tr,.app-item,.app-card,li,div')).filter(vis);
                const scored = nodes.map(el => {
                    const text = clean(el.innerText || el.textContent || '');
                    if (!text.includes(ydzText) || !text.includes(enterText)) return null;
                    if (blocked.some(token => text.includes(token))) return null;
                    let score = 0;
                    if (text.startsWith(ydzText)) score += 12;
                    if (text.includes(ydzText + '\u67e5\u770b\u8be6\u60c5')) score += 16;
                    if (text.includes('\u7528\u6237\u5217\u8868')) score += 3;
                    if (text.length <= 140) score += 5;
                    score -= Math.min(20, Math.floor(text.length / 80));
                    return {el, text, score};
                }).filter(Boolean).sort((a, b) => b.score - a.score || a.text.length - b.text.length);
                const row = scored[0];
                if (!row) return {clicked: false, reason: 'app_entry_not_found'};
                const controls = Array.from(row.el.querySelectorAll('button,a,span,div')).filter(vis);
                const hit = controls.find(el => clean(el.innerText || el.textContent || '') === enterText)
                    || controls.find(el => clean(el.innerText || el.textContent || '').includes(enterText));
                if (!hit) return {clicked: false, reason: 'enter_button_not_found', text: row.text};
                hit.dispatchEvent(new MouseEvent('mousedown', {bubbles: true}));
                hit.click();
                hit.dispatchEvent(new MouseEvent('mouseup', {bubbles: true}));
                return {clicked: true, text: row.text};
            }"""
        )
        if isinstance(result, dict):
            if result.get("clicked"):
                text = str(result.get("text") or "")
                LOGGER.info("Clicked Yidaizhang app entry from workbench%s.", f": {text[:80]}" if text else "")
                return True
            LOGGER.debug("Workbench Yidaizhang app entry was not clicked: %s", result)
            return False
        return bool(result)
    except Exception as exc:
        LOGGER.debug("Could not click Yidaizhang app entry from workbench: %s", exc)
        return False


def open_ydz_from_workbench_app_list(context: Any, env: YdzEnvironment, timeout: int) -> Any | None:
    page = find_page_by_url(context, ["workbench.chanjet.com"]) or context.new_page()
    try:
        page.goto(workbench_app_list_url(env), wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(3000)
        if not click_workbench_ydz_entry(page):
            return None
    except Exception as exc:
        LOGGER.debug("Could not open Yidaizhang from workbench app list: %s", exc)
        return None
    return wait_for_ydz_page(context, env, timeout=max(3, min(timeout, 30)))


def wait_for_ydz_or_direct_work(context: Any, env: YdzEnvironment, work_url: str, timeout: int) -> Any | None:
    deadline = time.time() + timeout
    last_direct_open = 0.0
    while time.time() < deadline:
        page = wait_for_ydz_page(context, env, timeout=2)
        if page is not None:
            return page
        now = time.time()
        if now - last_direct_open > 5:
            last_direct_open = now
            try:
                if open_ydz_redirect_vm_workbench(context, env, work_url):
                    time.sleep(1)
                    continue
                if click_ydz_public_entry(context, env):
                    time.sleep(1)
                    continue
                if open_ydz_from_workbench_app_list(context, env, timeout=8) is not None:
                    time.sleep(1)
                    continue
                candidate = find_page_by_url(context, [env.public_url]) or context.new_page()
                candidate.goto(work_url, wait_until="domcontentloaded", timeout=60_000)
            except Exception:
                pass
        time.sleep(1)
    return None


def ensure_ydz_login(context: Any, env: YdzEnvironment, timeout: int, ydz_work_url: str | None = None) -> Any | None:
    ready = wait_for_ydz_page(context, env, timeout=2)
    if ready is not None:
        LOGGER.info("Reusing existing Yidaizhang %s workbench session: %s", env.name, ready.url)
        return ready
    creds = configured_ydz_credentials(env)
    work_url = ydz_work_url or creds["workUrl"] or env.default_work_url
    if not creds["username"] or not creds["password"]:
        LOGGER.info("No configured Yidaizhang %s credentials; waiting for an existing/manual workbench session.", env.name)
        return wait_for_ydz_or_direct_work(context, env, work_url, timeout=timeout)

    LOGGER.info("No reusable Yidaizhang %s session detected; attempting password login.", env.name)
    page = find_page_by_url(context, [env.public_url, "ydz-login", "login.chanjet.com"]) or context.new_page()
    try:
        page.goto(ydz_login_url(env), wait_until="domcontentloaded", timeout=60_000)
    except Exception:
        page.goto(creds["url"], wait_until="domcontentloaded", timeout=60_000)
    page.wait_for_timeout(1000)
    if not has_visible_login_form(page):
        visible_text_click(page, "登录")
        page.wait_for_timeout(1500)
    if not has_visible_login_form(page):
        try:
            page.goto(ydz_login_url(env), wait_until="domcontentloaded", timeout=60_000)
        except Exception:
            pass
        page.wait_for_timeout(1000)
    manual_required = False
    if fill_chanjet_login_form(page, creds["username"], creds["password"], configured_ydz_login_captcha(env)):
        LOGGER.info("Submitted Yidaizhang %s login form.", env.name)
    for attempt in range(3):
        page.wait_for_timeout(3000)
        if not has_visible_login_form(page):
            break
        if ydz_login_requires_manual_verification(page):
            manual_required = True
            log_manual_verification_required(env, "password_login_slider")
            break
        LOGGER.info("Yidaizhang %s login form still visible; retrying submit (%s/3).", env.name, attempt + 1)
        submit_chanjet_login_form(page)
    if creds["enterprise"]:
        visible_text_click(page, creds["enterprise"], contains=True)
        page.wait_for_timeout(1000)
        visible_text_click(page, "确定")
    if find_page_by_url(context, [env.public_url]):
        try:
            public_page = find_page_by_url(context, [env.public_url])
            if public_page is not None:
                visible_text_click(public_page, "进入易代账", contains=True)
                public_page.wait_for_timeout(1000)
        except Exception:
            pass
    # Some integration accounts stop at a real-name-auth notice after selecting the org.
    # Directly opening the work.html URL reuses the new token and reaches the app when allowed.
    result = wait_for_ydz_or_direct_work(context, env, work_url, timeout=timeout)
    if result is not None and manual_required:
        LOGGER.info("Yidaizhang %s workbench session is ready after manual verification.", env.name)
    return result


def ensure_backend_login(context: Any, timeout: int) -> bool:
    if wait_for_backend_session(context, timeout=2):
        return True
    creds = configured_backend_credentials()
    page = find_page_by_url(context, [PUBLIC_MANAGE_MARKER, "login.chanjet.com"]) or context.new_page()
    if backend_page_forbidden(page):
        LOGGER.info("Public-manage page is forbidden for the current account; clearing page storage before login.")
        clear_page_storage(page)
    page.goto(creds["url"] or PUBLIC_MANAGE_URL, wait_until="domcontentloaded", timeout=60_000)
    page.wait_for_timeout(1000)
    if wait_for_backend_session(context, timeout=2):
        return True
    visible_text_click(page, "去登录")
    page.wait_for_timeout(3000)
    login_page = find_page_by_url(context, ["login.chanjet.com"]) or page
    if not creds["username"] or not creds["password"]:
        return wait_for_backend_session(context, timeout=timeout)
    if not has_visible_login_form(login_page):
        login_page = context.new_page()
        login_page.goto(backend_login_url(creds["url"] or PUBLIC_MANAGE_URL), wait_until="domcontentloaded", timeout=60_000)
        login_page.wait_for_timeout(1000)
    fill_chanjet_login_form(login_page, creds["username"], creds["password"])
    for attempt in range(3):
        login_page.wait_for_timeout(3000)
        if wait_for_backend_session(context, timeout=2):
            return True
        if not has_visible_login_form(login_page):
            break
        LOGGER.info("Public-manage login form still visible; retrying submit (%s/3).", attempt + 1)
        submit_chanjet_login_form(login_page)
    return wait_for_backend_session(context, timeout=timeout)


def ensure_login_sessions(context: Any, env: YdzEnvironment, args: argparse.Namespace) -> tuple[Any | None, bool]:
    ydz_page = ensure_ydz_login(context, env, timeout=args.session_timeout, ydz_work_url=args.ydz_work_url)
    backend_ready = ensure_backend_login(context, timeout=args.session_timeout)
    if ydz_page is None:
        work_url = args.ydz_work_url or configured_ydz_credentials(env)["workUrl"] or env.default_work_url
        ydz_page = wait_for_ydz_or_direct_work(context, env, work_url, timeout=min(args.session_timeout, 60))
    return ydz_page, backend_ready


def env_secret_status(env_name: str) -> dict[str, bool]:
    prefix = "YDZ_INTE" if env_name == "inte" else "YDZ_PROD"
    keys = [
        f"{prefix}_URL",
        f"{prefix}_USERNAME",
        f"{prefix}_PASSWORD",
        f"{prefix}_ENTERPRISE",
        "TAX_BACKEND_URL",
        "TAX_BACKEND_USERNAME",
        "TAX_BACKEND_PASSWORD",
    ]
    return {key: bool(os.environ.get(key)) for key in keys}


def apply_env_overrides(env: YdzEnvironment, args: argparse.Namespace) -> YdzEnvironment:
    prefix = "YDZ_INTE" if env.name == "inte" else "YDZ_PROD"
    default_work_url = args.ydz_work_url or os.environ.get(f"{prefix}_WORK_URL") or env.default_work_url
    return replace(
        env,
        default_work_url=default_work_url,
        org_id=args.org_id or env.org_id,
        user_id=args.user_id or env.user_id,
        accountant_id=args.accountant_id or env.accountant_id,
        accountant_name=args.accountant_name or env.accountant_name,
    )


def build_defaults(args: argparse.Namespace) -> YdzDefaults:
    return YdzDefaults(
        opening_period=args.opening_period or DEFAULT_OPENING_PERIOD,
        taxpayer_type=args.taxpayer_type or DEFAULT_TAXPAYER_TYPE,
        tax_industry_id=args.industry_id or DEFAULT_TAX_INDUSTRY_ID,
    )


def read_tax_numbers(args: argparse.Namespace) -> list[str]:
    values = list(args.tax_no or [])
    if getattr(args, "manual_source_env", False):
        values.append(os.environ.get("YDZ_MANUAL_TAX_NO") or "")
    if args.tax_no_file:
        values.append(Path(args.tax_no_file).read_text(encoding="utf-8-sig"))
    tax_numbers = split_tax_numbers(values)
    if not tax_numbers:
        raise SystemExit("No tax numbers were provided. Use --tax-no or --tax-no-file.")
    return tax_numbers


def manual_source_from_env() -> BackendSource:
    return BackendSource(
        tax_no=str(os.environ.get("YDZ_MANUAL_TAX_NO") or "").strip().upper(),
        name=str(os.environ.get("YDZ_MANUAL_CUSTOMER_NAME") or "").strip(),
        area_code=str(os.environ.get("YDZ_MANUAL_AREA_CODE") or "").strip(),
        area_name=str(os.environ.get("YDZ_MANUAL_AREA_NAME") or "").strip(),
        login_method=str(os.environ.get("YDZ_MANUAL_LOGIN_METHOD") or "").strip(),
        proxy_tax_no=str(os.environ.get("YDZ_MANUAL_PROXY_TAX_NO") or "").strip(),
        privacy_no=str(os.environ.get("YDZ_MANUAL_PRIVACY_NO") or "").strip(),
        password=str(os.environ.get("YDZ_MANUAL_PASSWORD") or ""),
        backend_task_id="manual",
    )


class ManualSourceResolver:
    def __init__(self, source: BackendSource) -> None:
        self.source = source

    def resolve(self, tax_no: str, ydz_api: YdzApi) -> BackendSource:
        source = self.source
        if source.tax_no and source.tax_no != tax_no:
            raise AccountSetError(f"Manual source tax number mismatch: source={source.tax_no} requested={tax_no}.")
        if not source.tax_no:
            source = replace(source, tax_no=tax_no)
        if not source.area_code or not source.area_name:
            area_code, area_name = ydz_api.query_tax_geo(tax_no)
            source = replace(
                source,
                area_code=source.area_code or area_code or fallback_area_code(source.area_name, tax_no),
                area_name=source.area_name or area_name,
            )
        source = replace(source, login_method=normalize_login_method(source.login_method), backend_task_id="manual")
        SourceResolver._validate_source(self, source)
        return source


def print_result(result: CreateResult) -> None:
    public = result.public_dict()
    print(
        "\t".join(
            [
                public["status"],
                public["action"],
                public["taxNo"],
                public["name"],
                public["custId"],
                public["areaName"],
                public["loginMethod"],
                public["accountantId"],
                public["accountantSource"] or "-",
                public["privacyPhoneStatus"] or "-",
                "verified" if public["verifyOk"] else "not_verified",
                "; ".join(public["errors"]) if public["errors"] else "",
            ]
        )
    )


def run_doctor(args: argparse.Namespace) -> int:
    load_env_file(args.env_file)
    env = apply_env_overrides(YDZ_ENVIRONMENTS[args.env], args)
    backend_token_provider: StaticAdminAuthProvider | None = None
    backend_auth_mode = "browser"
    backend_auth_status: dict[str, Any] | None = None
    if not args.skip_auto_login:
        backend_token_provider, backend_auth_mode, backend_auth_status = resolve_backend_token_provider(args)
    status: dict[str, Any] = {
        "env": env.name,
        "cdpPort": args.cdp_port,
        "chromeCdpAlive": is_cdp_alive(args.cdp_port),
        "envVarsPresent": env_secret_status(env.name),
        "ydzReady": False,
        "backendReady": backend_token_provider is not None,
        "backendAuthMode": backend_auth_mode,
        "backendAuth": backend_auth_status,
        "errors": [],
    }
    if args.open:
        try:
            launch_chrome_if_needed(args, env)
            status["chromeCdpAlive"] = True
        except Exception as exc:
            status["errors"].append(str(exc))
    if not status["chromeCdpAlive"]:
        print(json.dumps(status, ensure_ascii=False, indent=2))
        return 2
    try:
        sync_playwright = load_sync_playwright()

        with sync_playwright() as pw:
            browser = connect_chrome_over_cdp(pw, args, env) if args.open else pw.chromium.connect_over_cdp(f"http://127.0.0.1:{args.cdp_port}")
            context = browser.contexts[0] if browser.contexts else browser.new_context()
            status["cdpPort"] = args.cdp_port
            if args.open:
                ensure_pages_open(context, env, args.ydz_work_url, include_backend=backend_token_provider is None)
            if not args.skip_auto_login:
                if backend_token_provider is not None:
                    ensure_ydz_login(context, env, timeout=args.session_timeout, ydz_work_url=args.ydz_work_url)
                else:
                    ensure_login_sessions(context, env, args)
            page = find_ydz_page(context, env)
            if page is not None:
                try:
                    ctx = YdzApi(page, env).context()
                    status["ydzReady"] = True
                    status["ydzOrgId"] = ctx.get("orgId")
                    status["ydzOrgName"] = ctx.get("orgName")
                except Exception as exc:
                    status["errors"].append(str(exc))
            else:
                status["errors"].append("Yidaizhang work page was not found.")
            status["backendReady"] = backend_token_provider is not None or wait_for_backend_session(context, timeout=args.session_timeout)
            if not status["backendReady"]:
                status["errors"].append("Public-manage login token was not found.")
    except Exception as exc:
        status["errors"].append(str(exc))
    print(json.dumps(status, ensure_ascii=False, indent=2))
    return 0 if status["ydzReady"] and status["backendReady"] else 2


def run_login(args: argparse.Namespace) -> int:
    load_env_file(args.env_file)
    env = apply_env_overrides(YDZ_ENVIRONMENTS[args.env], args)
    backend_token_provider: StaticAdminAuthProvider | None = None
    backend_auth_mode = "browser"
    backend_auth_status: dict[str, Any] | None = None
    if not args.skip_auto_login:
        backend_token_provider, backend_auth_mode, backend_auth_status = resolve_backend_token_provider(args)
    status: dict[str, Any] = {
        "env": env.name,
        "cdpPort": args.cdp_port,
        "chromeCdpAlive": False,
        "ydzReady": False,
        "backendReady": False,
        "backendAuthMode": backend_auth_mode,
        "backendAuth": backend_auth_status,
        "envVarsPresent": env_secret_status(env.name),
        "errors": [],
    }
    try:
        sync_playwright = load_sync_playwright()

        with sync_playwright() as pw:
            browser = connect_chrome_over_cdp(pw, args, env)
            context = browser.contexts[0] if browser.contexts else browser.new_context()
            status["cdpPort"] = args.cdp_port
            status["chromeCdpAlive"] = True
            ensure_pages_open(context, env, args.ydz_work_url, include_backend=backend_token_provider is None)
            if backend_token_provider is not None:
                ydz_page = ensure_ydz_login(context, env, timeout=args.session_timeout, ydz_work_url=args.ydz_work_url)
                backend_ready = True
            else:
                ydz_page, backend_ready = ensure_login_sessions(context, env, args)
            if ydz_page is not None:
                try:
                    ctx = YdzApi(ydz_page, env).context()
                    status["ydzReady"] = True
                    status["ydzOrgId"] = ctx.get("orgId")
                    status["ydzOrgName"] = ctx.get("orgName")
                except Exception as exc:
                    status["errors"].append(str(exc))
            else:
                status["errors"].append("Yidaizhang login did not reach work.html.")
            status["backendReady"] = backend_ready
            if not backend_ready:
                status["errors"].append("Public-manage login token was not found.")
    except Exception as exc:
        status["errors"].append(str(exc))
    print(json.dumps(status, ensure_ascii=False, indent=2))
    return 0 if status["ydzReady"] and status["backendReady"] else 2


def run_create(args: argparse.Namespace) -> int:
    load_env_file(args.env_file)
    logging.basicConfig(level=getattr(logging, str(args.log_level).upper(), logging.INFO), format="%(levelname)s %(message)s")
    env = apply_env_overrides(YDZ_ENVIRONMENTS[args.env], args)
    defaults = build_defaults(args)
    tax_numbers = read_tax_numbers(args)
    lookback_days = parse_lookback_days(args.lookback_days)
    manual_mode = bool(getattr(args, "manual_source_env", False))
    ydz_auth_mode = resolved_ydz_auth_mode(args)
    if ydz_auth_mode not in {"auto", "browser", "token", "password"}:
        raise SystemExit("YDZ_AUTH_MODE must be auto, browser, token, or password.")
    ydz_token_context = configured_ydz_token_context(env, args.ydz_work_url) if ydz_auth_mode == "token" else None
    ydz_password_status: dict[str, Any] | None = None
    if ydz_auth_mode in {"auto", "password"}:
        ydz_token_context, ydz_password_status = configured_ydz_password_context(
            env,
            ydz_work_url=args.ydz_work_url,
            timeout=args.session_timeout,
        )
        if ydz_token_context is not None:
            ydz_auth_mode = "password"
        elif ydz_auth_mode == "auto":
            LOGGER.info(
                "Yidaizhang password auth did not produce a usable token context; falling back to browser login. status=%s",
                ydz_password_status.get("status") if ydz_password_status else "FAILED",
            )
            ydz_auth_mode = "browser"
    if ydz_auth_mode == "token" and ydz_token_context is None:
        prefix = env_prefix(env.name)
        print(
            "Yidaizhang token auth is not configured. Set "
            f"{prefix}_IFRAME_TOKEN/{prefix}_CIA_TOKEN and {prefix}_WORK_URL, "
            "or use --ydz-auth-mode browser.",
            file=sys.stderr,
        )
        return 2
    if ydz_auth_mode == "password" and ydz_token_context is None:
        print(
            "Yidaizhang password auth did not produce a usable API token context. "
            f"status={ydz_password_status.get('status') if ydz_password_status else 'FAILED'} "
            f"message={ydz_password_status.get('message') if ydz_password_status else ''}. "
            "Use --ydz-auth-mode browser for interactive login or --ydz-auth-mode token with valid token variables.",
            file=sys.stderr,
        )
        return 2
    backend_token_provider: StaticAdminAuthProvider | None = None
    backend_auth_mode = "none"
    backend_auth_status: dict[str, Any] | None = None
    if not manual_mode:
        backend_token_provider, backend_auth_mode, backend_auth_status = resolve_backend_token_provider(args)
        if backend_token_provider is None and resolved_backend_auth_mode(args) in {"token", "password"}:
            print(
                "Public-manage API authentication did not produce usable tokens. "
                f"mode={resolved_backend_auth_mode(args)} "
                f"status={backend_auth_status.get('status') if backend_auth_status else 'FAILED'} "
                f"message={backend_auth_status.get('message') if backend_auth_status else ''}. "
                "Use --backend-auth-mode auto/browser for browser fallback, or provide valid backend token variables.",
                file=sys.stderr,
            )
            return 2
    if ydz_auth_mode in {"token", "password"} and manual_mode:
        creator = Creator(
            YdzApi(None, env, auth_context=ydz_token_context),
            ManualSourceResolver(manual_source_from_env()),
            env,
            defaults,
            privacy_phone_bridge=None,
            prepare_privacy_phone=False,
            login_account=configured_ydz_credentials(env)["username"],
        )
        print("status\taction\ttaxNo\tname\tcustId\tarea\tloginMethod\taccountantId\taccountantSource\tprivacyPhone\tverification\terrors")
        results = []
        for tax_no in tax_numbers:
            result = creator.process_tax_no(tax_no, dry_run=args.dry_run)
            results.append(result)
            print_result(result)
        if args.output_json:
            output_path = Path(args.output_json)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                json.dumps([result.public_dict() for result in results], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        return 1 if any(result.status in {"FAILED", "PARTIAL"} for result in results) else 0
    if ydz_auth_mode in {"token", "password"} and backend_token_provider is not None:
        creator = Creator(
            YdzApi(None, env, auth_context=ydz_token_context),
            SourceResolver(AdminTaskQuery(token_provider=backend_token_provider), lookback_days=lookback_days),
            env,
            defaults,
            privacy_phone_bridge=(
                None
                if getattr(args, "skip_privacy_phone_sync", False)
                else PrivacyPhoneBridge(token_provider=backend_token_provider) if env.name == "inte" else None
            ),
            prepare_privacy_phone=not getattr(args, "skip_privacy_phone_sync", False),
            login_account=configured_ydz_credentials(env)["username"],
        )
        print("status\taction\ttaxNo\tname\tcustId\tarea\tloginMethod\taccountantId\taccountantSource\tprivacyPhone\tverification\terrors")
        results = []
        for tax_no in tax_numbers:
            result = creator.process_tax_no(tax_no, dry_run=args.dry_run)
            results.append(result)
            print_result(result)
        if args.output_json:
            output_path = Path(args.output_json)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                json.dumps([result.public_dict() for result in results], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        return 1 if any(result.status in {"FAILED", "PARTIAL"} for result in results) else 0
    sync_playwright = load_sync_playwright()

    results: list[CreateResult] = []
    with sync_playwright() as pw:
        browser = connect_chrome_over_cdp(pw, args, env)
        context = browser.contexts[0] if browser.contexts else browser.new_context()
        ensure_pages_open(
            context,
            env,
            args.ydz_work_url,
            include_backend=not manual_mode and backend_token_provider is None,
        )
        ydz_page = None
        backend_ready = manual_mode or backend_token_provider is not None
        if ydz_auth_mode in {"token", "password"}:
            if not manual_mode and backend_token_provider is None:
                backend_ready = (
                    wait_for_backend_session(context, timeout=args.session_timeout)
                    if args.skip_auto_login
                    else ensure_backend_login(context, timeout=args.session_timeout)
                )
        elif not args.skip_auto_login:
            if manual_mode:
                ydz_page = ensure_ydz_login(context, env, timeout=args.session_timeout, ydz_work_url=args.ydz_work_url)
            elif backend_token_provider is not None:
                ydz_page = ensure_ydz_login(context, env, timeout=args.session_timeout, ydz_work_url=args.ydz_work_url)
            else:
                ydz_page, backend_ready = ensure_login_sessions(context, env, args)
        work_url = args.ydz_work_url or configured_ydz_credentials(env)["workUrl"] or env.default_work_url
        if ydz_auth_mode == "browser" and ydz_page is None:
            if args.skip_auto_login:
                ydz_page = wait_for_ydz_page(context, env, timeout=args.session_timeout)
            else:
                ydz_page = wait_for_ydz_or_direct_work(context, env, work_url, timeout=args.session_timeout)
        if not backend_ready and backend_token_provider is None:
            backend_ready = wait_for_backend_session(context, timeout=args.session_timeout)
        if (ydz_auth_mode == "browser" and ydz_page is None) or not backend_ready:
            if manual_mode:
                print(
                    "Yidaizhang login session is not ready. Log in to Yidaizhang in the opened Chrome window, "
                    "select the target enterprise, then rerun this command.",
                    file=sys.stderr,
                )
            else:
                print(
                    "Login session is not ready. Log in to Yidaizhang and public-manage in the opened Chrome window, "
                    "select the target enterprise, then rerun this command.",
                    file=sys.stderr,
                )
            return 2

        creator = Creator(
            YdzApi(None, env, auth_context=ydz_token_context)
            if ydz_auth_mode in {"token", "password"}
            else YdzApi(ydz_page, env),
            ManualSourceResolver(manual_source_from_env())
            if manual_mode
            else SourceResolver(
                AdminTaskQuery(
                    None if backend_token_provider is not None else context,
                    token_provider=backend_token_provider,
                ),
                lookback_days=lookback_days,
            ),
            env,
            defaults,
            privacy_phone_bridge=(
                None
                if manual_mode or getattr(args, "skip_privacy_phone_sync", False)
                else PrivacyPhoneBridge(
                    None if backend_token_provider is not None else context,
                    token_provider=backend_token_provider,
                ) if env.name == "inte" else None
            ),
            prepare_privacy_phone=not (manual_mode or getattr(args, "skip_privacy_phone_sync", False)),
            login_account=configured_ydz_credentials(env)["username"],
        )
        print("status\taction\ttaxNo\tname\tcustId\tarea\tloginMethod\taccountantId\taccountantSource\tprivacyPhone\tverification\terrors")
        for tax_no in tax_numbers:
            result = creator.process_tax_no(tax_no, dry_run=args.dry_run)
            results.append(result)
            print_result(result)

    if args.output_json:
        output_path = Path(args.output_json)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps([result.public_dict() for result in results], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    return 1 if any(result.status in {"FAILED", "PARTIAL"} for result in results) else 0


def add_common_browser_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--env", choices=sorted(YDZ_ENVIRONMENTS), default="inte")
    parser.add_argument("--env-file", help="Optional local env file. Do not commit files containing passwords.")
    parser.add_argument("--cdp-port", type=int, default=9222)
    parser.add_argument("--chrome-path", default=DEFAULT_CHROME_PATH)
    parser.add_argument("--user-data-dir", default=DEFAULT_PROFILE_DIR)
    parser.add_argument("--ydz-work-url", help="Override Yidaizhang work.html URL.")
    parser.add_argument("--session-timeout", type=int, default=120)
    parser.add_argument("--org-id", help="Override expected Yidaizhang org id.")
    parser.add_argument("--user-id", help="Override Yidaizhang user id used in user_req params.")
    parser.add_argument("--accountant-id", help="Override assigned accountant employee id.")
    parser.add_argument("--accountant-name", help="Override assigned accountant display name.")
    parser.add_argument("--no-launch-chrome", action="store_true")
    parser.add_argument("--skip-auto-login", action="store_true", help="Only check existing browser sessions; do not use configured credentials to login.")
    parser.add_argument(
        "--ydz-auth-mode",
        choices=["auto", "browser", "token", "password"],
        default=None,
        help=(
            "Yidaizhang auth source: auto tries password first and falls back to browser; "
            "browser reads a logged-in workbench page; "
            "token reads YDZ_*_IFRAME_TOKEN and YDZ_*_CIA_TOKEN; "
            "password tries direct Chanjet password login and reports manual-verification blockers."
        ),
    )
    parser.add_argument(
        "--backend-auth-mode",
        choices=["auto", "browser", "token", "password"],
        default=None,
        help=(
            "Public-manage auth source: auto tries configured backend tokens, then password API login, "
            "then browser; token reads TAX_BACKEND_AUTHORIZATION and TAX_BACKEND_TOKEN/TAX_BACKEND_ACCESS_TOKEN."
        ),
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create or update Yidaizhang customers/account sets from backend login info.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor = subparsers.add_parser("doctor", help="Check Chrome, Yidaizhang, public-manage, and configured secret names.")
    add_common_browser_args(doctor)
    doctor.add_argument("--open", action="store_true", help="Launch/open Yidaizhang and public-manage pages when needed.")

    login = subparsers.add_parser("login", help="Open Chrome and login to Yidaizhang plus public-manage using configured secrets.")
    add_common_browser_args(login)

    create = subparsers.add_parser("create", help="Create/update customers and save tax login info.")
    add_common_browser_args(create)
    create.add_argument("--tax-no", action="append", default=[], help="Tax number. Can be passed multiple times.")
    create.add_argument("--tax-no-file", help="Text file containing tax numbers separated by whitespace, comma, or newline.")
    create.add_argument("--lookback-days", default="30,180,730,1460")
    create.add_argument("--opening-period")
    create.add_argument("--taxpayer-type")
    create.add_argument("--industry-id")
    create.add_argument(
        "--manual-source-env",
        action="store_true",
        help="Read customer/login source fields from YDZ_MANUAL_* environment variables instead of public-manage.",
    )
    create.add_argument(
        "--skip-privacy-phone-sync",
        action="store_true",
        help="Do not prepare/sync integration privacy-phone data before creating the account set.",
    )
    create.add_argument("--dry-run", action="store_true")
    create.add_argument("--output-json", help="Optional sanitized result report path.")
    create.add_argument("--log-level", default="INFO")

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.command == "doctor":
        return run_doctor(args)
    if args.command == "login":
        return run_login(args)
    if args.command == "create":
        return run_create(args)
    raise SystemExit(f"Unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
