import logging
import time
import re
from typing import Optional

from playwright.sync_api import Page, Browser

from src.login.login_detector import LoginDetector
from src.login.browser_manager import BrowserManager

logger = logging.getLogger(__name__)

CHANJET_TASK_URL = "https://public-manage.chanjet.com/taxserver#/taskManage/taxTaskList"


class AutoTaxLogin:
    """Automates tax bureau login via EtaxPlugin on an already-logged-in Chanjet page.

    Flow:
    1. User has manually logged into Chanjet backend
    2. Script connects to Chrome via CDP
    3. On Chanjet task page, triggers EtaxPlugin's startPollingTask or clicks "一键进税局"
    4. Plugin auto-login redirects to tax bureau
    5. Script waits for login completion and then navigates

    Usage:
        bm = BrowserManager()
        bm.connect_cdp(9222)
        page = bm.find_page_by_url("chanjet.com") or bm.get_page()
        auto = AutoTaxLogin(bm)
        auto.wait_for_chanjet_login(page, timeout=300)
        tax_page = auto.trigger_plugin_and_wait(page, task_id, province)
    """

    def __init__(self, browser_manager: BrowserManager, province: str = "jiangxi"):
        self.bm = browser_manager
        self.province = province
        self.detector = LoginDetector(province=province)

    def wait_for_chanjet_login(self, page: Page, timeout: int = 300) -> bool:
        """Poll until the Chanjet task page is loaded (user logged in manually).

        Checks URL for chanjet.com task list pattern and page content
        for task-related elements.
        """
        logger.info("Waiting for user to login to Chanjet...")
        start = time.time()

        while time.time() - start < timeout:
            # Find the Chanjet page across all tabs
            chanjet_page = self.bm.find_page_by_url("chanjet.com")
            if chanjet_page:
                try:
                    title = chanjet_page.title()
                    # Logged in if title doesn't contain "登录"
                    if title and "登录" not in title and "Login" not in title.lower():
                        logger.info(f"Chanjet logged in: title='{title}'")
                        return True
                except Exception:
                    pass
            time.sleep(3)

        logger.warning(f"Chanjet login wait timeout after {timeout}s")
        return False

    def trigger_plugin_and_wait(
        self, chanjet_page: Page, task_id: str, timeout: int = 120
    ) -> Optional[Page]:
        """Trigger EtaxPlugin login on Chanjet page and wait for tax bureau redirect.

        Strategy:
        1. Check if startPollingTask is available (plugin scripts injected)
        2. Try JS call: startPollingTask(taskId, '')
        3. If not available, try clicking "一键进税局" button on the page
        4. If button not found, try EtaxPlugin toolbar (popup)
        5. Wait for new tab/page at tax bureau URL

        Returns the tax bureau Page, or None on failure.
        """
        logger.info(f"Triggering EtaxPlugin auto-login for task: {task_id}")

        # Strategy 1: Call startPollingTask via JS
        triggered = self._try_js_trigger(chanjet_page, task_id)

        # Strategy 2: Click "一键进税局" button on page
        if not triggered:
            triggered = self._try_click_enter_button(chanjet_page, task_id)

        # Strategy 3: Click EtaxPlugin popup toolbar button
        if not triggered:
            triggered = self._try_plugin_popup(chanjet_page, task_id)

        if not triggered:
            logger.error("Could not trigger EtaxPlugin auto-login")
            return None

        # Wait for tax bureau page to appear
        return self._wait_for_tax_page(timeout)

    def _try_js_trigger(self, page: Page, task_id: str) -> bool:
        """Try calling startPollingTask via JavaScript on the Chanjet page."""
        try:
            has_func = page.evaluate("typeof window.startPollingTask === 'function'")
            if not has_func:
                logger.info("startPollingTask not available on this page")
                return False

            # Get robotId
            robot_id = page.evaluate("window.robotId || ''")
            logger.info(f"robotId: {robot_id or 'empty'}")

            # Call startPollingTask
            page.evaluate(f"window.startPollingTask('{task_id}', '')")
            logger.info("startPollingTask called successfully")
            return True
        except Exception as e:
            logger.warning(f"JS trigger failed: {e}")
            return False

    def _try_click_enter_button(self, page: Page, task_id: str) -> bool:
        """Try clicking a "一键进税局" or similar button on the task list page."""
        selectors = [
            "button:has-text('进税局')",
            "button:has-text('一键进')",
            "a:has-text('进税局')",
            "a:has-text('一键进')",
            "[class*='enter-tax']",
            "[class*='enterTax']",
        ]

        for selector in selectors:
            try:
                btn = page.query_selector(selector)
                if btn and btn.is_visible():
                    btn.click()
                    logger.info(f"Clicked button: {selector}")
                    return True
            except Exception:
                continue

        # Try to find the specific task row and click its action button
        try:
            rows = page.query_selector_all("tr, [class*='row'], [class*='item']")
            for row in rows:
                text = row.inner_text()
                if task_id in text or "增值税" in text:
                    action_btn = row.query_selector("button, a, [class*='action']")
                    if action_btn and action_btn.is_visible():
                        action_btn.click()
                        logger.info(f"Clicked action in task row")
                        return True
        except Exception as e:
            logger.warning(f"Task row click failed: {e}")

        logger.info("No '一键进税局' button found on page")
        return False

    def _try_plugin_popup(self, page: Page, task_id: str) -> bool:
        """Try to trigger EtaxPlugin via its popup HTML page.

        Opens the extension popup in a new tab and clicks the login button.
        """
        # EtaxPlugin popup URL - extension ID varies, try common pattern
        try:
            # Get extension ID from chrome://extensions
            # This requires navigating to extensions page
            # For now, try a direct approach
            popup_page = self.bm.new_page()
            # We can't reliably get the extension popup URL,
            # so this strategy is limited
            popup_page.close()
        except Exception:
            pass

        logger.info("Plugin popup trigger not available")
        return False

    def _wait_for_tax_page(self, timeout: int = 120) -> Optional[Page]:
        """Wait for a target-province tax bureau page to appear in any tab."""
        start = time.time()
        target_host = f"etax.{self.province}.chinatax.gov.cn"

        while time.time() - start < timeout:
            # Check all pages for the target province. Old tabs from other
            # provinces can remain open in the persistent Chrome profile.
            for tax_page in self.bm.get_all_pages():
                try:
                    url = tax_page.url or ""
                    if target_host not in url:
                        continue
                    if self.detector.is_logged_in(tax_page):
                        logger.info(f"Tax bureau logged in: {tax_page.url}")
                        return tax_page
                except Exception:
                    # Page might still be loading
                    pass
            time.sleep(3)

        logger.warning(f"Tax bureau login timeout after {timeout}s")
        return None
