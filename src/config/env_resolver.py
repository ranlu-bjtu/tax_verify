import os
import re
from typing import Any


class EnvResolver:
    """Substitutes ${VAR} and ${VAR:default} patterns in config values."""

    PATTERN = re.compile(r"\$\{([^}:]+)(?:\:([^}]*))?\}")

    def resolve(self, value: Any) -> Any:
        if isinstance(value, str):
            return self._resolve_string(value)
        elif isinstance(value, dict):
            return {k: self.resolve(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [self.resolve(item) for item in value]
        return value

    def _resolve_string(self, value: str) -> str:
        def replacer(match):
            var_name = match.group(1)
            default = match.group(2)
            env_val = os.environ.get(var_name)
            if env_val is not None:
                return env_val
            if default is not None:
                return default
            return match.group(0)

        return self.PATTERN.sub(replacer, value)