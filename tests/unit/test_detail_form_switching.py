import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import scripts.compare_tax_forms as compare_tax_forms  # noqa: E402
from scripts.compare_tax_forms import (
    TARGETS,
    can_switch_detail_form_between,
    confirm_target_page_for_evidence,
    ensure_supported_declaration_flow,
    extract_expected_tax_no,
    find_existing_tax_page,
    find_context_undeclared_entry_page,
    is_expected_undeclared_entry_url,
    select_target_content_scope,
    target_selection_keywords,
    target_period_range,
    target_title_keywords,
    undeclared_entry_urls,
    UNDECLARED_VAT_MENU_KEYWORDS,
)


class FakeFrame:
    def __init__(self, url, text):
        self.url = url
        self._text = text

    def evaluate(self, _script, *args):
        return self._text


class FakePage:
    def __init__(self, url, text, selected=True, frames=None):
        self.url = url
        self._text = text
        self._selected = selected
        self.frames = frames or []
        self.main_frame = None

    def evaluate(self, _script, *args):
        if args:
            return self._selected
        return self._text


class FakeSnippetPage(FakePage):
    def evaluate(self, _script, *args):
        return self._text


class FakeGotoSnippetPage(FakeSnippetPage):
    def __init__(self, url, text):
        super().__init__(url, text)
        self.clicked = False

    def goto(self, _url, **_kwargs):
        return None

    def evaluate(self, script, *args):
        if "async (payload)" in str(script):
            self.clicked = True
            return "entry_not_found"
        return self._text


class FakeContext:
    def __init__(self, pages):
        self.pages = pages


class FakeContextPage(FakePage):
    def __init__(self, url, text, selected=True, frames=None):
        super().__init__(url, text, selected=selected, frames=frames)
        self.context = FakeContext([self])


class FakeBrowserManager:
    def __init__(self, pages):
        self._pages = pages

    def get_all_pages(self):
        return self._pages


class FakeUndeclaredFormPage:
    url = "https://etax.shandong.chinatax.gov.cn:8443/sbzx/view/lzsfjssb/#/declare/zzsybnsrsb"

    def evaluate(self, _script, *args):
        return "already_form_view"


class FakeTpassLoginPage:
    url = "https://tpass.shandong.chinatax.gov.cn:8443/#/login?redirect_uri=https%3A%2F%2Fetax.shandong.chinatax.gov.cn"

    def __init__(self):
        self.context = FakeContext([self])

    def evaluate(self, _script, *args):
        return "fill_button_not_found"


class FakeTaxHomeWithoutTargetPage:
    url = "https://etax.shandong.chinatax.gov.cn:8443/loginb/"

    def __init__(self):
        self.context = FakeContext([self])

    def evaluate(self, _script, *args):
        return "fill_button_not_found"


class FakeTaxAuthCodeErrorPage:
    url = "https://etax.yunnan.chinatax.gov.cn:8443/mhzx/api/mh/tpass/code"

    def __init__(self):
        self.context = FakeContext([self])

    def evaluate(self, _script, *args):
        if args:
            return "fill_button_not_found"
        return '{"code":2997,"msg":"授权码不能为空！"}'


class FakeUndeclaredRedirectToTpassPage:
    url = "https://etax.shandong.chinatax.gov.cn:8443/loginb/"

    def __init__(self):
        self.context = FakeContext([self])

    def goto(self, _url, **_kwargs):
        self.url = "https://tpass.shandong.chinatax.gov.cn:8443/#/login?redirect_uri=https%3A%2F%2Fetax.shandong.chinatax.gov.cn"

    def evaluate(self, _script, *args):
        return ""


def test_can_switch_between_vat_general_appendices():
    assert can_switch_detail_form_between(
        TARGETS["vat_general_appendix1"],
        TARGETS["vat_general_appendix2"],
    )


def test_does_not_switch_between_different_tax_types():
    assert not can_switch_detail_form_between(
        TARGETS["vat_general_appendix1"],
        TARGETS["culture_fee_main"],
    )


def test_does_not_switch_when_current_target_has_no_detail_selector():
    target = replace(TARGETS["vat_general_appendix2"], detail_form_keywords=())

    assert not can_switch_detail_form_between(TARGETS["vat_general_appendix1"], target)


def test_existing_tax_page_requires_matching_tax_no():
    stale_portal_page = FakePage(
        "https://etax.henan.chinatax.gov.cn:8443/loginb/",
        "我要查询 纳税人识别号 91410105MACWB5X52Y",
    )
    target_page = FakePage(
        "https://etax.henan.chinatax.gov.cn:8443/szzh/zhcx/sbxx/sbxxcxxq?isCyqy=false",
        "申报信息查询详情 主附表表单 纳税人识别号 91410105MACWB5X52Y",
    )
    other_page = FakePage(
        "https://etax.henan.chinatax.gov.cn:8443/szzh/zhcx/sbxx/sbxxcx/detail?isCyqy=false",
        "我要查询 91410307MADPHCRK4E",
    )
    bm = FakeBrowserManager([other_page, stale_portal_page, target_page])

    assert find_existing_tax_page(bm, "henan", "91410105MACWB5X52Y") is target_page
    assert find_existing_tax_page(bm, "henan", "911111111111111111") is None


def test_existing_tax_page_does_not_reuse_loading_page():
    loading_page = FakePage(
        "https://etax.henan.chinatax.gov.cn:8443/loading",
        "纳税人识别号 91410300MA4664Q680",
    )
    bm = FakeBrowserManager([loading_page])

    assert find_existing_tax_page(bm, "henan", "91410300MA4664Q680") is None


def test_extract_expected_tax_no_from_api_param_json():
    payload = {
        "paramJson": {
            "province": "henan",
            "taxNo": "91410105MACWB5X52Y",
            "cookies": {"user_info": {"tax_no": "should-not-win"}},
        }
    }

    assert extract_expected_tax_no(payload) == "91410105MACWB5X52Y"


def test_extract_expected_tax_no_from_cookie_user_info():
    payload = {"paramJson": {"cookies": {"user_info": {"tax_no": "91410307MADPHCRK4E"}}}}

    assert extract_expected_tax_no(payload) == "91410307MADPHCRK4E"


def test_supported_unfiled_tax_types_are_not_blocked():
    for target_id in (
        "vat_small_main",
        "cit_a_main",
        "culture_fee_main",
        "consumption_tax_main",
    ):
        ensure_supported_declaration_flow(TARGETS[target_id], False)


def test_culture_fee_unfiled_url_uses_target_period():
    api_response = {
        "paramJson": {
            "numberData": [
                {
                    "name": "文化事业建设费申报表",
                    "pzzlDm": "BDA0610334",
                    "skssqq": "2026-05-01",
                    "skssqz": "2026-05-31",
                }
            ]
        }
    }
    target = TARGETS["culture_fee_main"]

    assert target_period_range(api_response, target) == ("2026-05-01", "2026-05-31")
    urls = undeclared_entry_urls(
        None,
        "shandong",
        target,
        api_response,
        fallback_origin="https://etax.shandong.chinatax.gov.cn:8443",
    )

    assert urls == [
        "https://etax.shandong.chinatax.gov.cn:8443/sbzx/view/sdsfsgjssb/#/yyzx/whsyjsf/tb/yssb?SssqQ=2026-05-01&SssqZ=2026-05-31&ZspmDmList=302170200"
    ]


def test_culture_fee_does_not_reuse_vat_undeclared_url():
    assert is_expected_undeclared_entry_url(
        "https://etax.shandong.chinatax.gov.cn:8443/sbzx/view/lzsfjssb/#/declare/zzsybnsrsb?jyjkId=10",
        TARGETS["culture_fee_main"],
    ) is False


def test_consumption_tax_undeclared_url_is_recognized():
    assert is_expected_undeclared_entry_url(
        "https://etax.shandong.chinatax.gov.cn:8443/sbzx/view/lzsfjssb/#/declare/xfssb?jyjkId=30",
        TARGETS["consumption_tax_main"],
    ) is True


def test_vat_small_undeclared_url_uses_small_scale_route():
    urls = undeclared_entry_urls(
        None,
        "jiangxi",
        TARGETS["vat_small_main"],
        {},
        fallback_origin="https://etax.jiangxi.chinatax.gov.cn:8443",
    )

    assert urls == [
        "https://etax.jiangxi.chinatax.gov.cn:8443/sbzx/view/lzsfjssb/#/declare/zzsxgmnsrsb?jyjkId=10"
    ]
    assert is_expected_undeclared_entry_url(urls[0], TARGETS["vat_small_main"]) is True
    assert (
        is_expected_undeclared_entry_url(
            "https://etax.jiangxi.chinatax.gov.cn:8443/sbzx/view/lzsfjssb/#/declare/zzsybnsrsb?jyjkId=10",
            TARGETS["vat_small_main"],
        )
        is False
    )


def test_find_context_undeclared_consumption_tax_page_after_home_click():
    home = FakeContextPage(
        "https://etax.shandong.chinatax.gov.cn:8443/loginb/",
        "本期应申报 消费税及附加税费申报 填写申报表",
    )
    consumption_page = FakeContextPage(
        "https://etax.shandong.chinatax.gov.cn:8443/sbzx/view/lzsfjssb/#/declare/xfssb?jyjkId=30",
        "报表列表 消费税及附加税费申报表 消费税附加税费计算表",
    )
    home.context = FakeContext([home, consumption_page])
    consumption_page.context = home.context

    assert find_context_undeclared_entry_page(home, TARGETS["consumption_tax_main"]) is consumption_page


def test_cit_undeclared_home_keywords_match_jiangsu_hot_service_entry():
    text = "热门服务 居民企业（查账征收）企业所... 财务报表报送及更正"

    assert compare_tax_forms.text_matches_keyword_groups(
        text,
        compare_tax_forms.undeclared_home_target_keyword_groups(TARGETS["cit_a_main"]),
    )


def test_cit_home_status_does_not_inherit_previous_vat_filed_status():
    page = FakeSnippetPage(
        "https://etax.jiangsu.chinatax.gov.cn:8443/loginb/",
        (
            "本期应申报 事项名称 操作 "
            "增值税及附加税费申报（一般纳税人适用） 已申报 更正作废 "
            "热门服务 居民企业（查账征收）企业所... 财务报表报送及更正"
        ),
    )

    assert compare_tax_forms.undeclared_home_target_declaration_status(page, TARGETS["cit_a_main"]) == ""


def test_cit_hot_service_only_is_not_undeclared_home_redirect():
    page = FakeSnippetPage(
        "https://etax.jiangsu.chinatax.gov.cn:8443/loginb/",
        (
            "\u672c\u671f\u5e94\u7533\u62a5 "
            "\u589e\u503c\u7a0e\u53ca\u9644\u52a0\u7a0e\u8d39\u7533\u62a5 \u672a\u7533\u62a5 \u586b\u5199\u7533\u62a5\u8868 "
            "\u70ed\u95e8\u670d\u52a1 "
            "\u5c45\u6c11\u4f01\u4e1a\uff08\u67e5\u8d26\u5f81\u6536\uff09\u4f01\u4e1a\u6240\u5f97\u7a0e "
            "\u8d22\u52a1\u62a5\u8868\u62a5\u9001\u53ca\u66f4\u6b63"
        ),
    )

    assert compare_tax_forms.is_undeclared_home_redirect_page(page, TARGETS["cit_a_main"]) is False


def test_cit_hot_service_only_prepare_fails_without_button_polling():
    page = FakeSnippetPage(
        "https://etax.guangdong.chinatax.gov.cn:8443/loginb/",
        (
            "\u672c\u671f\u5e94\u7533\u62a5 \u6682\u65e0\u6570\u636e "
            "\u70ed\u95e8\u670d\u52a1 "
            "\u5c45\u6c11\u4f01\u4e1a\uff08\u67e5\u8d26\u5f81\u6536\uff09\u4f01\u4e1a\u6240\u5f97\u7a0e "
            "\u8d22\u52a1\u62a5\u8868\u62a5\u9001\u53ca\u66f4\u6b63"
        ),
    )

    try:
        compare_tax_forms.prepare_undeclared_page_for_target(page, TARGETS["cit_a_main"])
    except compare_tax_forms.UndeclaredTaxTargetUnavailableError as exc:
        assert "cit_a_main" in str(exc)
    else:
        raise AssertionError("expected UndeclaredTaxTargetUnavailableError")


def test_cit_hot_service_only_navigation_fails_before_clicking():
    page = FakeGotoSnippetPage(
        "https://etax.guangdong.chinatax.gov.cn:8443/loginb/",
        (
            "\u672c\u671f\u5e94\u7533\u62a5 \u6682\u65e0\u6570\u636e "
            "\u70ed\u95e8\u670d\u52a1 "
            "\u5c45\u6c11\u4f01\u4e1a\uff08\u67e5\u8d26\u5f81\u6536\uff09\u4f01\u4e1a\u6240\u5f97\u7a0e "
            "\u8d22\u52a1\u62a5\u8868\u62a5\u9001\u53ca\u66f4\u6b63"
        ),
    )
    original_sleep = compare_tax_forms.time.sleep
    try:
        compare_tax_forms.time.sleep = lambda _seconds: None
        try:
            compare_tax_forms.navigate_to_undeclared_tax_page_from_home(
                page,
                "guangdong",
                TARGETS["cit_a_main"],
            )
        except compare_tax_forms.UndeclaredTaxTargetUnavailableError:
            pass
        else:
            raise AssertionError("expected UndeclaredTaxTargetUnavailableError")
    finally:
        compare_tax_forms.time.sleep = original_sleep

    assert page.clicked is False


def test_cit_a_declare_scope_is_undeclared_home_redirect():
    page = FakeSnippetPage(
        "https://etax.jiangsu.chinatax.gov.cn:8443/loginb/",
        (
            "\u672c\u671f\u5e94\u7533\u62a5 "
            "\u5c45\u6c11\u4f01\u4e1a\uff08\u67e5\u8d26\u5f81\u6536\uff09\u4f01\u4e1a\u6240\u5f97\u7a0e "
            "\u672a\u7533\u62a5 \u586b\u5199\u7533\u62a5\u8868 "
            "\u70ed\u95e8\u670d\u52a1 \u53d1\u7968\u4e1a\u52a1"
        ),
    )

    assert compare_tax_forms.is_undeclared_home_redirect_page(page, TARGETS["cit_a_main"]) is True
    assert compare_tax_forms.undeclared_home_target_declaration_status(page, TARGETS["cit_a_main"]) == "unfiled"


def test_cit_b_class_declare_scope_is_not_cit_a_home_redirect():
    page = FakeSnippetPage(
        "https://etax.jiangxi.chinatax.gov.cn:8443/loginb/",
        (
            "\u672c\u671f\u5e94\u7533\u62a5 "
            "\u5c45\u6c11\u4f01\u4e1a\uff08\u6838\u5b9a\u5f81\u6536\uff09\u4f01\u4e1a\u6240\u5f97\u7a0eB\u7c7b "
            "\u672a\u7533\u62a5 \u586b\u5199\u7533\u62a5\u8868 "
            "\u70ed\u95e8\u670d\u52a1 \u4f01\u4e1a\u6240\u5f97\u7a0eA\u7c7b"
        ),
    )

    assert compare_tax_forms.is_undeclared_home_redirect_page(page, TARGETS["cit_a_main"]) is False
    assert compare_tax_forms.undeclared_home_target_declaration_status(page, TARGETS["cit_a_main"]) == ""


def test_shandong_vat_home_redirect_is_detected():
    page = FakeSnippetPage(
        "https://etax.shandong.chinatax.gov.cn:8443/loginb/",
        (
            "\u672c\u671f\u5e94\u7533\u62a5 3 "
            "\u586b\u5199\u7533\u62a5\u8868 "
            "\u589e\u503c\u7a0e\u53ca\u9644\u52a0\u7a0e\u8d39\u7533\u62a5\uff08\u4e00\u822c..."
        ),
    )

    assert compare_tax_forms.is_undeclared_home_redirect_page(page, TARGETS["vat_general_main"]) is True


def test_tax_home_target_status_detects_consumption_tax_already_declared():
    page = FakeSnippetPage(
        "https://etax.shaanxi.chinatax.gov.cn/loginb/",
        (
            "\u672c\u671f\u5e94\u7533\u62a5 "
            "\u6d88\u8d39\u7a0e\u53ca\u9644\u52a0\u7a0e\u8d39\u7533\u62a5 "
            "2026-06-15 \u5df2\u7533\u62a5 \u66f4\u6b63\\\u4f5c\u5e9f "
            "\u6b8b\u75be\u4eba\u5c31\u4e1a\u4fdd\u969c\u91d1\u7533\u62a5"
        ),
    )

    assert (
        compare_tax_forms.undeclared_home_target_declaration_status(
            page,
            TARGETS["consumption_tax_main"],
        )
        == "filed"
    )


def test_tax_home_scoped_click_blocks_progress_query_fallback():
    source = Path(compare_tax_forms.__file__).read_text(encoding="utf-8")
    start = source.index("def click_tax_home_declare_entry_scoped")
    end = source.index("def prepare_undeclared_page_for_target", start)
    scoped_click_source = source[start:end]

    assert "\\\\u529e\\\\u7a0e\\\\u8fdb\\\\u5ea6\\\\u53ca\\\\u7ed3\\\\u679c\\\\u4fe1\\\\u606f\\\\u67e5\\\\u8be2" in scoped_click_source
    assert "rootScope" in scoped_click_source
    assert "target_title" in scoped_click_source
    assert "target_action" in scoped_click_source
    assert "fallback:${clickElement(fallbackAction)}" not in scoped_click_source


def test_tax_home_scoped_click_does_not_repeat_target_action_in_one_evaluation():
    source = Path(compare_tax_forms.__file__).read_text(encoding="utf-8")
    start = source.index("def click_tax_home_declare_entry_scoped")
    end = source.index("def prepare_undeclared_page_for_target", start)
    scoped_click_source = source[start:end]

    assert "scopedClickCount" not in scoped_click_source
    assert "clickScopedTargetAction(true)" in scoped_click_source


def test_tax_home_scoped_click_checks_target_before_navigation_steps():
    source = Path(compare_tax_forms.__file__).read_text(encoding="utf-8")
    start = source.index("def click_tax_home_declare_entry_scoped")
    end = source.index("def prepare_undeclared_page_for_target", start)
    scoped_click_source = source[start:end]

    assert scoped_click_source.index("const firstTargetText") < scoped_click_source.index("const navSteps")


def test_home_recovery_retries_after_target_title_click():
    page = FakeSnippetPage(
        "https://etax.tianjin.chinatax.gov.cn:8443/loginb/",
        "本期应申报 增值税及附加税费申报表（一般纳税人适用） 未申报 办理",
    )
    page.context = FakeContext([page])
    recovered_page = FakeUndeclaredFormPage()
    calls = []
    original_click = compare_tax_forms.click_tax_home_declare_entry_scoped
    original_wait = compare_tax_forms.wait_for_undeclared_entry_page
    original_sleep = compare_tax_forms.time.sleep
    try:
        def fake_click(_page, _target):
            calls.append("click")
            return "clicked:target_title:增值税及附加税费申报表" if len(calls) == 1 else "clicked:target_action:办理"

        def fake_wait(_page, _target, timeout=10):
            calls.append(f"wait:{timeout}")
            return recovered_page if len([item for item in calls if item == "click"]) >= 2 else None

        compare_tax_forms.click_tax_home_declare_entry_scoped = fake_click
        compare_tax_forms.wait_for_undeclared_entry_page = fake_wait
        compare_tax_forms.time.sleep = lambda _seconds: None

        result = compare_tax_forms.recover_undeclared_entry_from_home_redirect(page, TARGETS["vat_general_main"])
    finally:
        compare_tax_forms.click_tax_home_declare_entry_scoped = original_click
        compare_tax_forms.wait_for_undeclared_entry_page = original_wait
        compare_tax_forms.time.sleep = original_sleep

    assert result is recovered_page
    assert calls == ["click", "wait:8", "click", "wait:8"]


def test_home_recovery_stops_after_repeated_target_click_result():
    page = FakeSnippetPage(
        "https://etax.beijing.chinatax.gov.cn:8443/loginb/",
        (
            "\u672c\u671f\u5e94\u7533\u62a5 "
            "\u589e\u503c\u7a0e\u53ca\u9644\u52a0\u7a0e\u8d39\u7533\u62a5"
            "\uff08\u4e00\u822c\u7eb3\u7a0e\u4eba\u9002\u7528\uff09 "
            "\u672a\u7533\u62a5 \u586b\u5199\u7533\u62a5\u8868"
        ),
    )
    page.context = FakeContext([page])
    calls = []
    original_click = compare_tax_forms.click_tax_home_declare_entry_scoped
    original_wait = compare_tax_forms.wait_for_undeclared_entry_page
    original_sleep = compare_tax_forms.time.sleep
    try:
        def fake_click(_page, _target):
            calls.append("click")
            return "clicked:target_action:\u586b\u5199\u7533\u62a5\u8868"

        def fake_wait(_page, _target, timeout=10):
            calls.append(f"wait:{timeout}")
            return None

        compare_tax_forms.click_tax_home_declare_entry_scoped = fake_click
        compare_tax_forms.wait_for_undeclared_entry_page = fake_wait
        compare_tax_forms.time.sleep = lambda _seconds: None

        result = compare_tax_forms.recover_undeclared_entry_from_home_redirect(page, TARGETS["vat_general_main"])
    finally:
        compare_tax_forms.click_tax_home_declare_entry_scoped = original_click
        compare_tax_forms.wait_for_undeclared_entry_page = original_wait
        compare_tax_forms.time.sleep = original_sleep

    assert result is None
    assert calls == ["click", "wait:8", "click", "wait:8"]


def test_click_declaration_row_uses_safe_detail_button_keywords():
    source = Path(compare_tax_forms.__file__).read_text(encoding="utf-8")
    start = source.index("def click_declaration_row_once")
    end = source.index("def select_detail_form", start)
    click_source = source[start:end]

    assert "\\u3000\\u0028\\u0029\\uff08\\uff09" in click_source
    assert "锛堬級" not in click_source
    assert "detailKeywords = ['\\u67e5\\u770b'" in click_source
    assert "const detail = buttons.find((el) => /(" not in click_source


def test_consumption_tax_main_selection_requires_child_main_menu():
    target = TARGETS["consumption_tax_main"]
    menu_keywords = UNDECLARED_VAT_MENU_KEYWORDS[target.target_id]

    assert target_title_keywords(target, menu_keywords) == ("消费税及附加税费申报表",)
    assert target_selection_keywords(target, menu_keywords) == ("消费税及附加税费申报表", "主表")


def test_confirm_undeclared_vat_accepts_active_target():
    page = FakePage(
        "https://etax.hebei.chinatax.gov.cn:8443/sbzx/view/lzsfjssb/#/declare/zzsybnsrsb",
        "增值税及附加税费申报表附列资料（一）（本期销售情况明细）",
        selected=True,
    )

    confirm_target_page_for_evidence(page, TARGETS["vat_general_appendix1"], [], False)


def test_confirm_undeclared_vat_rejects_active_menu_with_wrong_body():
    page = FakePage(
        "https://etax.hebei.chinatax.gov.cn:8443/sbzx/view/lzsfjssb/#/declare/zzsybnsrsb",
        "增值税及附加税费申报表（一般纳税人适用）",
        selected=True,
    )

    try:
        confirm_target_page_for_evidence(page, TARGETS["vat_general_appendix1"], [], False)
    except RuntimeError as exc:
        assert "Target page was not confirmed" in str(exc)
    else:
        raise AssertionError("Expected active menu with wrong body to fail")


def test_confirm_undeclared_vat_rejects_unconfirmed_target():
    page = FakePage(
        "https://etax.hebei.chinatax.gov.cn:8443/sbzx/view/lzsfjssb/#/declare/zzsybnsrsb",
        "增值税及附加税费申报表附列资料（一）（本期销售情况明细）",
        selected=False,
    )

    try:
        confirm_target_page_for_evidence(page, TARGETS["vat_general_appendix1"], [], False)
    except RuntimeError as exc:
        assert "Target page was not confirmed" in str(exc)
    else:
        raise AssertionError("Expected unconfirmed undeclared VAT target to fail")


def test_confirm_undeclared_vat_accepts_visible_body_with_business_fields_without_active_menu():
    target = TARGETS["vat_general_appendix1"]
    menu_keywords = UNDECLARED_VAT_MENU_KEYWORDS[target.target_id]
    page = FakePage(
        "https://etax.shandong.chinatax.gov.cn:8443/sbzx/view/lzsfjssb/#/declare/zzsybnsrsb",
        " ".join(target_title_keywords(target, menu_keywords)),
        selected=False,
    )
    original_count_business_fields = compare_tax_forms.count_business_fields
    try:
        compare_tax_forms.count_business_fields = lambda *_args, **_kwargs: 10
        confirm_target_page_for_evidence(page, target, [object()] * 80, False)
    finally:
        compare_tax_forms.count_business_fields = original_count_business_fields


def test_confirm_undeclared_vat_accepts_business_field_fallback():
    original_target_content_visible = compare_tax_forms.target_content_visible_in_any_scope
    original_count_business_fields = compare_tax_forms.count_business_fields
    try:
        compare_tax_forms.target_content_visible_in_any_scope = lambda *_args, **_kwargs: False
        compare_tax_forms.count_business_fields = lambda *_args, **_kwargs: 10
        page = FakePage(
            "https://etax.jiangxi.chinatax.gov.cn:8443/sbzx/view/lzsfjssb/#/declare/zzsxgmnsrsb?jyjkId=10",
            "报表列表 主表 增值税及附加税费申报表",
            selected=True,
        )

        confirm_target_page_for_evidence(page, TARGETS["vat_small_main"], [object()] * 40, False)
    finally:
        compare_tax_forms.target_content_visible_in_any_scope = original_target_content_visible
        compare_tax_forms.count_business_fields = original_count_business_fields


def test_confirm_undeclared_consumption_tax_accepts_active_target():
    page = FakePage(
        "https://etax.shandong.chinatax.gov.cn:8443/sbzx/view/lzsfjssb/#/declare/zzsybnsrsb",
        "消费税及附加税费申报表 本期销售额 本期应纳税额",
        selected=True,
    )

    confirm_target_page_for_evidence(page, TARGETS["consumption_tax_main"], [], False)


def test_confirm_undeclared_consumption_tax_accepts_visible_content_without_active_menu():
    page = FakePage(
        "https://etax.shandong.chinatax.gov.cn:8443/sbzx/view/lzsfjssb/#/declare/xfssb?jyjkId=30",
        "消费税附加税费计算表 城市维护建设税 教育费附加 地方教育附加 本期应补",
        selected=False,
    )
    original_count_business_fields = compare_tax_forms.count_business_fields
    try:
        compare_tax_forms.count_business_fields = lambda *_args, **_kwargs: 8
        confirm_target_page_for_evidence(
            page,
            TARGETS["consumption_tax_surcharge"],
            [object()] * 32,
            False,
        )
    finally:
        compare_tax_forms.count_business_fields = original_count_business_fields


def test_confirm_undeclared_culture_fee_accepts_embedded_form():
    frame = FakeFrame(
        "https://etax.shandong.chinatax.gov.cn:8443/static/sb/whsyjsf/form/whsyjsf_BDA0610334ggy.html",
        "文化事业建设费申报表 申报缴费信息 计费收入 本月（期）数 本年累计",
    )
    page = FakePage(
        "https://etax.shandong.chinatax.gov.cn:8443/sbzx/view/sdsfsgjssb/#/yyzx/whsyjsf/tb/iframe",
        "文化事业建设费申报 提交申报 延续 结束",
        selected=False,
        frames=[frame],
    )

    assert select_target_content_scope(page, TARGETS["culture_fee_main"], []) is frame
    confirm_target_page_for_evidence(page, TARGETS["culture_fee_main"], [], False)


def test_undeclared_vat_general_appendix1_body_title_confirms_target_visible():
    page = FakePage(
        "https://etax.shandong.chinatax.gov.cn:8443/sbzx/view/lzsfjssb/#/declare/zzsybnsrsb?jyjkId=10",
        "\u589e\u503c\u7a0e\u7eb3\u7a0e\u7533\u62a5\u8868\u9644\u5217\u8d44\u6599\uff08\u4e00\uff09 "
        "\uff08\u672c\u671f\u9500\u552e\u60c5\u51b5\u660e\u7ec6\uff09 "
        "\u9879\u76ee\u53ca\u680f\u6b21 \u5f00\u5177\u589e\u503c\u7a0e\u4e13\u7528\u53d1\u7968",
        selected=False,
    )

    assert compare_tax_forms.target_content_visible_in_any_scope(
        page,
        TARGETS["vat_general_appendix1"],
        [],
        UNDECLARED_VAT_MENU_KEYWORDS["vat_general_appendix1"],
    )


def test_prepare_undeclared_appendix_accepts_clicked_menu_without_extra_wait():
    calls = []
    original_target_content_visible = compare_tax_forms.target_content_visible_in_any_scope
    original_select_menu = compare_tax_forms.select_undeclared_vat_menu_item
    original_wait_visible = compare_tax_forms.wait_for_undeclared_target_visible
    original_dismiss = compare_tax_forms.dismiss_known_undeclared_info_dialogs
    original_sleep = compare_tax_forms.time.sleep
    try:
        compare_tax_forms.target_content_visible_in_any_scope = lambda *_args, **_kwargs: False
        compare_tax_forms.select_undeclared_vat_menu_item = (
            lambda *_args, **_kwargs: calls.append("select") or "clicked_menu_item"
        )
        compare_tax_forms.wait_for_undeclared_target_visible = lambda *_args, **_kwargs: calls.append("wait") or True
        compare_tax_forms.dismiss_known_undeclared_info_dialogs = lambda *_args, **_kwargs: ""
        compare_tax_forms.time.sleep = lambda _seconds: None

        compare_tax_forms.prepare_undeclared_page_for_target(
            FakeUndeclaredFormPage(),
            TARGETS["vat_general_appendix2"],
            [],
        )
    finally:
        compare_tax_forms.target_content_visible_in_any_scope = original_target_content_visible
        compare_tax_forms.select_undeclared_vat_menu_item = original_select_menu
        compare_tax_forms.wait_for_undeclared_target_visible = original_wait_visible
        compare_tax_forms.dismiss_known_undeclared_info_dialogs = original_dismiss
        compare_tax_forms.time.sleep = original_sleep

    assert calls == ["select"]


def test_confirm_undeclared_appendix_accepts_recent_clicked_menu_marker():
    page = FakeUndeclaredFormPage()
    target = TARGETS["vat_general_appendix1"]

    compare_tax_forms.mark_recent_undeclared_menu_target(page, target)

    compare_tax_forms.confirm_target_page_for_evidence(page, target, [], False)


def test_prepare_undeclared_page_returns_page_when_target_already_visible():
    original_target_content_visible = compare_tax_forms.target_content_visible_in_any_scope
    original_dismiss = compare_tax_forms.dismiss_known_undeclared_info_dialogs
    original_sleep = compare_tax_forms.time.sleep
    try:
        compare_tax_forms.target_content_visible_in_any_scope = lambda *_args, **_kwargs: True
        compare_tax_forms.dismiss_known_undeclared_info_dialogs = lambda *_args, **_kwargs: ""
        compare_tax_forms.time.sleep = lambda _seconds: None

        page = FakeUndeclaredFormPage()
        page.context = FakeContext([page])

        assert (
            compare_tax_forms.prepare_undeclared_page_for_target(
                page,
                TARGETS["consumption_tax_main"],
                [],
            )
            is page
        )
    finally:
        compare_tax_forms.target_content_visible_in_any_scope = original_target_content_visible
        compare_tax_forms.dismiss_known_undeclared_info_dialogs = original_dismiss
        compare_tax_forms.time.sleep = original_sleep


def test_prepare_undeclared_page_recovers_when_menu_selection_returns_home():
    calls = []
    original_target_content_visible = compare_tax_forms.target_content_visible_in_any_scope
    original_select_menu = compare_tax_forms.select_undeclared_vat_menu_item
    original_wait_visible = compare_tax_forms.wait_for_undeclared_target_visible
    original_recover = compare_tax_forms.recover_undeclared_entry_from_home_redirect
    original_dismiss = compare_tax_forms.dismiss_known_undeclared_info_dialogs
    original_sleep = compare_tax_forms.time.sleep
    recovered_page = FakeUndeclaredFormPage()
    try:
        compare_tax_forms.target_content_visible_in_any_scope = (
            lambda page, *_args, **_kwargs: page is recovered_page
        )
        compare_tax_forms.select_undeclared_vat_menu_item = (
            lambda *_args, **_kwargs: calls.append("select") or "menu_item_not_found"
        )
        compare_tax_forms.wait_for_undeclared_target_visible = lambda *_args, **_kwargs: calls.append("wait") or True
        compare_tax_forms.recover_undeclared_entry_from_home_redirect = (
            lambda *_args, **_kwargs: calls.append("recover") or recovered_page
        )
        compare_tax_forms.dismiss_known_undeclared_info_dialogs = lambda *_args, **_kwargs: ""
        compare_tax_forms.time.sleep = lambda _seconds: None

        result = compare_tax_forms.prepare_undeclared_page_for_target(
            FakeUndeclaredFormPage(),
            TARGETS["vat_general_main"],
            [],
        )
    finally:
        compare_tax_forms.target_content_visible_in_any_scope = original_target_content_visible
        compare_tax_forms.select_undeclared_vat_menu_item = original_select_menu
        compare_tax_forms.wait_for_undeclared_target_visible = original_wait_visible
        compare_tax_forms.recover_undeclared_entry_from_home_redirect = original_recover
        compare_tax_forms.dismiss_known_undeclared_info_dialogs = original_dismiss
        compare_tax_forms.time.sleep = original_sleep

    assert result is recovered_page
    assert calls == ["select", "recover"]


def test_prepare_undeclared_page_recovers_from_home_before_menu_wait():
    calls = []
    original_target_content_visible = compare_tax_forms.target_content_visible_in_any_scope
    original_select_menu = compare_tax_forms.select_undeclared_vat_menu_item
    original_recover = compare_tax_forms.recover_undeclared_entry_from_home_redirect
    original_is_home_redirect = compare_tax_forms.is_undeclared_home_redirect_page
    original_dismiss = compare_tax_forms.dismiss_known_undeclared_info_dialogs
    original_sleep = compare_tax_forms.time.sleep
    page = FakeUndeclaredFormPage()
    page.context = FakeContext([page])
    recovered_page = FakeUndeclaredFormPage()
    recovered_page.context = FakeContext([recovered_page])
    try:
        compare_tax_forms.target_content_visible_in_any_scope = (
            lambda candidate, *_args, **_kwargs: candidate is recovered_page
        )
        compare_tax_forms.select_undeclared_vat_menu_item = (
            lambda *_args, **_kwargs: calls.append("select") or "menu_item_not_found"
        )
        compare_tax_forms.recover_undeclared_entry_from_home_redirect = (
            lambda *_args, **_kwargs: calls.append("recover") or recovered_page
        )
        compare_tax_forms.is_undeclared_home_redirect_page = (
            lambda candidate, _target: candidate is page
        )
        compare_tax_forms.dismiss_known_undeclared_info_dialogs = lambda *_args, **_kwargs: ""
        compare_tax_forms.time.sleep = lambda _seconds: None

        result = compare_tax_forms.prepare_undeclared_page_for_target(
            page,
            TARGETS["vat_general_main"],
            [],
        )
    finally:
        compare_tax_forms.target_content_visible_in_any_scope = original_target_content_visible
        compare_tax_forms.select_undeclared_vat_menu_item = original_select_menu
        compare_tax_forms.recover_undeclared_entry_from_home_redirect = original_recover
        compare_tax_forms.is_undeclared_home_redirect_page = original_is_home_redirect
        compare_tax_forms.dismiss_known_undeclared_info_dialogs = original_dismiss
        compare_tax_forms.time.sleep = original_sleep

    assert result is recovered_page
    assert calls == ["recover"]


def test_prepare_undeclared_page_recovers_from_home_before_fill_wait():
    calls = []
    original_target_content_visible = compare_tax_forms.target_content_visible_in_any_scope
    original_recover = compare_tax_forms.recover_undeclared_entry_from_home_redirect
    original_is_home_redirect = compare_tax_forms.is_undeclared_home_redirect_page
    original_dismiss = compare_tax_forms.dismiss_known_undeclared_info_dialogs
    original_sleep = compare_tax_forms.time.sleep
    page = FakeSnippetPage(
        "https://etax.jiangsu.chinatax.gov.cn:8443/loginb/",
        "\u672c\u671f\u5e94\u7533\u62a5 \u70ed\u95e8\u670d\u52a1 \u5c45\u6c11\u4f01\u4e1a\uff08\u67e5\u8d26\u5f81\u6536\uff09\u4f01\u4e1a\u6240...",
    )
    page.context = FakeContext([page])
    recovered_page = FakeUndeclaredFormPage()
    recovered_page.context = FakeContext([recovered_page])
    try:
        compare_tax_forms.target_content_visible_in_any_scope = (
            lambda candidate, *_args, **_kwargs: candidate is recovered_page
        )
        compare_tax_forms.recover_undeclared_entry_from_home_redirect = (
            lambda *_args, **_kwargs: calls.append("recover") or recovered_page
        )
        compare_tax_forms.is_undeclared_home_redirect_page = (
            lambda candidate, _target: candidate is page
        )
        compare_tax_forms.dismiss_known_undeclared_info_dialogs = lambda *_args, **_kwargs: ""
        compare_tax_forms.time.sleep = lambda _seconds: None

        result = compare_tax_forms.prepare_undeclared_page_for_target(
            page,
            TARGETS["vat_general_main"],
            [],
        )
    finally:
        compare_tax_forms.target_content_visible_in_any_scope = original_target_content_visible
        compare_tax_forms.recover_undeclared_entry_from_home_redirect = original_recover
        compare_tax_forms.is_undeclared_home_redirect_page = original_is_home_redirect
        compare_tax_forms.dismiss_known_undeclared_info_dialogs = original_dismiss
        compare_tax_forms.time.sleep = original_sleep

    assert result is recovered_page
    assert calls == ["recover"]


def test_prepare_undeclared_page_reports_tpass_login_as_auth_error():
    original_time = compare_tax_forms.time.time
    original_sleep = compare_tax_forms.time.sleep
    ticks = iter([0, 1, 100])
    message = ""
    try:
        compare_tax_forms.time.time = lambda: next(ticks, 100)
        compare_tax_forms.time.sleep = lambda _seconds: None
        try:
            compare_tax_forms.prepare_undeclared_page_for_target(
                FakeTpassLoginPage(),
                TARGETS["culture_fee_main"],
                [],
            )
        except compare_tax_forms.DeclarationQueryAuthError as exc:
            message = str(exc)
        else:
            raise AssertionError("expected DeclarationQueryAuthError")
    finally:
        compare_tax_forms.time.time = original_time
        compare_tax_forms.time.sleep = original_sleep

    assert "culture_fee_main" in message
    assert "tpass.shandong" in message


def test_prepare_undeclared_page_reports_home_without_target_as_unavailable():
    original_time = compare_tax_forms.time.time
    original_sleep = compare_tax_forms.time.sleep
    ticks = iter([0, 1, 100])
    message = ""
    try:
        compare_tax_forms.time.time = lambda: next(ticks, 100)
        compare_tax_forms.time.sleep = lambda _seconds: None
        try:
            compare_tax_forms.prepare_undeclared_page_for_target(
                FakeTaxHomeWithoutTargetPage(),
                TARGETS["consumption_tax_main"],
                [],
                allow_home_recovery=False,
            )
        except compare_tax_forms.UndeclaredTaxTargetUnavailableError as exc:
            message = str(exc)
        else:
            raise AssertionError("expected UndeclaredTaxTargetUnavailableError")
    finally:
        compare_tax_forms.time.time = original_time
        compare_tax_forms.time.sleep = original_sleep

    assert "consumption_tax_main" in message
    assert "loginb" in message


def test_prepare_undeclared_page_reports_tpass_code_error_as_auth_error():
    original_time = compare_tax_forms.time.time
    original_sleep = compare_tax_forms.time.sleep
    ticks = iter([0, 1, 100])
    message = ""
    try:
        compare_tax_forms.time.time = lambda: next(ticks, 100)
        compare_tax_forms.time.sleep = lambda _seconds: None
        try:
            compare_tax_forms.prepare_undeclared_page_for_target(
                FakeTaxAuthCodeErrorPage(),
                TARGETS["culture_fee_main"],
                [],
                allow_home_recovery=False,
            )
        except compare_tax_forms.DeclarationQueryAuthError as exc:
            message = str(exc)
        else:
            raise AssertionError("expected DeclarationQueryAuthError")
    finally:
        compare_tax_forms.time.time = original_time
        compare_tax_forms.time.sleep = original_sleep

    assert "culture_fee_main" in message
    assert "tpass/code" in message


def test_undeclared_direct_entry_reports_tpass_login_immediately():
    original_sleep = compare_tax_forms.time.sleep
    message = ""
    try:
        compare_tax_forms.time.sleep = lambda _seconds: None
        try:
            compare_tax_forms.navigate_to_undeclared_tax_page(
                FakeUndeclaredRedirectToTpassPage(),
                "shandong",
                TARGETS["vat_general_main"],
                {},
            )
        except compare_tax_forms.DeclarationQueryAuthError as exc:
            message = str(exc)
        else:
            raise AssertionError("expected DeclarationQueryAuthError")
    finally:
        compare_tax_forms.time.sleep = original_sleep

    assert "tpass.shandong" in message


def test_tax_home_declare_entry_retries_once_when_navigation_interrupts_click():
    class FakeNavigationInterruptPage:
        def __init__(self):
            self.url = "https://etax.yunnan.chinatax.gov.cn:8443/loginb/"
            self.context = FakeContext([self])
            self.goto_calls = []
            self.evaluate_calls = 0
            self.wait_calls = 0

        def goto(self, url, **_kwargs):
            self.goto_calls.append(url)
            self.url = url

        def evaluate(self, _script, *args):
            self.evaluate_calls += 1
            if self.evaluate_calls == 1:
                raise RuntimeError("Page.evaluate: Execution context was destroyed, most likely because of a navigation")
            return "clicked:target_action"

        def wait_for_load_state(self, *_args, **_kwargs):
            self.wait_calls += 1

    page = FakeNavigationInterruptPage()
    original_wait = compare_tax_forms.wait_for_undeclared_entry_page
    original_find = compare_tax_forms.find_context_undeclared_entry_page
    original_sleep = compare_tax_forms.time.sleep
    try:
        compare_tax_forms.wait_for_undeclared_entry_page = lambda *_args, **_kwargs: None
        compare_tax_forms.find_context_undeclared_entry_page = lambda current_page, _target: current_page
        compare_tax_forms.time.sleep = lambda _seconds: None

        result = compare_tax_forms.navigate_to_undeclared_tax_page_from_home(
            page,
            "yunnan",
            TARGETS["culture_fee_main"],
        )
    finally:
        compare_tax_forms.wait_for_undeclared_entry_page = original_wait
        compare_tax_forms.find_context_undeclared_entry_page = original_find
        compare_tax_forms.time.sleep = original_sleep

    assert result is page
    assert page.evaluate_calls == 2
    assert page.wait_calls == 1


def test_tax_home_declare_entry_does_not_raise_when_repeated_navigation_interrupts():
    class FakeRepeatedNavigationInterruptPage:
        def __init__(self):
            self.url = "https://etax.yunnan.chinatax.gov.cn:8443/mhzx/api/mh/tpass/code"
            self.context = FakeContext([self])
            self.evaluate_calls = 0
            self.wait_calls = 0

        def goto(self, url, **_kwargs):
            self.url = url

        def evaluate(self, _script, *args):
            self.evaluate_calls += 1
            raise RuntimeError("Page.evaluate: Execution context was destroyed, most likely because of a navigation")

        def wait_for_load_state(self, *_args, **_kwargs):
            self.wait_calls += 1

    page = FakeRepeatedNavigationInterruptPage()
    original_wait = compare_tax_forms.wait_for_undeclared_entry_page
    original_find = compare_tax_forms.find_context_undeclared_entry_page
    original_sleep = compare_tax_forms.time.sleep
    try:
        compare_tax_forms.wait_for_undeclared_entry_page = lambda *_args, **_kwargs: None
        compare_tax_forms.find_context_undeclared_entry_page = lambda current_page, _target: current_page
        compare_tax_forms.time.sleep = lambda _seconds: None

        result = compare_tax_forms.navigate_to_undeclared_tax_page_from_home(
            page,
            "yunnan",
            TARGETS["culture_fee_main"],
        )
    finally:
        compare_tax_forms.wait_for_undeclared_entry_page = original_wait
        compare_tax_forms.find_context_undeclared_entry_page = original_find
        compare_tax_forms.time.sleep = original_sleep

    assert result is page
    assert page.evaluate_calls == 3
    assert page.wait_calls == 3


def test_undeclared_auth_error_relogs_once_and_retries_target():
    class FakeArgs:
        task_id = "2076981650034436464"
        tax_timeout = 1
        tax_login_strategy = "plugin_first"

    first_page = FakeContextPage("https://etax.shandong.chinatax.gov.cn:8443/loginb/", "")
    logged_in_page = FakeContextPage("https://etax.shandong.chinatax.gov.cn:8443/loginb/", "")
    target_page = FakeContextPage(
        "https://etax.shandong.chinatax.gov.cn:8443/sbzx/view/lzsfjssb/#/declare/xfssb?jyjkId=30",
        "",
    )
    prepared_page = FakeContextPage(
        "https://etax.shandong.chinatax.gov.cn:8443/sbzx/view/lzsfjssb/#/declare/xfssb?jyjkId=30",
        "",
    )
    calls = []

    original_navigate = compare_tax_forms.navigate_to_undeclared_tax_page
    original_prepare = compare_tax_forms.prepare_undeclared_page_for_target
    original_login = compare_tax_forms.login_tax_page_for_task
    try:
        def fake_navigate(page, province, target, api_response):
            calls.append(("navigate", page.url, province, target.target_id, api_response.get("province")))
            return target_page

        def fake_prepare(page, target, mappings=None):
            calls.append(("prepare", page.url, target.target_id, len(mappings or [])))
            if sum(1 for call in calls if call[0] == "prepare") == 1:
                raise compare_tax_forms.DeclarationQueryAuthError("expired")
            return prepared_page

        def fake_login(bm, chanjet_page, args, province, expected_tax_no):
            calls.append(("login", args.task_id, province, expected_tax_no))
            return logged_in_page, province, object()

        compare_tax_forms.navigate_to_undeclared_tax_page = fake_navigate
        compare_tax_forms.prepare_undeclared_page_for_target = fake_prepare
        compare_tax_forms.login_tax_page_for_task = fake_login

        result_page, result_province = compare_tax_forms.open_undeclared_target_with_auth_retry(
            bm=object(),
            chanjet_page=object(),
            args=FakeArgs(),
            tax_page=first_page,
            province="shandong",
            expected_tax_no="91370102MA7D3P0D2P",
            target=TARGETS["consumption_tax_main"],
            api_response={"province": "shandong"},
            mappings=[object()],
        )
    finally:
        compare_tax_forms.navigate_to_undeclared_tax_page = original_navigate
        compare_tax_forms.prepare_undeclared_page_for_target = original_prepare
        compare_tax_forms.login_tax_page_for_task = original_login

    assert result_page is prepared_page
    assert result_province == "shandong"
    assert calls == [
        (
            "navigate",
            "https://etax.shandong.chinatax.gov.cn:8443/loginb/",
            "shandong",
            "consumption_tax_main",
            "shandong",
        ),
        (
            "prepare",
            "https://etax.shandong.chinatax.gov.cn:8443/sbzx/view/lzsfjssb/#/declare/xfssb?jyjkId=30",
            "consumption_tax_main",
            1,
        ),
        ("login", "2076981650034436464", "shandong", "91370102MA7D3P0D2P"),
        (
            "navigate",
            "https://etax.shandong.chinatax.gov.cn:8443/loginb/",
            "shandong",
            "consumption_tax_main",
            "shandong",
        ),
        (
            "prepare",
            "https://etax.shandong.chinatax.gov.cn:8443/sbzx/view/lzsfjssb/#/declare/xfssb?jyjkId=30",
            "consumption_tax_main",
            1,
        ),
    ]


def test_declaration_row_click_receives_target_period_payload():
    class FakeQueryPage:
        def __init__(self):
            self.payload = None

        def evaluate(self, _script, payload):
            self.payload = payload
            return "not_found_period"

    page = FakeQueryPage()

    result = compare_tax_forms.click_declaration_row_once(
        page,
        ("消费税及附加税费申报表",),
        ("2026-05-01", "2026-05-31"),
    )

    assert result == "not_found_period"
    assert page.payload == {
        "keywords": ["消费税及附加税费申报表"],
        "periodStart": "2026-05-01",
        "periodEnd": "2026-05-31",
    }


def test_declaration_row_period_fallback_requires_unique_match():
    class FakeDetailPage:
        pass

    class FakeQueryPage:
        def __init__(self):
            self.context = FakeContext([self])
            self.payloads = []
            self.results = iter(["not_found_period", "not_found_period", "clicked_vue"])

        def evaluate(self, _script, payload=None):
            self.payloads.append(payload)
            return next(self.results)

    page = FakeQueryPage()
    detail_page = FakeDetailPage()
    original_is_query_page = compare_tax_forms.is_query_page
    original_refresh = compare_tax_forms.refresh_declaration_query_results
    original_wait = compare_tax_forms.wait_for_declaration_detail_page
    original_is_detail = compare_tax_forms.is_declaration_detail_page
    original_sleep = compare_tax_forms.time.sleep
    try:
        compare_tax_forms.is_query_page = lambda _page: True
        compare_tax_forms.refresh_declaration_query_results = lambda _page, _period_range=None: "query"
        compare_tax_forms.wait_for_declaration_detail_page = lambda _page, _before_pages: detail_page
        compare_tax_forms.is_declaration_detail_page = lambda current_page: current_page is detail_page
        compare_tax_forms.time.sleep = lambda _seconds: None

        result = compare_tax_forms.click_declaration_row(
            page,
            TARGETS["cit_a_main"].query_keywords,
            ("2026-01-01", "2026-03-31"),
            allow_period_fallback=True,
        )
    finally:
        compare_tax_forms.is_query_page = original_is_query_page
        compare_tax_forms.refresh_declaration_query_results = original_refresh
        compare_tax_forms.wait_for_declaration_detail_page = original_wait
        compare_tax_forms.is_declaration_detail_page = original_is_detail
        compare_tax_forms.time.sleep = original_sleep

    assert result is detail_page
    assert page.payloads[-1]["requireUnique"] is True
    assert page.payloads[-1]["periodStart"] == ""
    assert page.payloads[-1]["periodEnd"] == ""


def test_cit_filed_query_keywords_allow_backend_list_title_variants():
    assert TARGETS["cit_a_main"].query_keywords == ("企业所得税", "月", "季")
    assert "A200000" in TARGETS["cit_a_main"].detail_form_keywords[0]


if __name__ == "__main__":
    test_can_switch_between_vat_general_appendices()
    test_does_not_switch_between_different_tax_types()
    test_does_not_switch_when_current_target_has_no_detail_selector()
    test_existing_tax_page_requires_matching_tax_no()
    test_existing_tax_page_does_not_reuse_loading_page()
    test_extract_expected_tax_no_from_api_param_json()
    test_extract_expected_tax_no_from_cookie_user_info()
    test_supported_unfiled_tax_types_are_not_blocked()
    test_culture_fee_unfiled_url_uses_target_period()
    test_culture_fee_does_not_reuse_vat_undeclared_url()
    test_consumption_tax_undeclared_url_is_recognized()
    test_find_context_undeclared_consumption_tax_page_after_home_click()
    test_cit_undeclared_home_keywords_match_jiangsu_hot_service_entry()
    test_cit_home_status_does_not_inherit_previous_vat_filed_status()
    test_cit_hot_service_only_is_not_undeclared_home_redirect()
    test_cit_hot_service_only_prepare_fails_without_button_polling()
    test_cit_hot_service_only_navigation_fails_before_clicking()
    test_cit_a_declare_scope_is_undeclared_home_redirect()
    test_cit_b_class_declare_scope_is_not_cit_a_home_redirect()
    test_shandong_vat_home_redirect_is_detected()
    test_tax_home_target_status_detects_consumption_tax_already_declared()
    test_tax_home_scoped_click_blocks_progress_query_fallback()
    test_tax_home_scoped_click_does_not_repeat_target_action_in_one_evaluation()
    test_tax_home_scoped_click_checks_target_before_navigation_steps()
    test_home_recovery_retries_after_target_title_click()
    test_home_recovery_stops_after_repeated_target_click_result()
    test_click_declaration_row_uses_safe_detail_button_keywords()
    test_consumption_tax_main_selection_requires_child_main_menu()
    test_confirm_undeclared_vat_accepts_active_target()
    test_confirm_undeclared_vat_rejects_active_menu_with_wrong_body()
    test_confirm_undeclared_vat_rejects_unconfirmed_target()
    test_confirm_undeclared_vat_accepts_visible_body_with_business_fields_without_active_menu()
    test_confirm_undeclared_consumption_tax_accepts_active_target()
    test_confirm_undeclared_consumption_tax_accepts_visible_content_without_active_menu()
    test_confirm_undeclared_culture_fee_accepts_embedded_form()
    test_undeclared_vat_general_appendix1_body_title_confirms_target_visible()
    test_prepare_undeclared_appendix_accepts_clicked_menu_without_extra_wait()
    test_confirm_undeclared_appendix_accepts_recent_clicked_menu_marker()
    test_prepare_undeclared_page_returns_page_when_target_already_visible()
    test_prepare_undeclared_page_recovers_when_menu_selection_returns_home()
    test_prepare_undeclared_page_recovers_from_home_before_menu_wait()
    test_prepare_undeclared_page_recovers_from_home_before_fill_wait()
    test_prepare_undeclared_page_reports_tpass_login_as_auth_error()
    test_prepare_undeclared_page_reports_home_without_target_as_unavailable()
    test_prepare_undeclared_page_reports_tpass_code_error_as_auth_error()
    test_undeclared_direct_entry_reports_tpass_login_immediately()
    test_undeclared_auth_error_relogs_once_and_retries_target()
    test_declaration_row_click_receives_target_period_payload()
    test_declaration_row_period_fallback_requires_unique_match()
    test_cit_filed_query_keywords_allow_backend_list_title_variants()
    print("All detail form switching tests passed!")
