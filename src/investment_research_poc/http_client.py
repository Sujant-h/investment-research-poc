from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


class JsonHttpClient:
    def __init__(self, timeout_seconds: int = 30, max_retries: int = 3) -> None:
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries

    def get_json(self, url: str, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> dict[str, Any]:
        final_url = url
        if params:
            query = urllib.parse.urlencode(
                {key: normalize_query_value(value) for key, value in params.items() if value is not None},
                doseq=True,
            )
            delimiter = "&" if "?" in url else "?"
            final_url = f"{url}{delimiter}{query}"
        request = urllib.request.Request(
            final_url,
            headers=build_default_headers(headers),
            method="GET",
        )
        return self._send_json(request)

    def post_json(self, url: str, *, payload: dict[str, Any], headers: dict[str, str] | None = None) -> dict[str, Any]:
        encoded = json.dumps(payload).encode("utf-8")
        request_headers = build_default_headers({"Content-Type": "application/json", **(headers or {})})
        request = urllib.request.Request(url, data=encoded, headers=request_headers, method="POST")
        return self._send_json(request)

    def _send_json(self, request: urllib.request.Request) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                    content = response.read().decode("utf-8")
                    return json.loads(content)
            except urllib.error.HTTPError as exc:
                last_error = exc
                if exc.code not in {429, 500, 502, 503, 504} or attempt == self.max_retries:
                    detail = exc.read().decode("utf-8", errors="ignore")
                    raise RuntimeError(f"HTTP request failed with status {exc.code}: {detail}") from exc
                time.sleep(0.75 * attempt)
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                last_error = exc
                if attempt == self.max_retries:
                    break
                time.sleep(0.75 * attempt)
        raise RuntimeError(f"HTTP request failed after retries: {last_error}") from last_error


def normalize_query_value(value: Any) -> Any:
    if isinstance(value, bool):
        return "true" if value else "false"
    return value


def build_default_headers(headers: dict[str, str] | None = None) -> dict[str, str]:
    return {
        "Accept": "application/json",
        "User-Agent": "investment-research-poc/0.1",
        **(headers or {}),
    }
