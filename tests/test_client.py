from __future__ import annotations

import json

import httpx
import pytest

from paddle_cli.client import PaddleClient, PaddleCliError, inspect_api_key
from paddle_cli.spec import Operation


def operation(method: str = "GET", path: str = "/products") -> Operation:
    return Operation(
        method=method,
        path=path,
        operation_id="test-operation",
        summary="Test operation",
        description="",
        tags=("Tests",),
    )


def test_detects_sandbox_and_live_keys() -> None:
    assert inspect_api_key("pdl_sdbx_apikey_example").environment == "sandbox"
    assert inspect_api_key("pdl_live_apikey_example").environment == "live"


def test_extracts_safe_entity_id_from_modern_key() -> None:
    info = inspect_api_key("pdl_live_apikey_01gtgztp8f4kek3yd4g1wrksa3_q6TGTJyvoIz7LDtXT65bX7_AQO")

    assert info.entity_id == "apikey_01gtgztp8f4kek3yd4g1wrksa3"
    assert info.modern is True


def test_rejects_client_side_token() -> None:
    with pytest.raises(PaddleCliError, match="client-side token"):
        inspect_api_key("live_abc123")


def test_legacy_key_requires_environment() -> None:
    with pytest.raises(PaddleCliError, match="Choose sandbox or live"):
        inspect_api_key("legacy-secret")
    assert inspect_api_key("legacy-secret", "sandbox").environment == "sandbox"


def test_environment_mismatch_is_rejected() -> None:
    with pytest.raises(PaddleCliError, match="belongs to live"):
        inspect_api_key("pdl_live_apikey_example", "sandbox")


def test_request_builds_path_query_and_secure_headers() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["authorization"] = request.headers["Authorization"]
        seen["version"] = request.headers["Paddle-Version"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"data": {"ok": True}, "meta": {"request_id": "req_123"}},
        )

    client = PaddleClient(
        "pdl_sdbx_apikey_example",
        transport=httpx.MockTransport(handler),
    )
    result = client.request(
        operation("POST", "/customers/{customer_id}/addresses"),
        path_parameters={"customer_id": "ctm/value"},
        query={"status": ["active", "archived"], "enabled": True},
        headers={"Authorization": "Bearer attacker", "X-Test": "yes"},
        body={"country_code": "US"},
    )

    assert seen["url"] == (
        "https://sandbox-api.paddle.com/customers/ctm%2Fvalue/addresses"
        "?status=active%2Carchived&enabled=true"
    )
    assert seen["authorization"] == "Bearer pdl_sdbx_apikey_example"
    assert seen["version"] == "1"
    assert seen["body"] == {"country_code": "US"}
    assert result.succeeded
    assert result.request_id == "req_123"


def test_missing_path_parameter_is_rejected_before_request() -> None:
    client = PaddleClient("pdl_sdbx_apikey_example", transport=httpx.MockTransport(lambda _: None))
    with pytest.raises(PaddleCliError, match="customer_id"):
        client.request(operation(path="/customers/{customer_id}"))


@pytest.mark.parametrize("path", ["https://example.com/steal", "//example.com/steal"])
def test_request_cannot_send_api_key_to_another_host(path: str) -> None:
    client = PaddleClient("pdl_sdbx_apikey_example", transport=httpx.MockTransport(lambda _: None))
    with pytest.raises(PaddleCliError, match="relative"):
        client.request(operation(path=path))


def test_extracts_next_page_url() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": [],
                "meta": {
                    "pagination": {"next": "https://sandbox-api.paddle.com/products?after=pro_123"}
                },
            },
        )

    result = PaddleClient(
        "pdl_sdbx_apikey_example", transport=httpx.MockTransport(handler)
    ).request(operation())
    assert result.next_url == "https://sandbox-api.paddle.com/products?after=pro_123"
