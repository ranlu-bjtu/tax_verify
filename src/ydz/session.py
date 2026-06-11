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
YDZ_CLOUD_MARKERS = (YDZ_CLOUD_MARKER, "inte-cloud.chanjet.com/ydzee/")
YDZ_WORK_MARKER = "/work.html"
YDZ_BATCH_DECLARE_HASH = "#/home/gzt/batchDeclare"
YDZ_DEFAULT_WORK_URL = "https://cloud.chanjet.com/ydzee/u7anoc8y5p7p/49le0svcsa/work.html#/home/gzt/batchDeclare"
YDZ_WORKBENCH_HOME_URL = "https://workbench.chanjet.com/v2/home"
DEFAULT_CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
DEFAULT_PLUGIN_PATH = r"C:\Users\Administrator\Downloads\EtaxPlugin"
DEFAULT_PROFILE_DIR = r"./browser_profile/etax_compare_forms"
CHROME_AUTOMATION_STEALTH_ARGS = ["--disable-blink-features=AutomationControlled"]


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
        self.chrome_path = chrome_path or DEFAULT_CHROME_PATH
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
            if self._is_ydz_cloud_url(self._safe_page_url(page)):
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
            if not self._wait_for_api_tokens(page, timeout_ms=5_000):
                if username and password:
                    LOGGER.info("Yidaizhang workbench is open but API token is missing; refreshing login state.")
                    return self.refresh_login_state(username=username, password=password, enterprise=enterprise)
                raise RuntimeError("Yidaizhang login token is missing; provide YDZ_USERNAME/YDZ_PASSWORD or log in again.")
            self._go_batch_declare(page)
            ready = self._require_batch_declare_ready(page)
            if not self._wait_for_api_tokens(ready, timeout_ms=8_000):
                raise RuntimeError("Yidaizhang login token is missing after reaching batch declaration page.")
            return ready

        self._safe_goto_home(page)
        page.wait_for_timeout(800)
        if not self._is_inside_ydz(page):
            if not self._has_visible_login_form(page):
                direct_page = self._recover_authenticated_workbench(page, enterprise=enterprise, timeout_ms=8_000)
                if direct_page is not None:
                    page = direct_page
            if not self._has_enterprise_selector(page, enterprise):
                if not self._is_inside_ydz(page):
                    if not username or not password:
                        raise RuntimeError("YDZ_USERNAME and YDZ_PASSWORD are required when login state is absent.")
                    self._login(page, username, password)
            page = self._select_enterprise(page, enterprise)

        self._go_batch_declare(page)
        ready = self._require_batch_declare_ready(page)
        if not self._wait_for_api_tokens(ready, timeout_ms=8_000):
            raise RuntimeError("Yidaizhang login token is missing after reaching batch declaration page.")
        return ready

    def refresh_login_state(self, username: str | None, password: str | None, enterprise: str) -> Page:
        page = self.get_ydz_page()
        self._clear_ydz_auth_tokens()
        page.goto(YDZ_HOME_URL, wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(800)
        if not self._is_inside_ydz(page):
            if not self._has_visible_login_form(page):
                direct_page = self._recover_authenticated_workbench(page, enterprise=enterprise, timeout_ms=8_000)
                if direct_page is not None:
                    page = direct_page
            if not self._has_enterprise_selector(page, enterprise):
                if not self._is_inside_ydz(page):
                    if not username or not password:
                        raise RuntimeError(
                            "Yidaizhang login signature is invalid and YDZ_USERNAME/YDZ_PASSWORD "
                            "are required to refresh login state."
                        )
                    self._login(page, username, password)
            page = self._select_enterprise(page, enterprise)

        self._go_batch_declare(page)
        ready = self._require_batch_declare_ready(page)
        if not self._wait_for_api_tokens(ready, timeout_ms=10_000):
            raise RuntimeError("Yidaizhang login token is missing after login refresh.")
        return ready

    def open_work_url(self, work_url: str) -> Page:
        url = str(work_url or "").strip()
        if not url:
            raise RuntimeError("Yidaizhang work URL is required.")
        if not self._is_ydz_work_url(url):
            raise RuntimeError("Yidaizhang work URL must be a cloud work.html URL.")
        page = self.context.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(5_000)
        self._go_batch_declare(page)
        ready = self._require_batch_declare_ready(page)
        if not self._wait_for_api_tokens(ready, timeout_ms=10_000):
            raise RuntimeError("Yidaizhang login token is missing after opening explicit work URL.")
        return ready

    def ready_open_work_pages(self, exclude_urls: set[str] | None = None) -> list[Page]:
        excluded = set(exclude_urls or set())
        excluded_bases = {
            base for base in (self._work_url_base(url) for url in excluded) if base
        }
        pages: list[Page] = []
        seen: set[str] = set()
        seen_bases: set[str] = set()
        for page in list(self.context.pages):
            url = self._safe_page_url(page)
            base = self._work_url_base(url)
            if url in excluded or (base and base in excluded_bases) or not self._is_ydz_work_url(url):
                continue
            try:
                self._go_batch_declare(page)
                ready = self._require_batch_declare_ready(page)
                ready_url = self._safe_page_url(ready)
                ready_base = self._work_url_base(ready_url)
                if (
                    ready_url in excluded
                    or ready_url in seen
                    or (ready_base and ready_base in excluded_bases)
                    or (ready_base and ready_base in seen_bases)
                ):
                    continue
                if not self._wait_for_api_tokens(ready, timeout_ms=5_000):
                    continue
                pages.append(ready)
                seen.add(ready_url)
                if ready_base:
                    seen_bases.add(ready_base)
            except Exception as exc:
                LOGGER.debug("Ignoring non-ready Yidaizhang work page during open-tab scan: %s", exc)
        return pages

    def list_enterprises(self, username: str | None, password: str | None, limit: int = 50) -> list[str]:
        try:
            page = self._open_workbench_switcher()
            names = self._extract_workbench_enterprise_names(page, limit=limit)
            if names:
                return names
        except Exception as exc:
            LOGGER.debug("Could not list Yidaizhang enterprises from workbench: %s", exc)
        page = self._open_enterprise_selector(username=username, password=password, enterprise="")
        return self._extract_enterprise_names(page, limit=limit)

    def switch_enterprise(self, username: str | None, password: str | None, enterprise: str) -> Page:
        if not enterprise:
            raise RuntimeError("Yidaizhang enterprise name is required for switching.")
        workbench_error: Exception | None = None
        try:
            page = self._open_workbench_switcher()
            self._select_workbench_enterprise(page, enterprise)
            ydz_page = self._open_ydz_from_workbench(page)
            if ydz_page is not None:
                self._go_batch_declare(ydz_page)
                return self._require_batch_declare_ready(ydz_page)
            raise RuntimeError(
                "Yidaizhang app entry did not open a cloud workbench for the selected enterprise."
            )
        except Exception as exc:
            workbench_error = exc
            LOGGER.debug("Could not switch Yidaizhang enterprise from workbench: %s", exc)
        try:
            page = self._open_enterprise_selector(username=username, password=password, enterprise=enterprise)
            page = self._select_enterprise(page, enterprise)
            self._go_batch_declare(page)
            return self._require_batch_declare_ready(page)
        except Exception:
            if workbench_error is not None:
                raise workbench_error
            raise

    def _open_enterprise_selector(
        self,
        username: str | None,
        password: str | None,
        enterprise: str,
    ) -> Page:
        page = self.context.new_page()
        page.goto(YDZ_HOME_URL, wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(800)
        if self._is_inside_ydz(page):
            page.goto(YDZ_HOME_URL, wait_until="domcontentloaded", timeout=60_000)
            page.wait_for_timeout(800)
        if not self._has_visible_login_form(page):
            existing_cloud_urls = self._cloud_page_urls()
            self._open_enterprise_selector_if_authenticated(page, timeout_ms=8_000)
        if self._has_enterprise_selector(page, enterprise):
            return page
        direct_cloud_page = self._find_cloud_page(exclude_urls=existing_cloud_urls) if "existing_cloud_urls" in locals() else None
        if direct_cloud_page is not None or self._is_inside_ydz(page):
            if enterprise:
                raise RuntimeError(
                    "Yidaizhang enterprise selector was not shown; "
                    "the authenticated home page opened an existing workbench directly."
                )
            raise RuntimeError(
                "Yidaizhang enterprise selector was not shown; "
                "the authenticated home page opened the workbench directly."
            )
        if not username or not password:
            raise RuntimeError("YDZ_USERNAME and YDZ_PASSWORD are required when enterprise selector is absent.")
        if not self._has_visible_login_form(page):
            direct_page = self._recover_authenticated_workbench(page, enterprise=enterprise, timeout_ms=8_000)
            if self._has_enterprise_selector(page, enterprise):
                return page
            direct_cloud_page = direct_page or self._find_cloud_page()
            if direct_cloud_page is not None or self._is_inside_ydz(page):
                raise RuntimeError(
                    "Yidaizhang enterprise selector was not shown after entering the system; "
                    "cannot switch enterprise safely."
                )
            self._clear_ydz_auth_tokens()
            page.goto(YDZ_HOME_URL, wait_until="domcontentloaded", timeout=60_000)
            page.wait_for_timeout(800)
        self._login(page, username, password)
        if not self._has_enterprise_selector(page, enterprise):
            self._open_enterprise_selector_if_authenticated(page, timeout_ms=8_000)
        if not self._has_enterprise_selector(page, enterprise):
            raise RuntimeError("Could not open Yidaizhang enterprise selector after login.")
        return page

    def _clear_ydz_auth_tokens(self) -> None:
        for page in list(self.context.pages):
            try:
                if "ydz.chanjet.com" not in page.url and not self._is_ydz_cloud_url(page.url):
                    continue
                page.evaluate(
                    r"""() => {
                        const shouldRemove = key => {
                            const lower = String(key || '').toLowerCase();
                            return lower.includes('token')
                                || lower.includes('signature')
                                || lower === 'iframeToken'.toLowerCase()
                                || lower === 'ciaToken'.toLowerCase();
                        };
                        for (const storage of [window.localStorage, window.sessionStorage]) {
                            for (const key of Object.keys(storage)) {
                                if (shouldRemove(key)) storage.removeItem(key);
                            }
                        }
                    }"""
                )
            except Exception as exc:
                LOGGER.debug("Ignoring Yidaizhang token cleanup error: %s", exc)

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

    def _extract_enterprise_names(self, page: Page, limit: int) -> list[str]:
        limit = max(1, int(limit or 50))
        try:
            values = page.evaluate(
                r"""(limit) => {
                    const vis = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
                    const blocked = [
                        '\u9009\u62e9\u4f01\u4e1a', '\u767b\u5f55', '\u786e\u5b9a', '\u53d6\u6d88',
                        '\u8fdb\u5165\u7cfb\u7edf', '\u8fdb\u5165\u6613\u4ee3\u8d26', '\u641c\u7d22',
                        '\u4f01\u4e1a\u7f16\u7801', '\u4f01\u4e1a\u540d\u79f0'
                    ];
                    const clean = value => String(value || '').replace(/\s+/g, ' ').trim();
                    const leafish = el => {
                        const text = clean(el.innerText || el.textContent || '');
                        if (!text) return false;
                        const children = Array.from(el.children || []).filter(vis);
                        return !children.some(child => clean(child.innerText || child.textContent || '') === text);
                    };
                    const nodes = Array.from(document.querySelectorAll('li,td,div,span,label,a'))
                        .filter(el => vis(el) && leafish(el));
                    const result = [];
                    for (const el of nodes) {
                        let text = clean(el.innerText || el.textContent || '');
                        if (!text || text.length < 2 || text.length > 80) continue;
                        if (blocked.some(token => text.includes(token))) continue;
                        if (/^\d+$/.test(text)) continue;
                        if (!/[\u4e00-\u9fffA-Za-z]/.test(text)) continue;
                        if (result.includes(text)) continue;
                        result.push(text);
                        if (result.length >= limit) break;
                    }
                    return result;
                }""",
                limit,
            )
        except Exception as exc:
            LOGGER.debug("Could not extract Yidaizhang enterprise names: %s", exc)
            return []
        return [str(item).strip() for item in values or [] if str(item or "").strip()]

    def _open_workbench_page(self) -> Page:
        page = self.context.new_page()
        page.goto(YDZ_WORKBENCH_HOME_URL, wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(3_000)
        return page

    def _open_workbench_switcher(self) -> Page:
        page = self._open_workbench_page()
        clicked = page.evaluate(
            r"""() => {
                const switchText = '\u5207\u6362\u4f01\u4e1a';
                const vis = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
                const clean = value => String(value || '').replace(/\s+/g, '').trim();
                const buttons = Array.from(document.querySelectorAll('button')).filter(vis);
                const hit = buttons.find(el => clean(el.innerText || el.textContent || '') === switchText);
                if (hit) hit.click();
                return !!hit;
            }"""
        )
        if not clicked:
            raise RuntimeError("Could not locate workbench enterprise switch button.")
        deadline = time.time() + 10
        while time.time() < deadline:
            try:
                text = page.evaluate("() => document.body ? document.body.innerText : ''")
                if "\u5207\u6362\u5f53\u524d\u4f01\u4e1a" in text:
                    return page
            except Exception as exc:
                LOGGER.debug("Waiting for workbench enterprise switcher: %s", exc)
            page.wait_for_timeout(500)
        raise RuntimeError("Could not open workbench enterprise switcher.")

    def _extract_workbench_enterprise_names(self, page: Page, limit: int) -> list[str]:
        limit = max(1, int(limit or 50))
        try:
            values = page.evaluate(
                r"""(limit) => {
                    const vis = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
                    const compact = value => String(value || '').replace(/\s+/g, '').trim();
                    const nodes = Array.from(document.querySelectorAll('div,li')).filter(vis);
                    const result = [];
                    for (const el of nodes) {
                        const text = compact(el.innerText || el.textContent || '');
                        if (!text || text.length > 90 || !text.includes('ID\uff1a')) continue;
                        if (text.startsWith('\u4f01\u4e1aId') || text.includes('\u4f01\u4e1a\u7ba1\u7406\u5458')) continue;
                        const name = text.replace(/ID[:\uff1a]\d+.*$/, '').trim();
                        if (!name || name.includes('\u5207\u6362\u5f53\u524d\u4f01\u4e1a')) continue;
                        if (!result.includes(name)) result.push(name);
                        if (result.length >= limit) break;
                    }
                    return result;
                }""",
                limit,
            )
        except Exception as exc:
            LOGGER.debug("Could not extract workbench enterprise names: %s", exc)
            return []
        return [str(item).strip() for item in values or [] if str(item or "").strip()]

    def _select_workbench_enterprise(self, page: Page, enterprise: str) -> None:
        selected = page.evaluate(
            r"""(enterprise) => {
                const vis = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
                const compact = value => String(value || '').replace(/\s+/g, '').trim();
                const nodes = Array.from(document.querySelectorAll('.org-item,div,li')).filter(vis);
                const matches = nodes
                    .map(el => ({el, text: compact(el.innerText || el.textContent || '')}))
                    .filter(item => item.text.includes(enterprise) && item.text.includes('ID\uff1a') && item.text.length <= 100)
                    .sort((a, b) => {
                        const ac = String(a.el.className || '').includes('org-item') ? 0 : 1;
                        const bc = String(b.el.className || '').includes('org-item') ? 0 : 1;
                        if (ac !== bc) return ac - bc;
                        return a.text.length - b.text.length;
                    });
                const hit = matches.length ? matches[0].el : null;
                if (hit) {
                    hit.dispatchEvent(new MouseEvent('mouseover', {bubbles: true}));
                    hit.dispatchEvent(new MouseEvent('mousedown', {bubbles: true}));
                    hit.click();
                    hit.dispatchEvent(new MouseEvent('mouseup', {bubbles: true}));
                }
                return hit ? matches[0].text : '';
            }""",
            enterprise,
        )
        if not selected:
            raise RuntimeError(f"Could not locate Yidaizhang enterprise in workbench switcher: {enterprise}")
        deadline = time.time() + 12
        while time.time() < deadline:
            try:
                text = page.evaluate("() => document.body ? document.body.innerText : ''")
                if enterprise in text and "\u5207\u6362\u5f53\u524d\u4f01\u4e1a" not in text:
                    return
            except Exception as exc:
                LOGGER.debug("Waiting for workbench enterprise switch: %s", exc)
            page.wait_for_timeout(500)
        LOGGER.debug("Workbench enterprise switch did not visibly close selector for %s.", enterprise)

    def _open_ydz_from_workbench(self, page: Page) -> Page | None:
        existing_cloud_urls = self._cloud_page_urls()
        clicked = page.evaluate(
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
                const scored = Array.from(document.querySelectorAll('tr,.app-item,.app-card,li,div')).filter(vis).map(el => {
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
                if (!row) return false;
                const controls = Array.from(row.el.querySelectorAll('button,span,a,div')).filter(vis);
                const hit = controls.find(el => clean(el.innerText || el.textContent || '') === enterText)
                    || controls.find(el => clean(el.innerText || el.textContent || '').includes(enterText));
                if (hit) hit.click();
                return !!hit;
            }"""
        )
        if not clicked:
            raise RuntimeError("Could not locate Yidaizhang app entry in workbench.")
        deadline = time.time() + 30
        while time.time() < deadline:
            for candidate in self.context.pages:
                url = self._safe_page_url(candidate)
                if self._is_ydz_work_url(url) and url not in existing_cloud_urls:
                    return candidate
            if self._is_inside_ydz(page):
                return page
            page.wait_for_timeout(500)
        return self._find_cloud_page(exclude_urls=existing_cloud_urls)

    def _launch_chrome(self) -> None:
        Path(self.user_data_dir).mkdir(parents=True, exist_ok=True)
        args = [
            self.chrome_path,
            f"--load-extension={self.plugin_path}",
            f"--user-data-dir={self.user_data_dir}",
            f"--remote-debugging-port={self.cdp_port}",
            "--no-first-run",
            "--no-default-browser-check",
            *CHROME_AUTOMATION_STEALTH_ARGS,
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
            return self._is_ydz_work_url(page.url)
        except Exception:
            return False

    def _is_ydz_cloud_url(self, url: str) -> bool:
        value = str(url or "")
        return any(marker in value for marker in YDZ_CLOUD_MARKERS)

    def _is_ydz_work_url(self, url: str) -> bool:
        return self._is_ydz_cloud_url(url) and YDZ_WORK_MARKER in str(url or "")

    def _work_url_base(self, url: str) -> str:
        value = str(url or "")
        if YDZ_WORK_MARKER not in value:
            return ""
        return value.split(YDZ_WORK_MARKER, 1)[0] + YDZ_WORK_MARKER

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

    def _has_api_tokens(self, page: Page) -> bool:
        try:
            return bool(
                page.evaluate(
                    r"""() => {
                        const iframeToken = sessionStorage.getItem('iframeToken') || '';
                        const ciaToken = localStorage.getItem('ciaToken') || '';
                        return !!iframeToken && !!ciaToken;
                    }"""
                )
            )
        except Exception as exc:
            LOGGER.debug("Could not inspect Yidaizhang API tokens: %s", exc)
            return False

    def _wait_for_api_tokens(self, page: Page, timeout_ms: int) -> bool:
        deadline = time.time() + timeout_ms / 1000
        while time.time() < deadline:
            if self._has_api_tokens(page):
                return True
            page.wait_for_timeout(300)
        return self._has_api_tokens(page)

    def _wait_for_login_form(self, page: Page, timeout_ms: int) -> bool:
        deadline = time.time() + timeout_ms / 1000
        while time.time() < deadline:
            if self._has_visible_login_form(page):
                return True
            page.wait_for_timeout(300)
        return False

    def _open_enterprise_selector_if_authenticated(self, page: Page, timeout_ms: int = 8_000) -> None:
        existing_cloud_urls = self._cloud_page_urls()
        entry_href = self._find_ydz_entry_href(page)
        try:
            if entry_href:
                page.goto(entry_href, wait_until="domcontentloaded", timeout=60_000)
                opened = True
            else:
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
                            return text.includes('\u8fdb\u5165\u6613\u4ee3\u8d26') || text.includes('\u8fdb\u5165\u7cfb\u7edf');
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
            for candidate in self.context.pages:
                url = self._safe_page_url(candidate)
                if self._is_ydz_cloud_url(url) and url not in existing_cloud_urls:
                    return
            if self._is_ydz_cloud_url(self._safe_page_url(page)):
                return
            time.sleep(0.5)

    def _find_ydz_entry_href(self, page: Page) -> str | None:
        try:
            href = page.evaluate(
                r"""() => {
                    const vis = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
                    const anchors = Array.from(document.querySelectorAll('a[href]')).filter(vis);
                    const redirect = anchors.find(el => {
                        const href = String(el.href || '');
                        return href.includes('passport.chanjet.com/vm/redirectVM') && href.includes('appName=ydzee');
                    });
                    if (redirect) return redirect.href;
                    const entry = anchors.find(el => {
                        const text = (el.innerText || el.textContent || '').trim().replace(/\s+/g, '');
                        return text.includes('\u8fdb\u5165\u6613\u4ee3\u8d26') || text.includes('\u8fdb\u5165\u7cfb\u7edf');
                    });
                    return entry ? entry.href : '';
                }"""
            )
        except Exception as exc:
            LOGGER.debug("Could not find Yidaizhang entry href: %s", exc)
            return None
        href = str(href or "").strip()
        return href or None

    def _login(self, page: Page, username: str, password: str, captcha_code: str | None = None) -> None:
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

        effective_captcha_code = captcha_code if captcha_code is not None else get_env_login_captcha_code(page.url)
        filled = page.evaluate(
            r"""({username, password, captchaCode}) => {
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
                if (captchaInput && captchaCode) setInputValue(captchaInput, captchaCode);
                const checks = Array.from(document.querySelectorAll('input[type=checkbox]')).filter(vis);
                for (const cb of checks) {
                    if (!cb.checked) cb.click();
                }
                const agreeBox = Array.from(document.querySelectorAll('.check-box-wrapper, .check-box, .check-box-border, .login-common-checkbox'))
                    .find(el => vis(el) && el.closest('.agreement-wrapper'));
                if (agreeBox) agreeBox.click();
                return true;
            }""",
            {"username": username, "password": password, "captchaCode": effective_captcha_code},
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

    def _cloud_page_urls(self) -> set[str]:
        return {
            self._safe_page_url(candidate)
            for candidate in self.context.pages
                if self._is_ydz_cloud_url(self._safe_page_url(candidate))
        }

    def _direct_workbench_after_entry(self, page: Page, existing_cloud_urls: set[str]) -> Page | None:
        if self._is_inside_ydz(page):
            return page
        return self._find_cloud_page(exclude_urls=existing_cloud_urls)

    def _recover_authenticated_workbench(
        self,
        page: Page,
        enterprise: str,
        timeout_ms: int,
    ) -> Page | None:
        if self._is_inside_ydz(page):
            return page
        existing_cloud_urls = self._cloud_page_urls()
        self._open_enterprise_selector_if_authenticated(page, timeout_ms=timeout_ms)
        direct_page = self._direct_workbench_after_entry(page, existing_cloud_urls)
        if direct_page is not None:
            return direct_page
        if self._has_enterprise_selector(page, enterprise):
            return None
        if self._has_visible_login_form(page):
            return None
        direct_page = self._open_default_workbench(page)
        if direct_page is not None:
            return direct_page
        return None

    def _is_passport_redirect_page(self, page: Page) -> bool:
        try:
            return "passport.chanjet.com/vm/redirectVM" in page.url
        except Exception:
            return False

    def _open_default_workbench(self, page: Page) -> Page | None:
        for url in self._work_url_candidates():
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60_000)
                page.wait_for_timeout(5_000)
                if self._is_inside_ydz(page):
                    return page
            except Exception as exc:
                LOGGER.debug("Could not open default Yidaizhang workbench %s: %s", url, exc)
        return None

    def _work_url_candidates(self) -> list[str]:
        values = [
            os.environ.get("YDZ_WORK_URL", ""),
            os.environ.get("YDZ_PROD_WORK_URL", ""),
            YDZ_DEFAULT_WORK_URL,
        ]
        result: list[str] = []
        for value in values:
            url = str(value or "").strip()
            if not url or url in result:
                continue
            result.append(url)
        return result

    def _find_cloud_page(self, exclude_urls: set[str] | None = None) -> Page | None:
        excluded = exclude_urls or set()
        for candidate in self.context.pages:
            try:
                if self._is_ydz_cloud_url(candidate.url) and candidate.url not in excluded:
                    return candidate
            except Exception:
                continue
        return None

    def _select_enterprise(self, page: Page, enterprise: str) -> Page:
        page.wait_for_timeout(2000)
        if self._is_inside_ydz(page):
            return page
        try:
            text = page.evaluate("() => document.body ? document.body.innerText : ''")
        except Exception as exc:
            LOGGER.debug("Enterprise page changed while reading body: %s", exc)
            return self.get_ydz_page()
        if enterprise not in text and "\u786e\u5b9a" not in text:
            return self.get_ydz_page()

        existing_cloud_urls = self._cloud_page_urls()
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
            if self._is_inside_ydz(page):
                return page
            cloud_page = self._find_cloud_page(exclude_urls=existing_cloud_urls)
            if cloud_page is not None:
                return cloud_page
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


def get_env_login_captcha_code(url: str = "") -> str:
    for key in (
        "YDZ_INTE_LOGIN_CAPTCHA",
        "YDZ_INTE_CAPTCHA",
        "YDZ_INTE_VERIFY_CODE",
        "YDZ_LOGIN_CAPTCHA",
        "YDZ_CAPTCHA",
        "YDZ_VERIFY_CODE",
    ):
        value = os.environ.get(key)
        if value:
            return value
    lowered = str(url or "").lower()
    if ".inte." in lowered or "inte-" in lowered or "ydz-login.inte" in lowered:
        return "666666"
    return ""
