from typing import Optional

from src.models.tax_type import TaxTypeConfig, FormTemplate


class TaxTypeRegistry:
    """Registry of all tax types and their form templates."""

    def __init__(self):
        self._tax_types: dict[str, TaxTypeConfig] = {}

    def register(self, config: TaxTypeConfig) -> None:
        self._tax_types[config.tax_type_id] = config

    def register_from_yaml(self, path: str) -> None:
        from src.config.config_loader import ConfigLoader
        loader = ConfigLoader()
        configs = loader.load_tax_types(path)
        for tc in configs:
            self.register(tc)

    def get(self, tax_type_id: str) -> TaxTypeConfig:
        if tax_type_id not in self._tax_types:
            raise KeyError(f"Unsupported tax type: {tax_type_id}")
        return self._tax_types[tax_type_id]

    def get_form(self, tax_type_id: str, form_code: str) -> FormTemplate:
        tax_config = self.get(tax_type_id)
        for form in tax_config.forms:
            if form.form_code == form_code:
                return form
        raise KeyError(
            f"Form '{form_code}' not found in tax type '{tax_type_id}'"
        )

    def list_all(self) -> list[str]:
        return list(self._tax_types.keys())

    def list_forms(self, tax_type_id: str) -> list[str]:
        tax_config = self.get(tax_type_id)
        return [f.form_code for f in tax_config.forms]

    def load_all_from_dir(self, config_root: str) -> None:
        from src.config.config_loader import ConfigLoader
        loader = ConfigLoader(config_root=config_root)
        configs = loader.load_tax_types()
        for tc in configs:
            self.register(tc)