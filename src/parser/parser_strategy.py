from abc import ABC, abstractmethod
from typing import Any, Optional

from src.models.tax_type import PDFConfig, WebConfig


class BaseParser(ABC):
    """Base interface for data parsers."""

    @abstractmethod
    def parse(self, source: Any) -> dict[str, Any]:
        """Parse data source into {field_key: value} dict."""
        ...


class ParserStrategy:
    """Selects appropriate parser based on config."""

    _STRATEGIES = {
        "web_dom": "WebDOMParser",
        "table_extract": "PDFTableParser",
        "coordinate": "PDFCoordinateParser",
        "hybrid": "PDFHybridParser",
    }

    @classmethod
    def select(cls, config: Optional[PDFConfig] = None, source_type: str = "web_dom") -> BaseParser:
        if source_type == "web_dom":
            from src.parser.mock_parser import MockParser
            return MockParserPlaceholder()  # Use mock; real WebDOMParser requires a Page
        strategy_name = cls._STRATEGIES.get(
            config.parser_strategy if config else "table_extract",
            "PDFTableParser",
        )
        return PDFParserPlaceholder(strategy_name)


class MockParserPlaceholder(BaseParser):
    """Placeholder: returns mock web data for dry-run testing."""

    def parse(self, source: Any) -> dict[str, Any]:
        return {
            "sales_3_goods": "10000.50",
            "sales_3_service": "5000.25",
            "sales_5_goods": "3000.00",
            "tax_period": "2026年01月01日至2026年03月31日",
            "tax_due_current": "450.15",
            "tax_rate": "3%",
            "declare_date": "2026年04月15日",
            "tax_exempt_sales": "——",
        }


class PDFParserPlaceholder(BaseParser):
    """Placeholder: parses PDF tables."""

    def __init__(self, strategy_name: str = "PDFTableParser"):
        self.strategy_name = strategy_name

    def parse(self, source: Any) -> dict[str, Any]:
        return {
            "sales_3_goods": "10000.50",
            "sales_3_service": "5000.25",
            "sales_5_goods": "3000.00",
        }