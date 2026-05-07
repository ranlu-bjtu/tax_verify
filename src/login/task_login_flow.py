"""Task-driven tax bureau login flow.

This module promotes the working experiment from scripts into a reusable
service:

1. Call Chanjet getClientJob with the outer taskId in the logged-in browser.
2. Resolve province and inner taskId from the returned cookie taskInfo.
3. Poll getTaskCookie with the inner taskId and browser machineId.
4. Build the tpass login URL from returned cookies.
5. Ask EtaxPlugin background script to clear tax cookies and open the new tab.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.parse
from dataclasses import dataclass, field
from typing import Any, Optional

import requests
from playwright.sync_api import Page

from src.config.province_config import get_tax_domains
from src.login.browser_manager import BrowserManager
from src.login.login_detector import LoginDetector

logger = logging.getLogger(__name__)

GET_CLIENT_JOB_URL = (
    "https://data-task-management.chanjet.com/pub-tax-management/api/remote/getClientJob"
)
GET_CLIENT_JOB_FALLBACK_URL = (
    "https://data-task-management.chanapp.chanjet.com/pub-tax-management/api/remote/getClientJob"
)
DEFAULT_MACHINE_ID = "2D2D1044AF004A6A8CCAEBBDB5E03EDA"


@dataclass
class TaskLoginInfo:
    outer_task_id: str
    inner_task_id: str
    province: str
    machine_id: str
    tax_no: str = ""
    login_url: str = ""
    current_task_id: str = ""
    client_job: dict[str, Any] = field(default_factory=dict)
    task_cookie: dict[str, Any] = field(default_factory=dict)


class TaskLoginFlow:
    """Login to the tax bureau using task metadata from Chanjet APIs."""

    def __init__(
        self,
        browser_manager: BrowserManager,
        timeout: int = 180,
        poll_timeout: int = 60,
    ):
        self.bm = browser_manager
        self.timeout = timeout
        self.poll_timeout = poll_timeout

    def login(self, chanjet_page: Page, outer_task_id: str) -> tuple[Page, TaskLoginInfo]:
        """Run the task-login flow and return the logged-in tax page."""
        machine_id = self._get_machine_id(chanjet_page)
        client_job = self.get_client_job(chanjet_page, outer_task_id)
        info = self._build_info_from_client_job(
            outer_task_id=outer_task_id,
            machine_id=machine_id,
            client_job=client_job,
        )

        logger.info(
            "Resolved task metadata: province=%s, inner_task_id=%s, tax_no=%s",
            info.province,
            info.inner_task_id,
            info.tax_no or "-",
        )

        task_cookie = self.get_task_cookie(
            chanjet_page=chanjet_page,
            inner_task_id=info.inner_task_id,
            machine_id=machine_id,
        )
        info.task_cookie = task_cookie
        info.login_url = self.build_login_url(task_cookie, client_job)
        info.current_task_id = self._current_task_id(task_cookie) or info.inner_task_id

        self.close_tax_pages()
        self.dispatch_open_tax_tab(chanjet_page, info)

        tax_page = self.wait_for_tax_page(info.province, timeout=self.timeout)
        if not tax_page:
            logger.warning(
                "EtaxPlugin did not open a logged-in tax page before timeout; opening tpass login URL directly"
            )
            page = self.bm.new_page()
            page.goto(info.login_url, wait_until="domcontentloaded", timeout=30000)
            tax_page = self.wait_for_tax_page(info.province, timeout=min(60, self.timeout))
        if not tax_page:
            raise TimeoutError(f"Tax bureau login timeout for province={info.province}")
        return tax_page, info

    def get_client_job(self, page: Page, outer_task_id: str) -> dict[str, Any]:
        """Call getClientJob from the Chanjet page so auth headers are available."""
        logger.info("Calling getClientJob for outer taskId: %s", outer_task_id)
        try:
            result = page.evaluate(
                """async ({url, taskId}) => {
                    const requestUrl = `${url}?taskId=${taskId}&orgLoginType=NATIONAL&etaxPluginVersion=2.1.0.109`;
                    const auth = sessionStorage.getItem('Authorization') || '';
                    const accessToken = sessionStorage.getItem('access_token') || '';
                    const headers = { "Content-Type": "application/json" };
                    if (auth) headers["authorization"] = auth.startsWith('Bearer ') ? auth : "Bearer " + auth;
                    if (accessToken) headers["token"] = accessToken;
                    const resp = await fetch(requestUrl, {
                        method: "GET",
                        headers,
                        credentials: "include",
                    });
                    return await resp.json();
                }""",
                {"url": GET_CLIENT_JOB_URL, "taskId": outer_task_id},
            )
        except Exception as exc:
            logger.warning("Browser getClientJob failed, falling back to Python requests: %s", exc)
            result = self._get_client_job_with_requests(page, outer_task_id)

        if not isinstance(result, dict):
            raise RuntimeError("getClientJob returned a non-object response")
        if result.get("flag") == 0 or result.get("success") is False:
            raise RuntimeError(f"getClientJob failed: {result.get('msg') or result.get('message')}")
        return result

    def _get_client_job_with_requests(self, page: Page, outer_task_id: str) -> dict[str, Any]:
        tokens = page.evaluate(
            """() => ({
                auth: sessionStorage.getItem('Authorization') || '',
                accessToken: sessionStorage.getItem('access_token') || '',
            })"""
        )
        auth = tokens.get("auth") or ""
        access_token = tokens.get("accessToken") or ""
        if auth and not auth.startswith("Bearer "):
            auth = f"Bearer {auth}"

        headers = {
            "Content-Type": "application/json",
            "Origin": "https://public-manage.chanjet.com",
            "Referer": "https://public-manage.chanjet.com/",
        }
        if auth:
            headers["authorization"] = auth
        if access_token:
            headers["token"] = access_token

        resp = requests.get(
            GET_CLIENT_JOB_FALLBACK_URL,
            params={
                "taskId": outer_task_id,
                "orgLoginType": "NATIONAL",
                "etaxPluginVersion": "2.1.0.109",
            },
            headers=headers,
            timeout=20,
        )
        resp.raise_for_status()
        return resp.json()

    def get_task_cookie(
        self,
        chanjet_page: Page,
        inner_task_id: str,
        machine_id: str,
    ) -> dict[str, Any]:
        """Poll EtaxPlugin API getTaskCookie using the inner taskId."""
        logger.info("Polling getTaskCookie for inner taskId: %s", inner_task_id)
        start = time.time()
        last_message = ""

        while time.time() - start < self.poll_timeout:
            result = chanjet_page.evaluate(
                """async ({taskId, machineId}) => {
                    const fallback = 'https://data-task-scheduler-ex.chanapp.chanjet.com';
                    const apiRoot = window.etaxPlugin_getApiRoot ? window.etaxPlugin_getApiRoot() : fallback;
                    const resp = await fetch(`${apiRoot}/api/client/getTaskCookie`, {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ taskId, machineId })
                    });
                    return await resp.json();
                }""",
                {"taskId": inner_task_id, "machineId": machine_id},
            )

            flag = result.get("flag") if isinstance(result, dict) else None
            last_message = result.get("msg") or result.get("message") or "" if isinstance(result, dict) else ""
            elapsed = int(time.time() - start)
            logger.info("getTaskCookie poll: elapsed=%ss, flag=%s, msg=%s", elapsed, flag, last_message)

            if flag == 1 and result.get("data"):
                return result
            if flag == 0:
                raise RuntimeError(f"getTaskCookie failed: {last_message}")
            time.sleep(3)

        raise TimeoutError(f"getTaskCookie polling timeout: {last_message}")

    def build_login_url(self, task_cookie: dict[str, Any], client_job: dict[str, Any]) -> str:
        """Build the tpass login URL exactly like EtaxPlugin userLogin does."""
        gtc_data = task_cookie.get("data") or {}
        cj_data = client_job.get("data") or {}

        tydl = gtc_data.get("tydl") or {}
        declare_job = gtc_data.get("declareJob") or {}
        cookies = tydl.get("cookies") or {}
        pro_cid = tydl.get("proCid") or self._get(cj_data, "tydl.proCid", {})
        login_info = declare_job.get("loginInfo") or {}

        province = (
            declare_job.get("province")
            or self._get(cj_data, "declareJob.province", "")
            or self._get(cj_data, "tydl.cookies.taskInfo.province", "")
        )
        if not province:
            raise ValueError("Cannot resolve province from task cookie/client job data")

        login_cookies = {
            "province": province,
            "origin": "prod",
            "ciaToken": gtc_data.get("ciaToken", ""),
            "client_id": pro_cid.get("client_id", ""),
            "idcard": tydl.get("idcard") or self._get(cj_data, "tydl.idcard", ""),
            "taxNo": tydl.get("taxNo") or self._get(cj_data, "tydl.taxNo", ""),
            "batchNo": tydl.get("batchNo") or self._get(cj_data, "tydl.batchNo", ""),
            "orgId": declare_job.get("clientUseorgId") or self._get(cj_data, "declareJob.clientUseorgId", ""),
            "loginVersion": login_info.get("loginVersion") or self._get(cj_data, "declareJob.loginInfo.loginVersion", ""),
            "proxyTaxNo": login_info.get("cSiteLoginName") or self._get(cj_data, "declareJob.loginInfo.cSiteLoginName", ""),
            "tgtUrl": gtc_data.get("tgtUrl", ""),
            "forceRedirectEtaxProvinces": gtc_data.get("forceRedirectEtaxProvinces") or cj_data.get("forceRedirectEtaxProvinces", ""),
            **(cookies.get("tpass_localstorage") or {}),
            **(cookies.get("etax_cookie") or {}),
            **(cookies.get("taskInfo") or {}),
        }

        if gtc_data.get("floatSeconds"):
            login_cookies["floatSeconds"] = gtc_data["floatSeconds"]
        if gtc_data.get("warnSeconds"):
            login_cookies["warnSeconds"] = gtc_data["warnSeconds"]

        encoded_cookie = urllib.parse.quote(json.dumps(login_cookies, ensure_ascii=False))
        redirect_url = pro_cid.get("redirect_url", "")
        client_id = pro_cid.get("client_id", "")
        return (
            f"https://tpass.{province}.chinatax.gov.cn:8443/#/login"
            f"?redirect_uri={redirect_url}&client_id={client_id}&cookie={encoded_cookie}"
        )

    def dispatch_open_tax_tab(self, chanjet_page: Page, info: TaskLoginInfo) -> None:
        """Ask EtaxPlugin background script to clear cookies and open tpass tab."""
        tax_domains = get_tax_domains(info.province)
        logger.info("Dispatching clearTaxCookiesAndOpenNewTab for province=%s", info.province)

        has_plugin_bridge = chanjet_page.evaluate(
            "() => typeof window.etaxPlugin_getApiRoot === 'function'"
        )
        if not has_plugin_bridge:
            logger.warning(
                "EtaxPlugin bridge was not detected; opening tpass login URL directly without cookie cleanup"
            )
            page = self.bm.new_page()
            page.goto(info.login_url, wait_until="domcontentloaded", timeout=30000)
            return

        chanjet_page.evaluate(
            """() => {
                const fallback = 'https://data-task-scheduler-ex.chanapp.chanjet.com';
                const apiRoot = window.etaxPlugin_getApiRoot ? window.etaxPlugin_getApiRoot() : fallback;
                window.dispatchEvent(new CustomEvent('setApiRoot', { detail: { apiRoot } }));
            }"""
        )

        result = chanjet_page.evaluate(
            """({province, taxDomains, newTabUrl, taskId}) => {
                try {
                    window.dispatchEvent(new CustomEvent('clearTaxCookiesAndOpenNewTab', {
                        detail: { province, taxDomains, newTabUrl, ms: 2000, taskId }
                    }));
                    return 'dispatched';
                } catch (e) {
                    return 'ERROR: ' + e.message;
                }
            }""",
            {
                "province": info.province,
                "taxDomains": tax_domains,
                "newTabUrl": info.login_url,
                "taskId": info.current_task_id,
            },
        )
        if result != "dispatched":
            raise RuntimeError(f"Failed to dispatch EtaxPlugin login event: {result}")

    def wait_for_tax_page(self, province: str, timeout: int) -> Optional[Page]:
        """Wait until a logged-in tax page for the resolved province appears."""
        detector = LoginDetector(province=province)
        target_host = f"etax.{province}.chinatax.gov.cn"
        start = time.time()

        while time.time() - start < timeout:
            for page in self.bm.get_all_pages():
                try:
                    url = page.url or ""
                    if target_host not in url:
                        continue
                    if "tpass" in url:
                        continue
                    if detector.is_logged_in(page) or self._looks_like_tax_portal(page):
                        logger.info("Tax bureau logged in: %s", url)
                        return page
                except Exception:
                    continue
            time.sleep(3)

        return None

    def _looks_like_tax_portal(self, page: Page) -> bool:
        try:
            url = page.url or ""
            if "login" in url or "tpass" in url:
                return False
            text = page.evaluate("document.body ? document.body.innerText.slice(0, 3000) : ''")
        except Exception:
            return False
        return (
            "我要查询" in text
            or "我要办税" in text
            or "申报信息查询" in text
        )

    def close_tax_pages(self) -> int:
        """Close all existing tax tabs before opening the task-specific one."""
        closed = 0
        for page in list(self.bm.get_all_pages()):
            try:
                url = page.url or ""
                if "chinatax.gov.cn" not in url:
                    continue
                page.close()
                closed += 1
            except Exception:
                continue
        if closed:
            logger.info("Closed %s stale tax-bureau tab(s)", closed)
        return closed

    def _build_info_from_client_job(
        self,
        outer_task_id: str,
        machine_id: str,
        client_job: dict[str, Any],
    ) -> TaskLoginInfo:
        data = client_job.get("data") or {}
        inner_task_id = self._get(data, "tydl.cookies.taskInfo.taskId", "")
        province = self._get(data, "declareJob.province", "") or self._get(data, "tydl.cookies.taskInfo.province", "")
        tax_no = self._get(data, "tydl.taxNo", "") or self._get(data, "declareJob.taxNo", "")

        if not inner_task_id:
            raise ValueError("Cannot resolve inner taskId from getClientJob response")
        if not province:
            raise ValueError("Cannot resolve province from getClientJob response")

        return TaskLoginInfo(
            outer_task_id=outer_task_id,
            inner_task_id=inner_task_id,
            province=province,
            machine_id=machine_id,
            tax_no=tax_no,
            client_job=client_job,
        )

    def _get_machine_id(self, page: Page) -> str:
        machine_id = page.evaluate("window.robotId || ''")
        if not machine_id:
            logger.warning(
                "Cannot resolve machineId from Chanjet page window.robotId; using fallback machineId"
            )
            return DEFAULT_MACHINE_ID
        return machine_id

    def _current_task_id(self, task_cookie: dict[str, Any]) -> str:
        return self._get(task_cookie.get("data") or {}, "tydl.cookies.taskInfo.taskId", "")

    def _get(self, data: dict[str, Any], dotted_path: str, default: Any = "") -> Any:
        current: Any = data
        for part in dotted_path.split("."):
            if not isinstance(current, dict) or part not in current:
                return default
            current = current[part]
        return current
