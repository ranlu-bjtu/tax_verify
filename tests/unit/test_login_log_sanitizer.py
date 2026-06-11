from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.login.log_sanitizer import redact_sensitive_text


def test_redact_sensitive_url_query_and_json_values():
    text = (
        "https://tpass.example/#/login?cookie=abc123&token=secret-token&idCard=123456 "
        '{"access_token":"secret-access","mobile":"18100000000"}'
    )

    redacted = redact_sensitive_text(text)

    assert "abc123" not in redacted
    assert "secret-token" not in redacted
    assert "123456" not in redacted
    assert "secret-access" not in redacted
    assert "18100000000" not in redacted
    assert "<redacted>" in redacted


if __name__ == "__main__":
    test_redact_sensitive_url_query_and_json_values()
    print("All login log sanitizer tests passed!")
