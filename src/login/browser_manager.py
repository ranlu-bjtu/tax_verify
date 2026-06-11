import logging
import subprocess
import time
from pathlib import Path
from typing import Optional

from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page, Playwright

logger = logging.getLogger(__name__)

ETAX_PLUGIN_PATH = Path(r"C:\Users\Administrator\Downloads\EtaxPlugin")
DEFAULT_CDP_PORT = 9222
CHROME_AUTOMATION_STEALTH_ARGS = ["--disable-blink-features=AutomationControlled"]


class BrowserManager:
    """Manages Chrome browser lifecycle with two modes:

    1. CDP mode: Connect to an already-running Chrome via CDP.
       User starts Chrome manually with --load-extension and
       --remote-debugging-port. Playwright connects over CDP.
       This is the recommended mode for EtaxPlugin support.

    2. Launch mode: Start Chrome via Playwright persistent context.
       Extensions may not load properly in this mode.
    """

    def __init__(self):
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._chrome_process: Optional[subprocess.Popen] = None
        self._mode: str = "none"

    def connect_cdp(self, cdp_port: int = DEFAULT_CDP_PORT) -> BrowserContext:
        """Connect to an already-running Chrome via CDP.

        User must start Chrome manually with:
          --load-extension=<EtaxPlugin_path>
          --remote-debugging-port=<cdp_port>
          --user-data-dir=<profile_dir>

        Returns the first browser context.
        """
        self._mode = "cdp"
        self._playwright = sync_playwright().start()
        try:
            self._browser = self._playwright.chromium.connect_over_cdp(
                f"http://127.0.0.1:{cdp_port}"
            )
        except Exception:
            self._browser = self._playwright.chromium.connect_over_cdp(
                f"http://localhost:{cdp_port}"
            )
        contexts = self._browser.contexts
        self._context = contexts[0] if contexts else self._browser.new_context()
        logger.info(f"Connected to Chrome via CDP (port {cdp_port})")
        return self._context

    def launch_with_extension(self, config: Optional[dict] = None) -> BrowserContext:
        """Launch Chrome with EtaxPlugin as a subprocess + CDP.

        Starts Chrome as a native process (ensures extension loads),
        then connects Playwright via CDP.

        Args:
            config: dict with keys:
                - user_data_dir: Profile directory
                - cdp_port: Remote debugging port
                - plugin_path: Path to EtaxPlugin
                - headless: Must be False
        """
        if config is None:
            config = {}

        self._mode = "launch"
        user_data_dir = config.get("user_data_dir", "./browser_profile/etax_session")
        cdp_port = config.get("cdp_port", DEFAULT_CDP_PORT)
        plugin_path = config.get("plugin_path", str(ETAX_PLUGIN_PATH))
        chrome_path = config.get(
            "chrome_path",
            r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        )

        Path(user_data_dir).mkdir(parents=True, exist_ok=True)

        cmd = [
            chrome_path,
            f"--user-data-dir={user_data_dir}",
            f"--remote-debugging-port={cdp_port}",
            "--no-first-run",
            "--no-default-browser-check",
            *CHROME_AUTOMATION_STEALTH_ARGS,
        ]
        plugin_disabled_values = {"", "none", "disabled", "false", "0"}
        if str(plugin_path).strip().lower() not in plugin_disabled_values:
            cmd.insert(1, f"--load-extension={plugin_path}")
        else:
            logger.info("Launching Chrome without EtaxPlugin extension")

        logger.info(f"Launching Chrome: {cmd}")
        self._chrome_process = subprocess.Popen(cmd)
        time.sleep(3)

        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.connect_over_cdp(
            f"http://127.0.0.1:{cdp_port}"
        )
        contexts = self._browser.contexts
        self._context = contexts[0] if contexts else self._browser.new_context()
        logger.info("Chrome launched and connected via CDP")
        return self._context

    def get_page(self) -> Page:
        """Get the most recently active page."""
        if self._context is None:
            raise RuntimeError("Browser not connected. Call connect_cdp() or launch_with_extension() first.")

        if self._context.pages:
            self._page = self._context.pages[-1]
        else:
            self._page = self._context.new_page()

        return self._page

    def get_all_pages(self) -> list[Page]:
        """Get all open pages across all contexts."""
        if self._browser is None:
            raise RuntimeError("Browser not connected.")
        pages = []
        for ctx in self._browser.contexts:
            pages.extend(ctx.pages)
        return pages

    def find_page_by_url(self, url_pattern: str) -> Optional[Page]:
        """Find a page whose URL matches the given pattern."""
        for page in self.get_all_pages():
            if url_pattern in page.url:
                return page
        return None

    def new_page(self) -> Page:
        """Create a new page in the current context."""
        if self._context is None:
            raise RuntimeError("Browser not connected.")
        return self._context.new_page()

    @property
    def context(self) -> Optional[BrowserContext]:
        return self._context

    @property
    def browser(self) -> Optional[Browser]:
        return self._browser

    @property
    def is_running(self) -> bool:
        return self._browser is not None

    def close(self) -> None:
        """Disconnect from Chrome. Does NOT kill the Chrome process
        (so user can keep it open for next session)."""
        if self._browser:
            try:
                self._browser.close()
                logger.info("Disconnected from Chrome")
            except Exception as e:
                logger.error(f"Error disconnecting: {e}")
            self._browser = None
            self._context = None
            self._page = None

        if self._playwright:
            try:
                self._playwright.stop()
                logger.info("Playwright stopped")
            except Exception as e:
                logger.error(f"Error stopping Playwright: {e}")
            self._playwright = None

    def kill_chrome(self) -> None:
        """Kill the Chrome subprocess if launched by this manager."""
        if self._chrome_process:
            self._chrome_process.terminate()
            self._chrome_process = None
            logger.info("Chrome subprocess terminated")
