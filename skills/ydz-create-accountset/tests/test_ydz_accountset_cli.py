from __future__ import annotations

import ast
from datetime import datetime
import importlib.util
import os
from pathlib import Path
import unittest
from unittest.mock import patch


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "ydz_accountset_cli.py"
SPEC = importlib.util.spec_from_file_location("ydz_accountset_cli", MODULE_PATH)
cli = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
import sys

sys.modules[SPEC.name] = cli
SPEC.loader.exec_module(cli)


class YdzAccountSetCliTests(unittest.TestCase):
    def test_split_tax_numbers_deduplicates_and_accepts_chinese_comma(self):
        result = cli.split_tax_numbers(["91110116MAEETH8W2C， 91110116MAEETH8W2C", "91350105062259341P"])

        self.assertEqual(result, ["91110116MAEETH8W2C", "91350105062259341P"])

    def test_split_tax_numbers_strips_utf8_bom(self):
        result = cli.split_tax_numbers(["\ufeff91330YYJ3200684"])

        self.assertEqual(result, ["91330YYJ3200684"])

    def test_manual_verification_marker_is_stable_for_host_parsing(self):
        self.assertEqual(cli.MANUAL_VERIFICATION_REQUIRED_MARKER, "MANUAL_VERIFICATION_REQUIRED")

    def test_login_method_text_maps_to_backend_code(self):
        self.assertEqual(cli.normalize_login_method("税局隐私号登录"), "YSHDL")
        self.assertEqual(cli.normalize_login_method("税局隐私号-代理登录"), "DLYW-YSHDL")
        self.assertEqual(cli.normalize_login_method("税局手工录入验证码登录"), "SDSRDX")
        self.assertEqual(cli.normalize_login_method("税局手工录入验证码-代理登录"), "DLYW-SDSRDX")
        self.assertEqual(cli.normalize_login_method("DLYW-YSHDL"), "DLYW-YSHDL")
        self.assertEqual(cli.normalize_login_method("DLYW-SDSRDX"), "DLYW-SDSRDX")

    def test_proxy_tax_info_payload_uses_proxy_site_login_name(self):
        source = cli.BackendSource(
            tax_no="91110116MAEETH8W2C",
            name="Example Co",
            area_code="11",
            area_name="北京",
            login_method="DLYW-YSHDL",
            proxy_tax_no="91110116PROXY0001",
            privacy_no="15500000000",
            password="dummy-password",
        )

        payload = cli.build_tax_info_payload(source, "100", "200")

        self.assertEqual(payload["taxInfoDTO"]["cLoginMethodEnum"], "DLYW-YSHDL")
        self.assertEqual(payload["taxInfoDTO"]["cSiteLoginName"], "91110116PROXY0001")
        self.assertEqual(payload["taxInfoDTO"]["cTaxPreparerName"], "15500000000")
        self.assertEqual(payload["taxInfoDTO"]["cTaxPreparerPwd"], "dummy-password")

    def test_manual_captcha_tax_info_payload_uses_phone_and_proxy(self):
        source = cli.BackendSource(
            tax_no="91110116MAEETH8W2C",
            name="Example Co",
            area_code="11",
            area_name="Beijing",
            login_method="DLYW-SDSRDX",
            proxy_tax_no="91110116PROXY0001",
            privacy_no="15500000000",
            password="dummy-password",
        )

        tax_info = cli.build_tax_info_payload(source, "100", "200")["taxInfoDTO"]
        create_payload = cli.build_customer_create_payload(source, cli.YDZ_ENVIRONMENTS["inte"], cli.YdzDefaults())

        self.assertEqual(tax_info["cLoginMethodEnum"], "DLYW-SDSRDX")
        self.assertEqual(tax_info["cSiteLoginName"], "91110116PROXY0001")
        self.assertEqual(tax_info["cTaxPreparerName"], "15500000000")
        self.assertEqual(tax_info["cTaxPreparerPwd"], "dummy-password")
        self.assertEqual(create_payload["taxLoginMethodEnum"], "DLYW-SDSRDX")
        self.assertEqual(create_payload["taxSystemUserName"], "91110116PROXY0001")
        self.assertEqual(create_payload["realAccount"], "15500000000")

    def test_backend_row_filter_accepts_only_accountset_login_methods(self):
        self.assertTrue(
            cli.backend_row_has_supported_login(
                {
                    "loginJson": {
                        "cLoginMethodEnum": "SDSRDX",
                        "cTaxPreparerName": "15500000000",
                        "cTaxPreparerPwd": "dummy-password",
                    }
                }
            )
        )
        self.assertTrue(
            cli.backend_row_has_supported_login(
                {
                    "loginJson": {
                        "cLoginMethodEnum": "DLYW-SDSRDX",
                        "cSiteLoginName": "91110116PROXY0001",
                        "cTaxPreparerName": "15500000000",
                        "cTaxPreparerPwd": "dummy-password",
                    }
                }
            )
        )
        self.assertFalse(
            cli.backend_row_has_supported_login(
                {"loginJson": {"cLoginMethodEnum": "SBZMDL", "cTaxPreparerName": "account"}}
            )
        )

    def test_non_proxy_tax_info_payload_leaves_site_login_name_empty(self):
        source = cli.BackendSource(
            tax_no="91110116MAEETH8W2C",
            name="Example Co",
            area_code="11",
            area_name="北京",
            login_method="YSHDL",
            proxy_tax_no="91110116PROXY0001",
            privacy_no="15500000000",
            password="dummy-password",
        )

        self.assertEqual(cli.build_tax_info_payload(source, "100", "200")["taxInfoDTO"]["cSiteLoginName"], "")

    def test_customer_create_payload_contains_environment_defaults(self):
        source = cli.BackendSource(
            tax_no="91110116MAEETH8W2C",
            name="Example Co",
            area_code="11",
            area_name="北京",
            login_method="DLYW-YSHDL",
            proxy_tax_no="91110116PROXY0001",
            privacy_no="15500000000",
            password="dummy-password",
        )

        payload = cli.build_customer_create_payload(source, cli.YDZ_ENVIRONMENTS["inte"], cli.YdzDefaults())

        self.assertEqual(payload["accountBook"]["openingPeriod"], "202501")
        self.assertEqual(payload["accountBook"]["taxpayerTypeEnum"], "SMALL_TAXPAYER")
        self.assertEqual(payload["taxIndustryId"], "11079")
        self.assertEqual(payload["accountantEmployeeId"], "61000431181")
        self.assertEqual(payload["custName"], source.name)
        self.assertEqual(payload["corpName"], source.name)
        self.assertEqual(payload["taxSystemUserName"], source.proxy_tax_no)

    def test_customer_create_payload_accepts_resolved_accountant_id(self):
        source = cli.BackendSource(
            tax_no="91110116MAEETH8W2C",
            name="Example Co",
            area_code="11",
            area_name="Beijing",
            login_method="YSHDL",
            privacy_no="15500000000",
            password="dummy-password",
        )

        payload = cli.build_customer_create_payload(
            source,
            cli.YDZ_ENVIRONMENTS["inte"],
            cli.YdzDefaults(),
            accountant_employee_id="61000999999",
        )

        self.assertEqual(payload["accountantEmployeeId"], "61000999999")

    def test_ydz_api_resolves_accountant_by_login_mobile_from_real_employee_shape(self):
        env = cli.YDZ_ENVIRONMENTS["inte"]
        auth_context = cli.build_ydz_auth_context(
            env,
            iframe_token="iframe-token",
            cia_token="cia-token",
            work_url=env.default_work_url,
            user_id="61000411111",
        )
        api = cli.YdzApi(None, env, auth_context=auth_context)

        def fake_get_json(endpoint):
            self.assertEqual(endpoint, "/trans/easyacctg/employee/getChildEmpListByUserId")
            return {
                "data": [
                    {
                        "userId": "61000400000",
                        "name": "admin",
                        "mobile": "15500000000",
                        "roleTypeEnum": "EASYACCTG_ADMIN",
                    },
                    {
                        "userId": "61000411111",
                        "name": "matched",
                        "mobile": "15500000000",
                        "roleTypeEnum": "ACCOUNTANT",
                    },
                ]
            }

        with patch.object(api, "get_json", fake_get_json):
            accountant = api.resolve_assigned_accountant("15500000000")

        self.assertEqual(accountant.employee_id, "61000411111")
        self.assertEqual(accountant.name, "matched")
        self.assertEqual(accountant.mobile, "15500000000")
        self.assertEqual(accountant.source, "login_mobile")

    def test_ydz_api_resolves_accountant_by_env_default_when_lookup_fails(self):
        env = cli.YDZ_ENVIRONMENTS["inte"]
        auth_context = cli.build_ydz_auth_context(
            env,
            iframe_token="iframe-token",
            cia_token="cia-token",
            work_url=env.default_work_url,
        )
        api = cli.YdzApi(None, env, auth_context=auth_context)

        with patch.object(api, "get_json", side_effect=cli.AccountSetError("temporary")):
            accountant = api.resolve_assigned_accountant("15500000000")

        self.assertEqual(accountant.employee_id, env.accountant_id)
        self.assertEqual(accountant.name, env.accountant_name)
        self.assertEqual(accountant.source, "env_default")

    def test_extract_employee_rows_handles_nested_api_data(self):
        payload = {"data": {"employeeList": [{"userId": "1", "mobile": "15500000000"}]}}

        self.assertEqual(cli.extract_employee_rows(payload), [{"userId": "1", "mobile": "15500000000"}])

    def test_privacy_phone_payloads_match_online_and_integration_contracts(self):
        self.assertEqual(cli.build_inte_privacy_summary_payload("15500000001"), {"privatePhone": "15500000001"})
        self.assertEqual(cli.build_privacy_summary_payload("15500000001")["privatePhone"], "15500000001")
        self.assertEqual(cli.build_privacy_detail_payload("15500000001", "123")["orgId"], "123")

    def test_public_result_does_not_expose_password_value(self):
        source = cli.BackendSource(
            tax_no="91110116MAEETH8W2C",
            name="Example Co",
            area_code="11",
            area_name="北京",
            login_method="YSHDL",
            privacy_no="15500000000",
            password="dummy-password",
        )

        public = source.public_dict()

        self.assertTrue(public["hasPassword"])
        self.assertNotIn("password", public)
        self.assertNotIn("dummy-password", str(public))

    def test_backend_source_lookup_splits_large_lookback_windows(self):
        tax_no = "91110116MAEETH8W2C"
        calls = []

        class AdminQuery:
            def query_tasks(self, start_time, end_time, **_kwargs):
                calls.append((start_time, end_time))
                assert (end_time - start_time).total_seconds() <= 40 * 24 * 60 * 60
                if len(calls) == 3:
                    return [
                        {
                            "id": "task-3",
                            "createdStamp": "3",
                            "loginJson": {
                                "cLoginMethodEnum": "SDSRDX",
                                "cTaxPreparerName": "15500000000",
                                "cTaxPreparerPwd": "dummy-password",
                            },
                        }
                    ]
                return []

        resolver = cli.SourceResolver(AdminQuery(), lookback_days=[90])

        row = resolver._latest_backend_row(tax_no)

        self.assertEqual(row["id"], "task-3")
        self.assertEqual(len(calls), 3)

    def test_verification_helpers_match_expected_customer_and_tax_info(self):
        env = cli.YDZ_ENVIRONMENTS["inte"]
        defaults = cli.YdzDefaults()
        source = cli.BackendSource(
            tax_no="91110116MAEETH8W2C",
            name="Example Co",
            area_code="11",
            area_name="北京",
            login_method="YSHDL",
            privacy_no="15500000000",
            password="dummy-password",
        )
        customer = {
            "taxNo": source.tax_no,
            "custName": source.name,
            "corpName": source.name,
            "taxIndustryId": defaults.tax_industry_id,
            "taxpayerTypeEnum": defaults.taxpayer_type,
            "accountantEmployeeId": env.accountant_id,
            "accountBook": {"openingPeriod": defaults.opening_period},
        }
        tax_info = {
            "cLoginMethodEnum": "YSHDL",
            "cSiteLoginName": "",
            "cTaxPreparerName": "15500000000",
            "cTaxPreparerPwd": "dummy-password",
        }

        self.assertTrue(cli.verify_customer_info(customer, source, env, defaults))
        self.assertFalse(cli.verify_customer_info(customer, source, env, defaults, accountant_employee_id="61000999999"))
        self.assertTrue(cli.verify_tax_info(source, tax_info))

    def test_area_fallback_supports_region_names_and_tax_no_prefix(self):
        self.assertEqual(cli.fallback_area_code("北京", "91110116MAEETH8W2C"), "11")
        self.assertEqual(cli.fallback_area_code("厦门", "91350206MA31GRNX01"), "3502")
        self.assertEqual(cli.fallback_area_code("", "91150104MA0N04YR6D"), "15")

    def test_login_command_is_registered_and_auto_login_is_default(self):
        args = cli.parse_args(["login", "--env", "inte"])

        self.assertEqual(args.command, "login")
        self.assertFalse(args.skip_auto_login)
        self.assertEqual(cli.resolved_ydz_auth_mode(args), "auto")

    def test_create_command_can_select_token_auth_mode(self):
        args = cli.parse_args(["create", "--env", "inte", "--tax-no", "91110116MAEETH8W2C", "--ydz-auth-mode", "token"])

        self.assertEqual(args.command, "create")
        self.assertEqual(args.ydz_auth_mode, "token")

    def test_create_command_can_select_backend_token_auth_mode(self):
        args = cli.parse_args(["create", "--env", "inte", "--tax-no", "91110116MAEETH8W2C", "--backend-auth-mode", "token"])

        self.assertEqual(args.command, "create")
        self.assertEqual(args.backend_auth_mode, "token")
        self.assertEqual(cli.resolved_backend_auth_mode(args), "token")

    def test_create_command_can_select_password_auth_mode(self):
        args = cli.parse_args(["create", "--env", "inte", "--tax-no", "91110116MAEETH8W2C", "--ydz-auth-mode", "password"])

        self.assertEqual(args.command, "create")
        self.assertEqual(args.ydz_auth_mode, "password")

    def test_create_command_can_select_auto_auth_mode(self):
        args = cli.parse_args(["create", "--env", "inte", "--tax-no", "91110116MAEETH8W2C", "--ydz-auth-mode", "auto"])

        self.assertEqual(args.command, "create")
        self.assertEqual(args.ydz_auth_mode, "auto")

    def test_create_command_can_select_manual_source_mode(self):
        args = cli.parse_args(
            [
                "create",
                "--env",
                "inte",
                "--manual-source-env",
                "--skip-privacy-phone-sync",
            ]
        )

        self.assertEqual(args.command, "create")
        self.assertTrue(args.manual_source_env)
        self.assertTrue(args.skip_privacy_phone_sync)

    def test_manual_source_env_adds_tax_number_and_source_fields(self):
        args = cli.parse_args(["create", "--env", "inte", "--manual-source-env"])
        with patch.dict(
            os.environ,
            {
                "YDZ_MANUAL_TAX_NO": "91110116maeeth8w2c",
                "YDZ_MANUAL_CUSTOMER_NAME": "Manual Co",
                "YDZ_MANUAL_AREA_NAME": "Beijing",
                "YDZ_MANUAL_LOGIN_METHOD": "DLYW-YSHDL",
                "YDZ_MANUAL_PROXY_TAX_NO": "91110116PROXY0001",
                "YDZ_MANUAL_PRIVACY_NO": "15500000000",
                "YDZ_MANUAL_PASSWORD": "manual-secret",
            },
            clear=False,
        ):
            tax_numbers = cli.read_tax_numbers(args)
            source = cli.manual_source_from_env()

        self.assertEqual(tax_numbers, ["91110116MAEETH8W2C"])
        self.assertEqual(source.tax_no, "91110116MAEETH8W2C")
        self.assertEqual(source.name, "Manual Co")
        self.assertEqual(source.login_method, "DLYW-YSHDL")
        self.assertEqual(source.proxy_tax_no, "91110116PROXY0001")
        self.assertEqual(source.privacy_no, "15500000000")
        self.assertEqual(source.backend_task_id, "manual")
        self.assertNotIn("manual-secret", str(source.public_dict()))

    def test_manual_creator_skips_integration_privacy_phone_prepare(self):
        source = cli.BackendSource(
            tax_no="91110116MAEETH8W2C",
            name="Manual Co",
            area_code="11",
            area_name="Beijing",
            login_method="YSHDL",
            privacy_no="15500000000",
            password="manual-secret",
            backend_task_id="manual",
        )

        class Api:
            def resolve_assigned_accountant(self, login_account=None):
                return cli.AssignedAccountant.from_environment(cli.YDZ_ENVIRONMENTS["inte"])

            def query_existing_customer(self, tax_no):
                self.tax_no = tax_no
                return None

        creator = cli.Creator(
            Api(),
            cli.ManualSourceResolver(source),
            cli.YDZ_ENVIRONMENTS["inte"],
            cli.YdzDefaults(),
            privacy_phone_bridge=None,
            prepare_privacy_phone=False,
        )

        result = creator.process_tax_no(source.tax_no, dry_run=True)

        self.assertEqual(result.status, "DRY_RUN")
        self.assertEqual(result.action, "would_create")
        self.assertEqual(result.backend_task_id, "manual")
        self.assertEqual(result.errors, [])

    def test_manual_resolver_can_use_requested_tax_number_and_normalizes_login_method(self):
        source = cli.BackendSource(
            tax_no="",
            name="Manual Co",
            area_code="",
            area_name="Beijing",
            login_method="dlyw-yshdl",
            proxy_tax_no="91110116PROXY0001",
            privacy_no="15500000000",
            password="manual-secret",
        )

        class Api:
            def query_tax_geo(self, tax_no):
                self.tax_no = tax_no
                return "", ""

        resolved = cli.ManualSourceResolver(source).resolve("91110116MAEETH8W2C", Api())

        self.assertEqual(resolved.tax_no, "91110116MAEETH8W2C")
        self.assertEqual(resolved.login_method, "DLYW-YSHDL")
        self.assertEqual(resolved.area_code, "11")
        self.assertEqual(resolved.backend_task_id, "manual")

    def test_chanjet_password_encrypts_without_plaintext(self):
        encrypted = cli.chanjet_rsa_encrypt("secret-password")

        self.assertTrue(encrypted)
        self.assertNotIn("secret-password", encrypted)
        self.assertEqual(len(encrypted), 172)

    def test_integration_login_captcha_defaults_to_666666(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(cli.configured_ydz_login_captcha(cli.YDZ_ENVIRONMENTS["inte"]), "666666")
            self.assertEqual(cli.configured_ydz_login_captcha(cli.YDZ_ENVIRONMENTS["prod"]), "")

    def test_integration_login_captcha_can_be_overridden(self):
        with patch.dict(os.environ, {"YDZ_INTE_LOGIN_CAPTCHA": "123456"}, clear=True):
            self.assertEqual(cli.configured_ydz_login_captcha(cli.YDZ_ENVIRONMENTS["inte"]), "123456")

    def test_password_login_uses_captcha_verify_token_before_account_login(self):
        class Client(cli.ChanjetPasswordAuthClient):
            verify_args = None
            login_args = None

            def _open_login_page(self):
                return None

            def _get_auth_code(self):
                return "auth-code"

            def _account_verify(self, username, password, captcha_code):
                self.verify_args = (username, password, captcha_code)
                return {"result": True, "verifyToken": "captcha-token"}

            def _account_login(self, username, password, auth_code, verify_token):
                self.login_args = (username, password, auth_code, verify_token)
                return {"result": False, "errorCode": "expected-stop"}

        client = Client(cli.YDZ_ENVIRONMENTS["inte"])

        result = client.login("user", "pass", captcha_code="666666")

        self.assertEqual(client.verify_args, ("user", "pass", "666666"))
        self.assertEqual(client.login_args, ("user", "pass", "auth-code", "captcha-token"))
        self.assertEqual(result.status, cli.PASSWORD_LOGIN_FAILED)

    def test_password_login_classifies_manual_verification(self):
        client = cli.ChanjetPasswordAuthClient(cli.YDZ_ENVIRONMENTS["inte"])

        result = client._classify_login_response(
            {"result": False, "captchaResult": False, "errorCode": "访问拒绝"},
            work_url=None,
        )

        self.assertEqual(result.status, cli.PASSWORD_LOGIN_MANUAL_VERIFICATION_REQUIRED)
        self.assertIsNone(result.auth_context)

    def test_configured_ydz_password_context_reports_missing_credentials(self):
        with patch.dict(os.environ, {"YDZ_INTE_USERNAME": "", "YDZ_INTE_PASSWORD": ""}, clear=False):
            context, status = cli.configured_ydz_password_context(cli.YDZ_ENVIRONMENTS["inte"])

        self.assertIsNone(context)
        self.assertEqual(status["status"], cli.PASSWORD_LOGIN_FAILED)
        self.assertFalse(status["hasAuthContext"])

    def test_ydz_api_static_token_context_builds_request_url(self):
        env = cli.YDZ_ENVIRONMENTS["inte"]
        auth_context = cli.build_ydz_auth_context(
            env,
            iframe_token="iframe-token",
            cia_token="cia-token",
            work_url=env.default_work_url,
        )
        api = cli.YdzApi(None, env, auth_context=auth_context)
        context = api.context()
        url = api._absolute_url("/trans/easyacctg/customer/queryTaxGeoByTaxNo?taxNo=91110116MAEETH8W2C", context)

        self.assertEqual(context["iframeToken"], "iframe-token")
        self.assertEqual(context["ciaToken"], "cia-token")
        self.assertIn("user_req_userid=" + env.user_id, url)
        self.assertIn("user_req_orgid=" + env.org_id, url)

    def test_configured_ydz_token_context_reads_environment_specific_values(self):
        env = cli.YDZ_ENVIRONMENTS["inte"]
        with patch.dict(
            os.environ,
            {
                "YDZ_INTE_IFRAME_TOKEN": "iframe-token",
                "YDZ_INTE_CIA_TOKEN": "cia-token",
                "YDZ_INTE_WORK_URL": env.default_work_url,
                "YDZ_INTE_ORG_ID": env.org_id,
                "YDZ_INTE_USER_ID": env.user_id,
                "YDZ_INTE_USER_MOBILE": "15500000000",
                "YDZ_INTE_USER_NAME": "user7793",
            },
            clear=False,
        ):
            context = cli.configured_ydz_token_context(env)

        self.assertIsNotNone(context)
        self.assertEqual(context["iframeToken"], "iframe-token")
        self.assertEqual(context["ciaToken"], "cia-token")
        self.assertEqual(context["orgId"], env.org_id)
        self.assertEqual(context["userId"], env.user_id)
        self.assertEqual(context["userMobile"], "15500000000")
        self.assertEqual(context["userName"], "user7793")

    def test_configured_credentials_read_env_without_exposing_password_in_status(self):
        with patch.dict(
            os.environ,
            {
                "YDZ_INTE_USERNAME": "test-user",
                "YDZ_INTE_PASSWORD": "secret-password",
                "YDZ_INTE_ENTERPRISE": "test-enterprise",
                "TAX_BACKEND_USERNAME": "backend-user",
                "TAX_BACKEND_PASSWORD": "backend-secret",
            },
            clear=False,
        ):
            ydz = cli.configured_ydz_credentials(cli.YDZ_ENVIRONMENTS["inte"])
            backend = cli.configured_backend_credentials()
            status = cli.env_secret_status("inte")

        self.assertEqual(ydz["username"], "test-user")
        self.assertEqual(ydz["password"], "secret-password")
        self.assertEqual(ydz["enterprise"], "test-enterprise")
        self.assertEqual(backend["username"], "backend-user")
        self.assertEqual(backend["password"], "backend-secret")
        self.assertTrue(status["YDZ_INTE_PASSWORD"])
        self.assertNotIn("secret-password", str(status))
        self.assertNotIn("backend-secret", str(status))

    def test_ydz_login_url_uses_environment_public_url_as_callback(self):
        self.assertIn("ydz.inte.chanjet.com", cli.ydz_login_url(cli.YDZ_ENVIRONMENTS["inte"]))
        self.assertIn("login.chanjet.com", cli.ydz_login_url(cli.YDZ_ENVIRONMENTS["prod"]))

    def test_backend_forbidden_page_is_not_usable_session(self):
        class Page:
            def evaluate(self, _script):
                return "报税公共服务后台管理系统\n403\n抱歉，您当前登录的账号无权访问该页面"

        self.assertTrue(cli.backend_page_forbidden(Page()))

    def test_ydz_slider_challenge_is_reported_as_manual_verification(self):
        class Page:
            def evaluate(self, _script):
                return "账号密码登录\n请按住滑块，拖动到最右边\n登录"

        self.assertTrue(cli.ydz_login_requires_manual_verification(Page()))

    def test_ydz_public_entry_requires_logged_in_public_page(self):
        class Page:
            def __init__(self, text):
                self.text = text

            def evaluate(self, _script):
                return self.text

        self.assertTrue(cli.ydz_public_entry_available(Page("用户7793\n进入易代账")))
        self.assertFalse(cli.ydz_public_entry_available(Page("登录注册\n进入易代账")))

    def test_ydz_redirect_vm_page_opens_workbench_url(self):
        env = cli.YDZ_ENVIRONMENTS["inte"]

        class Page:
            url = "https://passport.inte.chanjet.com/vm/redirectVM?appName=ydzee&productId=260"
            goto_url = ""
            clicked = False

            def is_closed(self):
                return False

            def evaluate(self, _script):
                self.clicked = True
                return True

            def wait_for_timeout(self, _ms):
                return None

            def goto(self, url, **_kwargs):
                self.goto_url = url

        page = Page()

        class Context:
            pages = [page]

        with patch.object(cli, "wait_for_ydz_page", lambda *_args, **_kwargs: None):
            self.assertTrue(cli.is_ydz_redirect_vm_page(page, env))
            self.assertTrue(cli.open_ydz_redirect_vm_workbench(Context(), env, env.default_work_url))

        self.assertTrue(page.clicked)
        self.assertEqual(page.goto_url, env.default_work_url)

    def test_workbench_app_list_url_uses_environment_org_id(self):
        env = cli.YDZ_ENVIRONMENTS["prod"]

        self.assertEqual(
            cli.workbench_app_list_url(env),
            "https://workbench.chanjet.com/v2/myapp/list?orgId=90011827608",
        )

    def test_workbench_app_list_entry_opens_target_org_and_clicks_ydz(self):
        env = cli.YDZ_ENVIRONMENTS["prod"]
        ready_page = object()

        class Page:
            url = ""

            def __init__(self):
                self.goto_url = ""
                self.clicked = False

            def is_closed(self):
                return False

            def goto(self, url, **_kwargs):
                self.goto_url = url
                self.url = url

            def wait_for_timeout(self, _ms):
                return None

            def evaluate(self, script):
                self.clicked = "进入应用" in script or "\\u8fdb\\u5165\\u5e94\\u7528" in script
                return {"clicked": True, "text": "易代账查看详情企业购买用户列表进入应用"}

        class Context:
            def __init__(self):
                self.pages = []

            def new_page(self):
                page = Page()
                self.pages.append(page)
                return page

        context = Context()
        with patch.object(cli, "wait_for_ydz_page", lambda *_args, **_kwargs: ready_page):
            result = cli.open_ydz_from_workbench_app_list(context, env, timeout=5)

        self.assertIs(result, ready_page)
        self.assertEqual(context.pages[0].goto_url, cli.workbench_app_list_url(env))
        self.assertTrue(context.pages[0].clicked)

    def test_chrome_launch_uses_automation_controlled_flag(self):
        text = MODULE_PATH.read_text(encoding="utf-8")

        self.assertIn("--enable-automation", cli.CHROME_AUTOMATION_STEALTH_ARGS)
        self.assertIn("--disable-blink-features=AutomationControlled", cli.CHROME_AUTOMATION_STEALTH_ARGS)
        self.assertIn("*CHROME_AUTOMATION_STEALTH_ARGS", text)

    def test_connect_chrome_over_cdp_falls_back_when_requested_port_is_incompatible(self):
        args = cli.parse_args(["create", "--env", "inte", "--tax-no", "91110116MAEETH8W2C"])
        calls: list[str] = []
        launches: list[tuple[int, str]] = []

        class Chromium:
            def connect_over_cdp(self, url):
                calls.append(url)
                if url.endswith(":9222"):
                    raise RuntimeError("Chrome CDP connection failed: missing --enable-automation")
                return "browser"

        class Playwright:
            chromium = Chromium()

        def fake_launch(passed_args, _env):
            launches.append((passed_args.cdp_port, passed_args.user_data_dir))

        with patch.object(cli, "launch_chrome_if_needed", fake_launch), patch.object(
            cli, "cdp_candidate_ports", lambda preferred: [preferred, 9333]
        ):
            browser = cli.connect_chrome_over_cdp(Playwright(), args, cli.YDZ_ENVIRONMENTS["inte"])

        self.assertEqual(browser, "browser")
        self.assertEqual(calls, ["http://127.0.0.1:9222", "http://127.0.0.1:9333"])
        self.assertEqual(launches[0][0], 9222)
        self.assertEqual(launches[1][0], 9333)
        self.assertTrue(launches[1][1].endswith("browser_profile_9333"))
        self.assertEqual(args.cdp_port, 9333)
        self.assertTrue(args.user_data_dir.endswith("browser_profile_9333"))

    def test_playwright_is_lazy_optional_dependency_with_clear_hint(self):
        tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
        top_level_playwright_imports: list[str] = []
        for node in tree.body:
            if isinstance(node, ast.Import):
                top_level_playwright_imports.extend(alias.name for alias in node.names if alias.name.startswith("playwright"))
            elif isinstance(node, ast.ImportFrom) and str(node.module or "").startswith("playwright"):
                top_level_playwright_imports.append(str(node.module))

        self.assertEqual(top_level_playwright_imports, [])

        real_import = __import__

        def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "playwright.sync_api":
                raise ModuleNotFoundError("No module named 'playwright'", name="playwright")
            return real_import(name, globals, locals, fromlist, level)

        with patch("builtins.__import__", side_effect=fake_import):
            with self.assertRaises(SystemExit) as raised:
                cli.load_sync_playwright()

        self.assertIn("only required for browser/CDP login fallback", str(raised.exception))

    def test_backend_login_does_not_reference_missing_ydz_env_variable(self):
        text = MODULE_PATH.read_text(encoding="utf-8")
        block = text.split("def ensure_backend_login", 1)[1].split("def ensure_login_sessions", 1)[0]

        self.assertNotIn("configured_ydz_login_captcha(env)", block)

    def test_browser_mode_result_header_includes_accountant_columns(self):
        text = MODULE_PATH.read_text(encoding="utf-8")

        self.assertIn(
            "status\\taction\\ttaxNo\\tname\\tcustId\\tarea\\tloginMethod\\taccountantId\\taccountantSource\\tprivacyPhone\\tverification\\terrors",
            text,
        )
        self.assertNotIn(
            "status\\taction\\ttaxNo\\tname\\tcustId\\tarea\\tloginMethod\\tprivacyPhone\\tverification\\terrors",
            text,
        )

    def test_wait_for_ydz_page_retries_transient_navigation_context_loss(self):
        env = cli.YDZ_ENVIRONMENTS["inte"]

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
                    raise RuntimeError("Execution context was destroyed, most likely because of a navigation")
                return {"ready": True}

        with patch.object(cli, "YdzApi", FakeApi), patch.object(cli.time, "sleep", lambda _seconds: None):
            page = cli.wait_for_ydz_page(Context(), env, timeout=1)

        self.assertIsNotNone(page)
        self.assertEqual(calls["count"], 2)

    def test_privacy_phone_bridge_removes_token_for_integration_api_and_pulls_missing_phone(self):
        class Page:
            url = cli.PUBLIC_MANAGE_URL

            def is_closed(self):
                return False

            def evaluate(self, _script):
                return {"authorization": "Bearer token", "token": "access-token"}

            def wait_for_load_state(self, *_args, **_kwargs):
                return None

            def wait_for_timeout(self, _ms):
                return None

        class Context:
            pages = [Page()]

        class Response:
            status_code = 200

            def __init__(self, payload):
                self.payload = payload

            def raise_for_status(self):
                return None

            def json(self):
                return self.payload

        def ok(data):
            return {"code": "200", "success": True, "msg": "OK", "data": data}

        calls = []
        inte_summary_count = {"value": 0}

        def fake_post(url, headers, json, timeout):
            calls.append(("POST", url, json, dict(headers)))
            if url == cli.INTE_PRIVACY_PHONE_SUMMARY_URL:
                self.assertEqual(json, {"privatePhone": "15500000001"})
                self.assertNotIn("token", headers)
                inte_summary_count["value"] += 1
                if inte_summary_count["value"] == 1:
                    return Response(ok({"content": []}))
                return Response(ok({"content": [{"orgId": "inte"}]}))
            if url == cli.PRIVACY_PHONE_SUMMARY_URL:
                return Response(ok({"content": [{"orgId": "prod"}]}))
            if url == cli.PRIVACY_PHONE_DETAIL_URL:
                return Response(ok({"content": [{"orgId": "prod", "privatePhone": "15500000001"}]}))
            raise AssertionError(url)

        def fake_get(url, headers, params, timeout):
            calls.append(("GET", url, params, dict(headers)))
            self.assertEqual(params, {"privatePhone": "15500000001"})
            if url == cli.INTE_PRIVACY_PHONE_PULL_URL:
                self.assertNotIn("token", headers)
            return Response(ok(None))

        with patch("requests.post", fake_post), patch("requests.get", fake_get):
            result = cli.PrivacyPhoneBridge(Context()).ensure_integration_private_phone("15500000001")

        self.assertEqual(result.status, "PULLED")
        self.assertTrue(result.copy_success)
        self.assertTrue(result.pull_success)
        self.assertTrue(any(call[0] == "GET" and call[1] == cli.PRIVACY_PHONE_COPY_URL for call in calls))

    def test_creator_prepares_integration_privacy_phone(self):
        source = cli.BackendSource(
            tax_no="91110116MAEETH8W2C",
            name="Example Co",
            area_code="11",
            area_name="鍖椾含",
            login_method="YSHDL",
            privacy_no="15500000001",
            password="dummy-password",
        )

        class Resolver:
            def resolve(self, tax_no, ydz_api):
                return source

        class Api:
            def resolve_assigned_accountant(self, login_account=None):
                return cli.AssignedAccountant.from_environment(cli.YDZ_ENVIRONMENTS["inte"])

            def query_existing_customer(self, tax_no):
                return None

        class Bridge:
            def __init__(self):
                self.calls = []

            def ensure_integration_private_phone(self, private_phone, dry_run=False):
                self.calls.append((private_phone, dry_run))
                return cli.PrivacyPhonePrepareResult(private_phone, "DRY_RUN_EXISTS", inte_summary_count=1)

        bridge = Bridge()
        creator = cli.Creator(Api(), Resolver(), cli.YDZ_ENVIRONMENTS["inte"], cli.YdzDefaults(), privacy_phone_bridge=bridge)

        result = creator.process_tax_no(source.tax_no, dry_run=True)

        self.assertEqual(result.status, "DRY_RUN")
        self.assertEqual(result.privacy_phone_status, "DRY_RUN_EXISTS")
        self.assertEqual(bridge.calls, [("15500000001", True)])

    def test_creator_skips_privacy_phone_prepare_for_manual_captcha_login(self):
        source = cli.BackendSource(
            tax_no="91110116MAEETH8W2C",
            name="Example Co",
            area_code="11",
            area_name="Beijing",
            login_method="SDSRDX",
            privacy_no="15500000000",
            password="dummy-password",
        )

        class Resolver:
            def resolve(self, tax_no, ydz_api):
                return source

        class Api:
            def resolve_assigned_accountant(self, login_account=None):
                return cli.AssignedAccountant.from_environment(cli.YDZ_ENVIRONMENTS["inte"])

            def query_existing_customer(self, tax_no):
                return None

        class Bridge:
            def ensure_integration_private_phone(self, private_phone, dry_run=False):
                raise AssertionError("manual captcha login should not prepare privacy-phone data")

        creator = cli.Creator(Api(), Resolver(), cli.YDZ_ENVIRONMENTS["inte"], cli.YdzDefaults(), privacy_phone_bridge=Bridge())

        result = creator.process_tax_no(source.tax_no, dry_run=True)

        self.assertEqual(result.status, "DRY_RUN")
        self.assertEqual(result.privacy_phone_status, "")

    def test_backend_login_url_uses_public_manage_callback(self):
        url = cli.backend_login_url()

        self.assertIn("login.chanjet.com", url)
        self.assertIn("public-manage.chanjet.com", url)

    def test_backend_query_uses_task_categories_without_task_type_id(self):
        captured: dict[str, object] = {}

        class Page:
            url = cli.PUBLIC_MANAGE_URL

            def is_closed(self):
                return False

            def evaluate(self, _script):
                return {"authorization": "Bearer token", "token": "access-token"}

            def wait_for_load_state(self, *_args, **_kwargs):
                return None

        class Context:
            pages = [Page()]

        class Response:
            status_code = 200

            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "code": "200",
                    "success": True,
                    "data": {
                        "content": [
                            {
                                "id": "task-1",
                                "taxNo": "911",
                                "createdStamp": 1,
                            }
                        ]
                    },
                }

        def fake_post(_url, headers, json, timeout):
            captured["headers"] = headers
            captured["payload"] = json
            captured["timeout"] = timeout
            return Response()

        with patch("requests.post", fake_post):
            rows = cli.AdminTaskQuery(Context()).query_tasks(
                start_time=datetime(2026, 5, 1),
                end_time=datetime(2026, 5, 26),
                tax_no="911",
            )

        payload = captured["payload"]
        self.assertEqual(payload["taskCategorys"], "2,3")
        self.assertNotIn("taskTypeId", payload)
        self.assertEqual(payload["status"], "SUCCESS")
        self.assertEqual(payload["taskStatus"], "SUCCESS")
        self.assertEqual(payload["loginType"], "YSHDL,DLYW-YSHDL,SDSRDX,DLYW-SDSRDX")
        self.assertEqual(rows[0]["id"], "task-1")

    def test_configured_backend_token_provider_reads_header_tokens(self):
        with patch.dict(
            os.environ,
            {
                "TAX_BACKEND_AUTHORIZATION": "backend-authorization",
                "TAX_BACKEND_ACCESS_TOKEN": "backend-access-token",
                "TAX_BACKEND_USER_ID": "backend-user-id",
            },
            clear=False,
        ):
            provider, status = cli.configured_backend_token_provider()

        self.assertIsNotNone(provider)
        tokens = provider.get_tokens()
        self.assertEqual(tokens.authorization, "backend-authorization")
        self.assertEqual(tokens.token, "backend-access-token")
        self.assertEqual(tokens.user_id, "backend-user-id")
        self.assertTrue(status["hasTokens"])
        self.assertNotIn("backend-access-token", str(status))

    def test_backend_query_can_use_token_provider_without_browser_context(self):
        captured: dict[str, object] = {}

        class Provider:
            def get_tokens(self, force_refresh=False):
                return cli.AdminAuthTokens("Bearer token", "access-token", source="test")

        class Response:
            status_code = 200

            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "code": "200",
                    "success": True,
                    "data": {"content": [{"id": "task-1", "taxNo": "911", "createdStamp": 1}]},
                }

        def fake_post(_url, headers, json, timeout):
            captured["headers"] = headers
            captured["payload"] = json
            return Response()

        with patch("requests.post", fake_post):
            rows = cli.AdminTaskQuery(token_provider=Provider()).query_tasks(
                start_time=datetime(2026, 5, 1),
                end_time=datetime(2026, 5, 26),
                tax_no="911",
            )

        self.assertEqual(rows[0]["id"], "task-1")
        self.assertEqual(captured["headers"]["authorization"], "Bearer token")

    def test_cli_does_not_import_project_modules(self):
        tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
        banned_prefixes = ("src", "scripts")
        offenders: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] in banned_prefixes:
                        offenders.append(alias.name)
            elif isinstance(node, ast.ImportFrom) and node.module:
                if node.module.split(".")[0] in banned_prefixes:
                    offenders.append(node.module)

        self.assertEqual(offenders, [])

    def test_skill_docs_do_not_depend_on_project_paths(self):
        skill_dir = MODULE_PATH.parents[1]
        docs = [skill_dir / "SKILL.md", *sorted((skill_dir / "references").glob("*.md"))]
        combined = "\n".join(path.read_text(encoding="utf-8") for path in docs)

        self.assertNotIn("tax_verify", combined)
        self.assertNotIn("scripts/ydz_create_customers.py", combined)
        self.assertNotIn("scripts\\ydz_create_customers.py", combined)
        self.assertNotIn("from src", combined)
        self.assertNotIn("import src", combined)


if __name__ == "__main__":
    unittest.main()
