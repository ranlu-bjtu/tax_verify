import sys

sys.path.insert(0, ".")

from src.login.login_detector import LoginDetector
from src.login.task_login_flow import (
    DEFAULT_MACHINE_ID,
    ForceTaxLoginRequiredError,
    PendingTaxLoginJobError,
    TaxLoginNotReadyError,
    TaskLoginFlow,
    TaskLoginInfo,
)
import src.login.task_login_flow as task_login_flow


class DummyBrowserManager:
    pass


class DummyPageListBrowserManager:
    def __init__(self, pages=None):
        self.pages = list(pages or [])

    def get_all_pages(self):
        return list(self.pages)


class DummyClientJobPage:
    def __init__(self, response):
        self.response = response
        self.calls = 0

    def evaluate(self, *_args, **_kwargs):
        self.calls += 1
        return self.response


class DummySequenceClientJobPage:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def evaluate(self, *_args, **_kwargs):
        self.calls += 1
        if len(self.responses) > 1:
            return self.responses.pop(0)
        return self.responses[0]


class DummyContext:
    def __init__(self):
        self.init_scripts = []

    def add_init_script(self, script=None, path=None):
        self.init_scripts.append(script)


class DummyCookieContext(DummyContext):
    def __init__(self):
        super().__init__()
        self.clear_calls = []

    def clear_cookies(self, **kwargs):
        self.clear_calls.append(kwargs)


class DummyBrowserManagerWithContext:
    def __init__(self, context=None):
        self.context = context or DummyContext()


class DummyLoadingPage:
    url = "https://etax.henan.chinatax.gov.cn:8443/loading"

    def evaluate(self, *_args, **_kwargs):
        return "我要查询 纳税人识别号 91410300MA4664Q680"


class DummySessionExpiredPage:
    url = "https://etax.shandong.chinatax.gov.cn:8443/loginb/"

    def evaluate(self, *_args, **_kwargs):
        return "我要查询 统一社会信用代码 提示 会话失效，请重新登录 确认"


class DummyAuthCodeErrorPage:
    url = "https://etax.xinjiang.chinatax.gov.cn:8443/mhzx/api/mh/tpass/code"

    def evaluate(self, *_args, **_kwargs):
        return '{"code":2997,"msg":"\u6388\u6743\u7801\u4e0d\u80fd\u4e3a\u7a7a\uff01"}'


class DummyTpassLoginPage:
    url = "https://tpass.shandong.chinatax.gov.cn:8443/#/login?redirect_uri=https%3A%2F%2Fetax.shandong.chinatax.gov.cn"

    def evaluate(self, *_args, **_kwargs):
        return "\u7edf\u4e00\u8eab\u4efd\u8ba4\u8bc1 \u8bf7\u767b\u5f55"


class DummyDispatchPage:
    def __init__(self):
        self.events = []

    def evaluate(self, script, arg=None):
        if "setApiRoot" in script:
            self.events.append(("set_api", None))
            return None
        if "clearTaxCookiesAndOpenNewTab" in script:
            self.events.append(("clear_and_open", arg))
            return "dispatched"
        return None


class DummyDelayedMachinePage:
    def __init__(self, values):
        self.values = list(values)

    def evaluate(self, *_args, **_kwargs):
        if self.values:
            return self.values.pop(0)
        return ""


class DummyTaskCookieRetryPage:
    def __init__(self):
        self.calls = []

    def evaluate(self, script, arg=None):
        if "window.robotId" in script:
            return "real-machine"
        self.calls.append(arg)
        if arg["machineId"] == DEFAULT_MACHINE_ID:
            return {"flag": 0, "msg": "machine id mismatch"}
        return {"flag": 1, "data": {"ok": True}}


class DispatchFlow(TaskLoginFlow):
    def _has_plugin_bridge(self, page, timeout=0):
        return True

    def _end_previous_plugin_task_if_any(self, page):
        page.events.append(("end_previous", None))
        return "ended:old-task"


def test_default_login_strategy_prefers_plugin():
    flow = TaskLoginFlow(DummyBrowserManager())

    assert flow.login_strategy == "plugin_first"


def test_client_job_metadata_detects_incomplete_success_response():
    flow = TaskLoginFlow(DummyBrowserManager())
    response = {
        "flag": 1,
        "code": "200",
        "success": True,
        "msg": "OK",
        "data": {
            "declareJob": {"province": "hainan", "taxNo": "91460000MAE0TMR45K"},
            "tydl": {"taxNo": "91460000MAE0TMR45K", "cookies": {}},
        },
    }

    assert not flow._client_job_has_login_metadata(response)
    summary = flow._client_job_response_summary(response)
    assert summary["hasInnerTaskId"] is False
    assert summary["province"] == "hainan"
    assert summary["hasTaxNo"] is True


def test_build_info_from_client_job_uses_task_info_metadata():
    flow = TaskLoginFlow(DummyBrowserManager())
    response = {
        "flag": 1,
        "code": "200",
        "success": True,
        "data": {
            "declareJob": {"province": "hainan", "taxNo": "91460000MAE0TMR45K"},
            "tydl": {
                "taxNo": "91460000MAE0TMR45K",
                "cookies": {
                    "taskInfo": {
                        "taskId": "2071433372627634736",
                        "province": "hainan",
                    }
                },
            },
        },
    }

    assert flow._client_job_has_login_metadata(response)
    info = flow._build_info_from_client_job("2071433810716918573", "machine", response)
    assert info.outer_task_id == "2071433810716918573"
    assert info.inner_task_id == "2071433372627634736"
    assert info.province == "hainan"
    assert info.tax_no == "91460000MAE0TMR45K"


def test_build_info_routes_qingdao_tax_no_to_qingdao_host():
    flow = TaskLoginFlow(DummyBrowserManager())
    response = {
        "flag": 1,
        "code": "200",
        "success": True,
        "data": {
            "declareJob": {"province": "shandong", "taxNo": "91370203334145023C"},
            "tydl": {
                "taxNo": "91370203334145023C",
                "cookies": {
                    "taskInfo": {
                        "taskId": "inner-qingdao",
                        "province": "shandong",
                    }
                },
            },
        },
    }

    info = flow._build_info_from_client_job("outer", "machine", response)

    assert info.province == "qingdao"
    assert info.tax_no == "91370203334145023C"


def test_get_client_job_fallback_detects_ssl_eof():
    assert TaskLoginFlow._should_try_curl_fallback(
        RuntimeError("SSLEOFError: UNEXPECTED_EOF_WHILE_READING")
    )


def test_get_client_job_pending_login_fails_with_pending_task_id():
    flow = TaskLoginFlow(DummyBrowserManager())
    message = "您之前执行过 进税局(2076614043783903619) 操作并且暂未完成，请您耐心等待"
    page = DummyClientJobPage({"flag": 0, "msg": message})

    original_wait = task_login_flow.PENDING_CLIENT_JOB_MAX_WAIT_SECONDS
    try:
        task_login_flow.PENDING_CLIENT_JOB_MAX_WAIT_SECONDS = 0
        try:
            flow.get_client_job(page, "outer-task")
        except PendingTaxLoginJobError as exc:
            assert exc.pending_task_id == "2076614043783903619"
            assert "已有进税局任务未完成" in str(exc)
        else:
            raise AssertionError("expected PendingTaxLoginJobError")
    finally:
        task_login_flow.PENDING_CLIENT_JOB_MAX_WAIT_SECONDS = original_wait


def test_get_client_job_pending_login_fast_fails_repeated_same_task_id():
    flow = TaskLoginFlow(DummyPageListBrowserManager())
    message = "鎮ㄤ箣鍓嶆墽琛岃繃 杩涚◣灞€(2076614043783903619) 鎿嶄綔骞朵笖鏆傛湭瀹屾垚锛岃鎮ㄨ€愬績绛夊緟"
    page = DummySequenceClientJobPage([{"flag": 0, "msg": message}])

    original_sleep = task_login_flow.time.sleep
    original_repeat = task_login_flow.PENDING_CLIENT_JOB_FAST_FAIL_REPEAT_COUNT
    try:
        task_login_flow.time.sleep = lambda _seconds: None
        task_login_flow.PENDING_CLIENT_JOB_FAST_FAIL_REPEAT_COUNT = 3
        try:
            flow.get_client_job(page, "outer-task")
        except PendingTaxLoginJobError as exc:
            assert exc.pending_task_id == "2076614043783903619"
            assert page.calls == 3
        else:
            raise AssertionError("expected PendingTaxLoginJobError")
    finally:
        task_login_flow.time.sleep = original_sleep
        task_login_flow.PENDING_CLIENT_JOB_FAST_FAIL_REPEAT_COUNT = original_repeat


def test_get_client_job_need_force_tax_fails_fast():
    flow = TaskLoginFlow(DummyBrowserManager())
    page = DummyClientJobPage(
        {
            "flag": 1,
            "code": "200",
            "success": True,
            "data": {
                "declareJob": {"province": "henan", "taxNo": "91410300MA4664Q680"},
                "tydl": {
                    "taxNo": "91410300MA4664Q680",
                    "cookies": {
                        "taskInfo": {
                            "taskId": "inner-task",
                            "province": "henan",
                            "needForceTax": True,
                        }
                    },
                },
            },
        }
    )

    try:
        flow.get_client_job(page, "outer-task")
    except ForceTaxLoginRequiredError as exc:
        assert "needForceTax=true" in str(exc)
    else:
        raise AssertionError("expected ForceTaxLoginRequiredError")


def test_install_tpass_cookie_init_script_once():
    bm = DummyBrowserManagerWithContext()
    flow = TaskLoginFlow(bm)

    assert flow.install_tpass_cookie_init_script()
    assert flow.install_tpass_cookie_init_script()
    assert len(bm.context.init_scripts) == 1
    script = bm.context.init_scripts[0]
    assert "__taxVerifyTpassCookieInjected" in script
    assert "forceRedirectEtaxProvinces" in script
    assert "maybeJumpToTgtUrl" in script
    assert "etaxplgin" in script


def test_build_login_url_preserves_cookie_injection_payload():
    flow = TaskLoginFlow(DummyBrowserManager())
    task_cookie = {
        "data": {
            "ciaToken": "cia-token",
            "floatSeconds": 600,
            "warnSeconds": 60,
            "tgtUrl": "https://etax.hainan.chinatax.gov.cn:8443/loginb/",
            "tydl": {
                "idcard": "id-card",
                "taxNo": "91460000MAE0TMR45K",
                "batchNo": "batch-no",
                "proCid": {
                    "client_id": "client-id",
                    "redirect_url": "https://etax.hainan.chinatax.gov.cn:8443/loginb/",
                },
                "cookies": {
                    "tpass_localstorage": {"tpass_token": "token"},
                    "etax_cookie": {"SESSION": "session"},
                    "taskInfo": {"taskId": "inner-task", "province": "hainan"},
                },
            },
            "declareJob": {
                "province": "hainan",
                "clientUseorgId": "org-id",
                "loginInfo": {
                    "loginVersion": "v1",
                    "cSiteLoginName": "proxy-tax-no",
                },
            },
            "forceRedirectEtaxProvinces": "hainan",
        }
    }
    client_job = {"data": {}}

    url = flow.build_login_url(task_cookie, client_job)
    assert url.startswith("https://tpass.hainan.chinatax.gov.cn:8443/#/login?")
    cookie_payload = url.split("cookie=", 1)[1]
    import json
    import urllib.parse

    cookie = json.loads(urllib.parse.unquote(cookie_payload))
    assert cookie["province"] == "hainan"
    assert cookie["origin"] == "prod"
    assert cookie["ciaToken"] == "cia-token"
    assert cookie["client_id"] == "client-id"
    assert cookie["taxNo"] == "91460000MAE0TMR45K"
    assert cookie["tpass_token"] == "token"
    assert cookie["SESSION"] == "session"
    assert cookie["taskId"] == "inner-task"
    assert cookie["forceRedirectEtaxProvinces"] == "hainan"
    assert cookie["floatSeconds"] == 600
    assert cookie["warnSeconds"] == 60


def test_build_login_url_routes_qingdao_tax_no_and_payload_province():
    flow = TaskLoginFlow(DummyBrowserManager())
    task_cookie = {
        "data": {
            "ciaToken": "cia-token",
            "tgtUrl": "https://etax.shandong.chinatax.gov.cn:8443/loginb/",
            "tydl": {
                "taxNo": "91370203334145023C",
                "proCid": {
                    "client_id": "client-id",
                    "redirect_url": "https://etax.shandong.chinatax.gov.cn:8443/loginb/",
                },
                "cookies": {
                    "taskInfo": {
                        "taskId": "inner-task",
                        "province": "shandong",
                        "forceRedirectEtaxProvinces": "hebei",
                        "tgtUrl": "",
                    },
                },
            },
            "declareJob": {"province": "shandong"},
        }
    }
    client_job = {"data": {}}

    url = flow.build_login_url(task_cookie, client_job)

    assert url.startswith("https://tpass.qingdao.chinatax.gov.cn:8443/#/login?")
    assert "redirect_uri=https://etax.qingdao.chinatax.gov.cn" in url
    cookie_payload = url.split("cookie=", 1)[1]
    import json
    import urllib.parse

    cookie = json.loads(urllib.parse.unquote(cookie_payload))
    assert cookie["province"] == "qingdao"
    assert cookie["taxNo"] == "91370203334145023C"
    assert cookie["tgtUrl"] == "https://etax.qingdao.chinatax.gov.cn:8443/loginb/"
    assert cookie["forceRedirectEtaxProvinces"] == "qingdao"


def test_get_task_cookie_requests_fallback_posts_task_metadata():
    flow = TaskLoginFlow(DummyBrowserManager())
    calls = []

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"flag": 1, "data": {"ok": True}}

    def fake_post(url, json=None, timeout=None):
        calls.append({"url": url, "json": json, "timeout": timeout})
        return Response()

    original_post = task_login_flow.requests.post
    try:
        task_login_flow.requests.post = fake_post
        result = flow._get_task_cookie_with_requests("inner-task", "machine-id")
    finally:
        task_login_flow.requests.post = original_post

    assert result == {"flag": 1, "data": {"ok": True}}
    assert calls == [
        {
            "url": task_login_flow.GET_TASK_COOKIE_FALLBACK_URL,
            "json": {"taskId": "inner-task", "machineId": "machine-id"},
            "timeout": 20,
        }
    ]


def test_get_machine_id_waits_for_robot_id_before_fallback():
    flow = TaskLoginFlow(DummyBrowserManager(), timeout=10)
    page = DummyDelayedMachinePage(["", "", "machine-id"])
    current_time = {"value": 100.0}
    sleeps = []

    def fake_time():
        return current_time["value"]

    def fake_sleep(seconds):
        sleeps.append(seconds)
        current_time["value"] += seconds

    original_time = task_login_flow.time.time
    original_sleep = task_login_flow.time.sleep
    try:
        task_login_flow.time.time = fake_time
        task_login_flow.time.sleep = fake_sleep
        machine_id = flow._get_machine_id(page)
    finally:
        task_login_flow.time.time = original_time
        task_login_flow.time.sleep = original_sleep

    assert machine_id == "machine-id"
    assert sleeps == [0.5, 0.5]


def test_default_task_cookie_poll_timeout_is_bounded():
    flow = TaskLoginFlow(DummyBrowserManager(), timeout=600)

    assert flow.poll_timeout == task_login_flow.TASK_COOKIE_POLL_MAX_WAIT_SECONDS


def test_get_task_cookie_retries_once_when_fallback_machine_id_fails():
    flow = TaskLoginFlow(DummyBrowserManager(), poll_timeout=10)
    page = DummyTaskCookieRetryPage()

    result = flow.get_task_cookie(page, "inner-task", DEFAULT_MACHINE_ID)

    assert result == {"flag": 1, "data": {"ok": True}}
    assert page.calls == [
        {"taskId": "inner-task", "machineId": DEFAULT_MACHINE_ID},
        {"taskId": "inner-task", "machineId": "real-machine"},
    ]


def test_qingdao_direct_login_clears_plugin_special_cookies():
    context = DummyCookieContext()
    flow = TaskLoginFlow(DummyBrowserManagerWithContext(context))

    assert flow._clear_special_login_cookies("qingdao") == 2

    names = [call["name"] for call in context.clear_calls]
    assert names == ["TGCT", "enable_gizqLgxJ4gkh"]
    assert all(call["domain"].pattern == r"^\.?etax\.qingdao\.chinatax\.gov\.cn$" for call in context.clear_calls)


def test_login_detector_rejects_loading_page():
    detector = LoginDetector(province="henan")

    assert not detector.is_logged_in(DummyLoadingPage())


def test_login_detector_rejects_session_expired_page():
    detector = LoginDetector(province="shandong")

    assert not detector.is_logged_in(DummySessionExpiredPage())


def test_login_detector_rejects_tax_auth_code_error_page():
    detector = LoginDetector(province="xinjiang")

    assert not detector.is_logged_in(DummyAuthCodeErrorPage())


def test_plugin_wait_falls_back_quickly_when_no_tax_page_opens():
    flow = TaskLoginFlow(DummyPageListBrowserManager(), timeout=60)
    current_time = {"value": 100.0}
    sleeps = []

    def fake_time():
        return current_time["value"]

    def fake_sleep(seconds):
        sleeps.append(seconds)
        current_time["value"] += seconds

    original_time = task_login_flow.time.time
    original_sleep = task_login_flow.time.sleep
    try:
        task_login_flow.time.time = fake_time
        task_login_flow.time.sleep = fake_sleep
        result = flow.wait_for_tax_page("shandong", timeout=45, no_page_timeout=3)
    finally:
        task_login_flow.time.time = original_time
        task_login_flow.time.sleep = original_sleep

    assert result is None
    assert sleeps == [1, 1, 1]


def test_direct_login_wait_fails_fast_on_tpass_login_page():
    flow = TaskLoginFlow(DummyPageListBrowserManager([DummyTpassLoginPage()]), timeout=60)
    current_time = {"value": 100.0}

    def fake_time():
        return current_time["value"]

    def fake_sleep(seconds):
        current_time["value"] += seconds

    original_time = task_login_flow.time.time
    original_sleep = task_login_flow.time.sleep
    try:
        task_login_flow.time.time = fake_time
        task_login_flow.time.sleep = fake_sleep
        try:
            flow.wait_for_tax_page(
                "shandong",
                timeout=45,
                blocker_timeout=3,
                fail_on_login_blocker=True,
            )
        except TaxLoginNotReadyError as exc:
            assert "Tax bureau login state" in str(exc)
            assert "unified login page" in str(exc)
        else:
            raise AssertionError("expected TaxLoginNotReadyError")
    finally:
        task_login_flow.time.time = original_time
        task_login_flow.time.sleep = original_sleep


def test_plugin_dispatch_ends_previous_task_before_opening_new_tab():
    flow = DispatchFlow(DummyBrowserManager())
    page = DummyDispatchPage()
    info = TaskLoginInfo(
        outer_task_id="outer-task",
        inner_task_id="inner-task",
        province="henan",
        machine_id="machine-id",
        login_url="https://tpass.henan.chinatax.gov.cn:8443/#/login?cookie=payload",
        current_task_id="inner-task",
    )

    flow.dispatch_open_tax_tab(page, info)

    event_names = [event[0] for event in page.events]
    assert event_names == ["set_api", "end_previous", "clear_and_open"]
    clear_payload = page.events[-1][1]
    assert clear_payload["province"] == "henan"
    assert clear_payload["taskId"] == "inner-task"


if __name__ == "__main__":
    test_default_login_strategy_prefers_plugin()
    test_client_job_metadata_detects_incomplete_success_response()
    test_build_info_from_client_job_uses_task_info_metadata()
    test_build_info_routes_qingdao_tax_no_to_qingdao_host()
    test_get_client_job_fallback_detects_ssl_eof()
    test_get_client_job_pending_login_fails_with_pending_task_id()
    test_get_client_job_pending_login_fast_fails_repeated_same_task_id()
    test_get_client_job_need_force_tax_fails_fast()
    test_install_tpass_cookie_init_script_once()
    test_build_login_url_preserves_cookie_injection_payload()
    test_build_login_url_routes_qingdao_tax_no_and_payload_province()
    test_get_task_cookie_requests_fallback_posts_task_metadata()
    test_get_machine_id_waits_for_robot_id_before_fallback()
    test_default_task_cookie_poll_timeout_is_bounded()
    test_get_task_cookie_retries_once_when_fallback_machine_id_fails()
    test_qingdao_direct_login_clears_plugin_special_cookies()
    test_login_detector_rejects_loading_page()
    test_login_detector_rejects_session_expired_page()
    test_login_detector_rejects_tax_auth_code_error_page()
    test_plugin_wait_falls_back_quickly_when_no_tax_page_opens()
    test_direct_login_wait_fails_fast_on_tpass_login_page()
    test_plugin_dispatch_ends_previous_task_before_opening_new_tab()
    print("Task login flow tests passed!")
