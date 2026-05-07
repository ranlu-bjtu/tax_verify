import logging
from typing import Any, Optional

from playwright.sync_api import Page

from src.models.tax_type import NavigationStep, WebConfig

logger = logging.getLogger(__name__)


class NavigationEngine:
    """Navigates browser to target tax form page using configured steps.

    Executes a sequence of NavigationSteps (click, wait, fill, navigate)
    using Playwright API. Supports timeout and error handling per step.

    Also supports result-list pages: after navigation steps complete,
    if result_list is configured, iterates through query results by
    clicking each item and returning to the list page.
    """

    def __init__(self, page: Page):
        self.page = page

    def navigate_to_form(
        self,
        web_config: WebConfig,
        timeout_override: Optional[int] = None,
    ) -> bool:
        """Execute navigation steps to reach the target tax form page."""
        # Execute navigation steps
        for i, step in enumerate(web_config.navigation_steps):
            timeout = timeout_override or step.timeout
            logger.info(f"Step {i+1}: {step.action} — {step.description or 'no description'}")
            try:
                self._execute_step(step, timeout)
            except Exception as e:
                logger.error(f"Navigation step {i+1} failed: {step.action} — {e}")
                return False
        return True

    def get_result_count(self, result_list_config: Optional[dict] = None) -> int:
        """Get the number of query result items on the current page.

        Returns:
            Number of result rows/items found.
        """
        if not result_list_config:
            return 0

        row_selector = result_list_config.get("row_selector", "table tbody tr")
        try:
            rows = self.page.query_selector_all(row_selector)
            count = len([r for r in rows if r.is_visible()])
            logger.info(f"Found {count} result items on page")
            return count
        except Exception as e:
            logger.warning(f"Could not count result items: {e}")
            return 0

    def click_result_item(self, index: int, result_list_config: dict) -> bool:
        """Click the result item at the given index (0-based).

        Returns:
            True if successfully clicked and navigated to detail page.
        """
        row_selector = result_list_config.get("row_selector", "table tbody tr")
        click_selector = result_list_config.get("click_selector", "a, button, .view-btn")
        wait_ms = result_list_config.get("wait_after_click", 5000)

        try:
            rows = self.page.query_selector_all(row_selector)
            visible_rows = [r for r in rows if r.is_visible()]

            if index >= len(visible_rows):
                logger.warning(f"Result index {index} out of range ({len(visible_rows)} items)")
                return False

            row = visible_rows[index]
            # Try to find clickable element within the row
            clickable = row.query_selector(click_selector)
            if not clickable:
                # Fallback: click the row itself
                clickable = row

            logger.info(f"Clicking result item {index + 1}/{len(visible_rows)}")
            clickable.click()
            self.page.wait_for_load_state("domcontentloaded", timeout=wait_ms)
            return True

        except Exception as e:
            logger.error(f"Failed to click result item {index}: {e}")
            return False

    def go_back_to_results(self) -> bool:
        """Navigate back to the result list page from a detail page.

        Returns:
            True if successfully navigated back.
        """
        try:
            # Try common "back" or "return" buttons
            back_selectors = [
                "a:has-text('返回'), button:has-text('返回'), *:has-text('返回')",
                "a:has-text('返回列表'), button:has-text('返回列表')",
                "a.back-btn, .go-back-btn",
            ]
            for selector in back_selectors:
                try:
                    el = self.page.query_selector(selector)
                    if el and el.is_visible():
                        el.click()
                        self.page.wait_for_load_state("domcontentloaded", timeout=10000)
                        logger.info("Navigated back to result list")
                        return True
                except Exception:
                    continue

            # Fallback: browser back button
            self.page.go_back(wait_until="domcontentloaded", timeout=10000)
            logger.info("Used browser back to return to result list")
            return True

        except Exception as e:
            logger.warning(f"Failed to go back to results: {e}")
            return False

    def _execute_step(self, step: NavigationStep, timeout: int) -> None:
        """Execute a single navigation step."""
        action = step.action

        if action == "click":
            if not step.selector:
                raise ValueError("click step requires selector")
            self.page.click(step.selector, timeout=timeout)
            if step.wait_until:
                self.page.wait_for_load_state(step.wait_until, timeout=timeout)

        elif action == "wait":
            if not step.selector:
                raise ValueError("wait step requires selector")
            self.page.wait_for_selector(step.selector, timeout=timeout)

        elif action == "fill":
            if not step.selector or not step.value:
                raise ValueError("fill step requires selector and value")
            self.page.fill(step.selector, step.value, timeout=timeout)

        elif action == "navigate":
            if not step.value:
                raise ValueError("navigate step requires value (URL)")
            self.page.goto(step.value, wait_until="domcontentloaded", timeout=timeout)

        elif action == "select":
            if not step.selector or not step.value:
                raise ValueError("select step requires selector and value")
            self.page.select_option(step.selector, step.value, timeout=timeout)

        else:
            logger.warning(f"Unknown navigation action: {action}")


class PDFDownloader:
    """Downloads PDF from tax system using Playwright."""

    def __init__(self, page: Page, download_dir: str = "./output/pdf"):
        self.page = page
        self.download_dir = download_dir

    def download(self, pdf_config: Optional[Any] = None) -> Optional[str]:
        """Download PDF from the current page.

        Returns the path to the downloaded PDF file, or None on failure.
        """
        if pdf_config and pdf_config.url_template:
            url = pdf_config.url_template
            logger.info(f"Downloading PDF from: {url}")

        try:
            # Common PDF download approaches:
            # 1. Click a download/print button on the page
            download_btns = [
                "a[href*='.pdf']",
                "button:has-text('下载')",
                "button:has-text('打印')",
                ".download-btn",
                ".print-btn",
            ]

            for selector in download_btns:
                try:
                    el = self.page.query_selector(selector)
                    if el and el.is_visible():
                        with self.page.expect_download(timeout=30000) as download_info:
                            el.click()
                        download = download_info.value
                        path = download.path()
                        logger.info(f"PDF downloaded: {path}")
                        return str(path)
                except Exception:
                    continue

            logger.warning("Could not find PDF download button")
            return None

        except Exception as e:
            logger.error(f"PDF download failed: {e}")
            return None


class Screenshot:
    """Takes screenshots for auditing."""

    def __init__(self, output_dir: str = "./output/screenshots"):
        self.output_dir = output_dir

    def take(self, page: Page, name: str) -> Optional[str]:
        """Take a screenshot and save to output_dir."""
        from pathlib import Path

        Path(self.output_dir).mkdir(parents=True, exist_ok=True)
        filepath = Path(self.output_dir) / f"{name}.png"

        try:
            page.screenshot(path=str(filepath), full_page=True)
            logger.info(f"Screenshot saved: {filepath}")
            return str(filepath)
        except Exception as e:
            logger.error(f"Screenshot failed: {e}")
            return None