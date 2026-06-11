"""Task-driven tax bureau login flow.

This module promotes the working experiment from scripts into a reusable
service:

1. Call Chanjet getClientJob with the outer taskId in the logged-in browser.
2. Resolve province and inner taskId from the returned cookie taskInfo.
3. Poll getTaskCookie with the inner taskId and browser machineId.
4. Build the tpass login URL from returned cookies.
5. Install a browser init script that mirrors EtaxPlugin tpass cookie injection.
6. Prefer EtaxPlugin's clear-cookie/new-tab flow, with direct tpass URL as fallback.
"""

from __future__ import annotations

import json
import logging
import re
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
from src.login.log_sanitizer import redact_sensitive_text

logger = logging.getLogger(__name__)

GET_CLIENT_JOB_URL = (
    "https://data-task-management.chanjet.com/pub-tax-management/api/remote/getClientJob"
)
GET_CLIENT_JOB_FALLBACK_URL = (
    "https://data-task-management.chanapp.chanjet.com/pub-tax-management/api/remote/getClientJob"
)
GET_TASK_COOKIE_FALLBACK_URL = (
    "https://data-task-scheduler-ex.chanapp.chanjet.com/api/client/getTaskCookie"
)
DEFAULT_MACHINE_ID = "2D2D1044AF004A6A8CCAEBBDB5E03EDA"
PENDING_CLIENT_JOB_MAX_WAIT_SECONDS = 90
PENDING_CLIENT_JOB_FAST_FAIL_REPEAT_COUNT = 3
CLIENT_JOB_METADATA_MAX_WAIT_SECONDS = 90
TASK_COOKIE_POLL_MAX_WAIT_SECONDS = 90
TAX_PAGE_DIRECT_WAIT_MAX_SECONDS = 90
TAX_LOGIN_BLOCKER_FAST_FAIL_SECONDS = 15
TAX_LOADING_FAST_FAIL_SECONDS = 15


def normalize_task_province(province: str, tax_no: str = "") -> str:
    """Correct known task-province aliases before building tax-bureau URLs."""
    normalized = str(province or "").strip().lower()
    tax_no = str(tax_no or "").strip().upper()
    if normalized == "shandong" and is_qingdao_tax_no(tax_no):
        return "qingdao"
    return normalized


def is_qingdao_tax_no(tax_no: str) -> bool:
    """Qingdao uses a separate etax/tpass host although tasks may say shandong."""
    value = str(tax_no or "").strip().upper()
    return value.startswith("3702") or (len(value) >= 6 and value[2:6] == "3702")


def rewrite_province_url(value: str, source_province: str, target_province: str) -> str:
    if not value or not source_province or source_province == target_province:
        return value or ""
    result = str(value)
    for prefix in ("etax", "tpass", "dppt", "www.etax"):
        result = result.replace(
            f"{prefix}.{source_province}.chinatax.gov.cn",
            f"{prefix}.{target_province}.chinatax.gov.cn",
        )
    return result


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


class PendingTaxLoginJobError(RuntimeError):
    """Raised when Chanjet refuses a new tax-login job because another one is still running."""

    def __init__(self, message: str, pending_task_id: str = ""):
        self.pending_task_id = pending_task_id
        clean_message = message or "已有进税局任务暂未完成。"
        if pending_task_id and pending_task_id not in clean_message:
            clean_message = f"{clean_message} 占用任务：{pending_task_id}"
        super().__init__(clean_message)


class ForceTaxLoginRequiredError(RuntimeError):
    """Raised when Chanjet reports that a manual force-enter decision is required."""


class TaxLoginNotReadyError(RuntimeError):
    """Raised when the tax page is still at login/loading/auth-code instead of a usable portal."""


class TaskLoginFlow:
    """Login to the tax bureau using task metadata from Chanjet APIs."""

    def __init__(
        self,
        browser_manager: BrowserManager,
        timeout: int = 180,
        poll_timeout: int | None = None,
        login_strategy: str = "plugin_first",
    ):
        self.bm = browser_manager
        self.timeout = timeout
        self.poll_timeout = (
            poll_timeout
            if poll_timeout is not None
            else min(max(60, timeout), TASK_COOKIE_POLL_MAX_WAIT_SECONDS)
        )
        self.login_strategy = login_strategy if login_strategy in {"direct_first", "plugin_first"} else "plugin_first"
        self._tpass_cookie_init_script_installed = False

    def login(self, chanjet_page: Page, outer_task_id: str) -> tuple[Page, TaskLoginInfo]:
        """Run the task-login flow and return the logged-in tax page."""
        login_start = time.time()
        self.close_tax_pages()
        if self.login_strategy == "plugin_first":
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
        self.install_tpass_cookie_init_script()

        self.close_tax_pages()
        if self.login_strategy == "plugin_first":
            self.dispatch_open_tax_tab(chanjet_page, info)
            wait_start = time.time()
            plugin_wait_timeout = max(1, min(45, self.timeout))
            tax_page = self.wait_for_tax_page(
                info.province,
                timeout=plugin_wait_timeout,
                no_page_timeout=min(8, plugin_wait_timeout),
            )
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
                tax_page = self.wait_for_tax_page(
                    info.province,
                    timeout=min(TAX_PAGE_DIRECT_WAIT_MAX_SECONDS, max(60, self.timeout)),
                    blocker_timeout=TAX_LOGIN_BLOCKER_FAST_FAIL_SECONDS,
                    loading_timeout=TAX_LOADING_FAST_FAIL_SECONDS,
                    fail_on_login_blocker=True,
                )
        if not tax_page:
            raise TimeoutError(f"Tax bureau login timeout for province={info.province}")
        logger.info("Task tax login flow elapsed: %.1fs", time.time() - login_start)
        return tax_page, info

    def open_login_url_directly(self, info: TaskLoginInfo) -> Optional[Page]:
        self.install_tpass_cookie_init_script()
        self._clear_special_login_cookies(info.province)
        page = self.find_tax_login_page(info.province) or self.bm.new_page()
        page.goto(info.login_url, wait_until="domcontentloaded", timeout=30000)
        fallback_timeout = min(TAX_PAGE_DIRECT_WAIT_MAX_SECONDS, max(60, self.timeout))
        return self.wait_for_tax_page(
            info.province,
            timeout=fallback_timeout,
            blocker_timeout=TAX_LOGIN_BLOCKER_FAST_FAIL_SECONDS,
            loading_timeout=TAX_LOADING_FAST_FAIL_SECONDS,
            fail_on_login_blocker=True,
        )

    def install_tpass_cookie_init_script(self) -> bool:
        """Install a plugin-free tpass cookie injector for future navigations."""
        if self._tpass_cookie_init_script_installed:
            return True
        context = getattr(self.bm, "context", None)
        if context is None:
            context = getattr(self.bm, "_context", None)
        if context is None or not hasattr(context, "add_init_script"):
            logger.warning("Cannot install plugin-free tpass cookie init script: browser context is unavailable")
            return False
        context.add_init_script(script=self.tpass_cookie_init_script())
        self._tpass_cookie_init_script_installed = True
        logger.info("Installed plugin-free tpass cookie init script")
        return True

    @staticmethod
    def tpass_cookie_init_script() -> str:
        """Return a document-start script mirroring EtaxPlugin tpass cookie insertion."""
        return r"""
(() => {
  if (!window.location || !/\.chinatax\.gov\.cn$/i.test(window.location.hostname)) {
    return;
  }

  function getParam(name) {
    const sources = [];
    if (window.location.search) {
      sources.push(window.location.search.slice(1));
    }
    const hash = window.location.hash || '';
    const queryIndex = hash.indexOf('?');
    if (queryIndex >= 0) {
      sources.push(hash.slice(queryIndex + 1));
    }
    for (const source of sources) {
      for (const part of source.split('&')) {
        const eqIndex = part.indexOf('=');
        const key = eqIndex >= 0 ? part.slice(0, eqIndex) : part;
        if (key.toLowerCase() !== name.toLowerCase()) {
          continue;
        }
        const rawValue = eqIndex >= 0 ? part.slice(eqIndex + 1) : '';
        try {
          return decodeURIComponent(rawValue.replace(/\+/g, '%20'));
        } catch (e) {
          return rawValue;
        }
      }
    }
    return '';
  }

  function setCookie(name, value, daysToLive, path, domain) {
    if (!name || typeof document === 'undefined' || document.cookie === undefined) {
      return;
    }
    let cookie = String(name) + '=' + encodeURIComponent(value == null ? '' : String(value));
    if (typeof daysToLive === 'number') {
      const expires = new Date();
      expires.setTime(expires.getTime() + daysToLive * 24 * 60 * 60 * 1000);
      cookie += '; expires=' + expires.toUTCString();
    }
    if (domain) {
      cookie += '; domain=' + domain;
    }
    cookie += '; path=' + (path || '/');
    document.cookie = cookie;
  }

  function getCookie(name) {
    if (!name || typeof document === 'undefined' || document.cookie === undefined) {
      return '';
    }
    const prefix = String(name) + '=';
    for (const part of document.cookie.split(';')) {
      const value = part.trim();
      if (value.indexOf(prefix) === 0) {
        try {
          return decodeURIComponent(value.slice(prefix.length));
        } catch (e) {
          return value.slice(prefix.length);
        }
      }
    }
    return '';
  }

  function deleteCookie(name, path, domain) {
    if (!name || typeof document === 'undefined' || document.cookie === undefined) {
      return;
    }
    let cookie = String(name) + '=; expires=Thu, 01 Jan 1970 00:00:00 GMT';
    if (domain) {
      cookie += '; domain=' + domain;
    }
    cookie += '; path=' + (path || '/');
    document.cookie = cookie;
  }

  function setLocalStorage(name, value) {
    try {
      if (typeof localStorage !== 'undefined') {
        localStorage.setItem(name, value == null ? '' : String(value));
      }
    } catch (e) {}
  }

  function maybeParseJson(value) {
    if (!value) {
      return null;
    }
    if (typeof value === 'object') {
      return value;
    }
    try {
      return JSON.parse(value);
    } catch (e) {
      return null;
    }
  }

  function maybeJumpToTgtUrl() {
    if (!window.location || !/^etax\./i.test(window.location.hostname)) {
      return false;
    }
    if (!/\/loginb\/?/i.test(window.location.pathname || '')) {
      return false;
    }
    const target = getCookie('tgtUrl');
    if (!target || !/^https:\/\/[^/]+\.chinatax\.gov\.cn(?::\d+)?\//i.test(target)) {
      return false;
    }
    deleteCookie('tgtUrl', '/', '.chinatax.gov.cn');
    window.setTimeout(() => {
      window.location.href = target;
    }, 1000);
    return true;
  }

  const encodedCookie = getParam('cookie');
  if (!encodedCookie) {
    maybeJumpToTgtUrl();
    return;
  }

  let payload = null;
  try {
    payload = JSON.parse(encodedCookie);
  } catch (e) {
    try {
      payload = JSON.parse(decodeURIComponent(encodedCookie));
    } catch (inner) {
      return;
    }
  }
  if (!payload || typeof payload !== 'object') {
    return;
  }

  const etaxCookies = maybeParseJson(payload.etax_cookie);
  if (etaxCookies) {
    Object.keys(etaxCookies).forEach((key) => {
      setCookie(key, etaxCookies[key], '', '/', '.chinatax.gov.cn');
    });
  }

  const sharedDomainKeys = { tgtUrl: true, taskId: true, origin: true };
  let forceRedirect = false;
  let targetProvince = '';
  Object.keys(payload).forEach((key) => {
    const value = payload[key];
    if (sharedDomainKeys[key]) {
      setCookie(key, value, '', '/', '.chinatax.gov.cn');
    } else {
      setCookie(key, value, '', '/', '');
    }
    setLocalStorage(key, value);
    if (key === 'forceRedirectEtaxProvinces') {
      const province = payload.province || '';
      const provinces = String(value || '').split(',');
      if (province && provinces.includes(province)) {
        forceRedirect = true;
        targetProvince = province;
      }
    }
  });

  setCookie('etaxplgin', 'true', '', '/', '.chinatax.gov.cn');
  if (payload.floatSeconds) {
    setCookie('cookieExpireTime', Date.now() + 1000 * parseInt(payload.floatSeconds, 10), 1, '/', '.chinatax.gov.cn');
  }
  if (payload.warnSeconds) {
    setCookie('warnSeconds', payload.warnSeconds, 1, '/', '.chinatax.gov.cn');
  }

  window.__taxVerifyTpassCookieInjected = true;
  if (forceRedirect && targetProvince) {
    const noPort = ['shaanxi', 'sichuan'];
    const port = targetProvince === 'xizang' ? ':5100' : (noPort.includes(targetProvince) ? '' : ':8443');
    window.setTimeout(() => {
      window.location.href = `https://etax.${targetProvince}.chinatax.gov.cn${port}/loginb`;
    }, 2000);
  }
})();
"""

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
        deadline = time.time() + max(45, min(self.timeout, CLIENT_JOB_METADATA_MAX_WAIT_SECONDS))
        pending_deadline: float | None = None
        last_pending_message = ""
        last_pending_task_id = ""
        same_pending_task_count = 0
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
                if self._is_pending_client_job_message(message):
                    last_pending_message = message
                    pending_task_id = self._pending_client_job_task_id(message)
                    if pending_task_id and pending_task_id == last_pending_task_id:
                        same_pending_task_count += 1
                    else:
                        same_pending_task_count = 1 if pending_task_id else 0
                        last_pending_task_id = pending_task_id
                    if (
                        pending_task_id
                        and same_pending_task_count >= PENDING_CLIENT_JOB_FAST_FAIL_REPEAT_COUNT
                    ):
                        raise PendingTaxLoginJobError(
                            "已有进税局任务未完成，新的税局登录被后台拒绝。"
                            f"同一占用任务连续返回 {same_pending_task_count} 次，已快速结束本次候选，"
                            "请等待占用任务结束或在后台处理后重试。"
                            f"原始提示：{last_pending_message}",
                            pending_task_id=pending_task_id,
                        )
                    if pending_deadline is None:
                        pending_deadline = min(deadline, time.time() + PENDING_CLIENT_JOB_MAX_WAIT_SECONDS)
                    if time.time() < pending_deadline:
                        suffix = f" pendingTaskId={pending_task_id}" if pending_task_id else ""
                        logger.warning(
                            "getClientJob is blocked by a pending tax-login job%s repeat=%s/%s; waiting before retry: %s",
                            suffix,
                            same_pending_task_count,
                            PENDING_CLIENT_JOB_FAST_FAIL_REPEAT_COUNT,
                            message,
                        )
                        self.close_tax_pages()
                        time.sleep(min(15, max(1, pending_deadline - time.time())))
                        continue
                    pending_task_id = self._pending_client_job_task_id(last_pending_message)
                    raise PendingTaxLoginJobError(
                        f"已有进税局任务未完成，新的税局登录被后台拒绝。请等待任务结束，或在后台处理占用任务后重试。原始提示：{last_pending_message}",
                        pending_task_id=pending_task_id,
                    )
                raise RuntimeError(f"getClientJob failed: {message}")
            if self._client_job_needs_force_tax(result):
                summary = self._client_job_response_summary(result)
                raise ForceTaxLoginRequiredError(
                    "getClientJob returned needForceTax=true; the tax bureau has an active "
                    f"task that requires manual force-enter confirmation before verification can continue: {summary}"
                )
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
        active_machine_id = machine_id
        retried_with_browser_machine_id = False

        while time.time() - start < self.poll_timeout:
            try:
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
                    {"taskId": inner_task_id, "machineId": active_machine_id},
                )
            except Exception as exc:
                logger.warning("Browser getTaskCookie failed, falling back to Python requests: %s", exc)
                result = self._get_task_cookie_with_requests(inner_task_id, active_machine_id)

            flag = result.get("flag") if isinstance(result, dict) else None
            last_message = result.get("msg") or result.get("message") or "" if isinstance(result, dict) else ""
            elapsed = int(time.time() - start)
            logger.info("getTaskCookie poll: elapsed=%ss, flag=%s, msg=%s", elapsed, flag, last_message)

            if flag == 1 and result.get("data"):
                return result
            if flag == 0:
                if active_machine_id == DEFAULT_MACHINE_ID and not retried_with_browser_machine_id:
                    retried_with_browser_machine_id = True
                    refreshed_machine_id = self._get_machine_id(chanjet_page)
                    if refreshed_machine_id and refreshed_machine_id != DEFAULT_MACHINE_ID:
                        logger.warning(
                            "getTaskCookie failed with fallback machineId; retrying once with browser robotId"
                        )
                        active_machine_id = refreshed_machine_id
                        continue
                raise RuntimeError(f"getTaskCookie failed: {last_message}")
            time.sleep(3)

        elapsed = int(time.time() - start)
        raise TimeoutError(
            f"getTaskCookie polling timeout after {elapsed}s/{self.poll_timeout}s: {last_message}"
        )

    def _get_task_cookie_with_requests(self, inner_task_id: str, machine_id: str) -> dict[str, Any]:
        resp = requests.post(
            GET_TASK_COOKIE_FALLBACK_URL,
            json={"taskId": inner_task_id, "machineId": machine_id},
            timeout=20,
        )
        resp.raise_for_status()
        return resp.json()

    def build_login_url(self, task_cookie: dict[str, Any], client_job: dict[str, Any]) -> str:
        """Build the tpass login URL exactly like EtaxPlugin userLogin does."""
        gtc_data = task_cookie.get("data") or {}
        cj_data = client_job.get("data") or {}

        tydl = gtc_data.get("tydl") or {}
        declare_job = gtc_data.get("declareJob") or {}
        cookies = tydl.get("cookies") or {}
        pro_cid = tydl.get("proCid") or self._get(cj_data, "tydl.proCid", {})
        login_info = declare_job.get("loginInfo") or {}

        raw_province = (
            declare_job.get("province")
            or self._get(cj_data, "declareJob.province", "")
            or self._get(cj_data, "tydl.cookies.taskInfo.province", "")
        )
        tax_no = tydl.get("taxNo") or self._get(cj_data, "tydl.taxNo", "")
        province = normalize_task_province(raw_province, tax_no)
        if not province:
            raise ValueError("Cannot resolve province from task cookie/client job data")
        if raw_province and province != raw_province:
            logger.info("Adjusted task province from %s to %s for tax_no=%s", raw_province, province, tax_no or "-")

        redirect_url = rewrite_province_url(pro_cid.get("redirect_url", ""), raw_province, province)
        tgt_url = rewrite_province_url(
            gtc_data.get("tgtUrl")
            or self._get(cj_data, "tgtUrl", "")
            or self._get(cj_data, "tydl.cookies.taskInfo.tgtUrl", "")
            or redirect_url,
            raw_province,
            province,
        )
        login_cookies = {
            "province": province,
            "origin": "prod",
            "ciaToken": gtc_data.get("ciaToken", ""),
            "client_id": pro_cid.get("client_id", ""),
            "idcard": tydl.get("idcard") or self._get(cj_data, "tydl.idcard", ""),
            "taxNo": tax_no,
            "batchNo": tydl.get("batchNo") or self._get(cj_data, "tydl.batchNo", ""),
            "orgId": declare_job.get("clientUseorgId") or self._get(cj_data, "declareJob.clientUseorgId", ""),
            "loginVersion": login_info.get("loginVersion") or self._get(cj_data, "declareJob.loginInfo.loginVersion", ""),
            "proxyTaxNo": login_info.get("cSiteLoginName") or self._get(cj_data, "declareJob.loginInfo.cSiteLoginName", ""),
            "tgtUrl": tgt_url,
            "forceRedirectEtaxProvinces": gtc_data.get("forceRedirectEtaxProvinces") or cj_data.get("forceRedirectEtaxProvinces", ""),
            **(cookies.get("tpass_localstorage") or {}),
            **(cookies.get("etax_cookie") or {}),
            **(cookies.get("taskInfo") or {}),
        }
        login_cookies["province"] = province
        login_cookies["tgtUrl"] = tgt_url
        login_cookies["forceRedirectEtaxProvinces"] = province

        if gtc_data.get("floatSeconds"):
            login_cookies["floatSeconds"] = gtc_data["floatSeconds"]
        if gtc_data.get("warnSeconds"):
            login_cookies["warnSeconds"] = gtc_data["warnSeconds"]

        encoded_cookie = urllib.parse.quote(json.dumps(login_cookies, ensure_ascii=False))
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
        self._end_previous_plugin_task_if_any(chanjet_page)

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

    def _end_previous_plugin_task_if_any(self, page: Page) -> str:
        """Ask EtaxPlugin to close out a previous background task before opening a new tax tab."""
        try:
            result = page.evaluate(
                """async () => {
                    return await new Promise((resolve) => {
                        let done = false;
                        const finish = (value) => {
                            if (done) return;
                            done = true;
                            window.removeEventListener('getTaskIdResponse', handler);
                            resolve(value);
                        };
                        const handler = (event) => {
                            const taskId = event && event.detail && event.detail.taskId;
                            if (taskId) {
                                window.dispatchEvent(new CustomEvent('setEndCookie', { detail: { taskId } }));
                                finish('ended:' + taskId);
                            } else {
                                finish('no_task');
                            }
                        };
                        window.addEventListener('getTaskIdResponse', handler);
                        try {
                            window.dispatchEvent(new CustomEvent('getTaskId'));
                        } catch (e) {
                            finish('ERROR: ' + e.message);
                        }
                        window.setTimeout(() => finish('timeout'), 1500);
                    });
                }"""
            )
        except Exception as exc:
            logger.info("Could not ask EtaxPlugin to end previous tax-login task: %s", exc)
            return "ERROR"
        if isinstance(result, str) and result.startswith("ended:"):
            logger.info("Asked EtaxPlugin to end previous tax-login task before opening a new one: %s", result[6:])
        return str(result or "")

    def wait_for_tax_page(
        self,
        province: str,
        timeout: int,
        no_page_timeout: int | None = None,
        blocker_timeout: int | None = None,
        loading_timeout: int | None = None,
        fail_on_login_blocker: bool = False,
    ) -> Optional[Page]:
        """Wait until a logged-in tax page for the resolved province appears."""
        detector = LoginDetector(province=province)
        target_host = f"etax.{province}.chinatax.gov.cn"
        start = time.time()
        last_status_log = 0.0
        loading_started_at: float | None = None
        blocker_started_at: float | None = None
        blocker_limit = max(1, blocker_timeout or TAX_LOGIN_BLOCKER_FAST_FAIL_SECONDS)
        loading_limit = max(1, loading_timeout or 25)

        while time.time() - start < timeout:
            page = self._find_logged_in_tax_page(detector, target_host)
            if page:
                return page
            blocker = self._find_tax_login_blocker(province)
            loading_url = self._find_loading_tax_page_url(target_host)
            elapsed = time.time() - start
            if no_page_timeout is not None and elapsed >= no_page_timeout and not self._find_any_tax_page_url(province):
                logger.info(
                    "EtaxPlugin did not open a tax-bureau page within %.1fs; falling back quickly",
                    elapsed,
                )
                return None
            if blocker:
                if blocker_started_at is None:
                    blocker_started_at = time.time()
                elif time.time() - blocker_started_at >= min(blocker_limit, timeout):
                    message = (
                        "Tax bureau login state or digital account authentication is not ready: "
                        f"{blocker}. Please retry after the tax bureau login is ready."
                    )
                    logger.info(message)
                    if fail_on_login_blocker:
                        raise TaxLoginNotReadyError(message)
                    return None
            else:
                blocker_started_at = None
            if loading_url:
                if loading_started_at is None:
                    loading_started_at = time.time()
                elif time.time() - loading_started_at >= min(loading_limit, timeout):
                    message = (
                        "Tax bureau login state or digital account authentication is not ready: "
                        f"tax page stayed on loading page for {time.time() - loading_started_at:.1f}s; "
                        f"url={redact_sensitive_text(loading_url)}"
                    )
                    logger.info(
                        "%s",
                        message,
                    )
                    if fail_on_login_blocker:
                        raise TaxLoginNotReadyError(message)
                    logger.info(
                        "Tax bureau stayed on loading page for %.1fs; treating login as incomplete: %s",
                        time.time() - loading_started_at,
                        redact_sensitive_text(loading_url),
                    )
                    return None
            else:
                loading_started_at = None
            if elapsed - last_status_log >= 5:
                logger.info(
                    "Waiting for tax bureau login: elapsed=%.0fs timeout=%ss pages=%s",
                    elapsed,
                    timeout,
                    redact_sensitive_text(self._tax_page_status(target_host)),
                )
                last_status_log = elapsed
            time.sleep(1)

        return self._find_logged_in_tax_page(detector, target_host)

    def _find_tax_login_blocker(self, province: str) -> str:
        tpass_host = f"tpass.{province}.chinatax.gov.cn"
        etax_host = f"etax.{province}.chinatax.gov.cn"
        for page in self.bm.get_all_pages():
            try:
                url = page.url or ""
                lower = url.lower()
                if tpass_host not in url and etax_host not in url:
                    continue
                if "/loading" in lower:
                    continue
                text = ""
                try:
                    text = page.evaluate("document.body ? document.body.innerText.slice(0, 500) : ''")
                except Exception:
                    text = ""
                compact_text = " ".join(str(text or "").split())
                if tpass_host in url and "#/login" in lower:
                    return f"unified login page; url={redact_sensitive_text(url)}"
                if "/mhzx/api/mh/tpass/code" in lower:
                    return f"authorization-code page; url={redact_sensitive_text(url)}; text={compact_text[:120]}"
                blocker_hints = (
                    "\u4f1a\u8bdd\u5931\u6548",
                    "\u767b\u5f55\u5df2\u5931\u6548",
                    "\u767b\u5f55\u8d85\u65f6",
                    "\u8bf7\u91cd\u65b0\u767b\u5f55",
                    "\u6388\u6743\u7801\u4e0d\u80fd\u4e3a\u7a7a",
                    "session expired",
                )
                if any(hint in compact_text for hint in blocker_hints):
                    return f"session/login blocker; url={redact_sensitive_text(url)}; text={compact_text[:120]}"
            except Exception:
                continue
        return ""

    def _find_logged_in_tax_page(self, detector: LoginDetector, target_host: str) -> Optional[Page]:
        for page in self.bm.get_all_pages():
            try:
                url = page.url or ""
                if target_host not in url:
                    continue
                if "/loading" in url.lower():
                    continue
                if "tpass" in url and "#/login" in url:
                    continue
                if detector.is_logged_in(page) or self._looks_like_tax_portal(page):
                    logger.info("Tax bureau logged in: %s", redact_sensitive_text(url))
                    return page
            except Exception:
                continue
        return None

    def _find_loading_tax_page_url(self, target_host: str) -> str:
        for page in self.bm.get_all_pages():
            try:
                url = page.url or ""
                if target_host in url and "/loading" in url.lower():
                    return url
            except Exception:
                continue
        return ""

    def _find_any_tax_page_url(self, province: str) -> str:
        tpass_host = f"tpass.{province}.chinatax.gov.cn"
        etax_host = f"etax.{province}.chinatax.gov.cn"
        for page in self.bm.get_all_pages():
            try:
                url = page.url or ""
                if tpass_host in url or etax_host in url:
                    return url
            except Exception:
                continue
        return ""

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
                statuses.append(f"{redact_sensitive_text(url)} | {text[:80]}")
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
        session_expired_hints = (
            "\u4f1a\u8bdd\u5931\u6548",
            "\u767b\u5f55\u5df2\u5931\u6548",
            "\u767b\u5f55\u8d85\u65f6",
            "\u8bf7\u91cd\u65b0\u767b\u5f55",
            "session expired",
        )
        if any(hint in text for hint in session_expired_hints):
            return False
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

    def _clear_special_login_cookies(self, province: str) -> int:
        """Mirror targeted EtaxPlugin cookie cleanup for direct-login fallback."""
        if str(province or "").lower() != "qingdao":
            return 0
        context = getattr(self.bm, "context", None)
        if context is None:
            context = getattr(self.bm, "_context", None)
        if context is None or not hasattr(context, "clear_cookies"):
            logger.info("Cannot clear Qingdao special cookies before direct login: browser context unavailable")
            return 0

        domain_pattern = re.compile(r"^\.?etax\.qingdao\.chinatax\.gov\.cn$")
        cleared = 0
        for name in ("TGCT", "enable_gizqLgxJ4gkh"):
            try:
                context.clear_cookies(name=name, domain=domain_pattern)
                cleared += 1
            except Exception as exc:
                logger.warning("Failed to clear Qingdao special cookie %s before direct login: %s", name, exc)
        if cleared:
            logger.info("Cleared %s Qingdao special cookie(s) before direct tax login", cleared)
        return cleared

    def _build_info_from_client_job(
        self,
        outer_task_id: str,
        machine_id: str,
        client_job: dict[str, Any],
    ) -> TaskLoginInfo:
        data = client_job.get("data") or {}
        inner_task_id = self._client_job_inner_task_id(data)
        raw_province = self._client_job_province(data)
        tax_no = self._get(data, "tydl.taxNo", "") or self._get(data, "declareJob.taxNo", "")
        province = normalize_task_province(raw_province, tax_no)

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
        if raw_province and province != raw_province:
            logger.info("Adjusted task province from %s to %s for tax_no=%s", raw_province, province, tax_no or "-")

        return TaskLoginInfo(
            outer_task_id=outer_task_id,
            inner_task_id=inner_task_id,
            province=province,
            machine_id=machine_id,
            tax_no=tax_no,
            client_job=client_job,
        )

    def _get_machine_id(self, page: Page) -> str:
        deadline = time.time() + min(8, max(1, self.timeout))
        last_error = ""
        while True:
            try:
                machine_id = str(page.evaluate("window.robotId || ''") or "").strip()
            except Exception as exc:
                machine_id = ""
                last_error = str(exc)
            if machine_id:
                return machine_id
            if time.time() >= deadline:
                break
            time.sleep(0.5)

        if last_error:
            logger.warning(
                "Cannot resolve machineId from Chanjet page window.robotId; using fallback machineId: %s",
                last_error,
            )
        else:
            logger.warning(
                "Cannot resolve machineId from Chanjet page window.robotId; using fallback machineId"
            )
        return DEFAULT_MACHINE_ID

    def _current_task_id(self, task_cookie: dict[str, Any]) -> str:
        return self._get(task_cookie.get("data") or {}, "tydl.cookies.taskInfo.taskId", "")

    def _client_job_has_login_metadata(self, client_job: dict[str, Any]) -> bool:
        data = client_job.get("data") or {}
        return bool(self._client_job_inner_task_id(data) and self._client_job_province(data))

    def _client_job_needs_force_tax(self, client_job: dict[str, Any]) -> bool:
        data = client_job.get("data") if isinstance(client_job, dict) else None
        return self._contains_truthy_key(data if isinstance(data, dict) else {}, "needForceTax")

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
            "needForceTax": self._client_job_needs_force_tax(client_job),
        }

    def _is_pending_client_job_message(self, message: str) -> bool:
        text = str(message or "")
        normal_markers = (
            "正在执行进税局任务",
            "请您耐心等待",
            "之前执行过",
            "暂未完成",
            "耐心等待",
        )
        mojibake_markers = (
            "杩涚◣灞",
            "浠诲姟",
            "鎵ц",
            "绛夊緟",
            "鏆傛湭瀹屾垚",
            "鑰愬績",
        )
        if any(marker in text for marker in normal_markers + mojibake_markers):
            return True
        return bool(
            re.search(r"\d{12,}", text)
            and re.search(r"(pending|wait|unfinished|running|task)", text, re.IGNORECASE)
        )

    def _pending_client_job_task_id(self, message: str) -> str:
        text = str(message or "")
        match = re.search(r"进税局\((\d{12,})\)", text)
        if match:
            return match.group(1)
        match = re.search(r"(\d{12,})", text)
        return match.group(1) if match else ""

    def _contains_truthy_key(self, value: Any, key: str) -> bool:
        if isinstance(value, dict):
            for item_key, item_value in value.items():
                if item_key == key and self._is_truthy(item_value):
                    return True
                if self._contains_truthy_key(item_value, key):
                    return True
        elif isinstance(value, list):
            return any(self._contains_truthy_key(item, key) for item in value)
        return False

    @staticmethod
    def _is_truthy(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "y"}
        return bool(value)

    def _get(self, data: dict[str, Any], dotted_path: str, default: Any = "") -> Any:
        current: Any = data
        for part in dotted_path.split("."):
            if not isinstance(current, dict) or part not in current:
                return default
            current = current[part]
        return current
