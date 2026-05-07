from typing import Any


class MockParser:
    """Returns mock web data for testing the pipeline."""

    MOCK_WEB_DATA = {
        "sales_3_goods": "10,000.50",
        "sales_3_service": "5,000.25",
        "sales_5_goods": "3,000.00",
        "tax_period": "2026年01月01日至2026年03月31日",
        "tax_due_current": "450.15",
        "tax_rate": "3%",
        "declare_date": "2026年04月15日",
        "tax_exempt_sales": "——",
    }

    MOCK_API_DATA = {
        "data": {
            "salesGoods3Percent": 10000.50,
            "salesService3Percent": 5000.25,
            "salesGoods5Percent": 3000.00,
            "taxPeriod": "2026-01-01至2026-03-31",
            "taxDueCurrent": 450.15,
            "taxRate": 0.03,
            "declareDate": "2026-04-15",
            "taxExemptSales": "——",
        }
    }

    def get_web_data(self) -> dict[str, Any]:
        return self.MOCK_WEB_DATA.copy()

    def get_api_data(self) -> dict[str, Any]:
        return self.MOCK_API_DATA.copy()