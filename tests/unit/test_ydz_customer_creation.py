from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from playwright.sync_api import Error as PlaywrightError

from src.chanjet_admin.privacy_phone import PrivacyPhonePrepareResult
from src.ydz.customer_creation import (
    BackendCustomerSource,
    BackendCustomerSourceResolver,
    ManualCustomerSourceResolver,
    YDZ_CREATE_ENVIRONMENTS,
    YdzCustomerCreationError,
    YdzCustomerApi,
    YdzCustomerCreator,
    YdzCustomerDefaults,
    YdzAssignedAccountant,
    backend_row_has_supported_login,
    build_ydz_auth_context,
    build_customer_create_payload,
    build_tax_info_payload,
    expected_site_login_name,
    extract_customer_info,
    extract_employee_rows,
    extract_tax_info,
    fallback_area_code,
    login_method_requires_password,
    normalize_login_method,
    strip_operator_prefix,
    verify_customer_info,
    verify_tax_info,
    wait_for_ydz_page,
)


def test_strip_operator_prefix_removes_bracketed_owner():
    assert strip_operator_prefix("[operator]Example Co") == "Example Co"
    assert strip_operator_prefix("Example Co") == "Example Co"


def test_proxy_login_tax_info_uses_proxy_as_site_login_name():
    source = BackendCustomerSource(
        tax_no="91110116MAEETH8W2C",
        name="Example Co",
        area_code="11",
        area_name="Beijing",
        login_method="DLYW-YSHDL",
        proxy_tax_no="91110116PROXY0001",
        privacy_no="15500000000",
        password="secret",
    )

    payload = build_tax_info_payload(source, "100", "200")

    assert payload["taxInfoDTO"]["cLoginMethodEnum"] == "DLYW-YSHDL"
    assert payload["taxInfoDTO"]["cSiteLoginName"] == "91110116PROXY0001"
    assert payload["taxInfoDTO"]["cTaxPreparerName"] == "15500000000"
    assert payload["taxInfoDTO"]["cTaxPreparerPwd"] == "secret"


def test_manual_captcha_tax_info_uses_phone_and_proxy_fields():
    source = BackendCustomerSource(
        tax_no="91110116MAEETH8W2C",
        name="Example Co",
        area_code="11",
        area_name="Beijing",
        login_method="DLYW-SDSRDX",
        proxy_tax_no="91110116PROXY0001",
        privacy_no="15500000000",
        password="secret",
    )

    tax_info = build_tax_info_payload(source, "100", "200")["taxInfoDTO"]
    create_payload = build_customer_create_payload(source, YDZ_CREATE_ENVIRONMENTS["inte"], YdzCustomerDefaults())

    assert tax_info["cLoginMethodEnum"] == "DLYW-SDSRDX"
    assert tax_info["cSiteLoginName"] == "91110116PROXY0001"
    assert tax_info["cTaxPreparerName"] == "15500000000"
    assert tax_info["cTaxPreparerPwd"] == "secret"
    assert create_payload["taxLoginMethodEnum"] == "DLYW-SDSRDX"
    assert create_payload["taxSystemUserName"] == "91110116PROXY0001"
    assert create_payload["realAccount"] == "15500000000"


def test_backend_row_filter_accepts_only_supported_accountset_login_methods():
    assert backend_row_has_supported_login(
        {
            "loginJson": {
                "cLoginMethodEnum": "SDSRDX",
                "cTaxPreparerName": "15500000000",
                "cTaxPreparerPwd": "secret",
            }
        }
    )
    assert backend_row_has_supported_login(
        {
            "loginJson": {
                "cLoginMethodEnum": "DLYW-SDSRDX",
                "cSiteLoginName": "91110116PROXY0001",
                "cTaxPreparerName": "15500000000",
                "cTaxPreparerPwd": "secret",
            }
        }
    )
    assert not backend_row_has_supported_login(
        {"loginJson": {"cLoginMethodEnum": "SBZMDL", "cTaxPreparerName": "account"}}
    )


def test_non_proxy_login_tax_info_leaves_site_login_name_empty():
    source = BackendCustomerSource(
        tax_no="91110116MAEETH8W2C",
        name="Example Co",
        area_code="11",
        area_name="Beijing",
        login_method="YSHDL",
        proxy_tax_no="91110116PROXY0001",
        privacy_no="15500000000",
        password="secret",
    )

    assert expected_site_login_name(source.login_method, source.proxy_tax_no) == ""
    assert build_tax_info_payload(source, "100", "200")["taxInfoDTO"]["cSiteLoginName"] == ""


def test_customer_create_payload_contains_environment_defaults():
    env = YDZ_CREATE_ENVIRONMENTS["inte"]
    defaults = YdzCustomerDefaults()
    source = BackendCustomerSource(
        tax_no="91110116MAEETH8W2C",
        name="Example Co",
        area_code="11",
        area_name="Beijing",
        login_method="DLYW-YSHDL",
        proxy_tax_no="91110116PROXY0001",
        privacy_no="15500000000",
        password="secret",
    )

    payload = build_customer_create_payload(source, env, defaults)

    assert payload["orgId"] == int(env.org_id)
    assert payload["accountBook"]["openingPeriod"] == "202501"
    assert payload["accountBook"]["taxpayerTypeEnum"] == "SMALL_TAXPAYER"
    assert payload["taxIndustryId"] == "11079"
    assert payload["accountantEmployeeId"] == env.accountant_id
    assert payload["taxSystemUserName"] == source.proxy_tax_no
    assert payload["realAccount"] == source.privacy_no
    assert payload["realPwd"] == "secret"


def test_customer_create_payload_accepts_resolved_accountant_id():
    env = YDZ_CREATE_ENVIRONMENTS["inte"]
    defaults = YdzCustomerDefaults()
    source = BackendCustomerSource(
        tax_no="91110116MAEETH8W2C",
        name="Example Co",
        area_code="11",
        area_name="Beijing",
        login_method="YSHDL",
        privacy_no="15500000000",
        password="secret",
    )

    payload = build_customer_create_payload(source, env, defaults, accountant_employee_id="61000999999")

    assert payload["accountantEmployeeId"] == "61000999999"


def test_ydz_api_uses_static_token_context_without_browser_page():
    env = YDZ_CREATE_ENVIRONMENTS["inte"]
    auth_context = build_ydz_auth_context(
        env,
        iframe_token="iframe-token",
        cia_token="cia-token",
        work_url=env.default_work_url,
    )
    api = YdzCustomerApi(None, env, auth_context=auth_context)
    calls = []

    class Response:
        status_code = 200

        def json(self):
            return {"geoCode": "11", "geoName": "Beijing"}

    def fake_get(url, headers, timeout):
        calls.append({"url": url, "headers": headers, "timeout": timeout})
        return Response()

    with patch("src.ydz.customer_creation.requests.get", fake_get):
        data = api.get_json("/trans/easyacctg/customer/queryTaxGeoByTaxNo?taxNo=91110116MAEETH8W2C&orgId=90001204213")

    assert data["geoCode"] == "11"
    assert calls[0]["headers"]["Authorization"] == "Bearer iframe-token"
    assert calls[0]["headers"]["token"] == "cia-token"
    assert calls[0]["headers"]["Referer"].endswith("/work.html")
    assert "user_req_userid=" + env.user_id in calls[0]["url"]
    assert "user_req_orgid=" + env.org_id in calls[0]["url"]


def test_ydz_api_resolves_accountant_by_login_mobile_from_real_employee_shape():
    env = YDZ_CREATE_ENVIRONMENTS["inte"]
    auth_context = build_ydz_auth_context(
        env,
        iframe_token="iframe-token",
        cia_token="cia-token",
        work_url=env.default_work_url,
        user_id="61000411111",
    )
    api = YdzCustomerApi(None, env, auth_context=auth_context)

    def fake_get_json(endpoint):
        assert endpoint == "/trans/easyacctg/employee/getChildEmpListByUserId"
        return {
            "data": [
                {"userId": "61000400000", "name": "admin", "mobile": "15500000000", "roleTypeEnum": "EASYACCTG_ADMIN"},
                {"userId": "61000411111", "name": "matched", "mobile": "15500000000", "roleTypeEnum": "ACCOUNTANT"},
            ]
        }

    with patch.object(api, "get_json", fake_get_json):
        accountant = api.resolve_assigned_accountant("15500000000")

    assert accountant.employee_id == "61000411111"
    assert accountant.name == "matched"
    assert accountant.mobile == "15500000000"
    assert accountant.source == "login_mobile"


def test_ydz_api_resolves_accountant_by_env_default_when_lookup_fails():
    env = YDZ_CREATE_ENVIRONMENTS["inte"]
    auth_context = build_ydz_auth_context(
        env,
        iframe_token="iframe-token",
        cia_token="cia-token",
        work_url=env.default_work_url,
    )
    api = YdzCustomerApi(None, env, auth_context=auth_context)

    with patch.object(api, "get_json", side_effect=YdzCustomerCreationError("temporary")):
        accountant = api.resolve_assigned_accountant("15500000000")

    assert accountant.employee_id == env.accountant_id
    assert accountant.name == env.accountant_name
    assert accountant.source == "env_default"


def test_extract_employee_rows_handles_nested_api_data():
    payload = {"data": {"employeeList": [{"userId": "1", "mobile": "15500000000"}]}}

    assert extract_employee_rows(payload) == [{"userId": "1", "mobile": "15500000000"}]


def test_sbzmdl_does_not_require_password():
    assert login_method_requires_password("SBZMDL") is False
    assert login_method_requires_password("YSHDL") is True
    assert login_method_requires_password("DLYW-YSHDL") is True


def test_normalize_login_method_supports_chinese_labels():
    assert normalize_login_method("税局隐私号登录") == "YSHDL"
    assert normalize_login_method("税局隐私号-代理登录") == "DLYW-YSHDL"
    assert normalize_login_method("税局手工录入验证码登录") == "SDSRDX"
    assert normalize_login_method("税局手工录入验证码-代理登录") == "DLYW-SDSRDX"
    assert normalize_login_method("DLYW-YSHDL") == "DLYW-YSHDL"
    assert normalize_login_method("DLYW-SDSRDX") == "DLYW-SDSRDX"


def test_manual_source_resolver_uses_manual_fields_without_backend():
    source = BackendCustomerSource(
        tax_no="91110116MAEETH8W2C",
        name="Manual Co",
        area_code="",
        area_name="北京",
        login_method="税局隐私号-代理登录",
        proxy_tax_no="91110116PROXY0001",
        privacy_no="15500000000",
        password="secret",
    )

    class Api:
        def query_tax_geo(self, _tax_no):
            raise AssertionError("manual area name should avoid backend or YDZ geo fallback")

    resolved = ManualCustomerSourceResolver(source).resolve(source.tax_no, Api())

    assert resolved.name == "Manual Co"
    assert resolved.area_code == "11"
    assert resolved.area_name == "北京"
    assert resolved.login_method == "DLYW-YSHDL"
    assert resolved.backend_task_id == "manual"


def test_extract_and_verify_tax_info_from_nested_response():
    source = BackendCustomerSource(
        tax_no="91110116MAEETH8W2C",
        name="Example Co",
        area_code="11",
        area_name="Beijing",
        login_method="YSHDL",
        privacy_no="15500000000",
        password="secret",
    )
    response = {"data": {"easyacctgCustTaxInfo": [{"cLoginMethodEnum": "YSHDL", "cSiteLoginName": "", "cTaxPreparerName": "15500000000", "cTaxPreparerPwd": "secret"}]}}

    tax_info = extract_tax_info(response)

    assert verify_tax_info(source, tax_info) is True


def test_extract_and_verify_customer_info_from_nested_response():
    env = YDZ_CREATE_ENVIRONMENTS["inte"]
    defaults = YdzCustomerDefaults()
    source = BackendCustomerSource(
        tax_no="91110116MAEETH8W2C",
        name="Example Co",
        area_code="11",
        area_name="Beijing",
        login_method="YSHDL",
        privacy_no="15500000000",
        password="secret",
    )
    response = {
        "data": {
            "taxNo": source.tax_no,
            "custName": source.name,
            "corpName": source.name,
            "taxIndustryId": defaults.tax_industry_id,
            "taxpayerTypeEnum": defaults.taxpayer_type,
            "accountantEmployeeId": env.accountant_id,
            "accountBook": {"openingPeriod": defaults.opening_period},
        }
    }

    customer = extract_customer_info(response, tax_no=source.tax_no)

    assert verify_customer_info(customer, source, env, defaults) is True
    assert verify_customer_info(customer, source, env, defaults, accountant_employee_id="61000999999") is False


def test_fallback_area_code_supports_special_cities_and_tax_no_prefix():
    assert fallback_area_code("厦门", "91350206MA31GRNX01") == "3502"
    assert fallback_area_code("广东(不含深圳)", "92440605L54962136Q") == "44"
    assert fallback_area_code("", "91150104MA0N04YR6D") == "15"


def test_creator_marks_missing_backend_login_info_as_single_failed_result():
    class MissingResolver:
        def resolve(self, tax_no, ydz_api):
            raise YdzCustomerCreationError("No successful backend task with login info was found.")

    creator = YdzCustomerCreator(
        ydz_api=object(),
        source_resolver=MissingResolver(),
        env=YDZ_CREATE_ENVIRONMENTS["inte"],
    )

    result = creator.process_tax_no("91110116MAEETH8W2C")

    assert result.status == "FAILED"
    assert result.tax_no == "91110116MAEETH8W2C"
    assert "No successful backend task" in result.errors[0]


def test_backend_source_lookup_splits_large_lookback_windows():
    tax_no = "91110116MAEETH8W2C"
    calls = []

    class Task:
        created_stamp = 3
        raw = {
            "id": "task-3",
            "loginJson": {
                "cLoginMethodEnum": "SDSRDX",
                "cTaxPreparerName": "15500000000",
                "cTaxPreparerPwd": "secret",
            },
        }

        def __init__(self):
            self.tax_no = tax_no

    class AdminQuery:
        def query_tasks(self, start_time, end_time, **kwargs):
            calls.append((start_time, end_time))
            assert (end_time - start_time).total_seconds() <= 40 * 24 * 60 * 60
            assert kwargs["login_type"] == "YSHDL,DLYW-YSHDL,SDSRDX,DLYW-SDSRDX"
            return [Task()] if len(calls) == 3 else []

    resolver = BackendCustomerSourceResolver(AdminQuery(), lookback_days=[90])

    row = resolver._latest_backend_row(tax_no)

    assert row["id"] == "task-3"
    assert len(calls) == 3


def test_creator_prepares_integration_privacy_phone_before_dry_run_customer_check():
    source = BackendCustomerSource(
        tax_no="91110116MAEETH8W2C",
        name="Example Co",
        area_code="11",
        area_name="Beijing",
        login_method="YSHDL",
        privacy_no="15500000001",
        password="secret",
    )

    class Resolver:
        def resolve(self, tax_no, ydz_api):
            return source

    class Api:
        def resolve_assigned_accountant(self, login_account=None):
            return YdzAssignedAccountant.from_environment(YDZ_CREATE_ENVIRONMENTS["inte"])

        def query_existing_customer(self, tax_no):
            return None

    class Bridge:
        def __init__(self):
            self.calls = []

        def ensure_integration_private_phone(self, private_phone, dry_run=False):
            self.calls.append((private_phone, dry_run))
            return PrivacyPhonePrepareResult(
                private_phone=private_phone,
                status="DRY_RUN_EXISTS",
                inte_summary_count=1,
            )

    bridge = Bridge()
    creator = YdzCustomerCreator(
        ydz_api=Api(),
        source_resolver=Resolver(),
        env=YDZ_CREATE_ENVIRONMENTS["inte"],
        privacy_phone_bridge=bridge,
    )

    result = creator.process_tax_no(source.tax_no, dry_run=True)

    assert result.status == "DRY_RUN"
    assert result.privacy_phone_status == "DRY_RUN_EXISTS"
    assert bridge.calls == [("15500000001", True)]


def test_creator_skips_privacy_phone_prepare_for_manual_captcha_login():
    source = BackendCustomerSource(
        tax_no="91110116MAEETH8W2C",
        name="Example Co",
        area_code="11",
        area_name="Beijing",
        login_method="SDSRDX",
        privacy_no="15500000000",
        password="secret",
    )

    class Resolver:
        def resolve(self, tax_no, ydz_api):
            return source

    class Api:
        def resolve_assigned_accountant(self, login_account=None):
            return YdzAssignedAccountant.from_environment(YDZ_CREATE_ENVIRONMENTS["inte"])

        def query_existing_customer(self, tax_no):
            return None

    class Bridge:
        def ensure_integration_private_phone(self, private_phone, dry_run=False):
            raise AssertionError("manual captcha login should not prepare privacy-phone data")

    creator = YdzCustomerCreator(
        ydz_api=Api(),
        source_resolver=Resolver(),
        env=YDZ_CREATE_ENVIRONMENTS["inte"],
        privacy_phone_bridge=Bridge(),
    )

    result = creator.process_tax_no(source.tax_no, dry_run=True)

    assert result.status == "DRY_RUN"
    assert result.privacy_phone_status == ""


def test_creator_fails_integration_customer_when_privacy_phone_prepare_fails():
    source = BackendCustomerSource(
        tax_no="91110116MAEETH8W2C",
        name="Example Co",
        area_code="11",
        area_name="Beijing",
        login_method="YSHDL",
        privacy_no="15500000001",
        password="secret",
    )

    class Resolver:
        def resolve(self, tax_no, ydz_api):
            return source

    class Bridge:
        def ensure_integration_private_phone(self, private_phone, dry_run=False):
            return PrivacyPhonePrepareResult(
                private_phone=private_phone,
                status="FAILED",
                errors=["integration pull failed"],
            )

    creator = YdzCustomerCreator(
        ydz_api=type(
            "Api",
            (),
            {
                "resolve_assigned_accountant": lambda self, login_account=None: YdzAssignedAccountant.from_environment(
                    YDZ_CREATE_ENVIRONMENTS["inte"]
                )
            },
        )(),
        source_resolver=Resolver(),
        env=YDZ_CREATE_ENVIRONMENTS["inte"],
        privacy_phone_bridge=Bridge(),
    )

    result = creator.process_tax_no(source.tax_no)

    assert result.status == "FAILED"
    assert result.privacy_phone_status == "FAILED"
    assert "integration pull failed" in result.errors[0]


def test_wait_for_ydz_page_retries_transient_navigation_context_loss():
    env = YDZ_CREATE_ENVIRONMENTS["inte"]

    class Page:
        url = env.default_work_url

        def is_closed(self):
            return False

    class Context:
        pages = [Page()]

    calls = {"count": 0}

    class FakeApi:
        def __init__(self, page, env):
            self.page = page
            self.env = env

        def context(self):
            calls["count"] += 1
            if calls["count"] == 1:
                raise PlaywrightError("Execution context was destroyed, most likely because of a navigation")
            return {"ready": True}

    with patch("src.ydz.customer_creation.YdzCustomerApi", FakeApi), patch(
        "src.ydz.customer_creation.time.sleep",
        lambda _seconds: None,
    ):
        page = wait_for_ydz_page(Context(), env, timeout=1)

    assert page is not None
    assert calls["count"] == 2


if __name__ == "__main__":
    for name, func in sorted(globals().items()):
        if name.startswith("test_") and callable(func):
            func()
    print("All ydz customer creation tests passed!")
