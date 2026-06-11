import sys
import json
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.batch_collect_verify import (
    build_dashboard,
    classify_supplement_failure_step,
    coverage_gap_reason,
    declaration_status_for_report,
    direct_verify_reason,
    normalize_supplement_failure_reason,
    render_coverage_section,
    render_form_cell,
    render_problem_detail_sections,
    render_tax_matrix_header,
    render_tax_matrix_rows,
    status_badge,
    tail_error_reason,
    tax_item_status_css,
)


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
                "formResults": {
                    "vat_general_main": {
                        "problemCount": 0,
                        "effectiveRate": 100,
                    }
                },
                "summaryPath": "",
                "manualCategory": "",
                "manualReason": "",
                "manualAction": "",
            }
        ],
        [("vat_general_main", "增值税纳税申报表（一般纳税人适用）")],
        Path("."),
    )

    assert "<th>taskId</th>" in header
    assert "<code>task-a</code>" in rows


def test_tax_matrix_skips_items_without_completed_form_results():
    rows = render_tax_matrix_rows(
        [
            {
                "taxNo": "911_NOT_ENTERED",
                "taskId": "",
                "region": "北京",
                "custName": "未进税局企业",
                "taxItemStatuses": [],
                "collectStatus": "COLLECTED_FAIL",
                "manualRequired": True,
                "verifyStatus": "skipped",
                "problemCount": 0,
                "formResults": {},
                "summaryPath": "",
                "manualCategory": "需人工介入",
                "manualReason": "易代账登录失败",
                "manualAction": "",
            },
            {
                "taxNo": "911_VERIFIED",
                "taskId": "task-ok",
                "region": "北京",
                "custName": "已验证企业",
                "taxItemStatuses": [],
                "collectStatus": "COLLECTED",
                "manualRequired": False,
                "verifyStatus": "success",
                "problemCount": 0,
                "formResults": {
                    "vat_general_main": {
                        "problemCount": 0,
                        "effectiveRate": 100,
                    }
                },
                "summaryPath": "",
                "manualCategory": "",
                "manualReason": "",
                "manualAction": "",
            },
        ],
        [("vat_general_main", "增值税纳税申报表（一般纳税人适用）")],
        Path("."),
    )

    assert "911_NOT_ENTERED" not in rows
    assert "911_VERIFIED" in rows
    assert "task-ok" in rows


def test_tax_matrix_empty_when_no_completed_form_results():
    rows = render_tax_matrix_rows(
        [
            {
                "taxNo": "911_NOT_ENTERED",
                "taskId": "",
                "region": "北京",
                "custName": "未进税局企业",
                "taxItemStatuses": [],
                "collectStatus": "COLLECTED_FAIL",
                "manualRequired": True,
                "verifyStatus": "skipped",
                "problemCount": 0,
                "formResults": {},
                "summaryPath": "",
                "manualCategory": "需人工介入",
                "manualReason": "易代账登录失败",
                "manualAction": "",
            }
        ],
        [],
        Path("."),
    )

    assert "911_NOT_ENTERED" not in rows
    assert "暂无完成完整验证流程的表单结果" in rows


def test_dashboard_uses_per_task_reports_for_multi_task_tax_no():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        report_1 = root / "task-1.json"
        report_2 = root / "task-2.json"
        report_1.write_text(
            json.dumps(
                {
                    "batch_id": "vat_general_main",
                    "tax_type": "VAT_GENERAL",
                    "form_name": "增值税纳税申报表（一般纳税人适用）",
                    "declaration_status": "已申报",
                    "summary": {"match_rate": 100},
                    "field_results": [{"field_id": "a", "status": "match"}],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        report_2.write_text(
            json.dumps(
                {
                    "batch_id": "cit_a_main",
                    "tax_type": "CIT_A",
                    "form_name": "企业所得税年度纳税申报表",
                    "declaration_status": "已申报",
                    "summary": {"match_rate": 100},
                    "field_results": [{"field_id": "b", "status": "match"}],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        state = {
            "items": {
                "91370102MA7D3P0D2P": {
                    "taxNo": "91370102MA7D3P0D2P",
                    "collect": {
                        "verifyTaskId": "task-1",
                        "verifyTaskIds": ["task-1", "task-2"],
                        "account": {"custName": "测试企业", "areaCode": "37"},
                    },
                    "verifyTasks": {
                        "task-1": {"status": "success", "reportPaths": [str(report_1)]},
                        "task-2": {"status": "success", "reportPaths": [str(report_2)]},
                    },
                }
            }
        }

        dashboard = build_dashboard(state, root)

    row = dashboard["items"][0]
    assert row["taskId"] == "task-1、task-2"
    assert "vat_general_main" in row["formResults"]
    assert "cit_a_main" in row["formResults"]


def test_dashboard_treats_unknown_declaration_status_as_unfiled():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        report = root / "xfs.json"
        report.write_text(
            json.dumps(
                {
                    "batch_id": "consumption_tax_main",
                    "tax_type": "CONSUMPTION_TAX",
                    "form_name": "消费税及附加税费申报表",
                    "declaration_status": "未知",
                    "summary": {"match_rate": 100},
                    "field_results": [{"field_id": "a", "status": "match"}],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        state = {
            "items": {
                "91370102MA7D3P0D2P": {
                    "taxNo": "91370102MA7D3P0D2P",
                    "collect": {
                        "verifyTaskId": "task-xfs",
                        "account": {"custName": "测试企业", "areaCode": "37"},
                    },
                    "verify": {"status": "completed_with_differences", "reportPaths": [str(report)]},
                }
            }
        }

        dashboard = build_dashboard(state, root)

    row = dashboard["items"][0]
    assert row["formResults"]["consumption_tax_main"]["declarationStatus"] == "未申报"
    assert row["taxItemStatuses"][0]["declarationStatus"] == "未申报"
    assert "消费税:未申报" in row["taxItemStatusText"]

    html = render_form_cell(row["formResults"]["consumption_tax_main"])
    assert ">通过<" in html
    assert "申报状态" not in html
    assert ">未申报<" not in html


def test_dashboard_ignores_failed_task_partial_reports():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        report = root / "failed.json"
        report.write_text(
            json.dumps(
                {
                    "batch_id": "vat_general_main",
                    "tax_type": "VAT_GENERAL",
                    "form_name": "VAT general main",
                    "declaration_status": "unfiled",
                    "summary": {"match_rate": 50},
                    "field_results": [{"field_id": "a", "status": "mismatch"}],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        state = {
            "items": {
                "91310120MA7FB24479": {
                    "taxNo": "91310120MA7FB24479",
                    "collect": {
                        "verifyTaskId": "task-failed",
                        "account": {"custName": "company", "areaCode": "31"},
                    },
                    "verify": {
                        "status": "failed",
                        "returnCode": 1,
                        "reason": "external tax state conflict",
                        "reportPaths": [str(report)],
                    },
                }
            }
        }

        dashboard = build_dashboard(state, root)

    assert dashboard["items"][0]["problemCount"] == 0
    assert dashboard["items"][0]["formResults"] == {}
    assert dashboard["problem_details"] == []


def test_dashboard_keeps_completed_supplement_difference_reports_in_matrix():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        stale_report = root / "stale.json"
        clean_report = root / "clean.json"
        stale_report.write_text(
            json.dumps(
                {
                    "batch_id": "vat_small_main",
                    "tax_type": "VAT_SMALL",
                    "form_name": "VAT small main",
                    "declaration_status": "unfiled",
                    "summary": {"match_rate": 50},
                    "field_results": [{"field_id": "a", "status": "mismatch"}],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        clean_report.write_text(
            json.dumps(
                {
                    "batch_id": "vat_small_main",
                    "tax_type": "VAT_SMALL",
                    "form_name": "VAT small main",
                    "declaration_status": "unfiled",
                    "summary": {"match_rate": 100},
                    "field_results": [{"field_id": "a", "status": "match"}],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        state = {
            "items": {
                "stale": {
                    "source": "backend_supplement",
                    "taxNo": "91370302MA3BY3Y45Y",
                    "coverageSupplementTargets": ["VAT_SMALL:unfiled"],
                    "collect": {
                        "verifyTaskId": "task-stale",
                        "resolvedTask": {"coverageTarget": "VAT_SMALL:unfiled"},
                        "account": {"custName": "stale company", "areaCode": "37"},
                    },
                    "verify": {
                        "status": "completed_with_differences",
                        "returnCode": 1,
                        "reportPaths": [str(stale_report)],
                    },
                },
                "clean": {
                    "source": "backend_supplement",
                    "taxNo": "91370302MA3BXQKW20",
                    "coverageSupplementTargets": ["VAT_SMALL:unfiled"],
                    "collect": {
                        "verifyTaskId": "task-clean",
                        "resolvedTask": {"coverageTarget": "VAT_SMALL:unfiled"},
                        "account": {"custName": "clean company", "areaCode": "37"},
                    },
                    "verify": {
                        "status": "success",
                        "returnCode": 0,
                        "reportPaths": [str(clean_report)],
                    },
                },
            }
        }

        dashboard = build_dashboard(state, root)

    rows = {item["itemKey"]: item for item in dashboard["items"]}
    assert rows["stale"]["problemCount"] == 1
    assert "vat_small_main" in rows["stale"]["formResults"]
    assert rows["stale"]["verifyStatus"] == "completed_with_differences"
    assert rows["clean"]["problemCount"] == 0
    assert "vat_small_main" in rows["clean"]["formResults"]
    assert len(dashboard["problem_details"]) == 1
    assert dashboard["problem_details"][0]["taxNo"] == "91370302MA3BY3Y45Y"


def test_declaration_status_for_report_no_longer_uses_field_results_as_filed():
    assert declaration_status_for_report(
        {
            "declaration_status": "未知",
            "field_results": [{"field_id": "a", "status": "match"}],
        }
    ) == "未申报"
    assert declaration_status_for_report(
        {
            "current_period_flag": True,
            "field_results": [{"field_id": "a", "status": "match"}],
        }
    ) == "已申报"


def test_cbj_unknown_status_displays_as_verified_without_warning():
    assert declaration_status_for_report({"declaration_status": "未知"}, tax_type="CBJ_PERSONAL") == "已取数"
    assert declaration_status_for_report({"declaration_status": "未知"}, tax_type="CBJ_ANNUAL") == "已验证"
    assert declaration_status_for_report({"declaration_status": "未申报"}, tax_type="CBJ_PERSONAL") == "已取数"
    assert declaration_status_for_report({"declaration_status": "未申报"}, tax_type="CBJ_ANNUAL") == "已验证"

    html = render_form_cell({"problemCount": 0, "effectiveRate": 100, "declarationStatus": "已验证"})

    assert 'class="cell ok"' in html
    assert 'class="cell warn"' not in html


def test_unfiled_status_is_normal_not_warning():
    assert tax_item_status_css("未申报") == "ok"
    assert 'class="status ok"' in status_badge("未申报")


def test_coverage_section_uses_chinese_labels_only():
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp)
        payload = {
            "summary": {"coveredTargets": 1, "totalTargets": 2, "missingTargets": 1},
            "targets": [
                {
                    "key": "VAT_GENERAL:filed",
                    "taxType": "VAT_GENERAL",
                    "taxTypeName": "增值税（一般纳税人）",
                    "declarationStatus": "filed",
                    "declarationStatusName": "已申报",
                    "covered": True,
                    "hitCount": 1,
                    "backendTaxTypeIds": [1],
                    "examples": [
                        {
                            "taxNo": "911111111111111111",
                            "taskId": "task-filed",
                            "sourcePath": str(run_dir / "report.json"),
                        }
                    ],
                },
                {
                    "key": "VAT_GENERAL:unfiled",
                    "taxType": "VAT_GENERAL",
                    "taxTypeName": "增值税（一般纳税人）",
                    "declarationStatus": "unfiled",
                    "declarationStatusName": "未申报",
                    "covered": False,
                    "hitCount": 0,
                    "backendTaxTypeIds": [1],
                    "examples": [],
                },
            ],
            "missingTargets": [
                {
                    "key": "VAT_GENERAL:unfiled",
                    "taxType": "VAT_GENERAL",
                    "taxTypeName": "增值税（一般纳税人）",
                    "declarationStatus": "unfiled",
                    "declarationStatusName": "未申报",
                    "backendTaxTypeIds": [1],
                }
            ],
            "supplement": {
                "status": "no_candidates",
                "diagnostics": [
                    {
                        "targetKey": "VAT_GENERAL:unfiled",
                        "reason": "declaration_status_not_matched",
                        "queriedCount": 36,
                        "statusCounts": {"unknown": 33, "filed": 3},
                    }
                ],
            },
        }
        (run_dir / "coverage_status.json").write_text(
            json.dumps(payload, ensure_ascii=False),
            encoding="utf-8",
        )

        html = render_coverage_section(run_dir)

    assert "税种覆盖说明" in html
    assert "增值税（一般纳税人）" in html
    assert "已申报" in html
    assert "未申报" in html
    assert "已覆盖" in html
    assert "未覆盖" in html
    assert "911111111111111111" in html
    assert "task-filed" in html
    assert "未知：33 个；已申报：3 个" in html
    assert "VAT_GENERAL:unfiled" not in html
    assert "后台税种ID" not in html
    assert "taxTypeId" not in html


def test_coverage_gap_reason_translates_tax_type_mismatch():
    text = coverage_gap_reason(
        {},
        {},
        {
            "reason": "target_tax_type_not_matched",
            "queriedCount": 3,
            "taskTaxTypeCounts": {"VAT_GENERAL": 1, "unknown": 2},
        },
    )

    assert "target_tax_type_not_matched" not in text
    assert "\u589e\u503c\u7a0e\uff08\u4e00\u822c\u7eb3\u7a0e\u4eba\uff09" in text
    assert "\u672a\u77e5" in text

    cbj_text = coverage_gap_reason(
        {},
        {},
        {
            "reason": "target_tax_type_not_matched",
            "queriedCount": 1,
            "taskTaxTypeCounts": {"CBJ_UNKNOWN": 1},
            "cbjModeSourceCounts": {"api_result_fields": 1, "api_result_missing": 2},
        },
    )
    assert "CBJ_UNKNOWN" not in cbj_text
    assert "残保金识别来源分布" in cbj_text
    assert "接口字段识别为个税" in cbj_text
    assert "接口字段缺失" in cbj_text


def test_coverage_gap_reason_translates_required_backend_fields_missing():
    text = coverage_gap_reason(
        {},
        {},
        {
            "reason": "required_backend_fields_missing",
            "queriedCount": 1,
            "requiredFields": ["snzzzgrs_cbj", "snzzzggzze_cbj"],
            "requiredFieldMissingCount": 1,
        },
    )

    assert "required_backend_fields_missing" not in text
    assert "snzzzgrs_cbj" in text
    assert "snzzzggzze_cbj" in text
    assert "不能作为该税种的补齐任务" in text


def test_coverage_section_shows_supplement_attempts():
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp)
        payload = {
            "summary": {"totalTargets": 1, "coveredTargets": 0, "missingTargets": 1},
            "targets": [
                {
                    "key": "VAT_GENERAL:filed",
                    "taxType": "VAT_GENERAL",
                    "taxTypeName": "\u589e\u503c\u7a0e\uff08\u4e00\u822c\u7eb3\u7a0e\u4eba\uff09",
                    "declarationStatus": "filed",
                    "declarationStatusName": "\u5df2\u7533\u62a5",
                    "covered": False,
                    "backendTaxTypeIds": [1],
                    "examples": [],
                }
            ],
            "missingTargets": [{"key": "VAT_GENERAL:filed"}],
            "supplement": {
                "status": "verified",
                "attempts": [
                    {
                        "targetKey": "VAT_GENERAL:filed",
                        "taxType": "VAT_GENERAL",
                        "taxTypeName": "\u589e\u503c\u7a0e\uff08\u4e00\u822c\u7eb3\u7a0e\u4eba\uff09",
                        "declarationStatus": "filed",
                        "declarationStatusName": "\u5df2\u7533\u62a5",
                        "taxNo": "911",
                        "taskId": "task-1",
                        "attemptNo": 1,
                        "totalCandidates": 3,
                        "status": "failed",
                        "step": "\u7a0e\u5c40\u767b\u5f55",
                        "reason": "getTaskCookie failed",
                    }
                ],
            },
        }
        (run_dir / "coverage_status.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

        html = render_coverage_section(run_dir)

    assert "\u540e\u53f0\u8865\u9f50\u5c1d\u8bd5\u8bb0\u5f55" in html
    assert "task-1" in html
    assert "\u7a0e\u5c40\u767b\u5f55\u5931\u8d25" in html


def test_supplement_attempt_reason_normalizes_navigation_failure():
    reason = (
        "RuntimeError: Could not navigate to declaration query page before opening "
        "target=vat_general_main; url=https://etax.hubei.chinatax.gov.cn:8443/main"
    )

    text = normalize_supplement_failure_reason(reason)

    assert "RuntimeError" not in text
    assert "Could not navigate" not in text
    assert "\u672a\u80fd\u8fdb\u5165\u7533\u62a5\u4fe1\u606f\u67e5\u8be2\u9875" in text
    assert "vat_general_main" not in text
    assert "https://etax.hubei.chinatax.gov.cn:8443/main" in text


def test_supplement_attempt_reason_hides_unreadable_get_task_cookie_detail():
    reason = "RuntimeError: getTaskCookie failed: eT\ufffd\ufffd\u25a1\u25a1\u25a1i\ufffd\ufffd"

    text = normalize_supplement_failure_reason(reason)

    assert "RuntimeError" not in text
    assert "getTaskCookie failed" not in text
    assert "\ufffd" not in text
    assert "\u25a1" not in text
    assert "\u7a0e\u5c40\u767b\u5f55\u5931\u8d25" in text
    assert "\u539f\u59cb\u8fd4\u56de\u5185\u5bb9\u4e0d\u53ef\u8bfb" in text


def test_direct_verify_reason_reuses_supplement_reason_normalizer():
    reason = "RuntimeError: getTaskCookie failed: eT\ufffd\ufffd\u25a1\u25a1\u25a1i\ufffd\ufffd"

    text = direct_verify_reason({"reason": reason})

    assert "RuntimeError" not in text
    assert "getTaskCookie failed" not in text
    assert "\u7a0e\u5c40\u767b\u5f55\u5931\u8d25" in text


def test_tail_error_reason_prefers_final_tax_auth_error_over_navigation_race():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "stderr.log"
        path.write_text(
            "\n".join(
                [
                    "playwright._impl._errors.Error: Page.evaluate: Execution context was destroyed, most likely because of a navigation",
                    "During handling of the above exception, another exception occurred:",
                    "scripts.compare_tax_forms.DeclarationQueryAuthError: Tax bureau login state or digital account authentication expired: url=https://tpass.example/#/login",
                ]
            ),
            encoding="utf-8",
        )

        reason = tail_error_reason(path)

    assert reason.startswith("scripts.compare_tax_forms.DeclarationQueryAuthError:")
    assert "Execution context was destroyed" not in reason


def test_supplement_step_classifies_declaration_auth_error_as_tax_login():
    step = classify_supplement_failure_step(
        "scripts.compare_tax_forms.DeclarationQueryAuthError: Tax bureau login state expired",
        "failed",
    )

    assert step == classify_supplement_failure_step("RuntimeError: getTaskCookie failed: expired", "failed")
    assert step != classify_supplement_failure_step("plain verification failure", "failed")


if __name__ == "__main__":
    test_problem_details_group_by_form_then_account()
    test_tax_matrix_shows_task_id_column()
    test_tax_matrix_skips_items_without_completed_form_results()
    test_tax_matrix_empty_when_no_completed_form_results()
    test_dashboard_uses_per_task_reports_for_multi_task_tax_no()
    test_dashboard_treats_unknown_declaration_status_as_unfiled()
    test_dashboard_ignores_failed_task_partial_reports()
    test_dashboard_keeps_completed_supplement_difference_reports_in_matrix()
    test_declaration_status_for_report_no_longer_uses_field_results_as_filed()
    test_cbj_unknown_status_displays_as_verified_without_warning()
    test_unfiled_status_is_normal_not_warning()
    test_coverage_section_uses_chinese_labels_only()
    test_coverage_gap_reason_translates_tax_type_mismatch()
    test_coverage_gap_reason_translates_required_backend_fields_missing()
    test_coverage_section_shows_supplement_attempts()
    test_supplement_attempt_reason_normalizes_navigation_failure()
    test_supplement_attempt_reason_hides_unreadable_get_task_cookie_detail()
    test_direct_verify_reason_reuses_supplement_reason_normalizer()
    test_tail_error_reason_prefers_final_tax_auth_error_over_navigation_race()
    test_supplement_step_classifies_declaration_auth_error_as_tax_login()
    print("All batch summary rendering tests passed!")
