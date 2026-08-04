from __future__ import annotations

import subprocess

from paddle_cli.spec import Operation, PaddleSpec
from scripts.e2e_sandbox import (
    INVALID_ID,
    ProbeResult,
    _is_expected,
    _is_required_object_schema,
    _must_abort,
    _probe,
    _unproven_write_operations,
)


def test_required_object_schema_accepts_all_safe_choice_branches() -> None:
    spec = PaddleSpec(
        {
            "openapi": "3.1.0",
            "components": {
                "schemas": {
                    "CreateA": {
                        "type": "object",
                        "required": ["name"],
                        "properties": {"name": {"type": "string"}},
                    }
                }
            },
        }
    )
    schema = {
        "oneOf": [
            {"$ref": "#/components/schemas/CreateA"},
            {
                "type": "object",
                "required": ["email"],
                "properties": {"email": {"type": "string"}},
            },
        ]
    }

    assert _is_required_object_schema(spec, schema) is True


def test_required_object_schema_rejects_array_or_optional_branch() -> None:
    spec = PaddleSpec({"openapi": "3.1.0"})

    assert (
        _is_required_object_schema(
            spec,
            {
                "anyOf": [
                    {"type": "object", "required": ["name"]},
                    {"type": "array", "items": {"type": "string"}},
                ]
            },
        )
        is False
    )
    assert _is_required_object_schema(spec, {"type": "object", "properties": {}}) is False
    assert (
        _is_required_object_schema(spec, {"required": ["name"], "properties": {"name": {}}})
        is False
    )


def test_write_success_aborts_and_is_never_expected() -> None:
    operation = Operation("POST", "/products", "create", "Create", "", ("Products",))
    result = ProbeResult(operation, "/products", 201, 0, "HTTP 201")

    assert _must_abort(result) is True
    assert _is_expected(result) is False


def test_permission_gap_is_not_complete_coverage() -> None:
    operation = Operation("GET", "/products", "list", "List", "", ("Products",))
    result = ProbeResult(operation, "/products", 403, 1, "HTTP 403")

    assert _must_abort(result) is False
    assert _is_expected(result) is False


def test_pathless_delete_is_not_a_safe_schema_probe() -> None:
    spec = PaddleSpec({"openapi": "3.1.0"})
    operation = Operation(
        "DELETE",
        "/everything",
        "delete-all",
        "Delete all",
        "",
        ("Danger",),
    )

    assert _unproven_write_operations(spec, [operation]) == [operation]


def test_unknown_future_write_path_parameter_is_refused() -> None:
    spec = PaddleSpec({"openapi": "3.1.0"})
    operation = Operation(
        "POST",
        "/settings/{user_controlled_name}",
        "update-setting",
        "Update setting",
        "",
        ("Settings",),
    )

    assert _unproven_write_operations(spec, [operation]) == [operation]


def test_probe_pins_sandbox_and_never_reports_captured_content(monkeypatch) -> None:
    captured: dict[str, object] = {}
    fake_secret = "pdl_sdbx_apikey_never-report-this-value"

    def run(command, **kwargs) -> subprocess.CompletedProcess[str]:
        captured["command"] = command
        captured["environment"] = kwargs["env"]
        return subprocess.CompletedProcess(command, 1, fake_secret, "")

    monkeypatch.setenv("PADDLE_API_KEY", fake_secret)
    monkeypatch.setattr("scripts.e2e_sandbox.subprocess.run", run)
    operation = Operation(
        "PATCH",
        "/products/{product_id}",
        "update",
        "Update",
        "",
        ("Products",),
    )

    result = _probe("/tmp/paddle", operation)

    command = captured["command"]
    environment = captured["environment"]
    assert command == [
        "/tmp/paddle",
        "request",
        "PATCH",
        f"/products/{INVALID_ID}",
        "--environment",
        "sandbox",
        "--yes",
        "--body",
        "[]",
    ]
    assert "PADDLE_API_KEY" not in environment
    assert fake_secret not in result.detail
