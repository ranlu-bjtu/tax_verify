from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.chanjet_admin.task_execution_log import (
    CURRENT_PERIOD_LOG_TYPE,
    cbj_mode_from_logs,
    current_period_flag_from_logs,
)


def test_current_period_flag_falls_back_when_tax_code_lsn_is_absent():
    logs = [
        {
            "createdStamp": 1,
            "logType": "其他日志",
            "lsn": "sz_whsyjsf",
            "logInfo": "false",
        },
        {
            "createdStamp": 2,
            "logType": "成功保存数据-是否是当期",
            "lsn": "not_sz_zzs",
            "logInfo": "true",
        },
    ]

    assert current_period_flag_from_logs(logs, tax_code="sz_zzs") is True


def test_current_period_flag_prefers_matching_tax_code_lsn():
    logs = [
        {
            "createdStamp": 1,
            "logType": CURRENT_PERIOD_LOG_TYPE,
            "lsn": "sz_qysds",
            "logInfo": "false",
        },
        {
            "createdStamp": 2,
            "logType": CURRENT_PERIOD_LOG_TYPE,
            "lsn": "sz_whsyjsf",
            "logInfo": "true",
        },
    ]

    assert current_period_flag_from_logs(logs, tax_code="sz_qysds") is False


def test_current_period_flag_uses_latest_matching_log():
    logs = [
        {
            "createdStamp": 1,
            "logType": "成功保存数据-是否是当期",
            "lsn": "sz_zzs",
            "logInfo": "true",
        },
        {
            "createdStamp": 2,
            "logType": "成功保存数据-是否是当期",
            "lsn": "sz_zzs",
            "logInfo": "false",
        },
    ]

    assert current_period_flag_from_logs(logs, tax_code="sz_zzs") is False


def test_cbj_mode_from_logs_uses_annual_query_marker():
    logs = [
        {
            "createdStamp": 1,
            "logType": "\u6b8b\u4fdd\u91d1\u4efb\u52a1\u8fd4\u56de\u7ed3\u679c",
            "logInfo": "\u6570\u636e\u5e93\u672a\u67e5\u8be2\u5230\u8fd4\u56de\u6570\u636e\uff0c\u8c03\u7528\u6c47\u7b97\u6e05\u7f34\u53d6\u6570\u63a5\u53e3\u67e5\u8be2",
        },
        {
            "createdStamp": 2,
            "logType": "\u6b8b\u4fdd\u91d1\u4efb\u52a1\u8fd4\u56de\u7ed3\u679c",
            "logInfo": "\u6210\u529f",
        },
    ]

    assert cbj_mode_from_logs(logs) == "annual"


def test_cbj_mode_from_logs_uses_personal_summary_markers():
    logs = [
        {
            "createdStamp": 1,
            "logType": "\u6b8b\u4fdd\u91d1\u4efb\u52a1\u8fd4\u56de\u7ed3\u679c",
            "logInfo": "{\"personNum\":2,\"personNumSum\":24,\"monthNumSum\":12,\"amountSum\":201442.82}",
        },
        {
            "createdStamp": 2,
            "logType": "\u6b8b\u4fdd\u91d1\u4efb\u52a1\u8fd4\u56de\u7ed3\u679c",
            "logInfo": "\u7533\u62a5\u6708\u4efd\u6c47\u603b:\u301012\u3011 \u7533\u62a5\u4eba\u6b21\u6c47\u603b:\u301024\u3011",
        },
    ]

    assert cbj_mode_from_logs(logs) == "backend"


def test_cbj_mode_from_logs_prefers_annual_marker_over_personal_markers():
    logs = [
        {
            "createdStamp": 1,
            "logType": "\u6b8b\u4fdd\u91d1\u4efb\u52a1\u8fd4\u56de\u7ed3\u679c",
            "logInfo": "\u6570\u636e\u5e93\u672a\u67e5\u8be2\u5230\u8fd4\u56de\u6570\u636e\uff0c\u8c03\u7528\u6c47\u7b97\u6e05\u7f34\u53d6\u6570\u63a5\u53e3\u67e5\u8be2",
        },
        {
            "createdStamp": 2,
            "logType": "\u6b8b\u4fdd\u91d1\u4efb\u52a1\u8fd4\u56de\u7ed3\u679c",
            "logInfo": "{\"personNum\":2,\"amountSum\":201442.82}",
        },
    ]

    assert cbj_mode_from_logs(logs) == "annual"


def test_cbj_mode_from_logs_returns_none_without_mode_marker():
    logs = [
        {
            "createdStamp": 1,
            "logType": "\u6b8b\u4fdd\u91d1\u4efb\u52a1\u8fd4\u56de\u7ed3\u679c",
            "logInfo": "\u6210\u529f",
        }
    ]

    assert cbj_mode_from_logs(logs) is None


if __name__ == "__main__":
    test_current_period_flag_falls_back_when_tax_code_lsn_is_absent()
    test_current_period_flag_prefers_matching_tax_code_lsn()
    test_current_period_flag_uses_latest_matching_log()
    test_cbj_mode_from_logs_uses_annual_query_marker()
    test_cbj_mode_from_logs_uses_personal_summary_markers()
    test_cbj_mode_from_logs_prefers_annual_marker_over_personal_markers()
    test_cbj_mode_from_logs_returns_none_without_mode_marker()
    print("All task execution log tests passed!")
