from __future__ import annotations

import re
from dataclasses import dataclass
from time import monotonic
from typing import Any
from urllib.parse import quote

import httpx

from paddle_cli import __version__
from paddle_cli.spec import Operation

BASE_URLS = {
    "sandbox": "https://sandbox-api.paddle.com",
    "live": "https://api.paddle.com",
}
MODERN_API_KEY_PATTERN = re.compile(
    r"^pdl_(?P<environment>live|sdbx)_apikey_"
    r"(?P<identifier>[a-z\d]{26})_[A-Za-z\d]{22}_[A-Za-z\d]{3}$"
)


class PaddleCliError(RuntimeError):
    """A safe, user-facing Paddle CLI error."""


@dataclass(frozen=True)
class KeyInfo:
    environment: str
    modern: bool
    identifier: str | None = None

    @property
    def entity_id(self) -> str | None:
        return f"apikey_{self.identifier}" if self.identifier else None


@dataclass(frozen=True)
class ResponseResult:
    status_code: int
    reason: str
    body: Any
    request_id: str | None
    elapsed_ms: int
    next_url: str | None = None

    @property
    def succeeded(self) -> bool:
        return 200 <= self.status_code < 300


def inspect_api_key(api_key: str, environment: str | None = None) -> KeyInfo:
    key = api_key.strip()
    if not key:
        raise PaddleCliError("An API key is required.")
    if key.startswith(("test_", "live_")) and "apikey" not in key:
        raise PaddleCliError(
            "This looks like a client-side token. Use a server-side Paddle API key."
        )
    modern_match = MODERN_API_KEY_PATTERN.fullmatch(key)
    if key.startswith("pdl_sdbx_"):
        detected = "sandbox"
    elif key.startswith("pdl_live_"):
        detected = "live"
    else:
        detected = environment or ""
    if environment and detected and environment != detected:
        raise PaddleCliError(
            f"The key belongs to {detected}, but the requested environment is {environment}."
        )
    if detected not in BASE_URLS:
        raise PaddleCliError("This key does not identify an environment. Choose sandbox or live.")
    return KeyInfo(
        environment=detected,
        modern=key.startswith("pdl_"),
        identifier=modern_match.group("identifier") if modern_match else None,
    )


class PaddleClient:
    def __init__(
        self,
        api_key: str,
        *,
        environment: str | None = None,
        timeout: float = 30,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.key_info = inspect_api_key(api_key, environment)
        self.api_key = api_key.strip()
        self.base_url = BASE_URLS[self.key_info.environment]
        self.timeout = timeout
        self.transport = transport

    def verify(self) -> ResponseResult:
        operation = Operation(
            method="GET",
            path="/event-types",
            operation_id="verify-authentication",
            summary="Verify authentication",
            description="",
            tags=("Event types",),
        )
        return self.request(operation)

    def request(
        self,
        operation: Operation,
        *,
        path_parameters: dict[str, Any] | None = None,
        query: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        body: Any = None,
    ) -> ResponseResult:
        path = operation.path
        if "://" in path or path.startswith("//"):
            raise PaddleCliError("API paths must be relative to the selected Paddle environment.")
        for name, value in (path_parameters or {}).items():
            path = path.replace("{" + name + "}", quote(str(value), safe=""))
        unresolved = re.findall(r"\{([^}]+)\}", path)
        if unresolved:
            raise PaddleCliError(f"Missing path parameter: {unresolved[0]}")
        if not path.startswith("/"):
            path = "/" + path

        request_headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
            "Paddle-Version": "1",
            "User-Agent": f"paddle-api-cli/{__version__}",
        }
        for name, value in (headers or {}).items():
            if name.lower() not in {"authorization", "host", "proxy-authorization"}:
                request_headers[name] = value
        if body is not None:
            request_headers["Content-Type"] = "application/json"

        normalized_query = {
            key: _query_value(value) for key, value in (query or {}).items() if value is not None
        }
        started_at = monotonic()
        try:
            with httpx.Client(
                base_url=self.base_url,
                timeout=self.timeout,
                transport=self.transport,
                follow_redirects=False,
            ) as client:
                response = client.request(
                    operation.method,
                    path,
                    params=normalized_query,
                    headers=request_headers,
                    json=body if body is not None else None,
                )
        except httpx.TimeoutException as exc:
            raise PaddleCliError(
                f"Paddle did not respond within {self.timeout:g} seconds."
            ) from exc
        except httpx.HTTPError as exc:
            raise PaddleCliError(f"Could not reach the Paddle API: {exc}") from exc

        elapsed_ms = round((monotonic() - started_at) * 1000)
        try:
            response_body: Any = response.json()
        except ValueError:
            response_body = response.text
        request_id = response.headers.get("Paddle-Request-Id") or _nested_request_id(response_body)
        next_url = _next_url(response_body)
        return ResponseResult(
            status_code=response.status_code,
            reason=response.reason_phrase,
            body=response_body,
            request_id=request_id,
            elapsed_ms=elapsed_ms,
            next_url=next_url,
        )


def _query_value(value: Any) -> str:
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, list):
        return ",".join(_query_value(item) for item in value)
    return str(value)


def _nested_request_id(body: Any) -> str | None:
    if not isinstance(body, dict):
        return None
    meta = body.get("meta")
    if isinstance(meta, dict) and isinstance(meta.get("request_id"), str):
        return meta["request_id"]
    error = body.get("error")
    if isinstance(error, dict) and isinstance(error.get("request_id"), str):
        return error["request_id"]
    return None


def _next_url(body: Any) -> str | None:
    if not isinstance(body, dict):
        return None
    meta = body.get("meta")
    pagination = meta.get("pagination") if isinstance(meta, dict) else None
    next_url = pagination.get("next") if isinstance(pagination, dict) else None
    return next_url if isinstance(next_url, str) and next_url else None
