from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.chanjet_admin.task_execution_log import current_period_flag_from_logs


def test_current_period_flag_filters_by_log_type_and_lsn():
    logs = [
        {
            "createdStamp": 1,
            "logType": "成功保存数据-是否是当期",
            "lsn": "sz_whsyjsf",
            "logInfo": "false",
        },
        {
            "createdStamp": 2,
            "logType": "成功保存数据-是否是当期",
            "lsn": "sz_zzs",
            "logInfo": "true",
        },
    ]

    assert current_period_flag_from_logs(logs, tax_code="sz_zzs") is True


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


if __name__ == "__main__":
    test_current_period_flag_filters_by_log_type_and_lsn()
    test_current_period_flag_uses_latest_matching_log()
    print("All task execution log tests passed!")
