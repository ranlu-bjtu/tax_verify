from __future__ import annotations

import logging
from typing import Any

from playwright.sync_api import Page

from src.ydz.models import sanitize_collect_tax_type_ids

LOGGER = logging.getLogger(__name__)


class YdzApiError(RuntimeError):
    pass


class YdzApi:
    def __init__(self, page: Page) -> None:
        self.page = page

    def get_batch_list(
        self,
        tax_no: str,
        period: str,
        area_code: str = "00",
        page_now: int = 1,
        limit: int = 30,
    ) -> dict[str, Any]:
        payload = self._batch_list_payload(tax_no, period, area_code, page_now, limit)
        return self._post_json("/trans/easyacctg/query/getBatchList", payload)

    def submit_collect_task(
        self,
        tax_no: str,
        period: str,
        tenant_id: int,
        area_code: str,
        tax_type_ids: list[int],
        include_verify_collect: bool = False,
        include_invoice: bool = False,
    ) -> dict[str, Any]:
        tax_type_ids = sanitize_collect_tax_type_ids(tax_type_ids)
        payload = {
            "taskTypeCode": "020103",
            "isBatch": True,
            "period": period,
            "declareReqs": [
                {
                    "tenantId": tenant_id,
                    "taxNo": tax_no,
                    "taxiationArea": area_code,
                    "taxTypeIds": tax_type_ids,
                }
            ],
            "useDeclareData": 1,
            "cashJournal": 2,
            "nbCashJournal": 2,
            "taxCollTask": "1" if include_verify_collect else "0",
            "taxInitTask": "1",
            "invoiceTask": "1" if include_invoice else "0",
        }
        return self._post_json("/trans/easyacctg/taxReq/batchSubmitTask/020103", payload)

    def _post_json(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        self._ensure_api_context(endpoint)
        try:
            result = self.page.evaluate(
                r"""async ({endpoint, payload}) => {
                if (!location.hostname.includes('cloud.chanjet.com') || !location.pathname.includes('/work.html')) {
                    return {
                        clientError: 'Yidaizhang API context is not ready',
                        currentUrl: location.href
                    };
                }
                const prefix = location.pathname.split('/work.html')[0];
                let ws = {};
                try { ws = JSON.parse(localStorage.getItem('wsInfo') || '{}'); } catch (e) {}
                const auth = sessionStorage.getItem('iframeToken') || localStorage.getItem('ciaToken') || '';
                const userId = ws.userId || ws.UserId || '60009603684';
                const orgId = ws.orgId || ws.OrgId || '90011827608';
                const reqId = 'ydz-codex-' + Date.now() + '-' + Math.random().toString(16).slice(2);
                const sep = endpoint.includes('?') ? '&' : '?';
                const url = prefix + endpoint + sep
                    + 'user_req_id=' + encodeURIComponent(reqId)
                    + '&user_req_userid=' + encodeURIComponent(userId)
                    + '&user_req_orgid=' + encodeURIComponent(orgId);
                const controller = new AbortController();
                const timer = setTimeout(() => controller.abort(), 60000);
                try {
                    const res = await fetch(url, {
                        method: 'POST',
                        headers: {
                            'accept': 'application/json, text/plain, */*',
                            'content-type': 'application/json;charset=UTF-8',
                            'authorization': auth
                        },
                        credentials: 'include',
                        body: JSON.stringify(payload),
                        signal: controller.signal
                    });
                    const text = await res.text();
                    let data = null;
                    try { data = JSON.parse(text); } catch (e) { data = {rawText: text}; }
                    return {httpStatus: res.status, data};
                } finally {
                    clearTimeout(timer);
                }
            }""",
                {"endpoint": endpoint, "payload": payload},
            )
        except Exception as exc:
            raise YdzApiError(
                f"{endpoint} failed before HTTP response: {self._friendly_browser_error(exc)}"
            ) from exc
        client_error = result.get("clientError")
        if client_error:
            raise YdzApiError(
                f"{endpoint} failed: {client_error}; current_url={result.get('currentUrl') or self._safe_page_url()}"
            )
        http_status = int(result.get("httpStatus") or 0)
        data = result.get("data") or {}
        if http_status >= 400 or str(data.get("code")) in {"701", "500"}:
            message = data.get("msg") or data.get("message") or data.get("rootCause") or "Yidaizhang API request failed"
            raise YdzApiError(f"{endpoint} failed: http={http_status}, code={data.get('code')}, msg={message}")
        return data

    def _ensure_api_context(self, endpoint: str) -> None:
        url = self._safe_page_url()
        if "cloud.chanjet.com/ydzee/" not in url or "/work.html" not in url:
            raise YdzApiError(
                f"{endpoint} failed: Yidaizhang API context is not ready; "
                f"current_url={url}; expected cloud.chanjet.com/ydzee/.../work.html"
            )

    def _safe_page_url(self) -> str:
        try:
            return self.page.url
        except Exception:
            return "<unavailable>"

    def _friendly_browser_error(self, exc: Exception) -> str:
        text = str(exc)
        if "Failed to fetch" in text:
            return (
                "browser fetch failed; likely login state is invalid, the page is not in the "
                f"Yidaizhang cloud app, or the request was blocked; current_url={self._safe_page_url()}"
            )
        if "AbortError" in text or "aborted" in text.lower():
            return f"browser request timed out; current_url={self._safe_page_url()}"
        return f"{text}; current_url={self._safe_page_url()}"

    def _batch_list_payload(
        self,
        tax_no: str,
        period: str,
        area_code: str,
        page_now: int,
        limit: int,
    ) -> dict[str, Any]:
        return {
            "pageNow": page_now,
            "limit": limit,
            "period": period,
            "keyWord": tax_no,
            "assocTenantIds": None,
            "taxiationArea": area_code,
            "taxClaimMethodEnum": None,
            "onlyShowStatus": False,
            "hasTaxCtrl": None,
            "initCompletedTimeEnd": None,
            "hasEstimate": None,
            "cDeclStatusEnum": None,
            "cPayStatusEnum": None,
            "paymentTypeEnumList": [],
            "paidTaxDiffEnum": None,
            "label": None,
            "taxPreparerMobile": None,
            "taxPreparerIdentityEnum": None,
            "fiClosed": None,
            "isZzsDqdeCorrect": None,
            "enterpriseFormEnumList": None,
            "taxpayerTypeEnum": None,
            "initStatusEnumList": None,
            "taxCheckStatusEnumList": None,
            "contrastStatusEnumList": None,
            "hasTaxAmount": None,
            "hasCTaxAmount": None,
            "salesChannelEnumList": None,
            "taxAmountExamineEnumList": None,
            "cDeclDlStatusEnumList": None,
            "loginMethodEnumList": None,
            "invState": None,
            "deliveryStatusList": None,
            "isWeComBind": None,
            "compOfThreeTbList": None,
            "cPayTaxesDlStatusEnumList": None,
            "bureauDeclStatusEnumList": None,
            "bureauPayStatusEnumList": None,
            "detailList": [],
            "tagList": None,
            "taxAreaIdList": None,
        }
