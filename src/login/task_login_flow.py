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
import shutil
import subprocess
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
        poll_timeout: int | None = None,
        login_strategy: str = "direct_first",
    ):
        self.bm = browser_manager
        self.timeout = timeout
        self.poll_timeout = poll_timeout if poll_timeout is not None else max(60, timeout)
        self.login_strategy = login_strategy if login_strategy in {"direct_first", "plugin_first"} else "direct_first"

    def login(self, chanjet_page: Page, outer_task_id: str) -> tuple[Page, TaskLoginInfo]:
        """Run the task-login flow and return the logged-in tax page."""
        login_start = time.time()
        self.close_tax_pages()
        self.ensure_plugin_bridge(chanjet_page)
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
        if self.login_strategy == "plugin_first":
            self.dispatch_open_tax_tab(chanjet_page, info)
            wait_start = time.time()
            tax_page = self.wait_for_tax_page(info.province, timeout=min(8, self.timeout))
            logger.info("Tax bureau first-page wait elapsed: %.1fs", time.time() - wait_start)
            if not tax_page:
                logger.warning(
                    "EtaxPlugin did not open a logged-in tax page before timeout; opening tpass login URL directly"
                )
                tax_page = self.open_login_url_directly(info)
        else:
            logger.info("Opening tpass login URL directly for province=%s", info.province)
            try:
                tax_page = self.open_login_url_directly(info)
            except Exception as exc:
                logger.warning("Direct tpass login failed; will try EtaxPlugin fallback: %s", exc)
                tax_page = None

        if not tax_page:
            if self.login_strategy != "plugin_first":
                logger.warning("Direct tpass login did not complete; trying EtaxPlugin open-tab fallback")
                self.close_tax_pages()
                self.dispatch_open_tax_tab(chanjet_page, info)
                tax_page = self.wait_for_tax_page(info.province, timeout=min(120, max(60, self.timeout)))
        if not tax_page:
            raise TimeoutError(f"Tax bureau login timeout for province={info.province}")
        logger.info("Task tax login flow elapsed: %.1fs", time.time() - login_start)
        return tax_page, info

    def open_login_url_directly(self, info: TaskLoginInfo) -> Optional[Page]:
        page = self.find_tax_login_page(info.province) or self.bm.new_page()
        page.goto(info.login_url, wait_until="domcontentloaded", timeout=30000)
        fallback_timeout = min(120, max(60, self.timeout))
        return self.wait_for_tax_page(info.province, timeout=fallback_timeout)

    def ensure_plugin_bridge(self, page: Page, timeout: int = 12) -> bool:
        """Ensure EtaxPlugin content scripts are injected before dispatching login events."""

        if self._has_plugin_bridge(page, timeout=timeout):
            return True

        logger.info("EtaxPlugin bridge not ready on Chanjet page; reloading page before tax login")
        try:
            page.reload(wait_until="load", timeout=30000)
        except Exception as exc:
            logger.warning("Chanjet page reload for EtaxPlugin bridge failed: %s", exc)

        if self._has_plugin_bridge(page, timeout=timeout):
            logger.info("EtaxPlugin bridge became ready after Chanjet page reload")
            return True

        logger.warning("EtaxPlugin bridge is still unavailable after reload; direct tpass fallback may be slower")
        return False

    def _has_plugin_bridge(self, page: Page, timeout: int = 0) -> bool:
        deadline = time.time() + max(timeout, 0)
        while True:
            try:
                if page.evaluate("() => typeof window.etaxPlugin_getApiRoot === 'function'"):
                    return True
            except Exception:
                pass
            if time.time() >= deadline:
                return False
            time.sleep(0.5)

    def get_client_job(self, page: Page, outer_task_id: str) -> dict[str, Any]:
        """Call getClientJob from the Chanjet page so auth headers are available."""
        deadline = time.time() + max(45, min(self.timeout, 600))
        attempt = 0
        while True:
            attempt += 1
            logger.info("Calling getClientJob for outer taskId: %s (attempt %s)", outer_task_id, attempt)
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
                message = result.get("msg") or result.get("message") or ""
                if self._is_pending_client_job_message(message) and time.time() < deadline:
                    logger.warning("getClientJob is blocked by a pending tax-login job; waiting before retry: %s", message)
                    self.close_tax_pages()
                    time.sleep(min(15, max(1, deadline - time.time())))
                    continue
                raise RuntimeError(f"getClientJob failed: {message}")
            if not self._client_job_has_login_metadata(result):
                summary = self._client_job_response_summary(result)
                if time.time() < deadline:
                    logger.warning(
                        "getClientJob returned success but tax-login metadata is incomplete; retrying: %s",
                        summary,
                    )
                    time.sleep(min(5, max(1, deadline - time.time())))
                    continue
                raise RuntimeError(f"getClientJob returned incomplete tax-login metadata: {summary}")
            return result

        raise RuntimeError("getClientJob failed after retries")

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

        params = {
            "taskId": outer_task_id,
            "orgLoginType": "NATIONAL",
            "etaxPluginVersion": "2.1.0.109",
        }
        try:
            resp = requests.get(
                GET_CLIENT_JOB_FALLBACK_URL,
                params=params,
                headers=headers,
                timeout=20,
            )
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            if self._should_try_curl_fallback(exc):
                result = self._get_client_job_with_curl(headers, params, timeout=20)
                if result is not None:
                    return result
            raise

    def _get_client_job_with_curl(
        self,
        headers: dict[str, str],
        params: dict[str, str],
        timeout: int,
    ) -> dict[str, Any] | None:
        curl_path = shutil.which("curl.exe") or shutil.which("curl")
        if not curl_path:
            return None
        url = f"{GET_CLIENT_JOB_FALLBACK_URL}?{urllib.parse.urlencode(params)}"
        command = [
            curl_path,
            "-L",
            "--silent",
            "--show-error",
            "--max-time",
            str(timeout),
        ]
        for key, value in headers.items():
            command.extend(["-H", f"{key}: {value}"])
        command.append(url)
        try:
            logger.warning("Requests getClientJob failed; retrying with curl fallback")
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout + 5,
                check=False,
            )
            if completed.returncode != 0:
                logger.error("curl getClientJob fallback failed: %s", completed.stderr.strip())
                return None
            return json.loads(completed.stdout)
        except Exception as exc:
            logger.error("curl getClientJob fallback raised error: %s", exc)
            return None

    @staticmethod
    def _should_try_curl_fallback(exc: Exception) -> bool:
        text = str(exc)
        return "SSLEOFError" in text or "UNEXPECTED_EOF_WHILE_READING" in text

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

        elapsed = int(time.time() - start)
        raise TimeoutError(
            f"getTaskCookie polling timeout after {elapsed}s/{self.poll_timeout}s: {last_message}"
        )

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

        has_plugin_bridge = self._has_plugin_bridge(chanjet_page, timeout=3)
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
        last_status_log = 0.0

        while time.time() - start < timeout:
            page = self._find_logged_in_tax_page(detector, target_host)
            if page:
                return page
            elapsed = time.time() - start
            if elapsed - last_status_log >= 5:
                logger.info(
                    "Waiting for tax bureau login: elapsed=%.0fs timeout=%ss pages=%s",
                    elapsed,
                    timeout,
                    self._tax_page_status(target_host),
                )
                last_status_log = elapsed
            time.sleep(1)

        return self._find_logged_in_tax_page(detector, target_host)

    def _find_logged_in_tax_page(self, detector: LoginDetector, target_host: str) -> Optional[Page]:
        for page in self.bm.get_all_pages():
            try:
                url = page.url or ""
                if target_host not in url:
                    continue
                if "tpass" in url and "#/login" in url:
                    continue
                if detector.is_logged_in(page) or self._looks_like_tax_portal(page):
                    logger.info("Tax bureau logged in: %s", url)
                    return page
            except Exception:
                continue
        return None

    def find_tax_login_page(self, province: str) -> Optional[Page]:
        tpass_host = f"tpass.{province}.chinatax.gov.cn"
        etax_host = f"etax.{province}.chinatax.gov.cn"
        for page in reversed(self.bm.get_all_pages()):
            try:
                url = page.url or ""
                if tpass_host in url or etax_host in url:
                    page.bring_to_front()
                    return page
            except Exception:
                continue
        return None

    def _tax_page_status(self, target_host: str) -> str:
        statuses: list[str] = []
        for page in self.bm.get_all_pages():
            try:
                url = page.url or ""
                if "chinatax.gov.cn" not in url:
                    continue
                text = page.evaluate("document.body ? document.body.innerText.slice(0, 120) : ''")
                text = " ".join(str(text or "").split())
                statuses.append(f"{url} | {text[:80]}")
            except Exception:
                continue
        return " || ".join(statuses) or f"no {target_host} page"

    def _looks_like_tax_portal(self, page: Page) -> bool:
        try:
            url = page.url or ""
            if "login" in url or "tpass" in url:
                return False
            text = page.evaluate("document.body ? document.body.innerText.slice(0, 3000) : ''")
        except Exception:
            return False
        logged_in_hints = (
            "\u6211\u8981\u67e5\u8be2",
            "\u6211\u8981\u529e\u7a0e",
            "\u7533\u62a5\u4fe1\u606f\u67e5\u8be2",
            "\u672c\u671f\u5e94\u7533\u62a5",
            "\u7edf\u4e00\u793e\u4f1a\u4fe1\u7528\u4ee3\u7801",
            "\u7eb3\u7a0e\u4eba\u8bc6\u522b\u53f7",
        )
        if any(hint in text for hint in logged_in_hints):
            return True
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
        inner_task_id = self._client_job_inner_task_id(data)
        province = self._client_job_province(data)
        tax_no = self._get(data, "tydl.taxNo", "") or self._get(data, "declareJob.taxNo", "")

        if not inner_task_id:
            raise ValueError(
                f"Cannot resolve inner taskId from getClientJob response: "
                f"{self._client_job_response_summary(client_job)}"
            )
        if not province:
            raise ValueError(
                f"Cannot resolve province from getClientJob response: "
                f"{self._client_job_response_summary(client_job)}"
            )

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

    def _client_job_has_login_metadata(self, client_job: dict[str, Any]) -> bool:
        data = client_job.get("data") or {}
        return bool(self._client_job_inner_task_id(data) and self._client_job_province(data))

    def _client_job_inner_task_id(self, data: dict[str, Any]) -> str:
        for path in (
            "tydl.cookies.taskInfo.taskId",
            "tydl.taskInfo.taskId",
            "taskInfo.taskId",
            "declareJob.taskInfo.taskId",
        ):
            value = self._get(data, path, "")
            if value:
                return str(value)
        return ""

    def _client_job_province(self, data: dict[str, Any]) -> str:
        for path in (
            "declareJob.province",
            "tydl.cookies.taskInfo.province",
            "tydl.taskInfo.province",
            "taskInfo.province",
        ):
            value = self._get(data, path, "")
            if value:
                return str(value)
        return ""

    def _client_job_response_summary(self, client_job: dict[str, Any]) -> dict[str, Any]:
        data = client_job.get("data") if isinstance(client_job, dict) else None
        data = data if isinstance(data, dict) else {}
        tydl = data.get("tydl") if isinstance(data.get("tydl"), dict) else {}
        cookies = tydl.get("cookies") if isinstance(tydl.get("cookies"), dict) else {}
        task_info = cookies.get("taskInfo") if isinstance(cookies.get("taskInfo"), dict) else {}
        declare_job = data.get("declareJob") if isinstance(data.get("declareJob"), dict) else {}
        return {
            "flag": client_job.get("flag") if isinstance(client_job, dict) else None,
            "code": client_job.get("code") if isinstance(client_job, dict) else None,
            "success": client_job.get("success") if isinstance(client_job, dict) else None,
            "message": (client_job.get("msg") or client_job.get("message") or "") if isinstance(client_job, dict) else "",
            "dataKeys": sorted(data.keys()),
            "tydlKeys": sorted(tydl.keys()),
            "cookieKeys": sorted(cookies.keys()),
            "taskInfoKeys": sorted(task_info.keys()),
            "hasInnerTaskId": bool(self._client_job_inner_task_id(data)),
            "province": self._client_job_province(data),
            "hasDeclareJob": bool(declare_job),
            "hasTaxNo": bool(self._get(data, "tydl.taxNo", "") or self._get(data, "declareJob.taxNo", "")),
        }

    def _is_pending_client_job_message(self, message: str) -> bool:
        return (
            "正在执行进税局任务" in message
            or "请您耐心等待" in message
            or "之前执行过" in message
            or "暂未完成" in message
            or "耐心等待" in message
        )

    def _get(self, data: dict[str, Any], dotted_path: str, default: Any = "") -> Any:
        current: Any = data
        for part in dotted_path.split("."):
            if not isinstance(current, dict) or part not in current:
                return default
            current = current[part]
        return current
