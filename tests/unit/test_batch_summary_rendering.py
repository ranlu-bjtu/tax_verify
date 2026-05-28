import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.batch_collect_verify import render_problem_detail_sections, render_tax_matrix_header, render_tax_matrix_rows


def test_problem_details_group_by_form_then_account():
    details = [
        {
            "taxNo": "911111111111111111",
            "custName": "测试企业A",
            "taskId": "task-a",
            "region": "河北",
            "summaryPath": "output/reports/task-a/summary.html",
            "formId": "vat_general_main",
            "formName": "增值税纳税申报表（一般纳税人适用）",
            "formShortName": "增值税主表",
            "fieldId": "field_a",
            "displayName": "字段A",
            "lineNo": "1",
            "status": "mismatch",
            "apiRawValue": "1",
            "webRawValue": "2",
        },
        {
            "taxNo": "911111111111111111",
            "custName": "测试企业A",
            "taskId": "task-a",
            "region": "河北",
            "summaryPath": "output/reports/task-a/summary.html",
            "formId": "vat_general_main",
            "formName": "增值税纳税申报表（一般纳税人适用）",
            "formShortName": "增值税主表",
            "fieldId": "field_b",
            "displayName": "字段B",
            "lineNo": "2",
            "status": "api_missing",
            "apiRawValue": "",
            "webRawValue": "3",
        },
        {
            "taxNo": "922222222222222222",
            "custName": "测试企业B",
            "taskId": "task-b",
            "region": "四川",
            "summaryPath": "output/reports/task-b/summary.html",
            "formId": "vat_general_main",
            "formName": "增值税纳税申报表（一般纳税人适用）",
            "formShortName": "增值税主表",
            "fieldId": "field_c",
            "displayName": "字段C",
            "lineNo": "3",
            "status": "web_missing",
            "apiRawValue": "4",
            "webRawValue": "",
        },
    ]

    html = render_problem_detail_sections(details, Path("."))

    assert html.count('class="account-row"') == 2
    assert "911111111111111111" in html
    assert "taskId=task-a" in html
    assert "测试企业A" in html
    assert "2 项差异" in html
    assert "922222222222222222" in html
    assert "测试企业B" in html


def test_tax_matrix_shows_task_id_column():
    header = render_tax_matrix_header([])
    rows = render_tax_matrix_rows(
        [
            {
                "taxNo": "911111111111111111",
                "taskId": "task-a",
                "region": "河北",
                "custName": "测试企业A",
                "taxItemStatuses": [],
                "collectStatus": "COLLECTED",
                "manualRequired": False,
                "verifyStatus": "success",
                "problemCount": 0,
                "formResults": {},
                "summaryPath": "",
                "manualCategory": "",
                "manualReason": "",
                "manualAction": "",
            }
        ],
        [],
        Path("."),
    )

    assert "<th>taskId</th>" in header
    assert "<code>task-a</code>" in rows


if __name__ == "__main__":
    test_problem_details_group_by_form_then_account()
    test_tax_matrix_shows_task_id_column()
    print("All batch summary rendering tests passed!")
