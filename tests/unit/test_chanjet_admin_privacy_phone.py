from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import src.chanjet_admin.privacy_phone as privacy_phone
from src.chanjet_admin.auth import AdminAuthTokens
from src.chanjet_admin.privacy_phone import (
    ChanjetPrivacyPhoneBridge,
    ChanjetPrivacyPhoneSync,
    build_detail_payload,
    build_integration_summary_payload,
    build_summary_payload,
)


class FakePage:
    url = "https://public-manage.chanjet.com/taxserver#/privacyNumber/newPrivatePhoneNumber"

    def is_closed(self):
        return False

    def evaluate(self, _script):
        return {"authorization": "Bearer token", "token": "access-token"}

    def wait_for_load_state(self, *_args, **_kwargs):
        return None

    def wait_for_timeout(self, _ms):
        return None


class FakeContext:
    pages = [FakePage()]


class FakeTokenProvider:
    def get_tokens(self, force_refresh=False):
        return AdminAuthTokens(authorization="Bearer token", token="access-token", source="test")


class FakeResponse:
    status_code = 200

    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def ok_response(data):
    return {"code": "200", "success": True, "msg": "OK", "data": data}


def test_privacy_phone_payloads_match_captured_page_requests():
    assert build_summary_payload("15500000001") == {
        "customerDingSettingId": None,
        "phone": None,
        "privatePhone": "15500000001",
        "username": None,
        "yshIdCard": None,
        "accountingAgencyName": None,
        "mailbox": None,
        "isTaxBureauConfiguration": None,
        "orgId": None,
        "orgName": None,
        "orderStatus": None,
        "isSoonExpire": None,
        "exceedFlag": None,
        "phoneExpiredFlag": None,
        "pageSize": 10,
        "pageNo": 1,
    }
    assert build_detail_payload("15500000001", "1233739005141141") == {
        "privatePhone": "15500000001",
        "phone": None,
        "isException": None,
        "orgId": "1233739005141141",
        "pageSize": 20,
        "pageNo": 1,
    }
    assert build_integration_summary_payload("15500000001") == {"privatePhone": "15500000001"}


def test_sync_private_phone_queries_summary_detail_then_copy_without_sensitive_report_fields():
    calls = []
    original_post = privacy_phone.requests.post
    original_get = privacy_phone.requests.get

    def fake_post(url, headers, json, timeout):
        calls.append(("POST", url, json, headers, timeout))
        if url == privacy_phone.PRIVACY_PHONE_SUMMARY_URL:
            return FakeResponse(
                ok_response(
                    {
                        "content": [
                            {
                                "id": "3218",
                                "orgId": "1233739005141141",
                                "orgName": "test org",
                                "orderStatus": "using",
                            }
                        ]
                    }
                )
            )
        if url == privacy_phone.PRIVACY_PHONE_DETAIL_URL:
            return FakeResponse(
                ok_response(
                    {
                        "content": [
                            {
                                "id": "detail-1",
                                "orgId": "1233739005141141",
                                "dingTalkId": "1233739005141141",
                                "privatePhone": "15500000001",
                                "phone": "16653992015",
                                "mail": "hidden@example.test",
                                "idcard": "hidden-id",
                                "bindId": "bind-1",
                            }
                        ]
                    }
                )
            )
        raise AssertionError(url)

    def fake_get(url, headers, params, timeout):
        calls.append(("GET", url, params, headers, timeout))
        return FakeResponse(ok_response(None))

    try:
        privacy_phone.requests.post = fake_post
        privacy_phone.requests.get = fake_get
        result = ChanjetPrivacyPhoneSync(FakeContext()).sync_private_phone("15500000001")
    finally:
        privacy_phone.requests.post = original_post
        privacy_phone.requests.get = original_get

    assert result.status == "OK"
    assert result.copy_success is True
    assert [call[0] for call in calls] == ["POST", "POST", "GET"]
    assert calls[0][2]["privatePhone"] == "15500000001"
    assert calls[1][2]["orgId"] == "1233739005141141"
    assert calls[2][2] == {"privatePhone": "15500000001"}

    report = result.to_report()
    assert "16653992015" not in str(report)
    assert "hidden@example.test" not in str(report)
    assert "hidden-id" not in str(report)


def test_sync_private_phone_stops_before_copy_when_detail_is_missing():
    calls = []
    original_post = privacy_phone.requests.post
    original_get = privacy_phone.requests.get

    def fake_post(url, headers, json, timeout):
        calls.append(("POST", url, json))
        if url == privacy_phone.PRIVACY_PHONE_SUMMARY_URL:
            return FakeResponse(ok_response({"content": [{"orgId": "123"}]}))
        if url == privacy_phone.PRIVACY_PHONE_DETAIL_URL:
            return FakeResponse(ok_response({"content": []}))
        raise AssertionError(url)

    def fake_get(*_args, **_kwargs):
        raise AssertionError("copy API should not be called")

    try:
        privacy_phone.requests.post = fake_post
        privacy_phone.requests.get = fake_get
        result = ChanjetPrivacyPhoneSync(FakeContext()).sync_private_phone("15500000001")
    finally:
        privacy_phone.requests.post = original_post
        privacy_phone.requests.get = original_get

    assert result.status == "NOT_FOUND"
    assert result.copy_success is False
    assert [call[0] for call in calls] == ["POST", "POST"]


def test_bridge_copies_online_then_pulls_into_integration_when_integration_summary_is_empty():
    calls = []
    inte_summary_calls = {"count": 0}
    original_post = privacy_phone.requests.post
    original_get = privacy_phone.requests.get

    def fake_post(url, headers, json, timeout):
        calls.append(("POST", url, json))
        if url == privacy_phone.INTE_PRIVACY_PHONE_SUMMARY_URL:
            assert json == {"privatePhone": "15500000001"}
            assert "token" not in headers
            inte_summary_calls["count"] += 1
            if inte_summary_calls["count"] == 1:
                return FakeResponse(ok_response({"content": []}))
            return FakeResponse(ok_response({"content": [{"orgId": "inte-org"}]}))
        if url == privacy_phone.PRIVACY_PHONE_SUMMARY_URL:
            return FakeResponse(ok_response({"content": [{"orgId": "prod-org"}]}))
        if url == privacy_phone.PRIVACY_PHONE_DETAIL_URL:
            return FakeResponse(
                ok_response(
                    {
                        "content": [
                            {
                                "orgId": "prod-org",
                                "privatePhone": "15500000001",
                                "bindId": "bind-1",
                            }
                        ]
                    }
                )
            )
        raise AssertionError(url)

    def fake_get(url, headers, params, timeout):
        calls.append(("GET", url, params))
        assert params == {"privatePhone": "15500000001"}
        if url == privacy_phone.INTE_PRIVACY_PHONE_PULL_URL:
            assert "token" not in headers
        return FakeResponse(ok_response(None))

    try:
        privacy_phone.requests.post = fake_post
        privacy_phone.requests.get = fake_get
        result = ChanjetPrivacyPhoneBridge(FakeContext()).ensure_integration_private_phone("15500000001")
    finally:
        privacy_phone.requests.post = original_post
        privacy_phone.requests.get = original_get

    assert result.status == "PULLED"
    assert result.copy_success is True
    assert result.pull_success is True
    assert result.inte_summary_count == 1
    assert result.to_report()["inteSummaryRows"] == [{"orgId": "inte-org"}]
    assert ("GET", privacy_phone.PRIVACY_PHONE_COPY_URL, {"privatePhone": "15500000001"}) in calls
    assert ("GET", privacy_phone.INTE_PRIVACY_PHONE_PULL_URL, {"privatePhone": "15500000001"}) in calls


def test_bridge_can_use_token_provider_without_browser_context():
    calls = []
    inte_summary_calls = {"count": 0}
    original_post = privacy_phone.requests.post
    original_get = privacy_phone.requests.get

    def fake_post(url, headers, json, timeout):
        calls.append(("POST", url, json, headers))
        if url == privacy_phone.INTE_PRIVACY_PHONE_SUMMARY_URL:
            assert "token" not in headers
            inte_summary_calls["count"] += 1
            if inte_summary_calls["count"] == 1:
                return FakeResponse(ok_response({"content": []}))
            return FakeResponse(ok_response({"content": [{"orgId": "inte-org"}]}))
        if url == privacy_phone.PRIVACY_PHONE_SUMMARY_URL:
            assert headers["token"] == "access-token"
            return FakeResponse(ok_response({"content": [{"orgId": "prod-org"}]}))
        if url == privacy_phone.PRIVACY_PHONE_DETAIL_URL:
            return FakeResponse(ok_response({"content": [{"orgId": "prod-org", "privatePhone": "15500000001"}]}))
        raise AssertionError(url)

    def fake_get(url, headers, params, timeout):
        calls.append(("GET", url, params, headers))
        if url == privacy_phone.INTE_PRIVACY_PHONE_PULL_URL:
            assert "token" not in headers
        return FakeResponse(ok_response(None))

    try:
        privacy_phone.requests.post = fake_post
        privacy_phone.requests.get = fake_get
        result = ChanjetPrivacyPhoneBridge(token_provider=FakeTokenProvider()).ensure_integration_private_phone(
            "15500000001"
        )
    finally:
        privacy_phone.requests.post = original_post
        privacy_phone.requests.get = original_get

    assert result.status == "PULLED"
    assert result.pull_success is True
    assert any(call[1] == privacy_phone.INTE_PRIVACY_PHONE_PULL_URL for call in calls)


if __name__ == "__main__":
    for name, func in sorted(globals().items()):
        if name.startswith("test_") and callable(func):
            func()
    print("All Chanjet admin privacy phone tests passed!")
