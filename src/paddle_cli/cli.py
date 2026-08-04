from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from pathlib import Path
from typing import Any

from rich.console import Console

from paddle_cli import __version__
from paddle_cli.client import PaddleClient, PaddleCliError
from paddle_cli.credentials import CredentialError, CredentialStore
from paddle_cli.spec import Operation, SpecError, SpecStore
from paddle_cli.ui import (
    confirm_execution,
    operations_table,
    render_response,
    run_interactive,
    run_key_check,
)

console = Console()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="paddle",
        description="Validate a Paddle API key or explore the Paddle Billing API.",
    )
    parser.add_argument("--version", action="version", version=f"Paddle CLI {__version__}")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("interactive", help="Open the interactive API navigator")

    auth = subparsers.add_parser("auth", help="Manage the saved Paddle API key")
    auth_subparsers = auth.add_subparsers(dest="auth_command", required=True)
    auth_subparsers.add_parser("login", help="Validate and save a new API key")
    auth_subparsers.add_parser("logout", help="Remove the saved API key")

    operations = subparsers.add_parser("operations", help="List operations in Paddle's API spec")
    operations.add_argument("--search", help="Filter by resource, operation, method, or path")
    operations.add_argument("--refresh", action="store_true", help="Download the latest API spec")

    request = subparsers.add_parser("request", help="Send one Paddle API request")
    request.add_argument("method", choices=["GET", "POST", "PATCH", "PUT", "DELETE"])
    request.add_argument("path", help="API path, for example /products")
    request.add_argument("--query", default="{}", help="Query parameters as a JSON object")
    request.add_argument("--body", help="JSON body or @path/to/file.json")
    request.add_argument("--environment", choices=["sandbox", "live"])
    request.add_argument("--yes", action="store_true", help="Execute writes without prompting")

    spec = subparsers.add_parser("spec", help="Manage the cached Paddle API specification")
    spec_subparsers = spec.add_subparsers(dest="spec_command", required=True)
    spec_subparsers.add_parser("update", help="Download the latest official specification")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    spec_store = SpecStore()
    credential_store = CredentialStore()
    try:
        if args.command is None:
            return run_key_check(credential_store)
        if args.command == "interactive":
            return run_interactive(spec_store, credential_store)
        if args.command == "auth" and args.auth_command == "login":
            return run_key_check(credential_store, force_prompt=True)
        if args.command == "auth" and args.auth_command == "logout":
            return _logout(credential_store)
        if args.command == "operations":
            return _list_operations(spec_store, args.search, refresh=args.refresh)
        if args.command == "request":
            return _request(args, credential_store)
        if args.command == "spec" and args.spec_command == "update":
            path = spec_store.update()
            count = len(spec_store.load().operations())
            console.print(f"Updated {path} with {count} Paddle API operations.")
            return 0
    except (CredentialError, PaddleCliError, SpecError, ValueError) as exc:
        console.print(f"[red]Error:[/red] {exc}", file=sys.stderr)
        return 1
    return 0


def _list_operations(store: SpecStore, search: str | None, *, refresh: bool) -> int:
    operations = store.load(refresh=refresh).operations()
    if search:
        phrase = search.lower()
        operations = [
            item
            for item in operations
            if phrase
            in " ".join(
                [item.method, item.path, item.operation_id, item.summary, *item.tags]
            ).lower()
        ]
    console.print(operations_table(operations))
    console.print(f"[dim]{len(operations)} operations[/dim]")
    return 0


def _request(args: argparse.Namespace, credential_store: CredentialStore) -> int:
    api_key = os.environ.get("PADDLE_API_KEY")
    environment = args.environment
    if not api_key:
        saved = credential_store.load()
        if saved is not None:
            api_key = saved.api_key
            environment = environment or saved.environment
        else:
            if not sys.stdin.isatty():
                raise PaddleCliError(
                    "Run 'paddle auth login' or set PADDLE_API_KEY for a noninteractive request."
                )
            api_key = getpass.getpass("Paddle API key: ")
    query = _json_object(args.query, "query")
    body = _body(args.body)
    client = PaddleClient(api_key, environment=environment)
    operation = Operation(
        method=args.method,
        path=args.path,
        operation_id="direct-request",
        summary="Direct API request",
        description="",
        tags=("Direct",),
    )
    if operation.is_write and not args.yes and not sys.stdin.isatty():
        raise PaddleCliError("Noninteractive writes require the explicit --yes flag.")
    if not confirm_execution(operation, client.key_info.environment, assume_yes=args.yes):
        console.print("Request canceled.")
        return 2
    response = client.request(operation, query=query, body=body)
    render_response(response)
    return 0 if response.succeeded else 1


def _logout(store: CredentialStore) -> int:
    if store.delete():
        console.print("Removed the saved Paddle API key from system credentials.")
    else:
        console.print("No Paddle API key is saved.")
    return 0


def _json_object(raw: str, name: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{name} is not valid JSON: {exc.msg}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a JSON object.")
    return value


def _body(raw: str | None) -> Any:
    if raw is None:
        return None
    if raw.startswith("@"):
        path = Path(raw[1:]).expanduser()
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ValueError(f"Could not read request body file: {exc}") from exc
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"body is not valid JSON: {exc.msg}") from exc


if __name__ == "__main__":
    raise SystemExit(main())
