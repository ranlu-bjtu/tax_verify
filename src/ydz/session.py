from __future__ import annotations

import logging
import os
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Iterable

from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright

LOGGER = logging.getLogger(__name__)

YDZ_HOME_URL = "https://ydz.chanjet.com/?a=sztqwl&c=sztqwl"
YDZ_CLOUD_MARKER = "cloud.chanjet.com/ydzee/"
YDZ_WORK_MARKER = "/work.html"
YDZ_BATCH_DECLARE_HASH = "#/home/gzt/batchDeclare"
DEFAULT_CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
DEFAULT_PLUGIN_PATH = r"C:\Users\Administrator\Downloads\EtaxPlugin"
DEFAULT_PROFILE_DIR = r"./browser_profile/etax_compare_forms"


class YdzSession:
    """Owns a Chrome CDP session for Yidaizhang.

    The browser is used for login, enterprise selection, and as a safe token
    container. Business operations should go through YdzApi once login is ready.
    """

    def __init__(
        self,
        cdp_port: int = 9222,
        chrome_path: str = DEFAULT_CHROME_PATH,
        plugin_path: str = DEFAULT_PLUGIN_PATH,
        user_data_dir: str = DEFAULT_PROFILE_DIR,
        launch_if_needed: bool = True,
    ) -> None:
        self.cdp_port = cdp_port
        self.chrome_path = chrome_path
        self.plugin_path = plugin_path
        self.user_data_dir = user_data_dir
        self.launch_if_needed = launch_if_needed
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._chrome_process: subprocess.Popen | None = None

    @property
    def context(self) -> BrowserContext:
        if self._context is None:
            raise RuntimeError("Browser context is not connected.")
        return self._context

    def connect(self) -> BrowserContext:
        if not self._is_cdp_alive():
            if not self.launch_if_needed:
                raise RuntimeError(f"Chrome CDP is not available on port {self.cdp_port}.")
            self._launch_chrome()

        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.connect_over_cdp(
            f"http://127.0.0.1:{self.cdp_port}"
        )
        self._context = self._browser.contexts[0] if self._browser.contexts else self._browser.new_context()
        return self._context

    def close(self) -> None:
        if self._browser is not None:
            try:
                self._browser.close()
            except Exception as exc:
                LOGGER.debug("Error disconnecting browser: %s", exc)
        if self._playwright is not None:
            try:
                self._playwright.stop()
            except Exception as exc:
                LOGGER.debug("Error stopping Playwright: %s", exc)
        self._browser = None
        self._context = None
        self._playwright = None

    def get_ydz_page(self) -> Page:
        for page in self.context.pages:
            if YDZ_CLOUD_MARKER in page.url:
                return page
        for page in reversed(self.context.pages):
            if "ydz.chanjet.com" in page.url:
                return page
        page = self.context.new_page()
        self._safe_goto_home(page)
        return page

    def ensure_ready(self, username: str | None, password: str | None, enterprise: str) -> Page:
        page = self.get_ydz_page()
        if self._is_inside_ydz(page):
            self._go_batch_declare(page)
            return self._require_batch_declare_ready(page)

        self._safe_goto_home(page)
        page.wait_for_timeout(800)
        if not self._is_inside_ydz(page):
            if not self._has_visible_login_form(page):
                self._open_enterprise_selector_if_authenticated(page, timeout_ms=8_000)
            if not self._has_enterprise_selector(page, enterprise):
                if not username or not password:
                    raise RuntimeError("YDZ_USERNAME and YDZ_PASSWORD are required when login state is absent.")
                self._login(page, username, password)
            page = self._select_enterprise(page, enterprise)

        self._go_batch_declare(page)
        return self._require_batch_declare_ready(page)

    def _safe_goto_home(self, page: Page) -> None:
        if "ydz.chanjet.com" in page.url:
            return
        for attempt in range(3):
            try:
                page.goto(YDZ_HOME_URL, wait_until="domcontentloaded", timeout=60_000)
                return
            except Exception as exc:
                if "ERR_ABORTED" not in str(exc) or attempt == 2:
                    raise
                LOGGER.debug("Yidaizhang home navigation was interrupted; retrying: %s", exc)
                page.wait_for_timeout(1000)
                if "ydz.chanjet.com" in page.url or self._find_cloud_page() is not None:
                    return

    def _is_cdp_alive(self) -> bool:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{self.cdp_port}/json/version", timeout=2):
                return True
        except Exception:
            return False

    def _launch_chrome(self) -> None:
        Path(self.user_data_dir).mkdir(parents=True, exist_ok=True)
        args = [
            self.chrome_path,
            f"--load-extension={self.plugin_path}",
            f"--user-data-dir={self.user_data_dir}",
            f"--remote-debugging-port={self.cdp_port}",
            "--no-first-run",
            "--no-default-browser-check",
        ]
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        LOGGER.info("Launching Chrome with CDP on port %s", self.cdp_port)
        self._chrome_process = subprocess.Popen(args, creationflags=creationflags)
        deadline = time.time() + 15
        while time.time() < deadline:
            if self._is_cdp_alive():
                return
            time.sleep(0.5)
        raise RuntimeError(f"Chrome CDP did not become ready on port {self.cdp_port}.")

    def _is_inside_ydz(self, page: Page) -> bool:
        try:
            return YDZ_CLOUD_MARKER in page.url and YDZ_WORK_MARKER in page.url
        except Exception:
            return False

    def _has_enterprise_selector(self, page: Page, enterprise: str) -> bool:
        try:
            text = page.evaluate("() => document.body ? document.body.innerText : ''")
            return "\u9009\u62e9\u4f01\u4e1a" in text and enterprise in text
        except Exception:
            return False

    def _has_visible_login_form(self, page: Page) -> bool:
        try:
            return bool(
                page.evaluate(
                    r"""() => {
                        const vis = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
                        const roots = Array.from(document.querySelectorAll('.login-wrapper, .login-main, .account-wrapper'))
                            .filter(vis);
                        const scope = roots.find(el => (el.innerText || el.textContent || '').includes('\u8d26\u53f7\u5bc6\u7801\u767b\u5f55'))
                            || roots[0]
                            || document;
                        const inputs = Array.from(scope.querySelectorAll('input')).filter(vis);
                        const hasPassword = inputs.some(el => el.type === 'password' || (el.placeholder || '').includes('\u5bc6\u7801'));
                        const hasAccount = inputs.some(el => (el.placeholder || '').includes('\u8d26\u53f7') || (el.placeholder || '').includes('\u624b\u673a'))
                            || inputs.length >= 2;
                        return hasPassword && hasAccount;
                    }"""
                )
            )
        except Exception:
            return False

    def _wait_for_login_form(self, page: Page, timeout_ms: int) -> bool:
        deadline = time.time() + timeout_ms / 1000
        while time.time() < deadline:
            if self._has_visible_login_form(page):
                return True
            page.wait_for_timeout(300)
        return False

    def _open_enterprise_selector_if_authenticated(self, page: Page, timeout_ms: int = 8_000) -> None:
        try:
            opened = page.evaluate(
                r"""() => {
                    const vis = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
                    const body = document.body ? document.body.innerText : '';
                    if (!body.includes('\u8fdb\u5165\u6613\u4ee3\u8d26') && !body.includes('\u8fdb\u5165\u7cfb\u7edf')) {
                        return false;
                    }
                    const nodes = Array.from(document.querySelectorAll('button,a,div,span')).filter(vis);
                    const hit = nodes.find(el => {
                        const text = (el.innerText || el.textContent || '').trim().replace(/\s+/g, '');
                        return text === '\u8fdb\u5165\u6613\u4ee3\u8d26' || text === '\u8fdb\u5165\u7cfb\u7edf';
                    });
                    if (hit) hit.click();
                    return !!hit;
                }"""
            )
        except Exception as exc:
            LOGGER.debug("Could not open enterprise selector from authenticated home page: %s", exc)
            return
        if not opened:
            return
        deadline = time.time() + timeout_ms / 1000
        while time.time() < deadline:
            if self._find_cloud_page() is not None:
                return
            try:
                text = page.evaluate("() => document.body ? document.body.innerText : ''")
                if "\u9009\u62e9\u4f01\u4e1a" in text:
                    return
            except Exception as exc:
                LOGGER.debug("Waiting for enterprise selector after entering system: %s", exc)
            time.sleep(0.5)

    def _login(self, page: Page, username: str, password: str) -> None:
        if not self._has_visible_login_form(page):
            clicked = page.evaluate(
                r"""() => {
                    const vis = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
                    const buttons = Array.from(document.querySelectorAll('button')).filter(vis);
                    const hit = buttons.find(el => (el.innerText || el.textContent || '').trim() === '\u767b\u5f55');
                    if (hit) hit.click();
                    return !!hit;
                }"""
            )
            if not clicked:
                LOGGER.info("Login button was not found; checking whether page is already authenticated.")
                if self._has_enterprise_selector(page, ""):
                    return
            self._wait_for_login_form(page, timeout_ms=8_000)

        filled = page.evaluate(
            r"""({username, password}) => {
                const vis = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
                const setInputValue = (el, value) => {
                    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
                    setter.call(el, value);
                    el.dispatchEvent(new Event('input', {bubbles: true, composed: true}));
                    el.dispatchEvent(new Event('change', {bubbles: true, composed: true}));
                    el.dispatchEvent(new KeyboardEvent('keyup', {bubbles: true, composed: true, key: '1'}));
                    el.blur();
                };
                const loginRoot = Array.from(document.querySelectorAll('.login-wrapper, .login-main, .account-wrapper'))
                    .find(el => vis(el) && (el.innerText || el.textContent || '').includes('\u8d26\u53f7\u5bc6\u7801\u767b\u5f55'))
                    || document;
                const inputs = Array.from(loginRoot.querySelectorAll('input')).filter(vis);
                const userInput = inputs.find(el => (el.placeholder || '').includes('\u8d26\u53f7'))
                    || inputs.find(el => (el.placeholder || '').includes('\u624b\u673a'))
                    || inputs[0];
                const passInput = inputs.find(el => el.type === 'password')
                    || inputs.find(el => (el.placeholder || '').includes('\u5bc6\u7801'));
                if (!userInput || !passInput) return false;
                userInput.focus();
                setInputValue(userInput, username);
                passInput.focus();
                setInputValue(passInput, password);
                const checks = Array.from(document.querySelectorAll('input[type=checkbox]')).filter(vis);
                for (const cb of checks) {
                    if (!cb.checked) cb.click();
                }
                const agreeBox = Array.from(document.querySelectorAll('.check-box-wrapper, .check-box, .check-box-border, .login-common-checkbox'))
                    .find(el => vis(el) && el.closest('.agreement-wrapper'));
                if (agreeBox) agreeBox.click();
                return true;
            }""",
            {"username": username, "password": password},
        )
        if not filled:
            raise RuntimeError("Could not locate Yidaizhang login inputs.")

        clicked = page.evaluate(
            r"""() => {
                const vis = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
                const buttons = Array.from(document.querySelectorAll('button')).filter(vis);
                const btn = buttons.find(el => String(el.className || '').split(/\s+/).includes('login-button'))
                    || buttons.find(el => {
                    const text = (el.innerText || el.textContent || '').trim().replace(/\s+/g, '');
                    return text === '\u767b\u5f55' || text === '\u7acb\u5373\u767b\u5f55';
                });
                if (btn) {
                    btn.dispatchEvent(new MouseEvent('mousedown', {bubbles: true}));
                    btn.click();
                    btn.dispatchEvent(new MouseEvent('mouseup', {bubbles: true}));
                }
                return !!btn;
            }"""
        )
        if not clicked:
            raise RuntimeError("Could not locate Yidaizhang login submit button.")
        self._confirm_login_agreement_if_needed(page, timeout_ms=10_000)
        self._wait_for_login_result(page, timeout_ms=60_000)

    def _confirm_login_agreement_if_needed(self, page: Page, timeout_ms: int) -> None:
        deadline = time.time() + timeout_ms / 1000
        while time.time() < deadline:
            if self._find_cloud_page() is not None:
                return
            try:
                clicked = page.evaluate(
                    r"""() => {
                        const vis = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
                        const wrapper = Array.from(document.querySelectorAll('.verify-pwd-wrapper, .login-wrapper'))
                            .find(el => vis(el) && (el.innerText || el.textContent || '').includes('\u9605\u8bfb\u5e76\u540c\u610f'));
                        if (!wrapper) return false;
                        const buttons = Array.from(wrapper.querySelectorAll('button')).filter(vis);
                        const ok = buttons.find(el => (el.innerText || el.textContent || '').trim().replace(/\s+/g, '') === '\u786e\u5b9a');
                        if (ok) ok.click();
                        return !!ok;
                    }"""
                )
                if clicked:
                    return
            except Exception as exc:
                LOGGER.debug("Ignoring transient login confirmation error: %s", exc)
            time.sleep(0.5)

    def _wait_for_login_result(self, page: Page, timeout_ms: int) -> None:
        deadline = time.time() + timeout_ms / 1000
        while time.time() < deadline:
            if self._find_cloud_page() is not None:
                return
            try:
                body_text = page.evaluate("() => document.body ? document.body.innerText : ''")
                if "\u9009\u62e9\u4f01\u4e1a" in body_text:
                    return
            except Exception as exc:
                LOGGER.debug("Waiting through login navigation: %s", exc)
            time.sleep(0.5)
        raise RuntimeError(
            "Timed out waiting for Yidaizhang login to finish; "
            f"current_url={self._safe_page_url(page)}"
        )

    def _find_cloud_page(self) -> Page | None:
        for candidate in self.context.pages:
            try:
                if YDZ_CLOUD_MARKER in candidate.url:
                    return candidate
            except Exception:
                continue
        return None

    def _select_enterprise(self, page: Page, enterprise: str) -> Page:
        page.wait_for_timeout(2000)
        cloud_page = self._find_cloud_page()
        if cloud_page is not None:
            return cloud_page
        try:
            text = page.evaluate("() => document.body ? document.body.innerText : ''")
        except Exception as exc:
            LOGGER.debug("Enterprise page changed while reading body: %s", exc)
            return self.get_ydz_page()
        if enterprise not in text and "\u786e\u5b9a" not in text:
            return self.get_ydz_page()

        page.evaluate(
            r"""(enterprise) => {
                const vis = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
                const nodes = Array.from(document.querySelectorAll('div,span,li,label')).filter(vis);
                const hit = nodes.find(el => (el.innerText || el.textContent || '').includes(enterprise));
                if (hit) hit.click();
                const buttons = Array.from(document.querySelectorAll('button,a,div,span')).filter(vis);
                const ok = buttons.find(el => (el.innerText || el.textContent || '').trim().replace(/\s+/g, '') === '\u786e\u5b9a');
                if (ok) ok.click();
                return {selected: !!hit, confirmed: !!ok};
            }""",
            enterprise,
        )
        deadline = time.time() + 60
        while time.time() < deadline:
            for candidate in self.context.pages:
                if YDZ_CLOUD_MARKER in candidate.url:
                    return candidate
            page.wait_for_timeout(500)
        raise RuntimeError("Timed out waiting for Yidaizhang enterprise page after enterprise selection.")

    def _go_batch_declare(self, page: Page) -> None:
        if YDZ_BATCH_DECLARE_HASH not in page.url:
            page.evaluate(
                r"""() => {
                    const vis = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
                    const nodes = Array.from(document.querySelectorAll('li,a,button,div,span')).filter(vis);
                    const tax = nodes.find(el => (el.innerText || el.textContent || '').trim() === '\u62a5\u7a0e');
                    if (tax) tax.click();
                    const batch = nodes.find(el => (el.innerText || el.textContent || '').trim() === '\u6279\u91cf\u62a5\u7a0e');
                    if (batch) batch.click();
                }"""
            )
            page.wait_for_timeout(3000)
        if YDZ_BATCH_DECLARE_HASH not in page.url:
            prefix = page.url.split("/work.html", 1)[0] if "/work.html" in page.url else None
            if prefix:
                page.goto(prefix + "/work.html#/home/gzt/batchDeclare", wait_until="domcontentloaded", timeout=60_000)
                page.wait_for_timeout(3000)

    def _require_batch_declare_ready(self, page: Page) -> Page:
        cloud_page = self._find_cloud_page() or page
        if not self._is_inside_ydz(cloud_page):
            raise RuntimeError(
                "Yidaizhang is not inside the cloud application; "
                f"current_url={self._safe_page_url(cloud_page)}"
            )
        if YDZ_BATCH_DECLARE_HASH not in cloud_page.url:
            self._go_batch_declare(cloud_page)
        if YDZ_BATCH_DECLARE_HASH not in cloud_page.url:
            raise RuntimeError(
                "Yidaizhang did not reach the batch declaration page; "
                f"current_url={self._safe_page_url(cloud_page)}"
            )
        return cloud_page

    def _safe_page_url(self, page: Page | None) -> str:
        if page is None:
            return "<no page>"
        try:
            return page.url
        except Exception:
            return "<unavailable>"

    def _wait_until_any_url(self, page: Page, parts: Iterable[str], timeout_ms: int) -> None:
        deadline = time.time() + timeout_ms / 1000
        while time.time() < deadline:
            if any(part in page.url for part in parts):
                return
            page.wait_for_timeout(500)
        raise RuntimeError(f"Timed out waiting for URL containing one of {list(parts)}.")


def get_env_credentials() -> tuple[str | None, str | None]:
    return os.environ.get("YDZ_USERNAME"), os.environ.get("YDZ_PASSWORD")
