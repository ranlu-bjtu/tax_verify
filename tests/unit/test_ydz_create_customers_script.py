import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts import ydz_create_customers as cli


def test_parse_args_auto_login_is_default():
    args = cli.parse_args(["--env", "inte", "--tax-no", "91110116MAEETH8W2C"])

    assert args.env == "inte"
    assert args.skip_auto_login is False
    assert cli.resolved_ydz_auth_mode(args) == "auto"


def test_parse_args_can_skip_auto_login_for_existing_session_debugging():
    args = cli.parse_args(["--env", "prod", "--tax-no", "91110116MAEETH8W2C", "--skip-auto-login"])

    assert args.env == "prod"
    assert args.skip_auto_login is True


def test_parse_args_can_select_token_auth_mode():
    args = cli.parse_args(["--env", "inte", "--tax-no", "91110116MAEETH8W2C", "--ydz-auth-mode", "token"])

    assert args.ydz_auth_mode == "token"


def test_parse_args_can_select_backend_token_auth_mode():
    args = cli.parse_args(["--env", "inte", "--tax-no", "91110116MAEETH8W2C", "--backend-auth-mode", "token"])

    assert args.backend_auth_mode == "token"
    assert cli.resolved_backend_auth_mode(args) == "token"


def test_parse_args_can_select_password_auth_mode():
    args = cli.parse_args(["--env", "inte", "--tax-no", "91110116MAEETH8W2C", "--ydz-auth-mode", "password"])

    assert args.ydz_auth_mode == "password"


def test_parse_args_can_select_auto_auth_mode():
    args = cli.parse_args(["--env", "inte", "--tax-no", "91110116MAEETH8W2C", "--ydz-auth-mode", "auto"])

    assert args.ydz_auth_mode == "auto"


def test_parse_args_login_only_can_target_backend_without_tax_no():
    args = cli.parse_args(["--env", "inte", "--login-only", "--login-target", "backend"])

    assert args.login_only is True
    assert args.login_target == "backend"
    assert args.tax_no == []


def test_configured_ydz_credentials_are_environment_specific():
    with patch.dict(
        os.environ,
        {
            "YDZ_INTE_USERNAME": "inte-user",
            "YDZ_INTE_PASSWORD": "inte-secret",
            "YDZ_INTE_ENTERPRISE": "inte-enterprise",
            "YDZ_PROD_USERNAME": "prod-user",
            "YDZ_PROD_PASSWORD": "prod-secret",
            "YDZ_PROD_ENTERPRISE": "prod-enterprise",
        },
        clear=False,
    ):
        inte = cli.configured_ydz_credentials(cli.YDZ_CREATE_ENVIRONMENTS["inte"])
        prod = cli.configured_ydz_credentials(cli.YDZ_CREATE_ENVIRONMENTS["prod"])

    assert inte["username"] == "inte-user"
    assert inte["password"] == "inte-secret"
    assert inte["enterprise"] == "inte-enterprise"
    assert prod["username"] == "prod-user"
    assert prod["password"] == "prod-secret"
    assert prod["enterprise"] == "prod-enterprise"


def test_configured_ydz_login_captcha_defaults_only_for_integration():
    with patch.dict(os.environ, {}, clear=True):
        assert cli.configured_ydz_login_captcha(cli.YDZ_CREATE_ENVIRONMENTS["inte"]) == "666666"
        assert cli.configured_ydz_login_captcha(cli.YDZ_CREATE_ENVIRONMENTS["prod"]) == ""


def test_configured_ydz_login_captcha_can_be_overridden():
    with patch.dict(os.environ, {"YDZ_INTE_LOGIN_CAPTCHA": "123456"}, clear=False):
        assert cli.configured_ydz_login_captcha(cli.YDZ_CREATE_ENVIRONMENTS["inte"]) == "123456"


def test_configured_ydz_token_context_reads_environment_specific_values():
    env = cli.YDZ_CREATE_ENVIRONMENTS["inte"]
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

    assert context is not None
    assert context["iframeToken"] == "iframe-token"
    assert context["ciaToken"] == "cia-token"
    assert context["orgId"] == env.org_id
    assert context["userId"] == env.user_id
    assert context["userMobile"] == "15500000000"
    assert context["userName"] == "user7793"


def test_configured_ydz_password_context_reports_missing_credentials_without_tokens():
    env = cli.YDZ_CREATE_ENVIRONMENTS["inte"]
    with patch.dict(os.environ, {"YDZ_INTE_USERNAME": "", "YDZ_INTE_PASSWORD": ""}, clear=False):
        context, status = cli.configured_ydz_password_context(env, timeout=1)

    assert context is None
    assert status["status"] == "FAILED"
    assert status["hasAuthContext"] is False
    assert "password" in status["message"].lower()


def test_configured_backend_credentials_read_tax_backend_vars():
    with patch.dict(
        os.environ,
        {
            "TAX_BACKEND_URL": "https://public-manage.example.test",
            "TAX_BACKEND_USERNAME": "backend-user",
            "TAX_BACKEND_PASSWORD": "backend-secret",
        },
        clear=False,
    ):
        creds = cli.configured_backend_credentials()

    assert creds == {
        "url": "https://public-manage.example.test",
        "username": "backend-user",
        "password": "backend-secret",
    }


def test_configured_backend_token_provider_reads_header_tokens_without_leaking_values():
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

    assert provider is not None
    tokens = provider.get_tokens()
    assert tokens.authorization == "backend-authorization"
    assert tokens.token == "backend-access-token"
    assert tokens.user_id == "backend-user-id"
    assert status["hasTokens"] is True
    assert "backend-access-token" not in str(status)


def test_ydz_login_url_uses_environment_specific_login_host():
    assert "ydz-login.inte.chanjet.com" in cli.ydz_login_url(cli.YDZ_CREATE_ENVIRONMENTS["inte"])
    assert "login.chanjet.com" in cli.ydz_login_url(cli.YDZ_CREATE_ENVIRONMENTS["prod"])


def test_backend_forbidden_page_is_not_usable_session():
    class Page:
        def evaluate(self, _script):
            return "报税公共服务后台管理系统\n403\n抱歉，您当前登录的账号无权访问该页面"

    assert cli.backend_page_forbidden(Page()) is True


def test_backend_login_url_uses_public_manage_callback():
    url = cli.backend_login_url()

    assert "login.chanjet.com" in url
    assert "public-manage.chanjet.com" in url


def test_backend_forbidden_page_detects_chinese_forbidden_text():
    class Page:
        def evaluate(self, _script):
            return "报税公共服务后台管理系统\n403\n抱歉，您当前登录的账号无权访问该页面"

    assert cli.backend_page_forbidden(Page()) is True


def test_ydz_slider_challenge_is_reported_as_manual_verification():
    class Page:
        def evaluate(self, _script):
            return "账号密码登录\n请按住滑块，拖动到最右边\n登录"

    assert cli.ydz_login_requires_manual_verification(Page()) is True


def test_manual_verification_marker_is_stable_for_workbench_parsing():
    assert cli.MANUAL_VERIFICATION_REQUIRED_MARKER == "MANUAL_VERIFICATION_REQUIRED"


def test_ydz_public_entry_requires_logged_in_public_page():
    class Page:
        def __init__(self, text):
            self.text = text

        def evaluate(self, _script):
            return self.text

    assert cli.ydz_public_entry_available(Page("用户7793\n进入易代账")) is True
    assert cli.ydz_public_entry_available(Page("登录注册\n进入易代账")) is False


def test_ydz_redirect_vm_page_opens_workbench_url():
    env = cli.YDZ_CREATE_ENVIRONMENTS["inte"]

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
        assert cli.is_ydz_redirect_vm_page(page, env) is True
        assert cli.open_ydz_redirect_vm_workbench(Context(), env, env.default_work_url) is True

    assert page.clicked is True
    assert page.goto_url == env.default_work_url


def test_workbench_app_list_url_uses_environment_org_id():
    env = cli.YDZ_CREATE_ENVIRONMENTS["prod"]

    assert cli.workbench_app_list_url(env) == "https://workbench.chanjet.com/v2/myapp/list?orgId=90011827608"


def test_workbench_app_list_entry_opens_target_org_and_clicks_ydz():
    env = cli.YDZ_CREATE_ENVIRONMENTS["prod"]
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

    assert result is ready_page
    assert context.pages[0].goto_url == cli.workbench_app_list_url(env)
    assert context.pages[0].clicked is True


def test_customer_creation_does_not_close_shared_cdp_browser():
    text = Path(cli.__file__).read_text(encoding="utf-8")

    assert "browser.close()" not in text


def test_chrome_launch_uses_automation_controlled_flag():
    text = Path(cli.__file__).read_text(encoding="utf-8")

    assert "--enable-automation" in cli.CHROME_AUTOMATION_STEALTH_ARGS
    assert "--disable-blink-features=AutomationControlled" in cli.CHROME_AUTOMATION_STEALTH_ARGS
    assert "*CHROME_AUTOMATION_STEALTH_ARGS" in text


def test_connect_chrome_over_cdp_falls_back_when_requested_port_is_incompatible():
    args = cli.parse_args(["--env", "inte", "--tax-no", "91110116MAEETH8W2C"])
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
        browser = cli.connect_chrome_over_cdp(Playwright(), args, cli.YDZ_CREATE_ENVIRONMENTS["inte"])

    assert browser == "browser"
    assert calls == ["http://127.0.0.1:9222", "http://127.0.0.1:9333"]
    assert launches[0][0] == 9222
    assert launches[1][0] == 9333
    assert launches[1][1].endswith("ydz_customer_create_9333")
    assert args.cdp_port == 9333
    assert args.user_data_dir.endswith("ydz_customer_create_9333")


def test_load_env_file_does_not_override_existing_values():
    with tempfile.TemporaryDirectory() as tmp:
        env_file = Path(tmp) / "ydz.env"
        env_file.write_text("YDZ_INTE_USERNAME=file-user\nYDZ_INTE_PASSWORD=file-secret\n", encoding="utf-8")
        with patch.dict(os.environ, {"YDZ_INTE_USERNAME": "existing-user"}, clear=False):
            os.environ.pop("YDZ_INTE_PASSWORD", None)

            cli.load_env_file(str(env_file))

            assert os.environ["YDZ_INTE_USERNAME"] == "existing-user"
            assert os.environ["YDZ_INTE_PASSWORD"] == "file-secret"


def test_read_tax_numbers_strips_utf8_bom_from_file():
    with tempfile.TemporaryDirectory() as tmp:
        tax_no_file = Path(tmp) / "tax_nos.txt"
        tax_no_file.write_text("91330YYJ3200684", encoding="utf-8-sig")
        args = cli.parse_args(["--env", "inte", "--tax-no-file", str(tax_no_file)])

        assert cli.read_tax_numbers(args) == ["91330YYJ3200684"]


def test_manual_source_env_adds_tax_number_and_source_fields():
    args = cli.parse_args(["--env", "inte", "--manual-source-env"])
    with patch.dict(
        os.environ,
        {
            "YDZ_MANUAL_TAX_NO": "91110116MAEETH8W2C",
            "YDZ_MANUAL_CUSTOMER_NAME": "Manual Co",
            "YDZ_MANUAL_AREA_NAME": "北京",
            "YDZ_MANUAL_LOGIN_METHOD": "税局隐私号登录",
            "YDZ_MANUAL_PRIVACY_NO": "15500000000",
            "YDZ_MANUAL_PASSWORD": "secret",
        },
        clear=False,
    ):
        assert cli.read_tax_numbers(args) == ["91110116MAEETH8W2C"]
        source = cli.manual_source_from_env()

    assert source.tax_no == "91110116MAEETH8W2C"
    assert source.name == "Manual Co"
    assert source.area_name == "北京"
    assert source.login_method == "税局隐私号登录"
    assert source.has_password is True if hasattr(source, "has_password") else bool(source.password)


def test_ensure_pages_open_can_skip_backend_for_manual_source():
    class Page:
        def __init__(self):
            self.url = ""

        def is_closed(self):
            return False

        def goto(self, url, **_kwargs):
            self.url = url

    class Context:
        def __init__(self):
            self.pages = []

        def new_page(self):
            page = Page()
            self.pages.append(page)
            return page

    context = Context()

    cli.ensure_pages_open(context, cli.YDZ_CREATE_ENVIRONMENTS["inte"], None, include_backend=False)

    assert len(context.pages) == 1
    assert cli.PUBLIC_MANAGE_MARKER not in context.pages[0].url


def test_backend_login_does_not_reference_missing_ydz_env_variable():
    text = Path(cli.__file__).read_text(encoding="utf-8")
    block = text.split("def ensure_backend_login", 1)[1].split("def ensure_login_sessions", 1)[0]

    assert "configured_ydz_login_captcha(env)" not in block


if __name__ == "__main__":
    test_parse_args_auto_login_is_default()
    test_parse_args_can_skip_auto_login_for_existing_session_debugging()
    test_parse_args_can_select_token_auth_mode()
    test_parse_args_can_select_backend_token_auth_mode()
    test_parse_args_can_select_password_auth_mode()
    test_parse_args_can_select_auto_auth_mode()
    test_parse_args_login_only_can_target_backend_without_tax_no()
    test_configured_ydz_credentials_are_environment_specific()
    test_configured_ydz_login_captcha_defaults_only_for_integration()
    test_configured_ydz_login_captcha_can_be_overridden()
    test_configured_ydz_token_context_reads_environment_specific_values()
    test_configured_backend_credentials_read_tax_backend_vars()
    test_configured_backend_token_provider_reads_header_tokens_without_leaking_values()
    test_ydz_login_url_uses_environment_specific_login_host()
    test_backend_forbidden_page_is_not_usable_session()
    test_backend_login_url_uses_public_manage_callback()
    test_backend_forbidden_page_detects_chinese_forbidden_text()
    test_ydz_slider_challenge_is_reported_as_manual_verification()
    test_manual_verification_marker_is_stable_for_workbench_parsing()
    test_ydz_public_entry_requires_logged_in_public_page()
    test_ydz_redirect_vm_page_opens_workbench_url()
    test_workbench_app_list_url_uses_environment_org_id()
    test_workbench_app_list_entry_opens_target_org_and_clicks_ydz()
    test_customer_creation_does_not_close_shared_cdp_browser()
    test_chrome_launch_uses_automation_controlled_flag()
    test_connect_chrome_over_cdp_falls_back_when_requested_port_is_incompatible()
    test_load_env_file_does_not_override_existing_values()
    test_read_tax_numbers_strips_utf8_bom_from_file()
    test_manual_source_env_adds_tax_number_and_source_fields()
    test_ensure_pages_open_can_skip_backend_for_manual_source()
    test_backend_login_does_not_reference_missing_ydz_env_variable()
    print("All ydz create customer script tests passed!")
