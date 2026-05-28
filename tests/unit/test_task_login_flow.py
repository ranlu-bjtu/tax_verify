import sys

sys.path.insert(0, ".")

from src.login.task_login_flow import TaskLoginFlow


class DummyBrowserManager:
    pass


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


def test_get_client_job_fallback_detects_ssl_eof():
    assert TaskLoginFlow._should_try_curl_fallback(
        RuntimeError("SSLEOFError: UNEXPECTED_EOF_WHILE_READING")
    )
