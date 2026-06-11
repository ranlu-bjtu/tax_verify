from __future__ import annotations

import re
from typing import Any


SENSITIVE_KEYS = (
    "authorization",
    "access_token",
    "token",
    "cookie",
    "idcard",
    "idCard",
    "mobile",
    "phone",
)


def redact_sensitive_text(value: Any) -> str:
    text = str(value or "")
    for key in SENSITIVE_KEYS:
        text = re.sub(
            rf"(?i)({re.escape(key)}=)[^&\s|]+",
            rf"\1<redacted>",
            text,
        )
        text = re.sub(
            rf"(?i)(%22{re.escape(key)}%22%3A%22)[^%&\s|]+",
            rf"\1<redacted>",
            text,
        )
        text = re.sub(
            rf'(?i)("{re.escape(key)}"\s*:\s*")[^"]+',
            rf"\1<redacted>",
            text,
        )
    return text
