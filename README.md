# Tax Verify

Tax declaration data verification toolkit.  The canonical user-facing entry is
`main.py`.

## Run a Real Chanjet Task

Use this for production-style comparisons by outer taskId:

```powershell
python main.py --task-id 2063992930197976023
```

Useful variants:

```powershell
python main.py --task-id 2063992930197976023 --targets vat_general_main
python main.py --task-id 2063992930197976023 --targets all --skip-pdf
python main.py --task-id 2063992930197976023 --skip-browser
```

The real task flow is implemented once in `scripts/compare_tax_forms.py` and is
called by `main.py`.  Older scripts should be treated as compatibility wrappers
or development tools.

## Offline Pipeline Smoke Run

Use `--dry-run` when you want the framework pipeline with mock browser/API data:

```powershell
python main.py --dry-run --period 2026Q1 --tax-type VAT_SMALL_SCALE
```

## Legacy Compatibility

This still works, but only delegates to the canonical target flow:

```powershell
python scripts/compare_vat_small_main.py --task-id 2063992930197976023
```

Prefer the equivalent canonical command:

```powershell
python main.py --task-id 2063992930197976023 --targets vat_small_main
```
