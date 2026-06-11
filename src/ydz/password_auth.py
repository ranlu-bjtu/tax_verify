from __future__ import annotations

import base64
import json
import logging
import re
import secrets
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote, urlparse

import requests

from src.ydz.customer_creation import (
    YdzAuthContext,
    YdzCreateEnvironment,
    build_ydz_auth_context,
)

LOGGER = logging.getLogger(__name__)

CHANJET_LOGIN_CLIENT_ID = "4cb832be-e503-4075-9903-6aa8d9e29104"
CHANJET_LOGIN_RSA_MODULUS = (
    "D57B6EB2728B0377BBB94CD50EEC11902FF0BC5F2EBCA49AC2AA081621D28859A"
    "5272009C053BF1DDF765D831F88717869A7DC23F6AE2BBB92BF4ABEA487C5B44B5"
    "C9A108FE4B34994E03815F83D52584DAB454659B2A1AAC68006FA411747F8E7596"
    "7D060CC04EDCF3F5984B7D16D871A391D12BAA269C74E1B6B3E5A78B3E7"
)
CHANJET_LOGIN_RSA_EXPONENT = 0x10001

PASSWORD_LOGIN_TOKEN_READY = "TOKEN_READY"
PASSWORD_LOGIN_SSO_READY_TOKEN_UNAVAILABLE = "SSO_READY_TOKEN_UNAVAILABLE"
PASSWORD_LOGIN_MANUAL_VERIFICATION_REQUIRED = "MANUAL_VERIFICATION_REQUIRED"
PASSWORD_LOGIN_PASSWORD_CHANGE_REQUIRED = "PASSWORD_CHANGE_REQUIRED"
PASSWORD_LOGIN_BIND_PHONE_REQUIRED = "BIND_PHONE_REQUIRED"
PASSWORD_LOGIN_FAILED = "FAILED"

CHALLENGE_ERROR_CODES = {"400", "800", "900", "访问拒绝"}
PASSWORD_CHANGE_ERROR_CODES = {"20154", "10012", "10013"}
BIND_PHONE_ERROR_CODES = {"20115"}


@dataclass
class PasswordLoginResult:
    env: str
    status: str
    message: str = ""
    error_code: str = ""
    sso_ready: bool = False
    has_ticket: bool = False
    auth_context: YdzAuthContext | None = None
    raw_keys: list[str] = field(default_factory=list)

    def public_dict(self) -> dict[str, Any]:
        return {
            "env": self.env,
            "status": self.status,
            "message": self.message,
            "errorCode": self.error_code,
            "ssoReady": self.sso_ready,
            "hasTicket": self.has_ticket,
            "hasAuthContext": self.auth_context is not None,
            "rawKeys": list(self.raw_keys),
        }


def chanjet_rsa_encrypt(value: str) -> str:
    message = str(value or "").encode("utf-8")
    modulus = int(CHANJET_LOGIN_RSA_MODULUS, 16)
    key_len = (modulus.bit_length() + 7) // 8
    if len(message) > key_len - 11:
        raise ValueError("Chanjet login value is too long for RSA encryption.")
    padding_len = key_len - len(message) - 3
    padding = bytearray()
    while len(padding) < padding_len:
        chunk = secrets.token_bytes(padding_len - len(padding))
        padding.extend(byte for byte in chunk if byte != 0)
    encoded = b"\x00\x02" + bytes(padding[:padding_len]) + b"\x00" + message
    encrypted = pow(int.from_bytes(encoded, "big"), CHANJET_LOGIN_RSA_EXPONENT, modulus)
    encrypted_bytes = encrypted.to_bytes(key_len, "big")
    token = base64.b64encode(encrypted_bytes).decode("ascii")
    return "".join(token[index:index + 64] for index in range(0, len(token), 64))


def _parse_json_or_jsonp(text: str) -> dict[str, Any]:
    stripped = str(text or "").strip()
    if not stripped:
        return {}
    if stripped.startswith("{"):
        return json.loads(stripped)
    match = re.match(r"^[^(]+\((.*)\);?$", stripped, flags=re.S)
    if not match:
        raise ValueError("Response is neither JSON nor JSONP.")
    return json.loads(match.group(1))


class ChanjetPasswordAuthClient:
    """Best-effort direct Chanjet account-password login.

    The official login flow can require Aliyun slider, SMS, phone binding, or
    password-change prompts. This client only submits the documented password
    login endpoints and reports those challenge states. It does not solve or
    bypass CAPTCHA-style checks.
    """

    def __init__(
        self,
        env: YdzCreateEnvironment,
        session: requests.Session | None = None,
        timeout: int = 30,
    ) -> None:
        self.env = env
        self.session = session or requests.Session()
        self.timeout = timeout

    def login(
        self,
        username: str,
        password: str,
        *,
        work_url: str | None = None,
        verify_token: str | None = None,
        captcha_code: str | None = None,
    ) -> PasswordLoginResult:
        if not username or not password:
            return PasswordLoginResult(
                env=self.env.name,
                status=PASSWORD_LOGIN_FAILED,
                message="Yidaizhang username/password is not configured.",
            )
        try:
            self._open_login_page()
            auth_code = self._get_auth_code()
            effective_verify_token = verify_token or ""
            if not effective_verify_token and captcha_code:
                verify_response = self._account_verify(username, password, captcha_code)
                if not verify_response.get("result"):
                    return self._classify_login_response(verify_response, work_url=work_url)
                effective_verify_token = str(verify_response.get("verifyToken") or "").strip()
                if not effective_verify_token:
                    return PasswordLoginResult(
                        env=self.env.name,
                        status=PASSWORD_LOGIN_FAILED,
                        message="Yidaizhang captcha verification did not return a verifyToken.",
                        raw_keys=sorted(str(key) for key in verify_response.keys()),
                    )
            response = self._account_login(username, password, auth_code, effective_verify_token)
        except Exception as exc:
            LOGGER.debug("Direct Yidaizhang password login failed before response classification.", exc_info=True)
            return PasswordLoginResult(
                env=self.env.name,
                status=PASSWORD_LOGIN_FAILED,
                message=f"Direct password login request failed: {exc}",
            )

        return self._classify_login_response(response, work_url=work_url)

    def _classify_login_response(
        self,
        response: dict[str, Any],
        *,
        work_url: str | None,
    ) -> PasswordLoginResult:
        raw_keys = sorted(str(key) for key in response.keys())
        if response.get("result") is True:
            ticket_response = self._try_get_ticket()
            auth_context = self._try_extract_token_context(work_url or self.env.default_work_url)
            if auth_context is not None:
                return PasswordLoginResult(
                    env=self.env.name,
                    status=PASSWORD_LOGIN_TOKEN_READY,
                    message="Direct password login produced a Yidaizhang API token context.",
                    sso_ready=True,
                    has_ticket=bool(ticket_response),
                    auth_context=auth_context,
                    raw_keys=raw_keys,
                )
            return PasswordLoginResult(
                env=self.env.name,
                status=PASSWORD_LOGIN_SSO_READY_TOKEN_UNAVAILABLE,
                message=(
                    "Chanjet SSO login succeeded, but Yidaizhang business tokens were not exposed "
                    "through HTTP responses. Use browser mode to let work.html initialize tokens, "
                    "or provide token mode variables."
                ),
                sso_ready=True,
                has_ticket=bool(ticket_response),
                raw_keys=raw_keys,
            )

        error_code = str(
            response.get("errorCode")
            or (response.get("error") or {}).get("code")
            or ""
        )
        message = str(
            response.get("errorMessage")
            or response.get("msg")
            or (response.get("error") or {}).get("msg")
            or error_code
            or "Direct password login did not succeed."
        )
        if error_code in CHALLENGE_ERROR_CODES or response.get("captchaResult") is False:
            return PasswordLoginResult(
                env=self.env.name,
                status=PASSWORD_LOGIN_MANUAL_VERIFICATION_REQUIRED,
                message=(
                    message
                    or "Yidaizhang password login requires slider or other manual verification."
                ),
                error_code=error_code,
                raw_keys=raw_keys,
            )
        if error_code in PASSWORD_CHANGE_ERROR_CODES:
            return PasswordLoginResult(
                env=self.env.name,
                status=PASSWORD_LOGIN_PASSWORD_CHANGE_REQUIRED,
                message=message,
                error_code=error_code,
                raw_keys=raw_keys,
            )
        if error_code in BIND_PHONE_ERROR_CODES:
            return PasswordLoginResult(
                env=self.env.name,
                status=PASSWORD_LOGIN_BIND_PHONE_REQUIRED,
                message=message,
                error_code=error_code,
                raw_keys=raw_keys,
            )
        return PasswordLoginResult(
            env=self.env.name,
            status=PASSWORD_LOGIN_FAILED,
            message=message,
            error_code=error_code,
            raw_keys=raw_keys,
        )

    def _open_login_page(self) -> None:
        self.session.get(
            self.login_page_url,
            headers=self._headers(content_type=False),
            timeout=self.timeout,
        )

    def _get_auth_code(self) -> str:
        callback = f"jsonp_{int(time.time() * 1000)}_{secrets.randbelow(900) + 100}"
        response = self.session.get(
            f"{self.cia_base_url}/internal_api/getAuthCodeByJsonp",
            params={"client_id": CHANJET_LOGIN_CLIENT_ID, "callback": callback},
            headers=self._headers(content_type=False),
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = _parse_json_or_jsonp(response.text)
        auth_code = str(data.get("auth_code") or data.get("code") or "")
        if not auth_code:
            raise RuntimeError("Chanjet CIA auth_code was not returned.")
        return auth_code

    def _account_login(
        self,
        username: str,
        password: str,
        auth_code: str,
        verify_token: str,
    ) -> dict[str, Any]:
        payload = {
            "auth_username": chanjet_rsa_encrypt(username),
            "passwordEncrypted": chanjet_rsa_encrypt(password),
            "auth_code": auth_code,
            "verifyToken": verify_token,
            "jsonp": "0",
        }
        response = self.session.post(
            f"{self.api_base_url}/loginV2/accountLogin",
            data=payload,
            headers=self._headers(content_type=True),
            timeout=self.timeout,
        )
        response.raise_for_status()
        return _parse_json_or_jsonp(response.text)

    def _account_verify(self, username: str, password: str, captcha_code: str) -> dict[str, Any]:
        payload = {
            "authUsername": chanjet_rsa_encrypt(username),
            "passwordEncrypted": chanjet_rsa_encrypt(password),
            "captcha": str(captcha_code or "").strip(),
        }
        response = self.session.post(
            f"{self.api_base_url}/loginV2/accountVerify",
            data=payload,
            headers=self._headers(content_type=True),
            timeout=self.timeout,
        )
        response.raise_for_status()
        return _parse_json_or_jsonp(response.text)

    def _try_get_ticket(self) -> dict[str, Any] | None:
        try:
            response = self.session.post(
                f"{self.api_base_url}/loginV2/getTicket",
                headers=self._headers(content_type=True),
                timeout=self.timeout,
            )
            response.raise_for_status()
            return _parse_json_or_jsonp(response.text)
        except Exception:
            LOGGER.debug("Direct password login could not read getTicket.", exc_info=True)
            return None

    def _try_extract_token_context(self, work_url: str) -> YdzAuthContext | None:
        try:
            response = self.session.get(
                work_url,
                headers=self._headers(content_type=False),
                timeout=self.timeout,
            )
            response.raise_for_status()
        except Exception:
            LOGGER.debug("Direct password login could not fetch Yidaizhang work URL.", exc_info=True)
            return None
        text = response.text or ""
        iframe_token = self._extract_token_string(text, "iframeToken")
        cia_token = self._extract_token_string(text, "ciaToken")
        if not iframe_token or not cia_token:
            return None
        try:
            return build_ydz_auth_context(
                self.env,
                iframe_token=iframe_token,
                cia_token=cia_token,
                work_url=work_url,
            )
        except Exception:
            LOGGER.debug("Direct password login found token strings but context validation failed.", exc_info=True)
            return None

    @staticmethod
    def _extract_token_string(text: str, key: str) -> str:
        patterns = (
            rf"{re.escape(key)}['\"]?\s*[:=]\s*['\"]([^'\"]+)['\"]",
            rf"['\"]{re.escape(key)}['\"]\s*,\s*['\"]([^'\"]+)['\"]",
        )
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1).strip()
        return ""

    def _headers(self, *, content_type: bool) -> dict[str, str]:
        headers = {
            "Accept": "application/json, text/plain, */*",
            "User-Agent": "Mozilla/5.0",
            "Referer": self.login_page_url,
            "Domain": urlparse(self.login_page_url).hostname or "",
            "Chanjet-Client-Language": "zh-CN",
            "Chanjet-Client-TimeZone": "Asia/Shanghai",
        }
        if content_type:
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        return headers

    @property
    def login_page_url(self) -> str:
        callback = quote(self.env.public_url, safe="")
        if self.env.name == "inte":
            return f"https://ydz-login.inte.chanjet.com/?callback={callback}"
        return f"https://login.chanjet.com/?callback={callback}"

    @property
    def api_base_url(self) -> str:
        if self.env.name == "inte":
            return "https://passport.inte.chanjet.com"
        return "https://login.chanjet.com"

    @property
    def cia_base_url(self) -> str:
        if self.env.name == "inte":
            return "https://inte-cia.chanapp.chanjet.com"
        return "https://cia.chanapp.chanjet.com"
