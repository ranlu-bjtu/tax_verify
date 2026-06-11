from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from typing import Any, Iterable
from urllib.parse import urlparse

import requests
from playwright.sync_api import BrowserContext, Error as PlaywrightError, Page

from src.chanjet_admin.privacy_phone import ChanjetPrivacyPhoneBridge, PrivacyPhonePrepareResult
from src.chanjet_admin.task_query import ACCOUNTSET_LOGIN_TYPE_FILTER, ChanjetAdminTaskQuery

LOGGER = logging.getLogger(__name__)

DEFAULT_OPENING_PERIOD = "202501"
DEFAULT_TAXPAYER_TYPE = "SMALL_TAXPAYER"
DEFAULT_TAX_INDUSTRY_ID = "11079"
DEFAULT_ACCTG_SYSTEM_ID = "10001"
DEFAULT_SERVICE_TYPE = "ACCOUTING"
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
class YdzCreateEnvironment:
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


YDZ_CREATE_ENVIRONMENTS = {
    "inte": YdzCreateEnvironment(
        name="inte",
        cloud_marker="inte-cloud.chanjet.com/ydzee/",
        public_url="https://ydz.inte.chanjet.com/",
        default_work_url="https://inte-cloud.chanjet.com/ydzee/ujsoz429myw4/a41vioa2em/work.html#/customer-list",
        org_id="90001204213",
        user_id="61000431181",
        accountant_id="61000431181",
        accountant_name="user7793",
    ),
    "prod": YdzCreateEnvironment(
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
    env: YdzCreateEnvironment,
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
    parsed = urlparse(href)
    if not parsed.scheme or not parsed.netloc or "/work.html" not in parsed.path:
        raise YdzCustomerCreationError("YDZ token auth requires a full work.html URL.")
    origin = f"{parsed.scheme}://{parsed.netloc}"
    base = parsed.path.split("/work.html", 1)[0]
    context = YdzAuthContext(
        href=href,
        origin=origin,
        base=base,
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


def _normalize_ydz_context(data: Any, env: YdzCreateEnvironment) -> dict[str, str]:
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
        raise YdzCustomerCreationError("YDZ auth context is invalid.")
    normalized = {key: str(value or "") for key, value in normalized.items()}
    _validate_ydz_context(normalized, env)
    return normalized


def _validate_ydz_context(data: dict[str, str], env: YdzCreateEnvironment) -> None:
    href = str(data.get("href") or "")
    if env.cloud_marker not in href or "/work.html" not in href:
        raise YdzCustomerCreationError(
            f"YDZ auth context is not ready for {env.name}; current_url={href}"
        )
    if not data.get("origin") or not data.get("base"):
        raise YdzCustomerCreationError("YDZ API base path is missing.")
    if not data.get("iframeToken") or not data.get("ciaToken"):
        raise YdzCustomerCreationError("YDZ login token is missing. Log in and select the enterprise first.")
    if str(data.get("orgId") or "") != env.org_id:
        raise YdzCustomerCreationError(
            f"YDZ org mismatch: current={data.get('orgId')} expected={env.org_id}."
        )


@dataclass
class YdzCustomerDefaults:
    opening_period: str = DEFAULT_OPENING_PERIOD
    taxpayer_type: str = DEFAULT_TAXPAYER_TYPE
    tax_industry_id: str = DEFAULT_TAX_INDUSTRY_ID
    acctg_system_id: str = DEFAULT_ACCTG_SYSTEM_ID
    service_type: str = DEFAULT_SERVICE_TYPE


@dataclass
class BackendCustomerSource:
    tax_no: str
    name: str
    area_code: str
    area_name: str
    login_method: str
    proxy_tax_no: str = ""
    privacy_no: str = ""
    password: str = ""
    backend_task_id: str = ""
    raw_login_json: dict[str, Any] = field(default_factory=dict)

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
class YdzAssignedAccountant:
    employee_id: str
    name: str = ""
    mobile: str = ""
    source: str = "env_default"

    @classmethod
    def from_environment(cls, env: YdzCreateEnvironment, source: str = "env_default") -> "YdzAssignedAccountant":
        return cls(employee_id=env.accountant_id, name=env.accountant_name, source=source)


@dataclass
class YdzCustomerCreateResult:
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
            "errors": self.errors,
        }


class YdzCustomerCreationError(RuntimeError):
    pass


def strip_operator_prefix(name: str | None) -> str:
    return re.sub(r"^\[[^\]]+\]", "", name or "").strip()


def normalize_login_json(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def login_method_requires_password(login_method: str) -> bool:
    return bool(login_method) and login_method not in NO_PASSWORD_LOGIN_METHODS


def normalize_login_method(value: str | None) -> str:
    text = str(value or "").strip()
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
    if "申报账密" in compact or "账号密码" in compact:
        return "SBZMDL"
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


def expected_site_login_name(login_method: str, proxy_tax_no: str) -> str:
    return proxy_tax_no if str(login_method or "").startswith(PROXY_LOGIN_PREFIX) else ""


def normalize_phone(value: Any) -> str:
    return "".join(re.findall(r"\d+", str(value or "")))


def is_transient_page_error(exc: Exception) -> bool:
    text = str(exc)
    return any(marker in text for marker in TRANSIENT_PAGE_ERROR_MARKERS)


def build_customer_create_payload(
    source: BackendCustomerSource,
    env: YdzCreateEnvironment,
    defaults: YdzCustomerDefaults,
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


def build_tax_info_payload(source: BackendCustomerSource, cust_id: str, assoc_tenant_id: str) -> dict[str, Any]:
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
        if isinstance(data, list):
            for item in data:
                found = extract_customer_info(item, tax_no)
                if found:
                    return found
        for value in data.values() if isinstance(data, dict) else []:
            found = extract_customer_info(value, tax_no)
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


def fallback_area_code(area_name: str, tax_no: str) -> str:
    text = str(area_name or "")
    for name, code in AREA_NAME_TO_CODE.items():
        if name in text:
            return code
    if len(tax_no) >= 4 and tax_no[2:4].isdigit():
        return tax_no[2:4]
    return ""


def fallback_area_name(area_code: str) -> str:
    code = str(area_code or "")
    for name, current_code in AREA_NAME_TO_CODE.items():
        if current_code == code:
            return name
    return ""


def validate_customer_source(source: BackendCustomerSource, source_label: str = "Customer source") -> None:
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
        raise YdzCustomerCreationError(f"{source_label} is incomplete: " + ", ".join(missing))


def verify_tax_info(source: BackendCustomerSource, tax_info: dict[str, Any]) -> bool:
    return (
        str(tax_info.get("cLoginMethodEnum") or "") == source.login_method
        and str(tax_info.get("cSiteLoginName") or "") == expected_site_login_name(
            source.login_method,
            source.proxy_tax_no,
        )
        and str(tax_info.get("cTaxPreparerName") or "") == source.privacy_no
        and str(tax_info.get("cTaxPreparerPwd") or "") == source.password
    )


def verify_customer_info(
    customer: dict[str, Any],
    source: BackendCustomerSource,
    env: YdzCreateEnvironment,
    defaults: YdzCustomerDefaults,
    accountant_employee_id: str | None = None,
) -> bool:
    account_book = customer.get("accountBook") if isinstance(customer.get("accountBook"), dict) else {}
    opening_period = (
        account_book.get("openingPeriod")
        or customer.get("openingPeriod")
        or customer.get("lastBookPeriod")
    )
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


class YdzCustomerApi:
    def __init__(
        self,
        page: Page | None,
        env: YdzCreateEnvironment,
        timeout: int = 60,
        auth_context: YdzAuthContext | dict[str, Any] | None = None,
    ) -> None:
        if page is None and auth_context is None:
            raise YdzCustomerCreationError("YDZ API requires either a browser page or a token auth context.")
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
            raise YdzCustomerCreationError("YDZ browser page is not configured.")
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
        return str(data.get("geoCode") or ""), str(data.get("geoName") or "")

    def query_accountant_employees(self) -> list[dict[str, Any]]:
        data = self.get_json("/trans/easyacctg/employee/getChildEmpListByUserId")
        return [
            row
            for row in extract_employee_rows(data)
            if str(row.get("roleTypeEnum") or "") != "EASYACCTG_ADMIN"
        ]

    def resolve_assigned_accountant(self, login_account: str | None = None) -> YdzAssignedAccountant:
        fallback = YdzAssignedAccountant.from_environment(self.env)
        try:
            rows = self.query_accountant_employees()
        except Exception as exc:
            LOGGER.warning("YDZ accountant employee lookup failed; using env default accountant: %s", exc)
            return fallback
        if not rows:
            return fallback

        try:
            ctx = self.context()
        except Exception as exc:
            LOGGER.warning("YDZ context lookup failed during accountant resolution; using available fallback: %s", exc)
            ctx = {}
        login_mobile = normalize_phone(login_account) or normalize_phone(ctx.get("userMobile"))
        current_user_id = str(ctx.get("userId") or "")

        def build(row: dict[str, Any], source: str) -> YdzAssignedAccountant:
            return YdzAssignedAccountant(
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
        data = self.post_json(
            "/trans/easyacctg/custWorkbench/queryPageList",
            {"pageNo": 1, "pageSize": 20, "keyword": tax_no},
        )
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
        source: BackendCustomerSource,
        defaults: YdzCustomerDefaults,
        accountant: YdzAssignedAccountant | None = None,
    ) -> ExistingCustomer:
        payload = build_customer_create_payload(
            source,
            self.env,
            defaults,
            accountant_employee_id=(accountant.employee_id if accountant else None),
        )
        data = self.post_json("/trans/easyacctg/customer/create", payload)
        cust_id, assoc_tenant_id = find_ids(data)
        if not cust_id:
            message = data.get("message") or data.get("msg") or data.get("errorMsg") or "create response has no customer id"
            raise YdzCustomerCreationError(f"YDZ create customer failed: {message}")
        return ExistingCustomer(cust_id=cust_id, assoc_tenant_id=assoc_tenant_id, name=source.name, raw=data)

    def save_tax_info(self, source: BackendCustomerSource, customer: ExistingCustomer) -> dict[str, Any]:
        payload = build_tax_info_payload(source, customer.cust_id, customer.assoc_tenant_id)
        return self.post_json("/trans/easyacctg/taxInfo/saveCustTaxAndBusiInfo", payload)

    def query_customer(self, cust_id: str) -> dict[str, Any]:
        return self.get_json(
            f"/trans/easyacctg/customer/query?custId={cust_id}&assocTenantId=&orgId={self.env.org_id}&hasSecret=1"
        )

    def query_tax_info(self, cust_id: str) -> dict[str, Any]:
        return self.post_json("/trans/easyacctg/taxInfo/queryEasyacctgCustTaxInfo", [{"easyacctgCustId": str(cust_id)}])

    def post_json(self, endpoint: str, payload: Any) -> dict[str, Any]:
        return self._request_json("POST", endpoint, payload)

    def get_json(self, endpoint: str) -> dict[str, Any]:
        return self._request_json("GET", endpoint, None)

    def _request_json(self, method: str, endpoint: str, payload: Any) -> dict[str, Any]:
        ctx = self.context()
        url = self._absolute_url(endpoint, ctx)
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Authorization": "Bearer " + ctx["iframeToken"],
            "token": ctx["ciaToken"],
            "Content-Type": "application/json;charset=UTF-8",
            "Referer": ctx["origin"] + ctx["base"] + "/work.html",
        }
        if method == "GET":
            response = requests.get(url, headers=headers, timeout=self.timeout)
        else:
            response = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
        if response.status_code >= 400:
            raise YdzCustomerCreationError(f"YDZ API failed: endpoint={endpoint} http={response.status_code}")
        try:
            data = response.json()
        except ValueError as exc:
            raise YdzCustomerCreationError(f"YDZ API returned non-json response: endpoint={endpoint}") from exc
        if isinstance(data, dict):
            code = str(data.get("code") or "")
            if code in {"500", "701"}:
                message = data.get("msg") or data.get("message") or data.get("rootCause") or "YDZ API failed"
                raise YdzCustomerCreationError(f"YDZ API failed: endpoint={endpoint} code={code} msg={message}")
        return data

    def _absolute_url(self, endpoint: str, ctx: dict[str, str]) -> str:
        separator = "&" if "?" in endpoint else "?"
        req = (
            f"{separator}user_req_id=ydz-customer-create-{int(time.time() * 1000)}"
            f"&user_req_userid={ctx.get('userId') or self.env.user_id}"
            f"&user_req_orgid={ctx.get('orgId') or self.env.org_id}"
        )
        return ctx["origin"] + ctx["base"] + endpoint + req


class BackendCustomerSourceResolver:
    def __init__(self, admin_query: ChanjetAdminTaskQuery, lookback_days: list[int] | None = None) -> None:
        self.admin_query = admin_query
        self.lookback_days = lookback_days or [30, 180, 730, 1460]

    def resolve(self, tax_no: str, ydz_api: YdzCustomerApi) -> BackendCustomerSource:
        row = self._latest_backend_row(tax_no)
        if not row:
            raise YdzCustomerCreationError("No successful backend task with login info was found.")
        area_code, area_name = ydz_api.query_tax_geo(tax_no)
        backend_area_name = str(row.get("taxAreaName") or "")
        if not area_code:
            area_code = fallback_area_code(backend_area_name, tax_no)
        if not area_name:
            area_name = backend_area_name
        login_json = normalize_login_json(row.get("loginJson"))
        source = BackendCustomerSource(
            tax_no=tax_no,
            name=strip_operator_prefix(str(row.get("orgName") or "")),
            area_code=area_code,
            area_name=area_name,
            login_method=backend_row_login_method(row),
            proxy_tax_no=str(login_json.get("cSiteLoginName") or ""),
            privacy_no=str(login_json.get("cTaxPreparerName") or ""),
            password=str(login_json.get("cTaxPreparerPwd") or ""),
            backend_task_id=str(row.get("id") or ""),
            raw_login_json=login_json,
        )
        validate_customer_source(source, "Backend source")
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
                    is_mock=False,
                    login_type=ACCOUNTSET_LOGIN_TYPE_FILTER,
                    page_size=20,
                )
                exact = [task for task in tasks if task.tax_no == tax_no]
                candidates = [task for task in exact if backend_row_has_supported_login(task.raw)]
                if candidates:
                    selected = sorted(candidates, key=lambda item: item.created_stamp or 0, reverse=True)[0]
                    return selected.raw
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

class ManualCustomerSourceResolver:
    def __init__(self, source: BackendCustomerSource) -> None:
        self.source = source

    def resolve(self, tax_no: str, ydz_api: YdzCustomerApi) -> BackendCustomerSource:
        if tax_no != self.source.tax_no:
            raise YdzCustomerCreationError(
                f"Manual source tax number mismatch: current={tax_no} expected={self.source.tax_no}"
            )
        area_code = self.source.area_code
        area_name = self.source.area_name
        area_code = area_code or fallback_area_code(area_name, tax_no)
        area_name = area_name or fallback_area_name(area_code)
        if not area_code or not area_name:
            geo_code, geo_name = ydz_api.query_tax_geo(tax_no)
            area_code = area_code or geo_code
            area_name = area_name or geo_name
        source = replace(
            self.source,
            area_code=area_code,
            area_name=area_name,
            login_method=normalize_login_method(self.source.login_method),
            backend_task_id="manual",
        )
        validate_customer_source(source, "Manual source")
        return source


class YdzCustomerCreator:
    def __init__(
        self,
        ydz_api: YdzCustomerApi,
        source_resolver: Any,
        env: YdzCreateEnvironment,
        defaults: YdzCustomerDefaults | None = None,
        privacy_phone_bridge: ChanjetPrivacyPhoneBridge | None = None,
        prepare_privacy_phone: bool = True,
        login_account: str | None = None,
    ) -> None:
        self.ydz_api = ydz_api
        self.source_resolver = source_resolver
        self.env = env
        self.defaults = defaults or YdzCustomerDefaults()
        self.privacy_phone_bridge = privacy_phone_bridge
        self.prepare_privacy_phone = prepare_privacy_phone
        self.login_account = login_account or ""

    def process_tax_no(self, tax_no: str, dry_run: bool = False) -> YdzCustomerCreateResult:
        result: YdzCustomerCreateResult | None = None
        try:
            source = self.source_resolver.resolve(tax_no, self.ydz_api)
            result = YdzCustomerCreateResult(
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
                    raise YdzCustomerCreationError(result.privacy_phone_message)
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
            save_data = self.ydz_api.save_tax_info(source, customer)
            result.save_ok = api_success(save_data)

            customer_data = self.ydz_api.query_customer(customer.cust_id)
            tax_info_data = self.ydz_api.query_tax_info(customer.cust_id)
            customer_info = extract_customer_info(customer_data, tax_no=tax_no)
            tax_info = extract_tax_info(tax_info_data)
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
        except YdzCustomerCreationError as exc:
            if result is None:
                return YdzCustomerCreateResult(tax_no=tax_no, status="FAILED", errors=[str(exc)])
            result.status = "FAILED"
            result.errors.append(str(exc))
            return result

    def _prepare_privacy_phone(
        self,
        source: BackendCustomerSource,
        dry_run: bool = False,
    ) -> PrivacyPhonePrepareResult | None:
        if (
            not self.prepare_privacy_phone
            or self.env.name != "inte"
            or source.login_method not in PRIVACY_LOGIN_METHODS
            or not source.privacy_no
        ):
            return None
        if self.privacy_phone_bridge is None:
            raise YdzCustomerCreationError("Integration privacy phone bridge is not configured.")
        return self.privacy_phone_bridge.ensure_integration_private_phone(source.privacy_no, dry_run=dry_run)

    def _privacy_prepare_message(self, prepare: PrivacyPhonePrepareResult) -> str:
        if prepare.status in {"EXISTS", "DRY_RUN_EXISTS"}:
            return f"integration privacy phone exists: count={prepare.inte_summary_count}"
        if prepare.status == "DRY_RUN_MISSING":
            return "integration privacy phone is missing; online sync and integration pull would be required"
        if prepare.status == "PULLED":
            return "integration privacy phone was pulled after online sync"
        return "; ".join(prepare.errors) or prepare.pull_message or prepare.copy_message or prepare.status


def find_ydz_page(context: BrowserContext, env: YdzCreateEnvironment) -> Page | None:
    for page in context.pages:
        if page.is_closed():
            continue
        if env.cloud_marker in page.url and "/work.html" in page.url:
            return page
    return None


def wait_for_ydz_page(context: BrowserContext, env: YdzCreateEnvironment, timeout: int = 120) -> Page | None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        page = find_ydz_page(context, env)
        if page is not None:
            try:
                YdzCustomerApi(page, env).context()
                return page
            except YdzCustomerCreationError:
                pass
            except PlaywrightError as exc:
                if not is_transient_page_error(exc):
                    raise
        time.sleep(1)
    return None
