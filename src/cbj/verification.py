from __future__ import annotations

import argparse
import html
import json
import logging
import re
import time
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from src.api.api_client import APIClient

LOGGER = logging.getLogger(__name__)

CBJ_BACKEND_FIELDS = ("snzzzgrs_cbj", "snzzzggzze_cbj")
CBJ_FIELD_NAMES = {
    "snzzzgrs_cbj": "\u4e0a\u5e74\u5728\u804c\u804c\u5de5\u4eba\u6570",
    "snzzzggzze_cbj": "\u4e0a\u5e74\u5728\u804c\u804c\u5de5\u5de5\u8d44\u603b\u989d",
}


@dataclass(frozen=True)
class BackendField:
    field_id: str
    value: Any
    location: str

    @property
    def present(self) -> bool:
        return self.value is not None and str(self.value).strip() != ""


def fetch_backend_fields(task_id: str) -> tuple[dict[str, BackendField], dict[str, Any]]:
    response = APIClient().fetch_by_task_id(task_id)
    if response.get("error"):
        raise RuntimeError(f"API fetch failed: {response.get('error')}")
    search_roots = {
        "data": response.get("data") or {},
        "raw_resultJson": response.get("raw_resultJson") or {},
    }
    fields = {
        field_id: find_field(field_id, search_roots) or BackendField(field_id, None, "")
        for field_id in CBJ_BACKEND_FIELDS
    }
    return fields, response


def find_field(field_id: str, node: Any, path: str = "$") -> BackendField | None:
    if isinstance(node, dict):
        for key, value in node.items():
            key_text = str(key)
            current_path = f"{path}.{key_text}"
            if key_text == field_id or key_text.endswith(f".{field_id}"):
                return BackendField(field_id, value, current_path)
        for key, value in node.items():
            found = find_field(field_id, value, f"{path}.{key}")
            if found:
                return found
    elif isinstance(node, list):
        for index, value in enumerate(node):
            found = find_field(field_id, value, f"{path}[{index}]")
            if found:
                return found
    return None


def verify_personal_cbj(task_id: str, output_root: Path | str = "output/reports") -> Path:
    backend_fields, _response = fetch_backend_fields(task_id)
    rows = []
    for field_id in CBJ_BACKEND_FIELDS:
        field = backend_fields[field_id]
        rows.append(
            {
                "field_id": field_id,
                "display_name": CBJ_FIELD_NAMES[field_id],
                "business_name": CBJ_FIELD_NAMES[field_id],
                "api_raw_value": field.value,
                "web_raw_value": None,
                "status": "match" if field.present else "api_missing",
                "detail": f"backend location: {field.location}" if field.location else "backend field missing",
            }
        )
    return save_cbj_report(
        task_id=task_id,
        mode="personal",
        form_name="\u4e2a\u7a0e\u6b8b\u4fdd\u91d1\u53d6\u6570\u540e\u53f0\u5b57\u6bb5\u6821\u9a8c",
        field_results=rows,
        output_root=output_root,
    )


def verify_annual_settlement_cbj(
    task_id: str,
    args: argparse.Namespace,
    output_root: Path | str = "output/reports",
) -> Path:
    backend_fields, response = fetch_backend_fields(task_id)
    province = str(response.get("province") or "")
    web_values = fetch_annual_settlement_web_values(task_id, province, args)
    comparisons = [
        build_numeric_comparison(
            field_id="snzzzgrs_cbj",
            backend=backend_fields["snzzzgrs_cbj"],
            web_value=web_values.get("snzzzgrs_cbj"),
            tolerance=Decimal("0"),
        ),
        build_numeric_comparison(
            field_id="snzzzggzze_cbj",
            backend=backend_fields["snzzzggzze_cbj"],
            web_value=web_values.get("snzzzggzze_cbj"),
            tolerance=Decimal("0.01"),
        ),
    ]
    return save_cbj_report(
        task_id=task_id,
        mode="annual_settlement",
        form_name="\u6c47\u7b97\u6e05\u7f34\u6b8b\u4fdd\u91d1\u53d6\u6570\u6821\u9a8c",
        field_results=comparisons,
        output_root=output_root,
        province=province,
    )


def fetch_annual_settlement_web_values(task_id: str, province: str, args: argparse.Namespace) -> dict[str, Any]:
    from scripts.compare_tax_forms import (
        CHANJET_TASK_URL,
        click_declaration_row,
        connect_browser,
        extract_etax_host,
        find_existing_tax_page,
        get_web_config,
        is_declaration_detail_page,
        navigate_to_query_page_robust,
        wait_for_chanjet_login,
        wait_for_declaration_detail_page,
    )
    from src.login.task_login_flow import TaskLoginFlow

    bm = connect_browser(args)
    try:
        page = bm.find_page_by_url("chanjet.com") or bm.get_page()
        page.goto(CHANJET_TASK_URL, wait_until="domcontentloaded", timeout=30000)
        chanjet_page = wait_for_chanjet_login(bm, args.chanjet_timeout)
        tax_page = find_existing_tax_page(bm, province)
        if not tax_page:
            flow = TaskLoginFlow(
                bm,
                timeout=args.tax_timeout,
                login_strategy=getattr(args, "tax_login_strategy", "plugin_first"),
            )
            tax_page, info = flow.login(chanjet_page, task_id)
            province = info.province or province
            LOGGER.info("Logged into tax bureau for CBJ annual check: province=%s url=%s", province, tax_page.url)
        else:
            LOGGER.info("Reusing existing tax bureau page for CBJ annual check: %s", tax_page.url)

        web_config = get_web_config(args.config_root, "CIT_A_PREPAY")
        query_page = navigate_to_query_page_robust(tax_page, web_config)
        host = extract_etax_host(query_page.url or "")
        if not host:
            raise RuntimeError(f"Could not resolve tax bureau host from url={query_page.url}")
        window = annual_query_window(args.query_year)
        filter_result = fill_annual_query_filters(query_page, window, include_period=True)
        LOGGER.info("CBJ annual declaration query filter result: %s", filter_result)
        query_state = inspect_annual_query_state(query_page, window)
        if int(query_state.get("exact_count") or 0) <= 0:
            raise RuntimeError(
                "Annual CIT A100000 declaration query returned no row for "
                f"declarationDate={window['declaration_start']}..{window['declaration_end']}, "
                f"taxPeriod={window['period_start']}..{window['period_end']}; "
                f"url={query_page.url}; total={query_state.get('total')}; rows={query_state.get('rows')}"
            )
        try:
            detail_page = click_annual_declaration_row(query_page, window, wait_for_declaration_detail_page)
        except Exception:
            detail_page = click_declaration_row(query_page, ("BDA0610994", "A100000"))
        if not is_declaration_detail_page(detail_page):
            raise RuntimeError(f"Annual CIT detail page did not open; url={detail_page.url}")

        select_cbj_detail_form(detail_page, "\u804c\u5de5\u85aa\u916c\u652f\u51fa")
        wage_total = extract_a105050_wage_tax_amount(detail_page)

        select_cbj_detail_form(detail_page, "\u57fa\u7840\u4fe1\u606f\u8868")
        employee_count = extract_a000000_employee_count(detail_page)

        return {
            "snzzzggzze_cbj": wage_total,
            "snzzzgrs_cbj": employee_count,
        }
    finally:
        bm.close()


def annual_query_window(query_year: int | None = None, today: date | None = None) -> dict[str, str]:
    today = today or date.today()
    year = query_year or today.year
    declaration_end = today if today.year == year else date(year, 12, 31)
    previous_year = year - 1
    return {
        "declaration_start": f"{year}-01-01",
        "declaration_end": declaration_end.strftime("%Y-%m-%d"),
        "period_start": f"{previous_year}-01-01",
        "period_end": f"{previous_year}-12-31",
    }


def fill_annual_query_filters(page, window: dict[str, str]) -> str:
    result = page.evaluate(
        """async ({window}) => {
            const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
            const visible = (el) => !!(el && (el.offsetWidth || el.offsetHeight || el.getClientRects().length));
            const normalize = (value) => String(value || '').replace(/\\s+/g, '');
            const setValue = (input, value) => {
                if (!input) return false;
                input.scrollIntoView({ block: 'center', inline: 'center' });
                input.focus();
                const proto = Object.getPrototypeOf(input);
                const desc = proto && Object.getOwnPropertyDescriptor(proto, 'value');
                if (desc && desc.set) desc.set.call(input, value);
                else input.value = value;
                input.dispatchEvent(new Event('input', { bubbles: true }));
                input.dispatchEvent(new Event('change', { bubbles: true }));
                input.blur();
                return true;
            };
            const clickByText = (labels) => {
                const wanted = labels.map(normalize);
                const nodes = Array.from(document.querySelectorAll('button, a, [role=button], .el-button, .ant-btn, .t-button'))
                    .filter(visible);
                const node = nodes.find((el) => {
                    const text = normalize(el.innerText || el.textContent || el.getAttribute('aria-label'));
                    return wanted.some((label) => text === label || text.includes(label));
                });
                if (!node) return '';
                node.scrollIntoView({ block: 'center', inline: 'center' });
                node.click();
                return normalize(node.innerText || node.textContent || node.getAttribute('aria-label'));
            };
            const findContainerByLabel = (labels) => {
                const wanted = labels.map(normalize);
                const nodes = Array.from(document.querySelectorAll('label, span, div, td, th, p'))
                    .filter((el) => visible(el) && normalize(el.innerText || el.textContent).length <= 80);
                const label = nodes.find((el) => {
                    const text = normalize(el.innerText || el.textContent);
                    return wanted.some((value) => text.includes(value));
                });
                if (!label) return null;
                return label.closest('.el-form-item, .ant-form-item, .t-form__item, tr, td, div') || label.parentElement;
            };
            const fillRange = (labels, values) => {
                const container = findContainerByLabel(labels);
                if (!container) return `missing:${labels[0]}`;
                const inputs = Array.from(container.querySelectorAll('input:not([type=hidden])')).filter(visible);
                if (inputs.length >= 2) {
                    setValue(inputs[0], values[0]);
                    setValue(inputs[1], values[1]);
                    return `filled_range:${labels[0]}`;
                }
                if (inputs.length === 1) {
                    setValue(inputs[0], values.join(' - '));
                    return `filled_single:${labels[0]}`;
                }
                return `no_input:${labels[0]}`;
            };
            const fillFormType = async () => {
                const container = findContainerByLabel(['申报表种类', '申报表类型', '申报表名称']);
                if (!container) return 'form_type_label_missing';
                const trigger = Array.from(container.querySelectorAll('input:not([type=hidden]), .el-select, .ant-select, .t-select, [role=combobox]'))
                    .filter(visible)[0];
                if (!trigger) return 'form_type_trigger_missing';
                trigger.click();
                if (trigger.tagName === 'INPUT') setValue(trigger, 'BDA0610994');
                await wait(1000);
                const options = Array.from(document.querySelectorAll('.el-select-dropdown__item, .ant-select-item, .t-select-option, .t-option, li, [role=option], div'))
                    .filter((el) => visible(el) && normalize(el.innerText || el.textContent).length <= 300);
                const option = options.find((el) => {
                    const text = normalize(el.innerText || el.textContent);
                    return text.includes('BDA0610994') || (text.includes('A100000') && text.includes('企业所得税年度'));
                });
                if (!option) return 'form_type_option_missing';
                option.scrollIntoView({ block: 'center' });
                option.click();
                await wait(500);
                return 'form_type_selected';
            };

            const results = [];
            results.push(fillRange(['申报日期'], [window.declaration_start, window.declaration_end]));
            results.push(fillRange(['税款所属期'], [window.period_start, window.period_end]));
            results.push(await fillFormType());
            await wait(500);
            results.push(`query=${clickByText(['查询', '搜索']) || 'missing'}`);
            await wait(5000);
            return results.join(';');
        }""",
        {"window": window},
    )
    return str(result)


def fill_annual_query_filters(page, window: dict[str, str], include_period: bool = True) -> str:
    result = page.evaluate(
        """async ({window, includePeriod}) => {
            const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
            const visible = (el) => !!(el && (el.offsetWidth || el.offsetHeight || el.getClientRects().length));
            const normalize = (value) => String(value || '').replace(/\\s+/g, '');
            const normalizeDate = (value) => String(value || '').slice(0, 10);
            const findComponents = (el, out = []) => {
                if (!el) return out;
                if (el.__vue__) out.push(el.__vue__);
                if (el.__vueParentComponent) out.push(el.__vueParentComponent.proxy || el.__vueParentComponent);
                for (const child of el.children || []) findComponents(child, out);
                return out;
            };
            const exactRows = (rows) => (rows || []).filter((row) => {
                const text = Object.values(row || {}).map((value) => String(value ?? '')).join('');
                const codeOk = String(row && row.yzpzzlDm || '').includes('BDA0610994')
                    || text.includes('BDA0610994')
                    || text.includes('A100000');
                return codeOk
                    && normalizeDate(row && row.skssqq) === window.period_start
                    && normalizeDate(row && row.skssqz) === window.period_end;
            });
            const comp = findComponents(document.body).find((item) => {
                return item && item.$data && item.$data.formData && typeof item.DescribeSbmxcx2 === 'function';
            });
            if (comp) {
                const formData = comp.$data.formData;
                Object.assign(formData, {
                    yzpzzlDm: '',
                    gzlx: ['1', '5'],
                    zfbz: 'N',
                    sbrqq: window.declaration_start,
                    sbrqz: window.declaration_end,
                    skssqq: includePeriod ? window.period_start : '',
                    skssqz: includePeriod ? window.period_end : '',
                    pageNum: 1,
                    pageSize: Math.max(Number(formData.pageSize || 30), 100)
                });
                const syncQueryConfig = () => {
                    for (const item of comp.$data.querySearchConfig || []) {
                        if (Object.prototype.hasOwnProperty.call(formData, item.key)) {
                            item.value = formData[item.key];
                        }
                    }
                };
                const runQuery = async () => {
                    syncQueryConfig();
                    const ret = comp.DescribeSbmxcx2(formData);
                    if (ret && typeof ret.then === 'function') await ret;
                    const deadline = Date.now() + 15000;
                    while (Date.now() < deadline && comp.$data.isLoading) await wait(300);
                    await wait(1000);
                    return Array.isArray(comp.$data.data) ? comp.$data.data : [];
                };
                let rows = await runQuery();
                let exactCount = exactRows(rows).length;
                const total = Number(comp.$data.pagination && comp.$data.pagination.total || rows.length || 0);
                const pageSize = Math.max(Number(formData.pageSize || 30), 1);
                const maxPage = Math.max(1, Math.ceil(total / pageSize));
                let pagesChecked = 1;
                for (let pageNum = 2; exactCount <= 0 && pageNum <= maxPage; pageNum += 1) {
                    formData.pageNum = pageNum;
                    rows = await runQuery();
                    pagesChecked += 1;
                    exactCount = exactRows(rows).length;
                }
                return `vue_query:period=${includePeriod ? 'yes' : 'no'};total=${total};rows=${rows.length};page=${formData.pageNum};pagesChecked=${pagesChecked};exact=${exactCount}`;
            }

            const setValue = (input, value) => {
                if (!input) return false;
                input.scrollIntoView({ block: 'center', inline: 'center' });
                input.focus();
                const proto = Object.getPrototypeOf(input);
                const desc = proto && Object.getOwnPropertyDescriptor(proto, 'value');
                if (desc && desc.set) desc.set.call(input, value);
                else input.value = value;
                input.dispatchEvent(new Event('input', { bubbles: true }));
                input.dispatchEvent(new Event('change', { bubbles: true }));
                input.blur();
                return true;
            };
            const clickByText = (labels) => {
                const wanted = labels.map(normalize);
                const nodes = Array.from(document.querySelectorAll('button, a, [role=button], .el-button, .ant-btn, .t-button'))
                    .filter(visible);
                const node = nodes.find((el) => {
                    const text = normalize(el.innerText || el.textContent || el.getAttribute('aria-label'));
                    return wanted.some((label) => text === label || text.includes(label));
                });
                if (!node) return '';
                node.scrollIntoView({ block: 'center', inline: 'center' });
                node.click();
                return normalize(node.innerText || node.textContent || node.getAttribute('aria-label'));
            };
            const findContainerByLabel = (labels) => {
                const wanted = labels.map(normalize);
                const nodes = Array.from(document.querySelectorAll('label, span, div, td, th, p'))
                    .filter((el) => visible(el) && normalize(el.innerText || el.textContent).length <= 80);
                const label = nodes.find((el) => {
                    const text = normalize(el.innerText || el.textContent);
                    return wanted.some((value) => text.includes(value));
                });
                if (!label) return null;
                return label.closest('.el-form-item, .ant-form-item, .t-form__item, tr, td, div') || label.parentElement;
            };
            const fillRange = (labels, values) => {
                const container = findContainerByLabel(labels);
                if (!container) return `missing:${labels[0]}`;
                const inputs = Array.from(container.querySelectorAll('input:not([type=hidden])')).filter(visible);
                if (inputs.length >= 2) {
                    setValue(inputs[0], values[0]);
                    setValue(inputs[1], values[1]);
                    return `filled_range:${labels[0]}`;
                }
                if (inputs.length === 1) {
                    setValue(inputs[0], values.join(' - '));
                    return `filled_single:${labels[0]}`;
                }
                return `no_input:${labels[0]}`;
            };
            const clearFormType = async () => {
                const container = findContainerByLabel(['\\u7533\\u62a5\\u8868\\u79cd\\u7c7b', '\\u7533\\u62a5\\u8868\\u7c7b\\u578b', '\\u7533\\u62a5\\u8868\\u540d\\u79f0']);
                if (!container) return 'form_type_not_set';
                const clearButtons = Array.from(container.querySelectorAll(
                    '.el-select__caret.el-icon-circle-close, .el-tag__close, .ant-select-clear, .t-tag__icon-close, [aria-label="clear"], [aria-label="Clear"]'
                )).filter(visible);
                if (clearButtons.length) {
                    clearButtons.forEach((button) => button.click());
                    await wait(300);
                }
                const trigger = Array.from(container.querySelectorAll('input:not([type=hidden]), .el-select input:not([type=hidden]), .ant-select input:not([type=hidden]), .t-select input:not([type=hidden]), [role=combobox] input:not([type=hidden])'))
                    .filter(visible)[0];
                if (trigger && trigger.tagName === 'INPUT') setValue(trigger, '');
                return 'form_type_cleared';
            };

            const results = [];
            results.push(fillRange(['\\u7533\\u62a5\\u65e5\\u671f'], [window.declaration_start, window.declaration_end]));
            if (includePeriod) {
                results.push(fillRange(['\\u7a0e\\u6b3e\\u6240\\u5c5e\\u671f'], [window.period_start, window.period_end]));
            }
            results.push(await clearFormType());
            await wait(500);
            results.push(`query=${clickByText(['\\u67e5\\u8be2', '\\u641c\\u7d22']) || 'missing'}`);
            await wait(5000);
            return results.join(';');
        }""",
        {"window": window, "includePeriod": include_period},
    )
    return str(result)


def inspect_annual_query_state(page, window: dict[str, str]) -> dict[str, Any]:
    return page.evaluate(
        """({window}) => {
            const normalizeDate = (value) => String(value || '').slice(0, 10);
            const findComponents = (el, out = []) => {
                if (!el) return out;
                if (el.__vue__) out.push(el.__vue__);
                if (el.__vueParentComponent) out.push(el.__vueParentComponent.proxy || el.__vueParentComponent);
                for (const child of el.children || []) findComponents(child, out);
                return out;
            };
            const exact = (row) => {
                const text = Object.values(row || {}).map((value) => String(value ?? '')).join('');
                const codeOk = String(row && row.yzpzzlDm || '').includes('BDA0610994')
                    || text.includes('BDA0610994')
                    || text.includes('A100000');
                return codeOk
                    && normalizeDate(row && row.skssqq) === window.period_start
                    && normalizeDate(row && row.skssqz) === window.period_end;
            };
            const comp = findComponents(document.body).find((item) => {
                return item && item.$data && item.$data.formData && Array.isArray(item.$data.data);
            });
            if (comp) {
                const rows = comp.$data.data || [];
                const compactRows = rows.slice(0, 10).map((row) => ({
                    yzpzzlDm: row && row.yzpzzlDm,
                    yzpzzl: row && row.yzpzzl,
                    nssbrq: row && row.nssbrq,
                    skssqq: row && row.skssqq,
                    skssqz: row && row.skssqz,
                    gzlx: row && row.gzlx,
                    zfbz: row && row.zfbz,
                }));
                return {
                    source: 'vue',
                    total: comp.$data.pagination && comp.$data.pagination.total,
                    row_count: rows.length,
                    exact_count: rows.filter(exact).length,
                    rows: compactRows,
                };
            }
            return {
                source: 'dom',
                total: null,
                row_count: 0,
                exact_count: 0,
                rows: [],
                body: (document.body && document.body.innerText || '').slice(0, 1000),
            };
        }""",
        {"window": window},
    )


def click_annual_declaration_row(page, window: dict[str, str], wait_for_detail):
    before_pages = set(page.context.pages)
    result = page.evaluate(
        """({window}) => {
            const normalizeDate = (value) => String(value || '').slice(0, 10);
            const visible = (el) => !!(el && (el.offsetWidth || el.offsetHeight || el.getClientRects().length));
            const findComponents = (el, out = []) => {
                if (!el) return out;
                if (el.__vue__) out.push(el.__vue__);
                if (el.__vueParentComponent) out.push(el.__vueParentComponent.proxy || el.__vueParentComponent);
                for (const child of el.children || []) findComponents(child, out);
                return out;
            };
            const exact = (row) => {
                const text = Object.values(row || {}).map((value) => String(value ?? '')).join('');
                const codeOk = String(row && row.yzpzzlDm || '').includes('BDA0610994')
                    || text.includes('BDA0610994')
                    || text.includes('A100000');
                return codeOk
                    && normalizeDate(row && row.skssqq) === window.period_start
                    && normalizeDate(row && row.skssqz) === window.period_end;
            };
            const comp = findComponents(document.body).find((item) => {
                return item && item.$data && Array.isArray(item.$data.data);
            });
            if (comp) {
                const rowIndex = comp.$data.data.findIndex(exact);
                if (rowIndex >= 0 && typeof comp.rehandleClickOp === 'function') {
                    comp.rehandleClickOp(comp.$data.data[rowIndex], rowIndex);
                    return `clicked_vue:${rowIndex}`;
                }
            }
            const rows = Array.from(document.querySelectorAll('tr, .el-table__row, .t-table__row')).filter(visible);
            const hit = rows.find((row) => {
                const text = row.innerText || row.textContent || '';
                return (text.includes('BDA0610994') || text.includes('A100000'))
                    && text.includes(window.period_start)
                    && text.includes(window.period_end);
            });
            if (!hit) return 'not_found';
            const buttons = Array.from(hit.querySelectorAll('a, button, [role=button], .ant-btn, .el-button, .t-button'))
                .filter(visible);
            const detail = buttons.find((el) => {
                const text = el.innerText || el.textContent || '';
                return /\\u67e5\\u770b|\\u8be6\\u60c5|\\u6253\\u5f00|\\u7533\\u62a5/.test(text);
            });
            (detail || buttons[buttons.length - 1] || hit).click();
            return 'clicked_dom';
        }""",
        {"window": window},
    )
    if not str(result).startswith("clicked"):
        raise RuntimeError(f"Annual CIT declaration row was not found; result={result}")
    time.sleep(5)
    return wait_for_detail(page, before_pages, timeout=45)


def select_cbj_detail_form(page, keyword: str) -> str:
    result = page.evaluate(
        """async ({keyword}) => {
            const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
            const visible = (el) => !!(el && (el.offsetWidth || el.offsetHeight || el.getClientRects().length));
            const normalize = (value) => String(value || '').replace(/\\s+/g, '');
            if (normalize(document.body && document.body.innerText).includes(normalize(keyword))) {
                return `already_visible:${keyword}`;
            }
            const triggers = Array.from(document.querySelectorAll(
                '.t-select__wrap, .t-select-input, .t-input, input.t-input__inner, [role=combobox]'
            )).filter(visible);
            if (!triggers.length) return `trigger_not_found:${keyword}`;
            let options = [];
            for (const trigger of triggers) {
                trigger.scrollIntoView({ block: 'center', inline: 'center' });
                trigger.click();
                await wait(500);
                options = Array.from(document.querySelectorAll('li.t-select-option, .t-select-option, [role=option]'))
                    .filter(visible);
                if (options.length) break;
            }
            const option = options.find((el) => {
                const text = `${el.innerText || el.textContent || ''}${el.getAttribute('title') || ''}`;
                return normalize(text).includes(normalize(keyword));
            });
            if (!option) {
                return `option_not_found:${keyword};options=${options.map((el) => normalize(el.innerText || el.textContent)).join('|')}`;
            }
            option.scrollIntoView({ block: 'center', inline: 'center' });
            option.click();
            const deadline = Date.now() + 15000;
            while (Date.now() < deadline) {
                await wait(500);
                const bodyText = normalize(document.body && document.body.innerText);
                const inputValue = normalize(document.querySelector('input.t-input__inner')?.value || '');
                if (bodyText.includes(normalize(keyword)) && inputValue.includes(normalize(keyword))) {
                    return `selected:${keyword}`;
                }
            }
            return `select_unconfirmed:${keyword};value=${document.querySelector('input.t-input__inner')?.value || ''}`;
        }""",
        {"keyword": keyword},
    )
    if not str(result).startswith(("already_visible", "selected")):
        raise RuntimeError(f"Could not select CBJ detail form: {result}")
    LOGGER.info("CBJ detail form select result: %s", result)
    return str(result)


def extract_a105050_wage_tax_amount(page) -> Any:
    return page.evaluate(
        """() => {
            const visible = (el) => !!(el && (el.offsetWidth || el.offsetHeight || el.getClientRects().length));
            const clean = (value) => String(value || '').replace(/\\s+/g, '');
            const cellText = (cell) => {
                const input = cell.querySelector && cell.querySelector('input, textarea');
                return clean(input ? input.value : (cell.innerText || cell.textContent));
            };
            const rows = Array.from(document.querySelectorAll('tr, .el-table__row, .t-table__row'))
                .filter(visible);
            for (const row of rows) {
                const text = clean(row.innerText || row.textContent);
                if (!text.includes('工资薪金支出')) continue;
                const cells = Array.from(row.querySelectorAll('td, th, .cell, [class*=table-cell]')).filter(visible);
                const values = cells.map(cellText).filter(Boolean);
                if (values.length >= 5) return values[4];
                const numeric = values.filter((value) => /-?\\d[\\d,]*(\\.\\d+)?/.test(value));
                if (numeric.length) return numeric[Math.min(2, numeric.length - 1)];
            }
            return null;
        }"""
    )


def extract_a000000_employee_count(page) -> Any:
    return page.evaluate(
        """() => {
            const visible = (el) => !!(el && (el.offsetWidth || el.offsetHeight || el.getClientRects().length));
            const clean = (value) => String(value || '').replace(/\\s+/g, '');
            const readValues = (node) => {
                const inputs = node.querySelectorAll ? Array.from(node.querySelectorAll('input, textarea')).filter(visible).map((el) => clean(el.value)).filter(Boolean) : [];
                const text = clean(node.innerText || node.textContent);
                const numbers = Array.from(text.matchAll(/-?\\d[\\d,]*(\\.\\d+)?/g)).map((m) => m[0]);
                return inputs.length ? inputs : numbers;
            };
            const nodes = Array.from(document.querySelectorAll('tr, .el-table__row, .t-table__row, .el-form-item, .t-form__item, div'))
                .filter((el) => visible(el) && clean(el.innerText || el.textContent).length <= 500);
            for (const node of nodes) {
                const text = clean(node.innerText || node.textContent);
                if (!text.includes('104') || !text.includes('从业人数')) continue;
                const values = readValues(node).filter((value) => value !== '104');
                if (values.length) return values[values.length - 1];
            }
            return null;
        }"""
    )


def extract_a105050_wage_tax_amount(page) -> Any:
    return page.evaluate(
        """() => {
            const visible = (el) => !!(el && (el.offsetWidth || el.offsetHeight || el.getClientRects().length));
            const clean = (value) => String(value || '').replace(/\\s+/g, '');
            const cellText = (cell) => {
                const input = cell.querySelector && cell.querySelector('input, textarea');
                return clean(input ? input.value : (cell.innerText || cell.textContent));
            };
            const htmlDocuments = (() => {
                const docs = [document];
                function findComponents(el, out = []) {
                    if (!el) return out;
                    if (el.__vue__) out.push(el.__vue__);
                    if (el.__vueParentComponent) out.push(el.__vueParentComponent.proxy || el.__vueParentComponent);
                    for (const child of el.children || []) findComponents(child, out);
                    return out;
                }
                for (const comp of findComponents(document.body)) {
                    const data = comp && comp.$data;
                    for (const key of ['sbxxcxDetail', 'detailHtml', 'html', 'content']) {
                        const value = data && data[key];
                        if (typeof value === 'string' && value.includes('A105050')) {
                            docs.push(new DOMParser().parseFromString(value, 'text/html'));
                        }
                    }
                }
                return docs;
            })();
            for (const doc of htmlDocuments) {
                const rows = Array.from(doc.querySelectorAll('tr, .el-table__row, .t-table__row'))
                    .filter((row) => doc === document ? visible(row) : true);
                let taxAmountIndex = -1;
                for (const row of rows) {
                    const cells = Array.from(row.querySelectorAll('td, th, .cell, [class*=table-cell]'))
                        .filter((cell) => doc === document ? visible(cell) : true);
                    const values = cells.map(cellText);
                    const index = values.findIndex((value) => value === '\\u7a0e\\u6536\\u91d1\\u989d');
                    if (index >= 0) {
                        taxAmountIndex = index;
                        break;
                    }
                }
                for (const row of rows) {
                    const text = clean(row.innerText || row.textContent);
                    if (!text.includes('\\u5de5\\u8d44\\u85aa\\u91d1\\u652f\\u51fa')) continue;
                    const cells = Array.from(row.querySelectorAll('td, th, .cell, [class*=table-cell]'))
                        .filter((cell) => doc === document ? visible(cell) : true);
                    const values = cells.map(cellText).filter(Boolean);
                    if (taxAmountIndex >= 0 && taxAmountIndex < cells.length) return cellText(cells[taxAmountIndex]);
                    if (values.length >= 7) return values[6];
                    if (values.length >= 5) return values[4];
                    const numeric = values.filter((value) => /-?\\d[\\d,]*(\\.\\d+)?/.test(value));
                    if (numeric.length) return numeric[Math.min(2, numeric.length - 1)];
                }
            }
            return null;
        }"""
    )


def extract_a000000_employee_count(page) -> Any:
    return page.evaluate(
        """() => {
            const visible = (el) => !!(el && (el.offsetWidth || el.offsetHeight || el.getClientRects().length));
            const clean = (value) => String(value || '').replace(/\\s+/g, '');
            const readValues = (node, visibleOnly) => {
                const inputs = node.querySelectorAll
                    ? Array.from(node.querySelectorAll('input, textarea'))
                        .filter((el) => !visibleOnly || visible(el))
                        .map((el) => clean(el.value))
                        .filter(Boolean)
                    : [];
                const text = clean(node.innerText || node.textContent);
                const numbers = Array.from(text.matchAll(/-?\\d[\\d,]*(\\.\\d+)?/g)).map((m) => m[0]);
                return inputs.length ? inputs : numbers;
            };
            const htmlDocuments = (() => {
                const docs = [document];
                function findComponents(el, out = []) {
                    if (!el) return out;
                    if (el.__vue__) out.push(el.__vue__);
                    if (el.__vueParentComponent) out.push(el.__vueParentComponent.proxy || el.__vueParentComponent);
                    for (const child of el.children || []) findComponents(child, out);
                    return out;
                }
                for (const comp of findComponents(document.body)) {
                    const data = comp && comp.$data;
                    for (const key of ['sbxxcxDetail', 'detailHtml', 'html', 'content']) {
                        const value = data && data[key];
                        if (typeof value === 'string' && (value.includes('A000000') || value.includes('\\u4ece\\u4e1a\\u4eba\\u6570'))) {
                            docs.push(new DOMParser().parseFromString(value, 'text/html'));
                        }
                    }
                }
                return docs;
            })();
            for (const doc of htmlDocuments) {
                const nodes = Array.from(doc.querySelectorAll('tr, .el-table__row, .t-table__row, .el-form-item, .t-form__item, div'))
                    .filter((el) => doc !== document || (visible(el) && clean(el.innerText || el.textContent).length <= 500));
                for (const node of nodes) {
                    const text = clean(node.innerText || node.textContent);
                    if (!text.includes('104') || !text.includes('\\u4ece\\u4e1a\\u4eba\\u6570')) continue;
                    const values = readValues(node, doc === document).filter((value) => value !== '104');
                    if (values.length) return values[values.length - 1];
                }
            }
            return null;
        }"""
    )


def build_numeric_comparison(
    field_id: str,
    backend: BackendField,
    web_value: Any,
    tolerance: Decimal,
) -> dict[str, Any]:
    api_decimal = parse_decimal(backend.value)
    web_decimal = parse_decimal(web_value)
    if not backend.present:
        status = "api_missing"
        detail = "backend field missing"
    elif web_value is None or str(web_value).strip() == "":
        status = "web_missing"
        detail = "tax bureau value missing"
    elif api_decimal is None or web_decimal is None:
        status = "parse_error"
        detail = f"api={backend.value!r}; web={web_value!r}"
    else:
        diff = abs(api_decimal - web_decimal)
        status = "match" if diff <= tolerance else "mismatch"
        detail = f"diff={diff}; tolerance={tolerance}"
    return {
        "field_id": field_id,
        "display_name": CBJ_FIELD_NAMES[field_id],
        "business_name": CBJ_FIELD_NAMES[field_id],
        "api_raw_value": backend.value,
        "web_raw_value": web_value,
        "api_normalized": str(api_decimal) if api_decimal is not None else None,
        "web_normalized": str(web_decimal) if web_decimal is not None else None,
        "status": status,
        "detail": detail,
    }


def parse_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text in {"-", "/", "\u2014", "\u2013"}:
        return None
    text = text.replace(",", "").replace("\uffe5", "").replace("\u00a5", "")
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        return Decimal(match.group(0))
    except (InvalidOperation, ValueError):
        return None


def save_cbj_report(
    task_id: str,
    mode: str,
    form_name: str,
    field_results: list[dict[str, Any]],
    output_root: Path | str = "output/reports",
    province: str = "",
) -> Path:
    output_dir = Path(output_root) / task_id
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = output_dir / f"cbj_{mode}_compare_{task_id}_{ts}.json"
    summary_path = output_dir / f"cbj_summary_{task_id}_{ts}.html"
    summary = summarize_fields(field_results)
    tax_type = "CBJ_ANNUAL" if mode == "annual_settlement" else "CBJ_PERSONAL"
    payload = {
        "task_id": task_id,
        "batch_id": f"cbj_{mode}",
        "tax_type": tax_type,
        "form_code": f"CBJ_{mode.upper()}",
        "form_name": form_name,
        "province": province,
        "declaration_status": "\u4e0d\u533a\u5206\u7533\u62a5\u72b6\u6001" if mode == "annual_settlement" else "\u5df2\u53d6\u6570",
        "summary": summary,
        "field_results": field_results,
        "timestamp": datetime.now().isoformat(),
    }
    report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    summary_path.write_text(render_html_summary(payload, report_path.name), encoding="utf-8")
    LOGGER.info("Saved CBJ report: %s", report_path)
    LOGGER.info("Saved CBJ summary: %s", summary_path)
    return report_path


def summarize_fields(fields: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {
        "match_count": 0,
        "tolerance_match_count": 0,
        "mismatch_count": 0,
        "api_missing_count": 0,
        "web_missing_count": 0,
        "parse_error_count": 0,
        "mapping_error_count": 0,
        "both_missing_count": 0,
        "skip_count": 0,
    }
    for item in fields:
        status = str(item.get("status") or "")
        key = f"{status}_count"
        if key in counts:
            counts[key] += 1
    total = len(fields)
    passed = counts["match_count"] + counts["tolerance_match_count"]
    counts["total_fields"] = total
    counts["match_rate"] = round(passed / total * 100, 2) if total else 100.0
    return counts


def render_html_summary(payload: dict[str, Any], report_name: str) -> str:
    rows = []
    for item in payload.get("field_results") or []:
        rows.append(
            "<tr>"
            f"<td><code>{escape(item.get('field_id'))}</code><br>{escape(item.get('business_name'))}</td>"
            f"<td>{escape(item.get('api_raw_value'))}</td>"
            f"<td>{escape(item.get('web_raw_value'))}</td>"
            f"<td>{escape(item.get('status'))}</td>"
            f"<td>{escape(item.get('detail'))}</td>"
            "</tr>"
        )
    summary = payload.get("summary") or {}
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>{escape(payload.get("form_name"))}</title>
  <style>
    body {{ font-family: Arial, "Microsoft YaHei", sans-serif; margin: 24px; color: #172033; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border: 1px solid #d8dee8; padding: 8px; text-align: left; vertical-align: top; }}
    th {{ background: #eef2f7; }}
    code {{ font-family: Consolas, monospace; }}
  </style>
</head>
<body>
  <h1>{escape(payload.get("form_name"))}</h1>
  <p>taskId={escape(payload.get("task_id"))} | pass={escape(summary.get("match_rate"))}% | JSON=<a href="{escape(report_name)}">{escape(report_name)}</a></p>
  <table>
    <thead><tr><th>字段</th><th>接口值</th><th>网页值</th><th>状态</th><th>说明</th></tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
</body>
</html>
"""


def escape(value: Any) -> str:
    if value is None or value == "":
        return ""
    return html.escape(str(value))


def report_has_errors(report_path: Path) -> bool:
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    summary = payload.get("summary") or {}
    return any(
        int(summary.get(key, 0) or 0) > 0
        for key in (
            "mismatch_count",
            "api_missing_count",
            "web_missing_count",
            "parse_error_count",
            "mapping_error_count",
        )
    )
