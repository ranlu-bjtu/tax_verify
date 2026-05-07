# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Tax declaration data verification system (税务申报数据校验系统). Compares tax API response data against web/PDF tax form data to detect discrepancies, then generates comparison reports.

## Running the Application

`main.py` is the canonical entrypoint. For real Chanjet taskId comparisons,
prefer:

```bash
python main.py --task-id 2063992930197976023
python main.py --task-id 2063992930197976023 --targets vat_general_main
python main.py --task-id 2063992930197976023 --skip-browser
```

The maintained real task implementation lives in `scripts/compare_tax_forms.py`
and is imported by `main.py`. Do not add new production comparison logic to
one-off scripts; add a `CompareTarget` or reusable helper to the canonical flow.

```bash
# Basic run (requires --period)
python main.py --dry-run --period 2026Q1

# With specific tax type and company
python main.py --period 2026Q1 --tax-type VAT_SMALL_SCALE --company 测试企业A

# Dry run (no browser/API calls, uses mock data)
python main.py --period 2026Q1 --dry-run

# All tax types for all companies
python main.py --period 2026Q1 --tax-type all --company all
```

## Running Tests

Tests use plain `pytest` style but run as standalone scripts with `sys.path` manipulation. No pytest dependency is installed.

```bash
# Run all unit tests
python tests/unit/test_models.py
python tests/unit/test_normalizer_comparator.py
python tests/unit/test_config_loader.py
python tests/unit/test_mapping_loader.py

# Run integration test (requires mapping Excel file)
python tests/integration/test_pipeline_e2e.py
```

## Pipeline Architecture

The system runs a 6-step orchestrated pipeline per (company, period, tax_type) combination:

1. **get_form** — Lookup `FormTemplate` from `TaxTypeRegistry` based on tax_type ID
2. **load_mappings** — Load field mappings from Excel via `ExcelLoader` → `MappingCleaner` → `MappingValidator` → `list[FieldMapping]`
3. **fetch_api** — Fetch tax data from API (currently returns mock data; `APIClient` is placeholder)
4. **get_web_data** — Extract web/PDF form data (currently returns mock data via `MockParser`)
5. **compare** — Normalize both data sources by `data_type` using type-specific normalizers, then compare with `Comparator` using tolerance rules from `CompareRules`
6. **report** — Generate output in configured formats (excel, json, html, console)

The `Orchestrator` chains these steps; each step produces a `StepResult`. Critical failures in `get_form` or `load_mappings` halt the pipeline; other failures allow partial continuation.

## Key Architectural Concepts

### Data Types and Normalization
Each field mapping has a `data_type` (amount, rate, text, date, integer, empty_or_dash, formula, enum) that determines which normalizer processes it. Normalizers handle Chinese-specific patterns: comma-separated numbers (`1,234.56`), currency symbols (`￥`), dash-as-empty (`——`, `—`), percentage rates (`3%` vs `0.03`), and Chinese date formats (`2026年01月15日`).

### Value Comparison
`Comparator` compares normalized values with configurable tolerance. For amounts default tolerance is 0.01, for rates 0.0001. Calculated fields (`is_calculated=True`) are skipped. Fields marked `compare=False` are also skipped. Result statuses: match, tolerance_match, mismatch, api_missing, web_missing, both_missing, parse_error, skip.

### Mapping Excel Loading
`ExcelLoader` reads mapping Excel files with configurable header row and data start row. `MappingCleaner` translates Chinese column headers to standard English field names (e.g., "税种"→"tax_type", "是否比对"→"compare", "是"/"否"→True/False). `MappingValidator` auto-generates missing field_ids and defaults invalid data_types to "text".

### Configuration System
- `config/main.yaml` — Global settings (browser, compare rules, report formats, scheduler, hermes)
- `config/tax_types/*.yaml` — Tax type definitions with form templates, web/API/PDF configs, compare rules
- `config/companies/*.yaml` — Company definitions with taxpayer IDs, periods, and tax types
- `${VAR}` and `${VAR:default}` environment variable substitution handled by `EnvResolver`

### Placeholder Components
Several modules are placeholder/stub implementations awaiting production integration:
- `BrowserManager` — Playwright browser launch with EtaxPlugin extension
- `LoginDetector` / `SemiAutoHandler` — Login state detection and manual login waiting
- `NavigationEngine` / `PDFDownloader` — Browser navigation and PDF download
- `APIClient` — Real HTTP API calls (currently returns hardcoded mock data)
- `HermesBridge` — CDP-based connection to Hermes Agent for browser automation
- `Scheduler` — APScheduler wrapper for recurring execution

## Models

All data models use Pydantic v2 (`BaseModel`). Key model hierarchy:
- `PipelineContext` carries data through the pipeline steps (api_data, web_data, mappings, compare_result)
- `FieldMapping` defines how each tax form field maps to API (jsonpath), web (selector), and PDF (region) sources
- `CompareResult` → `FieldCompareResult` per field + `CompareSummary` with aggregate stats and match_rate
- `TaxTypeConfig` → `FormTemplate` with `WebConfig`, `PDFConfig`, `APIConfig`, `CompareRules`
