import logging
from typing import Any, Optional

from playwright.sync_api import Page

from src.models.field_mapping import FieldMapping
from src.models.tax_type import WebConfig
from src.parser.parser_strategy import BaseParser

logger = logging.getLogger(__name__)


class WebDOMParser(BaseParser):
    """Extracts tax form data from web page DOM using Playwright.

    Uses FieldMapping.web_selector to locate and extract values.
    Also supports table-based extraction via WebConfig selectors.
    """

    def __init__(self, page: Page):
        self.page = page

    def parse(self, source: Any = None) -> dict[str, Any]:
        """Parse web DOM into {field_id: value} dict.

        Args:
            source: Either a list[FieldMapping] or None (uses empty dict)
        """
        if source is None or not isinstance(source, list):
            return {}

        return self.extract_by_mappings(source)

    def extract_by_mappings(self, mappings: list[FieldMapping]) -> dict[str, Any]:
        """Extract values using each field's web_selector or web_cell_id."""
        result = {}
        for m in mappings:
            value = None

            # Try web_selector first (CSS selector for the specific element)
            if m.web_selector:
                try:
                    el = self.page.query_selector(m.web_selector)
                    if el:
                        value = el.inner_text().strip()
                        logger.debug(f"Extracted {m.field_id} via selector: {value}")
                    else:
                        logger.debug(f"Selector not found: {m.web_selector}")
                except Exception as e:
                    logger.warning(f"Error extracting {m.field_id}: {e}")

            # Try web_cell_id as fallback
            elif m.web_cell_id:
                try:
                    selector = f"[data-cell-id='{m.web_cell_id}']"
                    el = self.page.query_selector(selector)
                    if el:
                        value = el.inner_text().strip()
                    else:
                        # Try id attribute
                        el = self.page.query_selector(f"#{m.web_cell_id}")
                        if el:
                            value = el.inner_text().strip()
                except Exception as e:
                    logger.warning(f"Error extracting {m.field_id} via cell_id: {e}")

            # Try row/col indices as last fallback
            elif m.web_row_index is not None and m.web_col_index is not None:
                try:
                    selector = f"tr:nth-child({m.web_row_index}) td:nth-child({m.web_col_index})"
                    el = self.page.query_selector(selector)
                    if el:
                        value = el.inner_text().strip()
                except Exception as e:
                    logger.warning(f"Error extracting {m.field_id} via row/col: {e}")

            result[m.field_id] = value

        logger.info(f"Extracted {len([v for v in result.values() if v is not None])}/{len(mappings)} fields from DOM")
        return result

    def extract_table(self, web_config: WebConfig) -> dict[str, str]:
        """Extract all data from a table using table/row/cell selectors.

        Returns a flat dict of all cell values with composite keys
        like "row_N_col_M" or the cell's own attributes.
        """
        if not web_config.table_selector:
            return {}

        result = {}
        try:
            table_el = self.page.query_selector(web_config.table_selector)
            if not table_el:
                logger.warning(f"Table not found: {web_config.table_selector}")
                return {}

            row_selector = web_config.row_selector or "tr"
            cell_selector = web_config.cell_selector or "td"

            rows = table_el.query_selector_all(row_selector)
            for row_idx, row in enumerate(rows):
                cells = row.query_selector_all(cell_selector)
                for col_idx, cell in enumerate(cells):
                    text = cell.inner_text().strip()
                    # Use data-line/data-col attributes if present
                    line = cell.get_attribute("data-line") or str(row_idx)
                    col = cell.get_attribute("data-col") or str(col_idx)
                    key = f"line_{line}_col_{col}"
                    result[key] = text

            logger.info(f"Extracted table: {len(result)} cells")

        except Exception as e:
            logger.error(f"Table extraction failed: {e}")

        return result