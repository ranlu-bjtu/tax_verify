import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.compare_tax_forms import (
    TARGETS,
    can_switch_detail_form_between,
    extract_expected_tax_no,
    find_existing_tax_page,
)


class FakePage:
    def __init__(self, url, text):
        self.url = url
        self._text = text

    def evaluate(self, _script):
        return self._text


class FakeBrowserManager:
    def __init__(self, pages):
        self._pages = pages

    def get_all_pages(self):
        return self._pages


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
    target_page = FakePage(
        "https://etax.henan.chinatax.gov.cn:8443/loginb/",
        "我要查询 纳税人识别号 91410105MACWB5X52Y",
    )
    other_page = FakePage(
        "https://etax.henan.chinatax.gov.cn:8443/szzh/zhcx/sbxx/sbxxcx/detail?isCyqy=false",
        "我要查询 91410307MADPHCRK4E",
    )
    bm = FakeBrowserManager([other_page, target_page])

    assert find_existing_tax_page(bm, "henan", "91410105MACWB5X52Y") is target_page
    assert find_existing_tax_page(bm, "henan", "911111111111111111") is None


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


if __name__ == "__main__":
    test_can_switch_between_vat_general_appendices()
    test_does_not_switch_between_different_tax_types()
    test_does_not_switch_when_current_target_has_no_detail_selector()
    test_existing_tax_page_requires_matching_tax_no()
    test_extract_expected_tax_no_from_api_param_json()
    test_extract_expected_tax_no_from_cookie_user_info()
    print("All detail form switching tests passed!")
