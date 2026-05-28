import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.api.api_client import APIClient


def test_api_client_detects_ssl_eof_for_curl_fallback():
    assert APIClient._should_try_curl_fallback(
        RuntimeError("SSLEOFError: UNEXPECTED_EOF_WHILE_READING")
    )


if __name__ == "__main__":
    test_api_client_detects_ssl_eof_for_curl_fallback()
    print("All API client tests passed!")
