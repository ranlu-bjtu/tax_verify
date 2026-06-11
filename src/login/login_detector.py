import json
import logging
import re
import time
import urllib.parse
from typing import Any, Optional

import requests
from playwright.sync_api import Page

from src.config.province_config import (
    calc_etax_port, get_loginb_url, get_tpass_login_url,
    get_tpass_cookie_key, get_tax_domains, TPASS_COOKIE_KEY_MAP,
)
from src.login.log_sanitizer import redact_sensitive_text

logger = logging.getLogger(__name__)

# EtaxPlugin auto-login API endpoints
TASK_API_BASE = "https://data-task-management.chanapp.chanjet.com/data-task-scheduler"
TASK_COOKIE_API = f"{TASK_API_BASE}/api/client/getTaskCookie"


class LoginDetector:
    """Detects whether the user is logged in on the tax bureau website.

    Checks three types of indicators:
    1. URL pattern — no longer on loginb/ or tpass login page
    2. DOM element — a user-info element exists
    3. Cookie — tpass_* or specific session cookie is set
    """

    def __init__(self, indicators: Optional[list[dict]] = None, province: str = "shandong"):
        self.province = province
        # Default indicators: not on login page + have tpass cookie
        self.indicators = indicators or [
            {"type": "url_pattern", "value": f"*etax.{province}.chinatax.gov.cn*"},
            {"type": "url_not_pattern", "value": "*loginb*"},
            {"type": "url_not_pattern", "value": "*tpass*/#/login"},
            {"type": "cookie_prefix", "value": "tpass_"},
        ]

    def is_logged_in(self, page: Page) -> bool:
        """Check if logged in. Returns True if on main page (not login page)."""
        url = page.url
        lower_url = (url or "").lower()
        if (
            "/loading" in lower_url
            or "/mhzx/api/mh/tpass/code" in lower_url
            or "tpass." in lower_url
            and "#/login" in lower_url
        ):
            logger.info(f"Not logged in: transient or login url={redact_sensitive_text(url)}")
            return False
        on_main = False
        not_on_login = True

        try:
            text = page.evaluate("document.body ? document.body.innerText.slice(0, 5000) : ''")
            logged_in_hints = (
                "\u6211\u8981\u67e5\u8be2",
                "\u6211\u8981\u529e\u7a0e",
                "\u672c\u671f\u5e94\u7533\u62a5",
                "\u6211\u7684\u5f85\u529e",
                "\u7edf\u4e00\u793e\u4f1a\u4fe1\u7528\u4ee3\u7801",
                "\u7eb3\u7a0e\u4eba\u8bc6\u522b\u53f7",
                "\u8ddd\u672c\u6708\u5f81\u671f\u7ed3\u675f",
                "\u66f4\u6b63\u4f5c\u5e9f",
            )
            login_only_hints = (
                "\u201c\u591a\u5408\u4e00\u201d\u767b\u5f55",
                "\u6253\u5f00\u7535\u5b50\u7a0e\u52a1\u5c40APP\u626b\u4e00\u626b",
            )
            session_expired_hints = (
                "\u4f1a\u8bdd\u5931\u6548",
                "\u767b\u5f55\u5df2\u5931\u6548",
                "\u767b\u5f55\u8d85\u65f6",
                "\u8bf7\u91cd\u65b0\u767b\u5f55",
                "session expired",
            )
            text_lower = text.lower()
            is_auth_code_error = (
                "\u6388\u6743\u7801\u4e0d\u80fd\u4e3a\u7a7a" in text
                or ("\u6388\u6743\u7801" in text and "\u4e0d\u80fd\u4e3a\u7a7a" in text)
                or "auth code" in text_lower
                or "authorization code" in text_lower
            )
            if is_auth_code_error:
                logger.info(f"Not logged in: tax auth-code error url={redact_sensitive_text(url)}")
                return False
            if any(hint in text for hint in session_expired_hints):
                logger.info(f"Not logged in: tax bureau session expired url={redact_sensitive_text(url)}")
                return False
            if any(hint in text for hint in logged_in_hints):
                logger.info(f"Login detected: logged-in tax bureau content found ({redact_sensitive_text(url)})")
                return True
            if any(hint in text for hint in login_only_hints):
                logger.info(f"Not logged in: login form content found url={redact_sensitive_text(url)}")
                return False
        except Exception:
            pass

        for indicator in self.indicators:
            indicator_type = indicator.get("type")

            if indicator_type == "url_pattern":
                pattern = indicator.get("value", "")
                regex_pattern = pattern.replace("*", ".*")
                if re.search(regex_pattern, url):
                    on_main = True

            elif indicator_type == "url_not_pattern":
                pattern = indicator.get("value", "")
                regex_pattern = pattern.replace("*", ".*")
                if re.search(regex_pattern, url):
                    not_on_login = False

            elif indicator_type == "element":
                selector = indicator.get("selector", "")
                try:
                    el = page.query_selector(selector)
                    if el and el.is_visible():
                        logger.info(f"Login detected: element '{selector}' visible")
                        return True
                except Exception:
                    pass

            elif indicator_type == "cookie_prefix":
                try:
                    cookies = page.context.cookies()
                    province_tpass_key = get_tpass_cookie_key(self.province)
                    for cookie in cookies:
                        if province_tpass_key and cookie["name"] == province_tpass_key:
                            logger.info(f"Login detected: province tpass cookie '{cookie['name']}' found")
                            return True
                except Exception:
                    pass

            elif indicator_type == "cookie":
                cookie_name = indicator.get("name", "")
                try:
                    cookies = page.context.cookies()
                    for cookie in cookies:
                        if cookie["name"] == cookie_name:
                            logger.info(f"Login detected: cookie '{cookie_name}' found")
                            return True
                except Exception:
                    pass

        # Logged in if: on main page AND not on login page
        if on_main and not_on_login:
            logger.info(f"Login detected: on main page ({redact_sensitive_text(url)}), not on login page")
            return True

        logger.info(f"Not logged in: url={redact_sensitive_text(url)}")
        return False


def calc_port(province: str) -> str:
    """Alias for province_config.calc_etax_port."""
    return calc_etax_port(province)


class EtaxAutoLoginHandler:
    """Handles auto-login via EtaxPlugin's cookie injection mechanism.

    The EtaxPlugin ("一键进税局") auto-login flow:
    1. Call getTaskCookie API to get login credentials
    2. Construct login URL with cookie parameter
    3. Navigate to tpass login page with cookie data
    4. EtaxPlugin's content script injects cookies and redirects

    If getTaskCookie fails (e.g. expired task), fall back to checking
    existing session cookies in the persistent context.
    """

    def __init__(
        self,
        province: str = "shandong",
        task_id: str = "",
        login_detector: Optional[LoginDetector] = None,
        timeout: int = 120,
        machine_id: str = "",
    ):
        self.province = province
        self.task_id = task_id
        self.detector = login_detector or LoginDetector(province=province)
        self.timeout = timeout
        self.machine_id = machine_id

    def auto_login(self, page: Page) -> bool:
        """Attempt auto-login via EtaxPlugin mechanism.

        Strategy:
        1. Check if already logged in (persistent context cookies)
        2. Try EtaxPlugin cookie injection (getTaskCookie → navigate)
        3. If cookie injection fails, wait for manual login as fallback

        Returns True if logged in, raises TimeoutError if all methods fail.
        """
        port = calc_port(self.province)
        loginb_url = get_loginb_url(self.province)

        # Step 1: Check if already logged in (persistent context may have session)
        logger.info("Checking existing session in persistent context...")
        page.goto(loginb_url, wait_until="domcontentloaded", timeout=30000)
        time.sleep(3)  # Wait for plugin to process

        if self.detector.is_logged_in(page):
            logger.info("Already logged in via existing session cookies")
            return True

        # Step 2: Try EtaxPlugin auto-login via getTaskCookie API
        if self.task_id:
            logger.info(f"Attempting EtaxPlugin auto-login for task: {self.task_id}")
            try:
                # Get machineId from the browser (window.robotId set by 畅捷通 app)
                machine_id = self.machine_id
                if not machine_id:
                    try:
                        machine_id = page.evaluate("window.robotId || ''")
                    except Exception:
                        machine_id = ""

                cookie_data = self._get_task_cookie(self.task_id, machine_id)
                if cookie_data:
                    self._navigate_with_cookie(page, cookie_data)
                    # Wait for plugin to process cookie injection and redirect
                    if self._wait_for_login(page, timeout=60):
                        logger.info("Auto-login via EtaxPlugin succeeded")
                        return True
                    logger.warning("EtaxPlugin auto-login redirect did not complete within timeout")
            except Exception as e:
                logger.warning(f"EtaxPlugin auto-login failed: {e}")

        # Step 3: Fallback - wait for manual login or plugin-triggered login
        logger.info("Falling back to waiting for login completion...")
        page.goto(loginb_url, wait_until="domcontentloaded", timeout=30000)

        # If plugin has stored taskId, it may auto-login via startPollingTask
        # Try to trigger polling from the page
        if self.task_id:
            try:
                task_id_js = self.task_id
                page.evaluate("""
                    if (window.startPollingTask) {
                        window.startPollingTask(arguments[0], '');
                    }
                """, task_id_js)
            except Exception:
                pass

        if self._wait_for_login(page, timeout=self.timeout):
            return True

        raise TimeoutError(f"Login not completed within {self.timeout} seconds")

    def _get_task_cookie(self, task_id: str, machine_id: str) -> Optional[dict]:
        """Call getTaskCookie API to get login credentials."""
        try:
            data = {"taskId": task_id, "machineId": machine_id}
            resp = requests.post(TASK_COOKIE_API, json=data, timeout=15)
            result = resp.json()

            if result.get("flag") == 1 and result.get("data"):
                logger.info("getTaskCookie succeeded")
                return result["data"]
            else:
                msg = result.get("msg", result.get("message", "unknown error"))
                logger.warning(f"getTaskCookie failed: {msg}")
                return None
        except Exception as e:
            logger.error(f"getTaskCookie request failed: {e}")
            return None

    def _navigate_with_cookie(self, page: Page, cookie_data: dict) -> None:
        """Navigate to tpass login page with cookie parameter (EtaxPlugin auto-login).

        Replicates the userLogin() function from inject-bridge-login.js.
        Uses province_config to build province-specific URLs.
        """
        # Extract login params from cookie_data
        tydl = cookie_data.get("tydl", {})
        idcard = tydl.get("idcard", "")
        tax_no = tydl.get("taxNo", "")
        batch_no = tydl.get("batchNo", "")
        cookies_info = tydl.get("cookies", {})
        pro_cid = tydl.get("proCid", {})
        client_id = pro_cid.get("client_id", "")
        redirect_url = pro_cid.get("redirect_url", "")

        etax_cookie = cookies_info.get("etax_cookie", {})
        tpass_localstorage = cookies_info.get("tpass_localstorage", {})
        task_info = cookies_info.get("taskInfo", {})

        tgt_url = cookie_data.get("tgtUrl", "")
        declare_job = cookie_data.get("declareJob", {})
        cia_token = cookie_data.get("ciaToken", "")
        province = cookie_data.get("province", self.province)
        force_redirect_etax_provinces = cookie_data.get("forceRedirectEtaxProvinces", "")
        client_useorg_id = declare_job.get("clientUseorgId", "")
        login_info = declare_job.get("loginInfo", {})
        login_version = login_info.get("loginVersion", "")
        c_site_login_name = login_info.get("cSiteLoginName", "")

        # Build login cookies JSON (mirrors inject-bridge-login.js userLogin())
        login_cookies = {
            "province": province,
            "origin": "prod",
            "ciaToken": cia_token,
            "client_id": client_id,
            "idcard": idcard,
            "taxNo": tax_no,
            "batchNo": batch_no,
            "orgId": client_useorg_id,
            "loginVersion": login_version,
            "proxyTaxNo": c_site_login_name,
            "tgtUrl": tgt_url,
            "forceRedirectEtaxProvinces": force_redirect_etax_provinces,
            **tpass_localstorage,
            **etax_cookie,
            **task_info,
        }

        login_cookies_str = json.dumps(login_cookies, ensure_ascii=False)

        # Construct tpass login URL using province_config
        tpass_url = get_tpass_login_url(
            province=province,
            redirect_uri=redirect_url,
            client_id=client_id,
            cookie=login_cookies_str,
        )

        logger.info(f"Navigating to tpass login URL for province: {province}")
        page.goto(tpass_url, wait_until="domcontentloaded", timeout=30000)

    def _wait_for_login(self, page: Page, timeout: int = 120) -> bool:
        """Wait for login to complete (URL changes away from login pages)."""
        start = time.time()
        check_interval = 3

        while time.time() - start < timeout:
            if self.detector.is_logged_in(page):
                elapsed = int(time.time() - start)
                logger.info(f"Login confirmed after {elapsed}s")
                return True
            time.sleep(check_interval)

        logger.warning(f"Login wait timeout after {timeout}s")
        return False
