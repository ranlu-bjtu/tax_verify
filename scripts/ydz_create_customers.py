from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Iterable

from playwright.sync_api import BrowserContext, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.chanjet_admin.auth import (  # noqa: E402
    ADMIN_AUTH_MANUAL_VERIFICATION_REQUIRED,
    AdminAuthTokens,
    ChanjetAdminPasswordAuthClient,
    StaticAdminAuthProvider,
)
from src.chanjet_admin.privacy_phone import ChanjetPrivacyPhoneBridge  # noqa: E402
from src.chanjet_admin.task_query import ChanjetAdminTaskQuery, PUBLIC_MANAGE_URL  # noqa: E402
from src.ydz.customer_creation import (  # noqa: E402
    BackendCustomerSource,
    BackendCustomerSourceResolver,
    ManualCustomerSourceResolver,
    YDZ_CREATE_ENVIRONMENTS,
    YdzCreateEnvironment,
    YdzCustomerApi,
    YdzCustomerCreator,
    YdzCustomerDefaults,
    YdzCustomerCreateResult,
    build_ydz_auth_context,
    find_ydz_page,
    wait_for_ydz_page,
)
from src.ydz.password_auth import (  # noqa: E402
    ChanjetPasswordAuthClient,
    PASSWORD_LOGIN_MANUAL_VERIFICATION_REQUIRED,
    PASSWORD_LOGIN_PASSWORD_CHANGE_REQUIRED,
    PASSWORD_LOGIN_BIND_PHONE_REQUIRED,
)

LOGGER = logging.getLogger(__name__)
DEFAULT_CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
DEFAULT_PROFILE_DIR = str(ROOT / "browser_profile" / "ydz_customer_create")
CDP_FALLBACK_PORTS = (9333, 9444, 9555, 9666)
CHROME_AUTOMATION_STEALTH_ARGS = ["--enable-automation", "--disable-blink-features=AutomationControlled"]
PUBLIC_MANAGE_MARKER = "public-manage.chanjet.com/taxserver"
WORKBENCH_APP_LIST_URL = "https://workbench.chanjet.com/v2/myapp/list"
DEFAULT_ENTERPRISE_HINTS = {"inte": "7793uB6A", "prod": "蓝天之爱"}
MANUAL_VERIFICATION_REQUIRED_MARKER = "MANUAL_VERIFICATION_REQUIRED"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create or update Yidaizhang customers from public-manage backend task login info. "
            "Reuses existing browser sessions and can auto-login from configured environment variables."
        )
    )
    parser.add_argument("--env", choices=sorted(YDZ_CREATE_ENVIRONMENTS), default="inte")
    parser.add_argument("--env-file", help="Optional local env file. Do not commit files containing passwords.")
    parser.add_argument("--tax-no", action="append", default=[], help="Tax number. Can be passed multiple times.")
    parser.add_argument("--tax-no-file", help="Text file containing tax numbers separated by whitespace, comma, or newline.")
    parser.add_argument("--cdp-port", type=int, default=9222)
    parser.add_argument("--chrome-path", default=DEFAULT_CHROME_PATH)
    parser.add_argument("--user-data-dir", default=DEFAULT_PROFILE_DIR)
    parser.add_argument("--ydz-work-url", help="Override the Yidaizhang workbench URL opened when the session is missing.")
    parser.add_argument("--session-timeout", type=int, default=120, help="Seconds to wait for browser login sessions.")
    parser.add_argument("--lookback-days", default="30,180,730,1460", help="Comma-separated backend query windows.")
    parser.add_argument("--opening-period", default=None)
    parser.add_argument("--taxpayer-type", default=None)
    parser.add_argument("--industry-id", default=None)
    parser.add_argument("--dry-run", action="store_true", help="Resolve source data and existing customers, but do not create or save.")
    parser.add_argument(
        "--manual-source-env",
        action="store_true",
        help="Read customer/login source fields from YDZ_MANUAL_* environment variables instead of public-manage.",
    )
    parser.add_argument(
        "--skip-privacy-phone-sync",
        action="store_true",
        help="Do not prepare/sync integration privacy-phone data before creating the account set.",
    )
    parser.add_argument("--no-launch-chrome", action="store_true", help="Fail instead of launching Chrome when CDP is not available.")
    parser.add_argument(
        "--skip-auto-login",
        action="store_true",
        help="Only check existing browser sessions; do not use configured credentials to login.",
    )
    parser.add_argument(
        "--ydz-auth-mode",
        choices=["auto", "browser", "token", "password"],
        default=None,
        help=(
            "Yidaizhang authentication source. auto tries password first and falls back to browser; "
            "browser uses the logged-in Chrome workbench; "
            "token reads YDZ_*_IFRAME_TOKEN and YDZ_*_CIA_TOKEN from the environment; "
            "password tries direct Chanjet password login and reports manual-verification blockers."
        ),
    )
    parser.add_argument(
        "--backend-auth-mode",
        choices=["auto", "browser", "token", "password"],
        default=None,
        help=(
            "Public-manage authentication source. auto tries configured backend tokens, then "
            "account-password API login, then browser; token reads TAX_BACKEND_AUTHORIZATION and "
            "TAX_BACKEND_TOKEN/TAX_BACKEND_ACCESS_TOKEN; password is strict API login."
        ),
    )
    parser.add_argument("--login-only", action="store_true", help="Only prepare browser login sessions; do not create customers.")
    parser.add_argument(
        "--login-target",
        choices=["all", "ydz", "backend"],
        default="all",
        help="Which login session to prepare when --login-only is used.",
    )
    parser.add_argument("--output-json", help="Optional path for a sanitized JSON result report. Passwords and tokens are never written.")
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args(argv)


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


def read_tax_numbers(args: argparse.Namespace) -> list[str]:
    values: list[str] = []
    values.extend(args.tax_no or [])
    if getattr(args, "manual_source_env", False):
        values.append(os.environ.get("YDZ_MANUAL_TAX_NO") or "")
    if args.tax_no_file:
        text = Path(args.tax_no_file).read_text(encoding="utf-8-sig")
        for chunk in text.replace(",", "\n").replace("，", "\n").split():
            values.append(chunk.strip())
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        tax_no = value.strip().lstrip("\ufeff").upper()
        if not tax_no or tax_no in seen:
            continue
        seen.add(tax_no)
        result.append(tax_no)
    if not result:
        raise SystemExit("No tax numbers were provided. Use --tax-no or --tax-no-file.")
    return result


def manual_source_from_env() -> BackendCustomerSource:
    return BackendCustomerSource(
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


def parse_lookback_days(value: str) -> list[int]:
    result = []
    for chunk in value.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        result.append(int(chunk))
    return result or [30, 180, 730, 1460]


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


def launch_chrome_if_needed(args: argparse.Namespace, env: YdzCreateEnvironment) -> None:
    if is_cdp_alive(args.cdp_port):
        LOGGER.info(
            "Reusing existing Chrome CDP on port %s; startup flags cannot be changed for an already-running browser.",
            args.cdp_port,
        )
        return
    if args.no_launch_chrome:
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


def connect_chrome_over_cdp(playwright: Any, args: argparse.Namespace, env: YdzCreateEnvironment) -> Any:
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


def ensure_pages_open(
    context: BrowserContext,
    env: YdzCreateEnvironment,
    ydz_work_url: str | None,
    include_backend: bool = True,
) -> None:
    if find_ydz_page(context, env) is None:
        page = context.new_page()
        page.goto(ydz_work_url or env.default_work_url or env.public_url, wait_until="domcontentloaded", timeout=60_000)
    if not include_backend:
        return
    if not any("public-manage.chanjet.com/taxserver" in page.url for page in context.pages if not page.is_closed()):
        page = context.new_page()
        page.goto(configured_backend_credentials()["url"] or PUBLIC_MANAGE_URL, wait_until="domcontentloaded", timeout=60_000)


def wait_for_backend_session(context: BrowserContext, timeout: int) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        for page in context.pages:
            if page.is_closed() or "public-manage.chanjet.com/taxserver" not in page.url:
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


def backend_login_url(callback_url: str | None = None) -> str:
    callback = urllib.parse.quote(callback_url or PUBLIC_MANAGE_URL, safe="")
    return f"https://login.chanjet.com/?callback={callback}"


def env_prefix(env_name: str) -> str:
    return "YDZ_INTE" if env_name == "inte" else "YDZ_PROD"


def ydz_login_url(env: YdzCreateEnvironment) -> str:
    callback = urllib.parse.quote(env.public_url, safe="")
    if env.name == "inte":
        return f"https://ydz-login.inte.chanjet.com/?callback={callback}"
    return f"https://login.chanjet.com/?callback={callback}"


def configured_ydz_credentials(env: YdzCreateEnvironment) -> dict[str, str]:
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


def configured_ydz_login_captcha(env: YdzCreateEnvironment) -> str:
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
    return str(args.ydz_auth_mode or os.environ.get("YDZ_AUTH_MODE") or "auto").strip().lower()


def resolved_backend_auth_mode(args: argparse.Namespace) -> str:
    return str(args.backend_auth_mode or os.environ.get("TAX_BACKEND_AUTH_MODE") or "auto").strip().lower()


def configured_ydz_token_context(env: YdzCreateEnvironment, ydz_work_url: str | None = None) -> dict[str, str] | None:
    prefix = env_prefix(env.name)
    iframe_token = first_env_value(f"{prefix}_IFRAME_TOKEN", "YDZ_IFRAME_TOKEN")
    cia_token = first_env_value(f"{prefix}_CIA_TOKEN", "YDZ_CIA_TOKEN")
    if not iframe_token or not cia_token:
        return None
    work_url = (
        ydz_work_url
        or first_env_value(f"{prefix}_WORK_URL", "YDZ_WORK_URL")
        or env.default_work_url
    )
    return build_ydz_auth_context(
        env,
        iframe_token=iframe_token,
        cia_token=cia_token,
        work_url=work_url,
        org_id=first_env_value(f"{prefix}_ORG_ID", "YDZ_ORG_ID") or env.org_id,
        user_id=first_env_value(f"{prefix}_USER_ID", "YDZ_USER_ID") or env.user_id,
        org_name=first_env_value(f"{prefix}_ORG_NAME", "YDZ_ORG_NAME"),
        user_mobile=first_env_value(f"{prefix}_USER_MOBILE", f"{prefix}_MOBILE", "YDZ_USER_MOBILE", "YDZ_MOBILE"),
        user_name=first_env_value(f"{prefix}_USER_NAME", "YDZ_USER_NAME"),
    ).as_api_dict()


def configured_ydz_password_context(
    env: YdzCreateEnvironment,
    ydz_work_url: str | None = None,
    timeout: int = 30,
) -> tuple[dict[str, str] | None, dict[str, Any]]:
    creds = configured_ydz_credentials(env)
    status: dict[str, Any] = {
        "env": env.name,
        "status": "FAILED",
        "message": "",
        "hasAuthContext": False,
    }
    if not creds["username"] or not creds["password"]:
        status["message"] = "Yidaizhang username/password is not configured."
        return None, status
    prefix = env_prefix(env.name)
    verify_token = first_env_value(f"{prefix}_VERIFY_TOKEN", "YDZ_VERIFY_TOKEN")
    result = ChanjetPasswordAuthClient(env, timeout=timeout).login(
        creds["username"],
        creds["password"],
        work_url=ydz_work_url or creds["workUrl"] or env.default_work_url,
        verify_token=verify_token,
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
    status = {
        "mode": "token",
        "status": "FAILED",
        "hasTokens": bool(authorization and access_token),
    }
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
    status.update({"status": "TOKEN_READY", "message": "Backend token variables are configured.", "hasTokens": True})
    return provider, status


def configured_backend_password_provider(timeout: int = 30) -> tuple[StaticAdminAuthProvider | None, dict[str, Any]]:
    creds = configured_backend_credentials()
    client = ChanjetAdminPasswordAuthClient(
        creds["username"],
        creds["password"],
        public_manage_url=creds["url"] or PUBLIC_MANAGE_URL,
        timeout=timeout,
    )
    result = client.login()
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


def resolve_backend_token_provider(
    args: argparse.Namespace,
) -> tuple[StaticAdminAuthProvider | None, str, dict[str, Any]]:
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
                    const norm = value => String(value || '').trim().replace(/\s+/g, '');
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


def log_manual_verification_required(env: YdzCreateEnvironment, reason: str) -> None:
    LOGGER.warning(
        "%s ydz env=%s reason=%s action=complete_slider_in_browser message=Please complete the Yidaizhang slider in Chrome; the script will continue after the workbench session is ready.",
        MANUAL_VERIFICATION_REQUIRED_MARKER,
        env.name,
        reason,
    )


def ydz_public_entry_available(page: Any) -> bool:
    text = page_body_text(page)
    return "进入易代账" in text and ("用户" in text or "登录" not in text)


def click_ydz_public_entry(context: BrowserContext, env: YdzCreateEnvironment) -> bool:
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


def is_ydz_redirect_vm_page(page: Any, env: YdzCreateEnvironment) -> bool:
    try:
        url = str(page.url or "")
    except Exception:
        return False
    return (
        "/vm/redirectVM" in url
        and "passport" in url
        and ("appName=ydzee" in url or "productId=260" in url or env.name == "inte")
    )


def open_ydz_redirect_vm_workbench(context: BrowserContext, env: YdzCreateEnvironment, work_url: str) -> bool:
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
                        || buttons.find(el => String(el.innerText || el.textContent || '').trim().replace(/\s+/g, '') === '登录');
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
                        || buttons.find(el => String(el.innerText || el.textContent || '').trim().replace(/\s+/g, '') === '登录');
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


def find_page_by_url(context: BrowserContext, markers: Iterable[str]) -> Any | None:
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


def workbench_app_list_url(env: YdzCreateEnvironment) -> str:
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


def open_ydz_from_workbench_app_list(
    context: BrowserContext,
    env: YdzCreateEnvironment,
    timeout: int,
) -> Any | None:
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


def wait_for_ydz_or_direct_work(
    context: BrowserContext,
    env: YdzCreateEnvironment,
    work_url: str,
    timeout: int,
) -> Any | None:
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


def ensure_ydz_login(
    context: BrowserContext,
    env: YdzCreateEnvironment,
    timeout: int,
    ydz_work_url: str | None = None,
) -> Any | None:
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
    result = wait_for_ydz_or_direct_work(context, env, work_url, timeout=timeout)
    if result is not None and manual_required:
        LOGGER.info("Yidaizhang %s workbench session is ready after manual verification.", env.name)
    return result


def ensure_backend_login(context: BrowserContext, timeout: int) -> bool:
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
    if fill_chanjet_login_form(login_page, creds["username"], creds["password"]):
        LOGGER.info("Submitted public-manage login form.")
    for attempt in range(3):
        login_page.wait_for_timeout(3000)
        if wait_for_backend_session(context, timeout=2):
            return True
        if not has_visible_login_form(login_page):
            break
        LOGGER.info("Public-manage login form still visible; retrying submit (%s/3).", attempt + 1)
        submit_chanjet_login_form(login_page)
    return wait_for_backend_session(context, timeout=timeout)


def ensure_login_sessions(
    context: BrowserContext,
    env: YdzCreateEnvironment,
    args: argparse.Namespace,
) -> tuple[Any | None, bool]:
    ydz_page = ensure_ydz_login(context, env, timeout=args.session_timeout, ydz_work_url=args.ydz_work_url)
    backend_ready = ensure_backend_login(context, timeout=args.session_timeout)
    if ydz_page is None:
        work_url = args.ydz_work_url or configured_ydz_credentials(env)["workUrl"] or env.default_work_url
        ydz_page = wait_for_ydz_or_direct_work(context, env, work_url, timeout=min(args.session_timeout, 60))
    return ydz_page, backend_ready


def write_output_json(path_value: str | None, payload: Any) -> None:
    if not path_value:
        return
    path = Path(path_value)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def run_login_only(args: argparse.Namespace, env: YdzCreateEnvironment) -> int:
    login_auth_mode = resolved_ydz_auth_mode(args)
    target = str(args.login_target or "all")
    backend_token_provider: StaticAdminAuthProvider | None = None
    backend_auth_status: dict[str, Any] | None = None
    backend_effective_auth_mode = "browser"
    if target in {"all", "backend"} and not args.skip_auto_login:
        backend_token_provider, backend_effective_auth_mode, backend_auth_status = resolve_backend_token_provider(args)
        if backend_token_provider is None and resolved_backend_auth_mode(args) in {"token", "password"}:
            status = {
                "mode": "login",
                "env": env.name,
                "target": target,
                "backendAuthMode": backend_effective_auth_mode,
                "backendReady": False,
                "ready": False,
                "backendAuth": backend_auth_status,
            }
            write_output_json(args.output_json, status)
            print(json.dumps(status, ensure_ascii=False))
            return 2
        if target == "backend" and backend_token_provider is not None:
            status = {
                "mode": "login",
                "env": env.name,
                "target": target,
                "backendAuthMode": backend_effective_auth_mode,
                "backendReady": True,
                "ready": True,
                "backendAuth": backend_auth_status,
            }
            write_output_json(args.output_json, status)
            print(json.dumps(status, ensure_ascii=False))
            return 0
    if login_auth_mode in {"auto", "password"} and str(args.login_target or "all") in {"all", "ydz"}:
        ydz_token_context, ydz_status = configured_ydz_password_context(
            env,
            ydz_work_url=args.ydz_work_url,
            timeout=args.session_timeout,
        )
        if ydz_token_context is None and login_auth_mode == "auto":
            LOGGER.info(
                "Yidaizhang password auth did not produce a usable token context; falling back to browser login. status=%s",
                ydz_status.get("status"),
            )
        else:
            target = str(args.login_target or "all")
            status: dict[str, Any] = {
                "mode": "login",
                "env": env.name,
                "target": target,
                "authMode": login_auth_mode,
                "effectiveYdzAuthMode": "password" if ydz_token_context is not None else login_auth_mode,
                "backendAuthMode": backend_effective_auth_mode,
                "ydzReady": ydz_token_context is not None,
                "backendReady": None,
                "ready": ydz_token_context is not None,
                "ydzPasswordLogin": ydz_status,
                "backendAuth": backend_auth_status,
            }
            if target == "all":
                if backend_token_provider is not None:
                    status["backendReady"] = True
                else:
                    with sync_playwright() as pw:
                        browser = connect_chrome_over_cdp(pw, args, env)
                        context = browser.contexts[0] if browser.contexts else browser.new_context()
                        status["cdpPort"] = args.cdp_port
                        status["backendReady"] = (
                            wait_for_backend_session(context, timeout=args.session_timeout)
                            if args.skip_auto_login
                            else ensure_backend_login(context, timeout=args.session_timeout)
                        )
                status["ready"] = bool(status["ydzReady"]) and bool(status["backendReady"])
            write_output_json(args.output_json, status)
            print(json.dumps(status, ensure_ascii=False))
            return 0 if status["ready"] else 2

    status: dict[str, Any] = {
        "mode": "login",
        "env": env.name,
        "target": target,
        "backendAuthMode": backend_effective_auth_mode,
        "cdpPort": args.cdp_port,
        "ydzReady": None,
        "backendReady": None,
        "ready": False,
        "backendAuth": backend_auth_status,
    }

    with sync_playwright() as pw:
        browser = connect_chrome_over_cdp(pw, args, env)
        context = browser.contexts[0] if browser.contexts else browser.new_context()
        status["cdpPort"] = args.cdp_port
        if target in {"all", "ydz"} and not args.skip_auto_login:
            status["ydzReady"] = ensure_ydz_login(context, env, timeout=args.session_timeout, ydz_work_url=args.ydz_work_url) is not None
        elif target in {"all", "ydz"}:
            status["ydzReady"] = wait_for_ydz_page(context, env, timeout=args.session_timeout) is not None

        if target in {"all", "backend"} and backend_token_provider is not None:
            status["backendReady"] = True
        elif target in {"all", "backend"} and not args.skip_auto_login:
            status["backendReady"] = ensure_backend_login(context, timeout=args.session_timeout)
        elif target in {"all", "backend"}:
            status["backendReady"] = wait_for_backend_session(context, timeout=args.session_timeout)

    checks = [value for key, value in status.items() if key.endswith("Ready") and value is not None]
    status["ready"] = bool(checks) and all(bool(value) for value in checks)
    write_output_json(args.output_json, status)
    print(json.dumps(status, ensure_ascii=False))
    return 0 if status["ready"] else 2


def build_defaults(args: argparse.Namespace) -> YdzCustomerDefaults:
    defaults = YdzCustomerDefaults()
    if args.opening_period:
        defaults.opening_period = args.opening_period
    if args.taxpayer_type:
        defaults.taxpayer_type = args.taxpayer_type
    if args.industry_id:
        defaults.tax_industry_id = args.industry_id
    return defaults


def print_result(result: YdzCustomerCreateResult) -> None:
    public = result.public_dict()
    error_text = "; ".join(public["errors"]) if public["errors"] else ""
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
                error_text,
            ]
        )
    )


def run_creator_and_write_results(
    args: argparse.Namespace,
    creator: YdzCustomerCreator,
    tax_numbers: list[str],
) -> int:
    results: list[YdzCustomerCreateResult] = []
    print("status\taction\ttaxNo\tname\tcustId\tarea\tloginMethod\taccountantId\taccountantSource\tprivacyPhone\tverification\terrors")
    for tax_no in tax_numbers:
        result = creator.process_tax_no(tax_no, dry_run=args.dry_run)
        results.append(result)
        print_result(result)
    write_output_json(args.output_json, [result.public_dict() for result in results])
    return 1 if any(result.status in {"FAILED", "PARTIAL"} for result in results) else 0


def main() -> int:
    args = parse_args()
    load_env_file(args.env_file)
    logging.basicConfig(level=getattr(logging, str(args.log_level).upper(), logging.INFO), format="%(levelname)s %(message)s")
    env = YDZ_CREATE_ENVIRONMENTS[args.env]
    if args.login_only:
        return run_login_only(args, env)
    manual_mode = bool(args.manual_source_env)
    tax_numbers = read_tax_numbers(args)
    lookback_days = parse_lookback_days(args.lookback_days)
    defaults = build_defaults(args)
    ydz_auth_mode = resolved_ydz_auth_mode(args)
    if ydz_auth_mode not in {"auto", "browser", "token", "password"}:
        raise SystemExit("YDZ_AUTH_MODE must be auto, browser, token, or password.")
    ydz_password_status: dict[str, Any] | None = None
    ydz_token_context = configured_ydz_token_context(env, args.ydz_work_url) if ydz_auth_mode == "token" else None
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
            "Use --ydz-auth-mode browser for slider/manual verification, or use --ydz-auth-mode token "
            "with valid YDZ_*_IFRAME_TOKEN/YDZ_*_CIA_TOKEN.",
            file=sys.stderr,
        )
        write_output_json(args.output_json, {"status": "FAILED", "ydzPasswordLogin": ydz_password_status})
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
                "Use --backend-auth-mode auto/browser for browser fallback, or provide valid "
                "TAX_BACKEND_AUTHORIZATION and TAX_BACKEND_TOKEN/TAX_BACKEND_ACCESS_TOKEN.",
                file=sys.stderr,
            )
            write_output_json(
                args.output_json,
                {
                    "status": "FAILED",
                    "backendAuth": backend_auth_status,
                    "ydzPasswordLogin": ydz_password_status,
                },
            )
            return 2
    if ydz_auth_mode in {"token", "password"} and manual_mode:
        ydz_api = YdzCustomerApi(None, env, auth_context=ydz_token_context)
        creator = YdzCustomerCreator(
            ydz_api,
            ManualCustomerSourceResolver(manual_source_from_env()),
            env,
            defaults=defaults,
            privacy_phone_bridge=None,
            prepare_privacy_phone=False,
            login_account=configured_ydz_credentials(env)["username"],
        )
        return run_creator_and_write_results(args, creator, tax_numbers)

    if ydz_auth_mode in {"token", "password"} and backend_token_provider is not None:
        ydz_api = YdzCustomerApi(None, env, auth_context=ydz_token_context)
        admin_query = ChanjetAdminTaskQuery(token_provider=backend_token_provider)
        source_resolver = BackendCustomerSourceResolver(admin_query, lookback_days=lookback_days)
        privacy_phone_bridge = (
            None
            if args.skip_privacy_phone_sync
            else ChanjetPrivacyPhoneBridge(token_provider=backend_token_provider) if env.name == "inte" else None
        )
        creator = YdzCustomerCreator(
            ydz_api,
            source_resolver,
            env,
            defaults=defaults,
            privacy_phone_bridge=privacy_phone_bridge,
            prepare_privacy_phone=not args.skip_privacy_phone_sync,
            login_account=configured_ydz_credentials(env)["username"],
        )
        return run_creator_and_write_results(args, creator, tax_numbers)

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
            prefix = env_prefix(env.name)
            if manual_mode:
                print(
                    "Yidaizhang login session is not ready. Configure "
                    f"{prefix}_USERNAME/{prefix}_PASSWORD/{prefix}_ENTERPRISE for automatic login, or log in to "
                    "Yidaizhang in the opened Chrome window, select the target enterprise, then rerun this command.",
                    file=sys.stderr,
                )
            else:
                print(
                    "Login session is not ready. Configure "
                    f"{prefix}_USERNAME/{prefix}_PASSWORD/{prefix}_ENTERPRISE and "
                    "TAX_BACKEND_USERNAME/TAX_BACKEND_PASSWORD for automatic login, or log in to "
                    "Yidaizhang and public-manage in the opened Chrome window, select the target enterprise, "
                    "then rerun this command.",
                    file=sys.stderr,
                )
            return 2

        ydz_api = (
            YdzCustomerApi(None, env, auth_context=ydz_token_context)
            if ydz_auth_mode in {"token", "password"}
            else YdzCustomerApi(ydz_page, env)
        )
        if manual_mode:
            source_resolver = ManualCustomerSourceResolver(manual_source_from_env())
            privacy_phone_bridge = None
        else:
            admin_query = ChanjetAdminTaskQuery(
                None if backend_token_provider is not None else context,
                token_provider=backend_token_provider,
            )
            source_resolver = BackendCustomerSourceResolver(admin_query, lookback_days=lookback_days)
            privacy_phone_bridge = (
                None
                if args.skip_privacy_phone_sync
                else ChanjetPrivacyPhoneBridge(
                    None if backend_token_provider is not None else context,
                    token_provider=backend_token_provider,
                ) if env.name == "inte" else None
            )
        creator = YdzCustomerCreator(
            ydz_api,
            source_resolver,
            env,
            defaults=defaults,
            privacy_phone_bridge=privacy_phone_bridge,
            prepare_privacy_phone=not (manual_mode or args.skip_privacy_phone_sync),
            login_account=configured_ydz_credentials(env)["username"],
        )

        return run_creator_and_write_results(args, creator, tax_numbers)


if __name__ == "__main__":
    raise SystemExit(main())
