import os
import glob
from pathlib import Path
from typing import Optional

import yaml

from src.config.env_resolver import EnvResolver
from src.models.tax_type import TaxTypeConfig


class MainConfig:
    """Loaded and resolved main configuration."""

    def __init__(self, raw: dict):
        self._raw = raw
        self.resolver = EnvResolver()
        self._resolved = self.resolver.resolve(raw)

    @property
    def system(self) -> dict:
        return self._resolved.get("system", {})

    @property
    def browser(self) -> dict:
        return self._resolved.get("browser", {})

    @property
    def login_detection(self) -> dict:
        return self._resolved.get("login_detection", {})

    @property
    def data_source(self) -> dict:
        return self._resolved.get("data_source", {})

    @property
    def api_defaults(self) -> dict:
        return self._resolved.get("api", {})

    @property
    def compare(self) -> dict:
        return self._resolved.get("compare", {})

    @property
    def report(self) -> dict:
        return self._resolved.get("report", {})

    @property
    def scheduler(self) -> dict:
        return self._resolved.get("scheduler", {})

    @property
    def hermes(self) -> dict:
        return self._resolved.get("hermes", {})

    def to_dict(self) -> dict:
        return self._resolved


class ConfigLoader:
    """Loads YAML config files and assembles the full configuration."""

    def __init__(self, config_root: Optional[str] = None):
        self.config_root = config_root or ""

    def load_main(self, config_path: str) -> MainConfig:
        raw = self._read_yaml(config_path)
        return MainConfig(raw)

    def load_tax_types(self, pattern: str = "tax_types/*.yaml") -> list[TaxTypeConfig]:
        search_dir = os.path.join(self.config_root, pattern)
        configs = []
        for path in sorted(glob.glob(search_dir)):
            raw = self._read_yaml(path)
            resolver = EnvResolver()
            resolved = resolver.resolve(raw)
            tc = TaxTypeConfig(**resolved.get("tax_type", resolved))
            configs.append(tc)
        return configs

    def load_companies(self, pattern: str = "companies/*.yaml") -> list[dict]:
        search_dir = os.path.join(self.config_root, pattern)
        companies = []
        for path in sorted(glob.glob(search_dir)):
            raw = self._read_yaml(path)
            resolver = EnvResolver()
            resolved = resolver.resolve(raw)
            companies.append(resolved.get("company", resolved))
        return companies

    def _read_yaml(self, path: str) -> dict:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data or {}