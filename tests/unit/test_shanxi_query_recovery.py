"""Tests for recovering declaration query navigation from undeclared pages."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import scripts.compare_tax_forms as compare_tax_forms


class FakeContext:
    def __init__(self):
        self.pages = []

    def new_page(self):
        return FakePage("about:blank", self)


class FakePage:
    def __init__(self, url, context):
        self.url = url
        self.context = context
        self.goto_urls = []
        context.pages.append(self)

    def goto(self, url, wait_until=None, timeout=None):
        self.goto_urls.append(url)
        self.url = url

    def bring_to_front(self):
        return None


def test_undeclared_page_recovers_query_in_current_tab_before_same_page_retry():
    context = FakeContext()
    page = FakePage(
        "https://etax.shanxi.chinatax.gov.cn:8443/sbzx/view/lzsfjssb/#/declare/zzsybnsrsb?jyjkId=10",
        context,
    )
    recovered = FakePage("https://etax.shanxi.chinatax.gov.cn:8443/szzh/zhcx/sbxx/sbxxcx", context)
    calls = []

    original_wait = compare_tax_forms.wait_for_declaration_query_page
    original_recover_current = compare_tax_forms.recover_declaration_query_in_current_tab
    original_recover_fresh = compare_tax_forms.recover_declaration_query_in_fresh_tab
    original_open_digital = compare_tax_forms.open_digital_account_with_wait
    try:
        compare_tax_forms.wait_for_declaration_query_page = lambda page, host, timeout=60: None

        def fake_recover(page, host, timeout=60):
            calls.append((page.url, host, timeout))
            return recovered

        def fail_if_fresh_recovery(page, host, timeout=60):
            raise AssertionError("fresh-tab recovery should not run before current-tab recovery")

        def fail_if_same_page_retry(page, host, timeout=30):
            raise AssertionError("same-page digital-account retry should not run first")

        compare_tax_forms.recover_declaration_query_in_current_tab = fake_recover
        compare_tax_forms.recover_declaration_query_in_fresh_tab = fail_if_fresh_recovery
        compare_tax_forms.open_digital_account_with_wait = fail_if_same_page_retry

        result = compare_tax_forms.navigate_to_query_page_robust(page, web_config=object())
    finally:
        compare_tax_forms.wait_for_declaration_query_page = original_wait
        compare_tax_forms.recover_declaration_query_in_current_tab = original_recover_current
        compare_tax_forms.recover_declaration_query_in_fresh_tab = original_recover_fresh
        compare_tax_forms.open_digital_account_with_wait = original_open_digital

    assert result is recovered
    assert calls == [(page.url, "etax.shanxi.chinatax.gov.cn:8443", 60)]


def test_current_tab_recovery_resets_loginb_then_uses_portal_menu():
    context = FakeContext()
    page = FakePage(
        "https://etax.shanxi.chinatax.gov.cn:8443/sbzx/view/lzsfjssb/#/declare/zzsybnsrsb?jyjkId=10",
        context,
    )

    original_wait_portal = compare_tax_forms.wait_for_tax_portal_page
    original_find_portal = compare_tax_forms.find_context_tax_portal_page_for_host
    original_menu = compare_tax_forms.navigate_to_query_from_tax_portal
    original_sp_handler = compare_tax_forms.open_declaration_query_via_sp_handler
    try:
        compare_tax_forms.find_context_tax_portal_page_for_host = lambda candidate, host: None
        compare_tax_forms.wait_for_tax_portal_page = lambda candidate, host, timeout=30: candidate

        def fake_menu(candidate, host, timeout=60):
            return candidate

        def fail_if_sp_handler(candidate, host, timeout=60):
            raise AssertionError("spHandler should not run when portal menu navigation succeeds")

        compare_tax_forms.navigate_to_query_from_tax_portal = fake_menu
        compare_tax_forms.open_declaration_query_via_sp_handler = fail_if_sp_handler

        result = compare_tax_forms.recover_declaration_query_in_current_tab(
            page,
            "etax.shanxi.chinatax.gov.cn:8443",
            timeout=10,
        )
    finally:
        compare_tax_forms.wait_for_tax_portal_page = original_wait_portal
        compare_tax_forms.find_context_tax_portal_page_for_host = original_find_portal
        compare_tax_forms.navigate_to_query_from_tax_portal = original_menu
        compare_tax_forms.open_declaration_query_via_sp_handler = original_sp_handler

    assert result is page
    assert page.goto_urls[0] == "https://etax.shanxi.chinatax.gov.cn:8443/loginb/"


def test_fresh_tab_recovery_uses_sp_handler_deep_link():
    context = FakeContext()
    page = FakePage("https://etax.shanxi.chinatax.gov.cn:8443/loading", context)

    original_wait = compare_tax_forms.wait_for_declaration_query_page
    try:
        def fake_wait(candidate, host, timeout=60):
            if "spHandler?cdlj=/szzh/zhcx/sbxx/sbxxcx" in candidate.url:
                return candidate
            return None

        compare_tax_forms.wait_for_declaration_query_page = fake_wait

        result = compare_tax_forms.recover_declaration_query_in_fresh_tab(
            page,
            "etax.shanxi.chinatax.gov.cn:8443",
            timeout=10,
        )
    finally:
        compare_tax_forms.wait_for_declaration_query_page = original_wait

    assert result is not None
    assert result is not page
    assert result.goto_urls[0] == "https://etax.shanxi.chinatax.gov.cn:8443/loginb/"
    assert result.goto_urls[1] == (
        "https://etax.shanxi.chinatax.gov.cn:8443"
        "/szc/szzh/sjswszzh/spHandler?cdlj=/szzh/zhcx/sbxx/sbxxcx"
    )


if __name__ == "__main__":
    test_undeclared_page_recovers_query_in_current_tab_before_same_page_retry()
    test_current_tab_recovery_resets_loginb_then_uses_portal_menu()
    test_fresh_tab_recovery_uses_sp_handler_deep_link()
    print("Shanxi query recovery tests passed!")
