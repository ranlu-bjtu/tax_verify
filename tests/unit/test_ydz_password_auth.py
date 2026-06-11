from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.ydz.customer_creation import YDZ_CREATE_ENVIRONMENTS
from src.ydz.password_auth import (
    PASSWORD_LOGIN_FAILED,
    PASSWORD_LOGIN_MANUAL_VERIFICATION_REQUIRED,
    PASSWORD_LOGIN_SSO_READY_TOKEN_UNAVAILABLE,
    ChanjetPasswordAuthClient,
    chanjet_rsa_encrypt,
)


def test_chanjet_password_encrypts_without_plaintext():
    encrypted = chanjet_rsa_encrypt("secret-password")

    assert encrypted
    assert "secret-password" not in encrypted
    assert len(encrypted) == 172


def test_password_login_classifies_slider_or_waf_challenge():
    client = ChanjetPasswordAuthClient(YDZ_CREATE_ENVIRONMENTS["inte"])

    result = client._classify_login_response(
        {"result": False, "captchaResult": False, "errorCode": "访问拒绝"},
        work_url=None,
    )

    assert result.status == PASSWORD_LOGIN_MANUAL_VERIFICATION_REQUIRED
    assert result.auth_context is None


def test_password_login_success_without_work_tokens_stops_before_api_use():
    class Client(ChanjetPasswordAuthClient):
        def _try_get_ticket(self):
            return {"result": True, "ticket": "ticket"}

        def _try_extract_token_context(self, _work_url):
            return None

    client = Client(YDZ_CREATE_ENVIRONMENTS["inte"])

    result = client._classify_login_response({"result": True}, work_url=None)

    assert result.status == PASSWORD_LOGIN_SSO_READY_TOKEN_UNAVAILABLE
    assert result.sso_ready is True
    assert result.has_ticket is True
    assert result.auth_context is None


def test_password_login_uses_captcha_verify_token_before_account_login():
    class Client(ChanjetPasswordAuthClient):
        verify_args = None
        login_args = None

        def _open_login_page(self):
            return None

        def _get_auth_code(self):
            return "auth-code"

        def _account_verify(self, username, password, captcha_code):
            self.verify_args = (username, password, captcha_code)
            return {"result": True, "verifyToken": "captcha-token"}

        def _account_login(self, username, password, auth_code, verify_token):
            self.login_args = (username, password, auth_code, verify_token)
            return {"result": False, "errorCode": "expected-stop"}

    client = Client(YDZ_CREATE_ENVIRONMENTS["inte"])

    result = client.login("user", "pass", captcha_code="666666")

    assert client.verify_args == ("user", "pass", "666666")
    assert client.login_args == ("user", "pass", "auth-code", "captcha-token")
    assert result.status == PASSWORD_LOGIN_FAILED
