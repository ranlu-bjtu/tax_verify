from __future__ import annotations

import base64
import json
import logging
import re
import secrets
import time
from dataclasses import dataclass, field
from typing import Any, Protocol
from urllib.parse import quote, urlparse

import requests

LOGGER = logging.getLogger(__name__)

PUBLIC_MANAGE_TOKEN_URL = "https://public-manage.chanjet.com/token"
PUBLIC_MANAGE_DEFAULT_URL = "https://public-manage.chanjet.com/taxserver/#/taskManage/taxTaskList"
PUBLIC_MANAGE_CLIENT_ID = "f5b78222-5ade-465b-b080-cc31abc0f2b8"
CHANJET_LOGIN_RSA_CLIENT_ID = "4cb832be-e503-4075-9903-6aa8d9e29104"

ADMIN_AUTH_READY = "TOKEN_READY"
ADMIN_AUTH_MANUAL_VERIFICATION_REQUIRED = "MANUAL_VERIFICATION_REQUIRED"
ADMIN_AUTH_FAILED = "FAILED"

CHALLENGE_ERROR_CODES = {"400", "800", "900", "访问拒绝", "璁块棶鎷掔粷"}

CHANJET_LOGIN_RSA_MODULUS = (
    "D57B6EB2728B0377BBB94CD50EEC11902FF0BC5F2EBCA49AC2AA081621D28859A"
    "5272009C053BF1DDF765D831F88717869A7DC23F6AE2BBB92BF4ABEA487C5B44B5"
    "C9A108FE4B34994E03815F83D52584DAB454659B2A1AAC68006FA411747F8E7596"
    "7D060CC04EDCF3F5984B7D16D871A391D12BAA269C74E1B6B3E5A78B3E7"
)
CHANJET_LOGIN_RSA_EXPONENT = 0x10001


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


@dataclass(frozen=True)
class AdminAuthTokens:
    authorization: str
    token: str
    user_id: str = ""
    source: str = ""

    def as_dict(self) -> dict[str, str]:
        return {
            "authorization": self.authorization,
            "token": self.token,
        }


class AdminAuthTokenProvider(Protocol):
    def get_tokens(self, force_refresh: bool = False) -> AdminAuthTokens:
        ...


@dataclass
class AdminPasswordLoginResult:
    status: str
    message: str = ""
    error_code: str = ""
    tokens: AdminAuthTokens | None = None
    raw_keys: list[str] = field(default_factory=list)

    def public_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "message": self.message,
            "errorCode": self.error_code,
            "hasTokens": self.tokens is not None,
            "rawKeys": list(self.raw_keys),
        }


class StaticAdminAuthProvider:
    def __init__(self, tokens: AdminAuthTokens) -> None:
        self.tokens = tokens

    def get_tokens(self, force_refresh: bool = False) -> AdminAuthTokens:
        return self.tokens


class PasswordAdminAuthProvider:
    def __init__(self, client: "ChanjetAdminPasswordAuthClient") -> None:
        self.client = client
        self._tokens: AdminAuthTokens | None = None

    def get_tokens(self, force_refresh: bool = False) -> AdminAuthTokens:
        if self._tokens is not None and not force_refresh:
            return self._tokens
        result = self.client.login()
        if result.tokens is None:
            raise RuntimeError(
                f"Public management password auth failed: status={result.status} "
                f"code={result.error_code or '-'} message={result.message}"
            )
        self._tokens = result.tokens
        return self._tokens


class ChanjetAdminPasswordAuthClient:
    """Login to public-manage through the normal Chanjet SSO API chain.

    This is not a challenge bypass. If the login service requires slider/SMS
    verification, the caller receives MANUAL_VERIFICATION_REQUIRED and should
    fall back to the browser flow.
    """

    def __init__(
        self,
        username: str,
        password: str,
        *,
        public_manage_url: str = PUBLIC_MANAGE_DEFAULT_URL,
        session: requests.Session | None = None,
        timeout: int = 30,
    ) -> None:
        self.username = str(username or "")
        self.password = str(password or "")
        self.public_manage_url = str(public_manage_url or PUBLIC_MANAGE_DEFAULT_URL)
        self.session = session or requests.Session()
        self.timeout = timeout

    def login(self) -> AdminPasswordLoginResult:
        if not self.username or not self.password:
            return AdminPasswordLoginResult(
                status=ADMIN_AUTH_FAILED,
                message="Public management username/password is not configured.",
            )
        try:
            self._open_login_page()
            auth_code = self._get_auth_code(CHANJET_LOGIN_RSA_CLIENT_ID)
            login_response = self._account_login(auth_code)
        except Exception as exc:
            LOGGER.debug("Public management password login request failed.", exc_info=True)
            return AdminPasswordLoginResult(
                status=ADMIN_AUTH_FAILED,
                message=f"Public management password login request failed: {exc}",
            )

        classified = self._classify_login_response(login_response)
        if classified.status != ADMIN_AUTH_READY:
            return classified
        return self._exchange_public_manage_tokens()

    def _classify_login_response(self, response: dict[str, Any]) -> AdminPasswordLoginResult:
        raw_keys = sorted(str(key) for key in response.keys())
        if response.get("result") is True:
            self._try_get_ticket()
            return AdminPasswordLoginResult(status=ADMIN_AUTH_READY, raw_keys=raw_keys)
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
            or "Public management password login did not succeed."
        )
        if error_code in CHALLENGE_ERROR_CODES or response.get("captchaResult") is False:
            return AdminPasswordLoginResult(
                status=ADMIN_AUTH_MANUAL_VERIFICATION_REQUIRED,
                message=message,
                error_code=error_code,
                raw_keys=raw_keys,
            )
        return AdminPasswordLoginResult(
            status=ADMIN_AUTH_FAILED,
            message=message,
            error_code=error_code,
            raw_keys=raw_keys,
        )

    def _exchange_public_manage_tokens(self) -> AdminPasswordLoginResult:
        try:
            code_response = self._authorize_public_manage()
            if code_response.get("auth_code") and not code_response.get("code"):
                return AdminPasswordLoginResult(
                    status=ADMIN_AUTH_FAILED,
                    message="Chanjet SSO login did not authorize public-manage.",
                    raw_keys=sorted(str(key) for key in code_response.keys()),
                )
            code = str(code_response.get("code") or "").strip()
            if not code:
                return AdminPasswordLoginResult(
                    status=ADMIN_AUTH_FAILED,
                    message="public-manage authorizeByJsonp did not return code.",
                    raw_keys=sorted(str(key) for key in code_response.keys()),
                )
            response = self.session.get(
                PUBLIC_MANAGE_TOKEN_URL,
                params={"code": code},
                headers=self._browser_headers(self.public_manage_url),
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
            tokens = self._tokens_from_token_response(data)
            if tokens is None:
                return AdminPasswordLoginResult(
                    status=ADMIN_AUTH_FAILED,
                    message="public-manage token exchange did not return usable tokens.",
                    raw_keys=sorted(str(key) for key in data.keys()),
                )
            return AdminPasswordLoginResult(
                status=ADMIN_AUTH_READY,
                message="Public management password auth produced API tokens.",
                tokens=tokens,
                raw_keys=sorted(str(key) for key in data.keys()),
            )
        except Exception as exc:
            LOGGER.debug("Public management token exchange failed.", exc_info=True)
            return AdminPasswordLoginResult(
                status=ADMIN_AUTH_FAILED,
                message=f"Public management token exchange failed: {exc}",
            )

    def _tokens_from_token_response(self, data: dict[str, Any]) -> AdminAuthTokens | None:
        payload = data.get("data") if isinstance(data.get("data"), dict) else {}
        authorization = str(data.get("token") or data.get("Authorization") or "").strip()
        access_token = str(payload.get("access_token") or data.get("access_token") or "").strip()
        if not authorization or not access_token:
            return None
        return AdminAuthTokens(
            authorization=authorization,
            token=access_token,
            user_id=str(payload.get("user_id") or data.get("user_id") or ""),
            source="password",
        )

    def _open_login_page(self) -> None:
        self.session.get(
            self.login_page_url,
            headers=self._browser_headers(self.login_page_url),
            timeout=self.timeout,
        )

    def _get_auth_code(self, client_id: str) -> str:
        callback = f"jsonp_{int(time.time() * 1000)}_{secrets.randbelow(900) + 100}"
        response = self.session.get(
            f"{self.cia_base_url}/internal_api/getAuthCodeByJsonp",
            params={"client_id": client_id, "callback": callback},
            headers=self._browser_headers(self.login_page_url),
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = _parse_json_or_jsonp(response.text)
        auth_code = str(data.get("auth_code") or data.get("code") or "")
        if not auth_code:
            raise RuntimeError("Chanjet CIA auth_code was not returned.")
        return auth_code

    def _authorize_public_manage(self) -> dict[str, Any]:
        callback = f"callback_{int(time.time() * 1000)}_{secrets.randbelow(900) + 100}"
        response = self.session.get(
            f"{self.cia_base_url}/internal_api/authorizeByJsonp",
            params={"client_id": PUBLIC_MANAGE_CLIENT_ID, "callback": callback},
            headers=self._browser_headers("https://public-manage.chanjet.com/"),
            timeout=self.timeout,
        )
        response.raise_for_status()
        return _parse_json_or_jsonp(response.text)

    def _account_login(self, auth_code: str) -> dict[str, Any]:
        payload = {
            "auth_username": chanjet_rsa_encrypt(self.username),
            "passwordEncrypted": chanjet_rsa_encrypt(self.password),
            "auth_code": auth_code,
            "verifyToken": "",
            "jsonp": "0",
        }
        response = self.session.post(
            f"{self.login_api_base_url}/loginV2/accountLogin",
            data=payload,
            headers=self._browser_headers(self.login_page_url, content_type=True),
            timeout=self.timeout,
        )
        response.raise_for_status()
        return _parse_json_or_jsonp(response.text)

    def _try_get_ticket(self) -> dict[str, Any] | None:
        try:
            response = self.session.post(
                f"{self.login_api_base_url}/loginV2/getTicket",
                headers=self._browser_headers(self.login_page_url, content_type=True),
                timeout=self.timeout,
            )
            response.raise_for_status()
            return _parse_json_or_jsonp(response.text)
        except Exception:
            LOGGER.debug("Public management password auth could not read getTicket.", exc_info=True)
            return None

    def _browser_headers(self, referer: str, *, content_type: bool = False) -> dict[str, str]:
        headers = {
            "Accept": "application/json, text/plain, */*",
            "User-Agent": "Mozilla/5.0",
            "Referer": referer,
            "Domain": urlparse(self.login_page_url).hostname or "",
            "Chanjet-Client-Language": "zh-CN",
            "Chanjet-Client-TimeZone": "Asia/Shanghai",
        }
        if content_type:
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        return headers

    @property
    def login_page_url(self) -> str:
        return f"{self.login_base_url}/?callback={quote(self.public_manage_url, safe='')}"

    @property
    def is_integration(self) -> bool:
        host = urlparse(self.public_manage_url).hostname or ""
        return ".inte." in host or host.startswith("inte-")

    @property
    def login_base_url(self) -> str:
        return "https://ydz-login.inte.chanjet.com" if self.is_integration else "https://login.chanjet.com"

    @property
    def login_api_base_url(self) -> str:
        return "https://passport.inte.chanjet.com" if self.is_integration else "https://login.chanjet.com"

    @property
    def cia_base_url(self) -> str:
        return "https://inte-cia.chanapp.chanjet.com" if self.is_integration else "https://cia.chanapp.chanjet.com"
