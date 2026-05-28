import shutil
import sys
import tempfile
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from openpyxl import Workbook

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.compare_tax_forms import (  # noqa: E402
    TARGETS,
    load_layout_scan_mappings,
    load_workbook_compat,
    parse_consumption_tax_main_rows,
    parse_consumption_tax_surcharge_rows,
    resolve_auto_targets,
)


def inject_unsupported_sheet_protection_attr(workbook: Path) -> None:
    temp = workbook.with_suffix(".tmp.xlsx")
    with ZipFile(workbook, "r") as source, ZipFile(temp, "w", ZIP_DEFLATED) as target:
        for info in source.infolist():
            data = source.read(info.filename)
            if info.filename == "xl/worksheets/sheet1.xml":
                text = data.decode("utf-8")
                if "<sheetProtection" not in text:
                    text = text.replace(
                        "<sheetData>",
                        '<sheetProtection sheet="1" allowResizeRows="1"/><sheetData>',
                    )
                data = text.encode("utf-8")
            target.writestr(info, data)
    workbook.unlink()
    shutil.move(temp, workbook)


def test_load_workbook_compat_handles_unsupported_sheet_protection_attr():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "protected.xlsx"
        wb = Workbook()
        ws = wb.active
        ws["A1"] = "field_id"
        wb.save(path)
        wb.close()
        inject_unsupported_sheet_protection_attr(path)

        loaded = load_workbook_compat(path, data_only=True, read_only=True)
        try:
            values = [row[0] for row in loaded.active.iter_rows(values_only=True)]
        finally:
            loaded.close()

        assert values == ["field_id"]


def test_consumption_tax_layout_loader_filters_non_api_labels():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "consumption.xlsx"
        wb = Workbook()
        ws = wb.active
        ws.title = "Sheet1"
        ws.append(["纳税人识别号", "nsrsbh_xfsjfjsfsbb", "a"])
        ws.append(["项目", "ysxfpmc1_xfsjfjsfsbb", "bqxse1_xfsjfjsfsbb"])
        wb.save(path)
        wb.close()

        mappings = load_layout_scan_mappings(TARGETS["consumption_tax_main"], path)

        assert [mapping.field_id for mapping in mappings] == [
            "ysxfpmc1_xfsjfjsfsbb",
            "bqxse1_xfsjfjsfsbb",
        ]


def test_auto_targets_include_consumption_tax_forms_when_api_has_fields():
    mappings_by_target = {target_id: [] for target_id in TARGETS}
    mappings_by_target["consumption_tax_main"] = load_layout_scan_mappings(
        TARGETS["consumption_tax_main"],
        _workbook_with_fields("xfs-main.xlsx", ["bqxse1_xfsjfjsfsbb"]),
    )
    mappings_by_target["consumption_tax_surcharge"] = load_layout_scan_mappings(
        TARGETS["consumption_tax_surcharge"],
        _workbook_with_fields("xfs-surcharge.xlsx", ["jze1_xfsfjsfjsb"]),
    )
    api_by_tax = {
        "sz_xfs": {
            "xfszb_qc.bqxse1_xfsjfjsfsbb": "1",
            "xfsfb1_qc.jze1_xfsfjsfjsb": "2",
        }
    }

    selected = resolve_auto_targets(api_by_tax, mappings_by_target)

    assert [target.target_id for target in selected] == [
        "consumption_tax_main",
        "consumption_tax_surcharge",
    ]


def test_consumption_tax_main_parser_uses_current_period_columns():
    rows = [
        ["1", "2", "3", "4", "a", "5", "b", "6=1×4+2×5", "c"],
        ["金银首饰", "0.00", "0.05", "", "0.00", "0.00", "206,256.64", "1,089,600.87", "10,312.83", "54,480.04"],
        ["合计", "——", "——", "——", "——", "——", "——", "——", "10,312.83", "54,480.04"],
        ["本期应补（退）税额", "14=6-7-11-13", "10,312.83", "54,480.04"],
        ["城市维护建设税本期应补（退）税额", "15", "360.95", "1,906.80"],
    ]

    parsed = parse_consumption_tax_main_rows(rows)

    assert parsed["ysxfpmc1_xfsjfjsfsbb"] == "金银首饰"
    assert parsed["bqxse1_xfsjfjsfsbb"] == "206,256.64"
    assert parsed["bqynse1_xfsjfjsfsbb"] == "10,312.83"
    assert parsed["bqybtse_xfsjfjsfsbb"] == "10,312.83"
    assert parsed["bnljybtse_xfsjfjsfsbb"] == "54,480.04"
    assert parsed["bqcswhjssybtse_xfsjfjsfsbb"] == "360.95"


def test_consumption_tax_surcharge_parser_maps_rows_and_totals():
    rows = [
        ["城市维护建设税", "市区", "10,312.83", "0.07", "721.90", "", "0.00", "减免性质", "50.00", "360.95", "0.00", "360.95"],
        ["教育费附加", "教育费附加", "10,312.83", "0.03", "309.38", "", "0.00", "减免性质", "50.00", "154.69", "0.00", "154.69"],
        ["合计", "——", "——", "——", "1,237.54", "——", "0.00", "——", "——", "618.77", "0.00", "618.77"],
    ]

    parsed = parse_consumption_tax_surcharge_rows(rows)

    assert parsed["jsyjsfsse1_xfsfjsfjsb"] == "10,312.83"
    assert parsed["sfl2_xfsfjsfjsb"] == "0.03"
    assert parsed["jzbl1_xfsfjsfjsb"] == "0.5"
    assert parsed["jze1_xfsfjsfjsb"] == "360.95"
    assert parsed["bqynsfe4_xfsfjsfjsb"] == "1,237.54"
    assert parsed["bqybtsfe4_xfsfjsfjsb"] == "618.77"


def _workbook_with_fields(name: str, fields: list[str]) -> Path:
    temp_root = Path(tempfile.gettempdir()) / "tax_verify_consumption_tests"
    temp_root.mkdir(parents=True, exist_ok=True)
    path = temp_root / name
    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(fields)
    wb.save(path)
    wb.close()
    return path


if __name__ == "__main__":
    test_load_workbook_compat_handles_unsupported_sheet_protection_attr()
    test_consumption_tax_layout_loader_filters_non_api_labels()
    test_auto_targets_include_consumption_tax_forms_when_api_has_fields()
    test_consumption_tax_main_parser_uses_current_period_columns()
    test_consumption_tax_surcharge_parser_maps_rows_and_totals()
    print("All consumption tax support tests passed!")
