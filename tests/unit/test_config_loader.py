"""Unit tests for config loader and env resolver."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import os

from src.config.config_loader import ConfigLoader, MainConfig
from src.config.env_resolver import EnvResolver
from src.registry.tax_type_registry import TaxTypeRegistry


def test_env_resolver():
    resolver = EnvResolver()
    os.environ["TEST_VAR"] = "hello"
    # Simple substitution
    assert resolver.resolve("${TEST_VAR}") == "hello"
    # Default value
    assert resolver.resolve("${MISSING_VAR:default}") == "default"
    # Nested in dict
    result = resolver.resolve({"url": "${TEST_VAR}/path"})
    assert result["url"] == "hello/path"
    # Clean up
    del os.environ["TEST_VAR"]


def test_config_loader():
    loader = ConfigLoader(config_root="config")
    cfg = loader.load_main("config/main.yaml")
    assert cfg.system.get("version") == "1.0"
    assert cfg.browser.get("channel") == "chrome"
    assert cfg.compare.get("default_tolerance_amount") == 0.01


def test_tax_type_registry():
    registry = TaxTypeRegistry()
    registry.load_all_from_dir("config")
    assert "VAT_SMALL_SCALE" in registry.list_all()
    forms = registry.list_forms("VAT_SMALL_SCALE")
    assert "VAT_SMALL_SCALE_MAIN" in forms


def test_company_loading():
    loader = ConfigLoader(config_root="config")
    companies = loader.load_companies()
    assert len(companies) > 0
    assert companies[0].get("taxpayer_id") is not None


if __name__ == "__main__":
    test_env_resolver()
    test_config_loader()
    test_tax_type_registry()
    test_company_loading()
    print("All config/registry tests passed!")