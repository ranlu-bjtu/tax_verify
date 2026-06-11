from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.chanjet_admin.auth import (
    ADMIN_AUTH_MANUAL_VERIFICATION_REQUIRED,
    ADMIN_AUTH_READY,
    ChanjetAdminPasswordAuthClient,
)


def test_backend_token_exchange_response_maps_to_header_tokens():
    client = ChanjetAdminPasswordAuthClient("user", "secret")

    tokens = client._tokens_from_token_response(
        {
            "token": "authorization-token",
            "data": {"access_token": "access-token", "user_id": "user-id"},
        }
    )

    assert tokens is not None
    assert tokens.authorization == "authorization-token"
    assert tokens.token == "access-token"
    assert tokens.user_id == "user-id"


def test_backend_password_access_denied_is_manual_verification_required():
    client = ChanjetAdminPasswordAuthClient("user", "secret")

    result = client._classify_login_response(
        {"result": False, "errorCode": "访问拒绝", "captchaResult": False}
    )

    assert result.status == ADMIN_AUTH_MANUAL_VERIFICATION_REQUIRED
    assert result.tokens is None


def test_backend_password_success_requires_public_manage_token_exchange():
    class Client(ChanjetAdminPasswordAuthClient):
        def _try_get_ticket(self):
            return {"ticket": "ok"}

    client = Client("user", "secret")

    result = client._classify_login_response({"result": True})

    assert result.status == ADMIN_AUTH_READY
    assert result.tokens is None


if __name__ == "__main__":
    test_backend_token_exchange_response_maps_to_header_tokens()
    test_backend_password_access_denied_is_manual_verification_required()
    test_backend_password_success_requires_public_manage_token_exchange()
    print("All Chanjet admin auth tests passed!")
