from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass

from paddle_cli import __version__
from paddle_cli.client import PaddleClient
from paddle_cli.credentials import CredentialStore
from paddle_cli.spec import Operation, PaddleSpec, SpecStore, default_cache_path

INVALID_ID = "paddle-cli-e2e-invalid-id"
PATH_PARAMETER = re.compile(r"\{([^}]+)\}")
HTTP_STATUS = re.compile(r"\b([1-5]\d{2}) [^·\r\n]+ ·")
PUBLIC_READ_PATHS = {"/event-types", "/ips", "/simulation-types"}
SAFE_REJECTION_STATUSES = {400, 404, 422}


@dataclass(frozen=True)
class ProbeResult:
    operation: Operation
    path: str
    status: int | None
    return_code: int
    detail: str


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Safely route-probe Paddle's OpenAPI operations through the installed CLI."
    )
    parser.add_argument(
        "--include-write-probes",
        action="store_true",
        help="Probe writes with invalid IDs and structurally invalid JSON bodies.",
    )
    args = parser.parse_args(argv)

    paddle = shutil.which("paddle")
    if paddle is None:
        parser.error("The installed 'paddle' executable was not found on PATH.")

    os.environ.pop("PADDLE_API_KEY", None)
    credential = CredentialStore().resolve()
    if credential is None:
        parser.error("No saved credential. Run 'paddle login' first.")
    client = PaddleClient(credential.api_key, environment=credential.environment)
    if client.key_info.environment != "sandbox":
        parser.error("Refusing to probe write routes outside Paddle sandbox.")

    installed_version = subprocess.run(
        [paddle, "--version"],
        capture_output=True,
        check=False,
        text=True,
        timeout=10,
    ).stdout.strip()
    if installed_version != f"Paddle CLI {__version__}":
        parser.error(
            f"Installed executable is {installed_version or 'unreadable'}, "
            f"but this harness is version {__version__}. Reinstall first."
        )

    spec_path = default_cache_path()
    spec = SpecStore().load()
    operations = spec.operations()
    operation_pairs = {(operation.method, operation.path) for operation in operations}
    if len(operation_pairs) != len(operations):
        parser.error("The cached specification contains duplicate method/path operations.")
    writes_without_ids = [
        operation for operation in operations if operation.is_write and "{" not in operation.path
    ]
    unsafe_writes = [
        operation
        for operation in writes_without_ids
        if operation.method == "DELETE"
        or not operation.request_body_required
        or not _is_required_object_schema(spec, operation.request_body)
    ]
    if unsafe_writes:
        names = ", ".join(f"{item.method} {item.path}" for item in unsafe_writes)
        parser.error(f"Refusing structurally unproven write probes: {names}")

    selected = [
        operation for operation in operations if args.include_write_probes or not operation.is_write
    ]
    results: list[ProbeResult] = []
    for operation in selected:
        result = _probe(paddle, operation)
        results.append(result)
        status = str(result.status) if result.status is not None else "CLI_ERROR"
        print(f"{status:>9}  {result.operation.method:<6} {result.operation.path}")
        if _must_abort(result):
            print("Safety or connectivity stop triggered; remaining probes were not run.")
            break

    unsafe_successes = [
        result
        for result in results
        if result.operation.is_write and result.status is not None and 200 <= result.status < 300
    ]
    server_errors = [
        result for result in results if result.status is not None and result.status >= 500
    ]
    cli_errors = [result for result in results if result.status is None]
    unexpected_statuses = [result for result in results if not _is_expected(result)]
    status_counts: dict[int, int] = {}
    for result in results:
        if result.status is not None:
            status_counts[result.status] = status_counts.get(result.status, 0) + 1

    print()
    print(f"Executable:            {paddle}")
    print(f"CLI version:           {installed_version}")
    print(f"OpenAPI SHA-256:       {hashlib.sha256(spec_path.read_bytes()).hexdigest()}")
    print(f"Operations discovered: {len(operations)}")
    print(f"Operations probed:    {len(results)}")
    print(f"HTTP statuses:        {dict(sorted(status_counts.items()))}")
    print(f"CLI errors:           {len(cli_errors)}")
    print(f"Server errors:        {len(server_errors)}")
    print(f"Unsafe write success: {len(unsafe_successes)}")
    print(f"Unexpected status:    {len(unexpected_statuses)}")

    failures = list(
        dict.fromkeys([*cli_errors, *server_errors, *unsafe_successes, *unexpected_statuses])
    )
    if len(results) != len(selected):
        failures.append(results[-1])
    if failures:
        print("\nFailures:", file=sys.stderr)
        for result in failures:
            print(
                f"  {result.operation.method} {result.operation.path}: {result.detail}",
                file=sys.stderr,
            )
        return 1
    return 0


def _probe(paddle: str, operation: Operation) -> ProbeResult:
    path = PATH_PARAMETER.sub(
        INVALID_ID,
        operation.path,
    )
    command = [
        paddle,
        "request",
        operation.method,
        path,
        "--environment",
        "sandbox",
        "--yes",
    ]
    if (
        operation.method == "GET"
        and "{" not in operation.path
        and any(parameter.name == "per_page" for parameter in operation.parameters)
    ):
        command.extend(["--query", '{"per_page":"not-an-integer"}'])
    if operation.method in {"POST", "PATCH", "PUT"}:
        command.extend(["--body", "[]"])

    environment = os.environ.copy()
    environment.pop("PADDLE_API_KEY", None)
    environment.pop("PYTHON_KEYRING_BACKEND", None)
    environment["NO_COLOR"] = "1"
    environment["COLUMNS"] = "120"
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            check=False,
            env=environment,
            text=True,
            timeout=45,
        )
    except subprocess.TimeoutExpired:
        return ProbeResult(operation, path, None, 124, "timed out after 45 seconds")

    output = f"{completed.stdout}\n{completed.stderr}"
    status_match = HTTP_STATUS.search(output)
    status = int(status_match.group(1)) if status_match else None
    if status is None:
        detail = f"command exited {completed.returncode} without recognizable HTTP status"
    else:
        detail = f"HTTP {status}"
    return ProbeResult(operation, path, status, completed.returncode, detail)


def _is_required_object_schema(spec: PaddleSpec, raw_schema: dict[str, object] | None) -> bool:
    if not isinstance(raw_schema, dict):
        return False
    schema = spec.resolve(raw_schema)
    if not isinstance(schema, dict):
        return False
    for combinator in ("oneOf", "anyOf"):
        if combinator in schema:
            branches = schema[combinator]
            return bool(branches) and all(
                _is_required_object_schema(spec, branch)
                for branch in branches
                if isinstance(branch, dict)
            ) and all(isinstance(branch, dict) for branch in branches)
    if "allOf" in schema:
        branches = schema["allOf"]
        return bool(branches) and all(
            _is_required_object_schema(spec, branch)
            for branch in branches
            if isinstance(branch, dict)
        ) and all(isinstance(branch, dict) for branch in branches)
    is_object = schema.get("type") == "object" or "properties" in schema
    required = schema.get("required")
    return is_object and isinstance(required, list) and bool(required)


def _is_expected(result: ProbeResult) -> bool:
    if result.status is None:
        return False
    expected_exit = 0 if 200 <= result.status < 300 else 1
    if result.return_code != expected_exit:
        return False
    if result.operation.is_write:
        return result.status in SAFE_REJECTION_STATUSES
    if result.operation.path in PUBLIC_READ_PATHS:
        return 200 <= result.status < 300
    return result.status in SAFE_REJECTION_STATUSES


def _must_abort(result: ProbeResult) -> bool:
    if result.status is None:
        return True
    if result.operation.is_write and 200 <= result.status < 300:
        return True
    return result.status in {401, 429} or result.status >= 500


if __name__ == "__main__":
    raise SystemExit(main())
