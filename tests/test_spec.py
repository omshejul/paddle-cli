from __future__ import annotations

from pathlib import Path

import httpx

from paddle_cli.spec import PaddleSpec, SpecStore

DOCUMENT = {
    "openapi": "3.1.0",
    "info": {"title": "Test", "version": "1"},
    "tags": [
        {
            "name": "Products",
            "externalDocs": {"url": "https://developer.paddle.com/api-reference/products"},
        }
    ],
    "paths": {
        "/products/{product_id}": {
            "get": {
                "operationId": "get-product",
                "summary": "Get a product",
                "tags": ["Products"],
                "description": "Returns a product. Requires `product.read` permission.",
                "parameters": [
                    {"$ref": "#/components/parameters/ProductId"},
                    {
                        "name": "include",
                        "in": "query",
                        "schema": {"type": "array", "items": {"type": "string"}},
                    },
                ],
            },
            "patch": {
                "operationId": "update-product",
                "summary": "Update a product",
                "tags": ["Products"],
                "parameters": [{"$ref": "#/components/parameters/ProductId"}],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/UpdateProduct"}
                        }
                    },
                },
            },
        }
    },
    "components": {
        "parameters": {
            "ProductId": {
                "name": "product_id",
                "in": "path",
                "required": True,
                "schema": {"type": "string", "example": "pro_123"},
            }
        },
        "schemas": {
            "UpdateProduct": {
                "type": "object",
                "required": ["name"],
                "properties": {
                    "name": {"type": "string", "example": "Pro"},
                    "description": {"type": ["string", "null"]},
                },
            }
        },
    },
}


def test_extracts_all_operations_and_metadata() -> None:
    spec = PaddleSpec(DOCUMENT)
    operations = spec.operations()
    assert len(operations) == 2
    get = next(item for item in operations if item.method == "GET")
    assert get.permission == "product.read"
    assert get.parameters[0].name == "product_id"
    assert get.parameters[0].required is True
    assert get.docs_url == "https://developer.paddle.com/api-reference/products"
    update = next(item for item in operations if item.method == "PATCH")
    assert update.is_write
    assert update.request_body_required
    assert spec.example_for(update.request_body) == {"name": "Pro"}


def test_store_downloads_valid_spec_atomically(tmp_path: Path) -> None:
    import yaml

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=yaml.safe_dump(DOCUMENT))

    cache = tmp_path / "nested" / "openapi.yaml"
    store = SpecStore(
        cache_path=cache,
        source_url="https://example.test/openapi.yaml",
        transport=httpx.MockTransport(handler),
    )
    spec = store.load()
    assert cache.exists()
    assert len(spec.operations()) == 2
    assert not cache.with_suffix(".tmp").exists()


def test_store_uses_existing_cache_if_refresh_fails(tmp_path: Path) -> None:
    import yaml

    cache = tmp_path / "openapi.yaml"
    cache.write_text(yaml.safe_dump(DOCUMENT), encoding="utf-8")

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    store = SpecStore(cache_path=cache, transport=httpx.MockTransport(handler))
    assert len(store.load(refresh=True).operations()) == 2
