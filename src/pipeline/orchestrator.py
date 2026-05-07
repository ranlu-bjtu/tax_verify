import logging
import time
from typing import Optional

from src.config.config_loader import MainConfig
from src.registry.tax_type_registry import TaxTypeRegistry
from src.models.tax_type import FormTemplate, CompareRules
from src.models.field_mapping import FieldMapping, DataType
from src.models.compare_result import CompareResult
from src.models.execution import PipelineContext, StepResult, StepStatus
from src.mapping.excel_loader import ExcelLoader
from src.api.api_client import APIClient
from src.api.json_path_extractor import JSONPathExtractor
from src.api.api_config import ResponseStore
from src.compare.value_normalizer import get_normalizer, NormalizedValue
from src.compare.comparator import Comparator
from src.parser.mock_parser import MockParser
from src.report.excel_report import ExcelReport
from src.report.json_report import JSONReport
from src.report.console_report import ConsoleReport
from src.report.html_report import HTMLReport
from src.login.browser_manager import BrowserManager
from src.login.auto_tax_login import AutoTaxLogin
from src.navigation.navigation_engine import NavigationEngine
from src.parser.web_dom_parser import WebDOMParser
from src.config.config_loader import ConfigLoader

logger = logging.getLogger(__name__)

CHANJET_TASK_URL = "https://public-manage.chanjet.com/taxserver#/taskManage/taxTaskList"


class Orchestrator:
    """Orchestrates the full verification pipeline."""

    def __init__(self, config: MainConfig, registry: TaxTypeRegistry, dry_run: bool = False):
        self.config = config
        self.registry = registry
        self.dry_run = dry_run

    def run(self, context: PipelineContext) -> PipelineContext:
        start_time = time.time()

        try:
            # Step 1: Get form template
            step1 = self._step_get_form(context)
            context.steps.append(step1)
            if step1.status == StepStatus.FAILED:
                return context

            # Step 2: Load mappings
            step2 = self._step_load_mappings(context)
            context.steps.append(step2)
            if step2.status == StepStatus.FAILED:
                return context

            # Step 3: Fetch API data (mock)
            step3 = self._step_fetch_api(context)
            context.steps.append(step3)

            # Step 4: Get web data (mock)
            step4 = self._step_get_web_data(context)
            context.steps.append(step4)

            # Step 5: Normalize and compare
            step5 = self._step_compare(context)
            context.steps.append(step5)

            # Step 6: Generate report
            step6 = self._step_report(context)
            context.steps.append(step6)

        except Exception as e:
            logger.error(f"Pipeline error: {e}")
            context.steps.append(StepResult(
                step_name="pipeline_error", status=StepStatus.FAILED,
                error_message=str(e),
            ))

        duration = int((time.time() - start_time) * 1000)
        logger.info(f"Pipeline completed in {duration}ms")
        return context

    def _step_get_form(self, context: PipelineContext) -> StepResult:
        try:
            tax_config = self.registry.get(context.tax_type)
            form = tax_config.forms[0]  # Default to first form
            context.output_data = {"form": form}
            return StepResult(step_name="get_form", status=StepStatus.SUCCESS)
        except KeyError as e:
            return StepResult(step_name="get_form", status=StepStatus.FAILED,
                              error_message=str(e))

    def _step_load_mappings(self, context: PipelineContext) -> StepResult:
        try:
            tax_config = self.registry.get(context.tax_type)
            form = tax_config.forms[0]
            mapping_file = form.mapping_file or "./mappings/vat_small_scale_mapping.xlsx"
            sheet = form.mapping_sheet or None

            loader = ExcelLoader(
                mapping_file, sheet=sheet,
                header_row=form.mapping_header_row,
                data_start_row=form.mapping_data_start_row,
            )
            mappings = loader.load()
            context.mappings = mappings
            context.output_data = {"mappings": len(mappings)}
            return StepResult(step_name="load_mappings", status=StepStatus.SUCCESS,
                              output_data={"count": len(mappings)})
        except Exception as e:
            logger.error(f"Mapping load failed: {e}")
            return StepResult(step_name="load_mappings", status=StepStatus.FAILED,
                              error_message=str(e))

    def _step_fetch_api(self, context: PipelineContext) -> StepResult:
        try:
            client = APIClient()
            if self.dry_run:
                response = client.fetch(
                    taxpayer_id=context.company_id,
                    tax_period=context.period,
                    tax_type=context.tax_type,
                )
            elif context.task_id:
                response = client.fetch_by_task_id(context.task_id)
            else:
                response = client.fetch(
                    taxpayer_id=context.company_id,
                    tax_period=context.period,
                    tax_type=context.tax_type,
                )
            context.api_data = response
            # Extract province from API response for region-based routing
            if isinstance(response, dict) and response.get("province"):
                context.province = response["province"]
            return StepResult(step_name="fetch_api", status=StepStatus.SUCCESS)
        except Exception as e:
            return StepResult(step_name="fetch_api", status=StepStatus.FAILED,
                              error_message=str(e))

    def _step_get_web_data(self, context: PipelineContext) -> StepResult:
        bm = None
        try:
            # Dry run: use mock data, skip browser automation
            if self.dry_run:
                mock = MockParser()
                web_data = mock.get_web_data()
                context.web_data = web_data
                return StepResult(step_name="get_web_data", status=StepStatus.SUCCESS,
                                  output_data={"mode": "mock"})

            tax_config = self.registry.get(context.tax_type)
            form = tax_config.forms[0]

            if form.web_config and form.web_config.login_required:
                # Real browser automation flow via CDP connection
                province = context.province
                if not province:
                    province = self._get_province_from_company(context)
                if not province:
                    province = "jiangxi"

                logger.info(f"Province routing: {province}")

                # Connect to Chrome via CDP (user must start Chrome with extension manually)
                browser_config = self.config.browser if hasattr(self.config, 'browser') else {}
                cdp_port = browser_config.get("cdp_port", 9222)
                chanjet_timeout = browser_config.get("chanjet_login_timeout", 300)
                tax_login_timeout = browser_config.get("tax_login_timeout", 120)

                bm = BrowserManager()
                bm.connect_cdp(cdp_port)

                # Find or wait for Chanjet page (user logs in manually)
                auto_login = AutoTaxLogin(bm, province=province)

                chanjet_page = bm.find_page_by_url("chanjet.com")
                if not chanjet_page:
                    # Navigate to Chanjet task page
                    page = bm.get_page()
                    page.goto(CHANJET_TASK_URL, wait_until="domcontentloaded", timeout=30000)
                    chanjet_page = page

                if not auto_login.wait_for_chanjet_login(chanjet_page, timeout=chanjet_timeout):
                    bm.close()
                    return StepResult(step_name="get_web_data", status=StepStatus.FAILED,
                                      error_message="Chanjet login not completed")

                # Trigger EtaxPlugin auto-login to tax bureau
                tax_page = auto_login.trigger_plugin_and_wait(
                    chanjet_page, context.task_id, timeout=tax_login_timeout
                )
                if not tax_page:
                    bm.close()
                    return StepResult(step_name="get_web_data", status=StepStatus.FAILED,
                                      error_message="Tax bureau login failed")

                # Navigate to target form page
                nav = NavigationEngine(tax_page)
                nav_success = nav.navigate_to_form(form.web_config)
                if not nav_success:
                    logger.warning("Navigation to form page failed, attempting extraction anyway")

                # Handle result-list pages
                result_list_cfg = form.web_config.result_list if form.web_config else None
                if result_list_cfg and result_list_cfg.get("enabled"):
                    web_data = self._extract_from_result_list(tax_page, nav, result_list_cfg, context)
                else:
                    parser = WebDOMParser(tax_page)
                    web_data = parser.extract_by_mappings(context.mappings or [])

                context.web_data = web_data

                bm.close()
                return StepResult(step_name="get_web_data", status=StepStatus.SUCCESS)
            else:
                # Fallback to mock data
                mock = MockParser()
                web_data = mock.get_web_data()
                context.web_data = web_data
                return StepResult(step_name="get_web_data", status=StepStatus.SUCCESS)

        except Exception as e:
            logger.error(f"Web data extraction failed: {e}")
            if bm:
                bm.close()
            return StepResult(step_name="get_web_data", status=StepStatus.FAILED,
                              error_message=str(e))

    def _step_compare(self, context: PipelineContext) -> StepResult:
        try:
            mappings = context.mappings or []
            api_raw = context.api_data or {}
            web_raw = context.web_data or {}

            # Extract API values by JSONPath
            extractor = JSONPathExtractor()
            api_extracted = {}
            for m in mappings:
                if m.api_json_path:
                    api_extracted[m.field_id] = extractor.extract(api_raw, m.api_json_path)

            # Normalize both API and web values
            api_normalized = {}
            web_normalized = {}
            for m in mappings:
                normalizer = get_normalizer(m.data_type)
                api_val = api_extracted.get(m.field_id, api_raw.get("data", {}).get(m.field_id))
                web_val = web_raw.get(m.field_id)

                api_normalized[m.field_id] = normalizer.normalize(api_val)
                web_normalized[m.field_id] = normalizer.normalize(web_val)

            # Compare
            rules = self._get_compare_rules(context)
            comparator = Comparator(rules)
            result = comparator.compare_all(
                mappings=mappings,
                api_data=api_normalized,
                web_data=web_normalized,
                batch_id=context.company_id,
                company_name=context.company_id,
                taxpayer_id=context.company_id,
                period=context.period,
            )
            context.compare_result = result
            return StepResult(step_name="compare", status=StepStatus.SUCCESS,
                              output_data={"match_rate": result.summary.match_rate})
        except Exception as e:
            logger.error(f"Compare step failed: {e}")
            return StepResult(step_name="compare", status=StepStatus.FAILED,
                              error_message=str(e))

    def _step_report(self, context: PipelineContext) -> StepResult:
        try:
            result = context.compare_result
            if result is None:
                return StepResult(step_name="report", status=StepStatus.FAILED,
                                  error_message="No compare result")

            report_dir = self.config.report.get("output_dir", "./output/reports")
            formats = self.config.report.get("formats", ["excel", "console", "json"])

            generated_files = []
            for fmt in formats:
                if fmt == "excel":
                    gen = ExcelReport(report_dir)
                    path = gen.generate(result)
                    generated_files.append(path)
                elif fmt == "json":
                    gen = JSONReport(report_dir)
                    path = gen.generate(result)
                    generated_files.append(path)
                elif fmt == "html":
                    gen = HTMLReport(report_dir)
                    path = gen.generate(result)
                    generated_files.append(path)
                elif fmt == "console":
                    gen = ConsoleReport()
                    gen.generate(result)

            return StepResult(step_name="report", status=StepStatus.SUCCESS,
                              output_data={"files": generated_files})
        except Exception as e:
            return StepResult(step_name="report", status=StepStatus.FAILED,
                              error_message=str(e))

    def _extract_from_result_list(
        self, page, nav: NavigationEngine, result_list_cfg: dict, context: PipelineContext
    ) -> dict:
        """Iterate through result list items, extract data from each detail page."""
        count = nav.get_result_count(result_list_cfg)
        logger.info(f"Result list has {count} items")

        if count == 0:
            logger.warning("No result items found, falling back to page extraction")
            parser = WebDOMParser(page)
            return parser.extract_by_mappings(context.mappings or [])

        all_data = {}
        for i in range(count):
            logger.info(f"Processing result item {i+1}/{count}")
            if not nav.click_result_item(i, result_list_cfg):
                logger.warning(f"Failed to click result item {i+1}, skipping")
                continue

            # Extract data from detail page
            parser = WebDOMParser(page)
            detail_data = parser.extract_by_mappings(context.mappings or [])

            # Also try table extraction if configured
            tax_config = self.registry.get(context.tax_type)
            form = tax_config.forms[0]
            if form.web_config and form.web_config.table_selector:
                table_data = parser.extract_table(form.web_config)
                detail_data.update(table_data)

            # Merge into accumulated data (prefix with index if multiple)
            if count > 1:
                for key, val in detail_data.items():
                    all_data[f"item_{i}_{key}"] = val
            else:
                all_data.update(detail_data)

            # Navigate back to result list for next item
            if i < count - 1:
                if not nav.go_back_to_results():
                    logger.warning(f"Failed to return to result list after item {i+1}")
                    break

        return all_data

    def _get_compare_rules(self, context: PipelineContext) -> CompareRules:
        try:
            tax_config = self.registry.get(context.tax_type)
            return tax_config.forms[0].compare_rules
        except (KeyError, IndexError):
            compare_config = self.config.compare
            return CompareRules(
                default_tolerance_amount=compare_config.get("default_tolerance_amount", 0.01),
                default_tolerance_rate=compare_config.get("default_tolerance_rate", 0.0001),
                treat_dash_as_zero=compare_config.get("treat_dash_as_zero", True),
                treat_empty_as_zero=compare_config.get("treat_empty_as_zero", False),
                empty_equivalent_values=compare_config.get("empty_equivalent_values", ["——", "", "0.00", "0"]),
            )

    def _get_province_from_company(self, context: PipelineContext) -> str:
        """Get province from company config or task API paramJson."""
        # Check company config for province
        try:
            loader = ConfigLoader(config_root=context.config_root)
            companies = loader.load_companies()
            for c in companies:
                if c.get("name") == context.company_id or c.get("taxpayer_id") == context.company_id:
                    return c.get("province", "")
        except Exception:
            pass

        # Check API data paramJson
        if context.api_data and isinstance(context.api_data, dict):
            param_json = context.api_data.get("paramJson", {})
            if isinstance(param_json, dict):
                return param_json.get("province", "")

        return ""