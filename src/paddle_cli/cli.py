from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from paddle_cli import __version__
from paddle_cli.agent_skill import ensure_agent_skills
from paddle_cli.client import PaddleClient, PaddleCliError
from paddle_cli.credentials import (
    ACCOUNT_NAME,
    SERVICE_NAME,
    CredentialError,
    CredentialStore,
)
from paddle_cli.spec import Operation, SpecError, SpecStore, default_cache_path
from paddle_cli.ui import (
    confirm_execution,
    operations_table,
    render_response,
    run_doctor,
    run_interactive,
    run_login,
    run_whoami,
)

console = Console()
error_console = Console(stderr=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="paddle",
        description="Command line access to the Paddle Billing API.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""examples:
  paddle login
  paddle whoami
  paddle interactive
  paddle operations --search subscription
  paddle request GET /products

Run 'paddle help <command>' for command-specific help.""",
    )
    parser.add_argument("--version", action="version", version=f"Paddle CLI {__version__}")
    subparsers = parser.add_subparsers(dest="command")

    login = subparsers.add_parser(
        "login",
        help="Validate and securely save an API key",
        description="Validate a Paddle API key and save it in the system credential manager.",
    )
    key_input = login.add_mutually_exclusive_group()
    key_input.add_argument(
        "--key", help="API key to save (prefer the masked prompt or --key-stdin)"
    )
    key_input.add_argument(
        "--key-stdin",
        action="store_true",
        help="Read the API key from standard input without placing it in process arguments",
    )
    login.add_argument(
        "--environment",
        choices=["sandbox", "live"],
        help="Override environment detection, mainly for legacy keys",
    )

    subparsers.add_parser("logout", help="Remove the saved API key")

    whoami = subparsers.add_parser("whoami", help="Show local authentication status")
    whoami.add_argument(
        "--environment", choices=["sandbox", "live"], help="Override the selected environment"
    )

    doctor = subparsers.add_parser("doctor", help="Validate API connectivity and credentials")
    doctor.add_argument(
        "--environment", choices=["sandbox", "live"], help="Override the selected environment"
    )

    interactive = subparsers.add_parser("interactive", help="Open the interactive API navigator")
    interactive.add_argument(
        "--environment", choices=["sandbox", "live"], help="Override the selected environment"
    )

    subparsers.add_parser("config", help="Show credential storage and cache locations")

    help_parser = subparsers.add_parser("help", help="Show help for a command")
    help_parser.add_argument("topic", nargs="?", help="Command name")

    operations = subparsers.add_parser("operations", help="List operations in Paddle's API spec")
    operations.add_argument("--search", help="Filter by resource, operation, method, or path")
    operations.add_argument("--refresh", action="store_true", help="Download the latest API spec")

    request = subparsers.add_parser("request", help="Send one Paddle API request")
    request.add_argument("method", choices=["GET", "POST", "PATCH", "PUT", "DELETE"])
    request.add_argument("path", help="API path, for example /products")
    request.add_argument("--query", default="{}", help="Query parameters as a JSON object")
    request.add_argument("--body", help="JSON body or @path/to/file.json")
    request.add_argument(
        "--environment", choices=["sandbox", "live"], help="Override the selected environment"
    )
    request.add_argument("--yes", action="store_true", help="Execute writes without prompting")

    spec = subparsers.add_parser("spec", help="Manage the cached Paddle API specification")
    spec_subparsers = spec.add_subparsers(dest="spec_command", required=True)
    spec_subparsers.add_parser("update", help="Download the latest official specification")
    return parser


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        ensure_agent_skills()
    parser = build_parser()
    args = parser.parse_args(argv)
    spec_store = SpecStore()
    credential_store = CredentialStore()
    try:
        if args.command is None:
            parser.print_help()
            return 0
        if args.command == "help":
            return _show_help(parser, args.topic)
        if args.command == "login":
            api_key = args.key
            if args.key_stdin:
                api_key = sys.stdin.read().strip()
                if not api_key:
                    raise PaddleCliError("No API key was provided on standard input.")
            if api_key is None and not sys.stdin.isatty():
                raise PaddleCliError(
                    "Interactive input is unavailable. Pipe the key to 'paddle login --key-stdin'."
                )
            return run_login(
                credential_store,
                api_key=api_key,
                environment=args.environment,
            )
        if args.command == "logout":
            return _logout(credential_store)
        if args.command == "whoami":
            return run_whoami(credential_store, environment=args.environment)
        if args.command == "doctor":
            return run_doctor(credential_store, environment=args.environment)
        if args.command == "interactive":
            return run_interactive(
                spec_store,
                credential_store,
                environment=args.environment,
            )
        if args.command == "config":
            return _show_config(credential_store)
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
        error_console.print(f"[red]Error:[/red] {exc}")
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
    resolved = credential_store.resolve(args.environment)
    if resolved is None:
        raise PaddleCliError("Authentication required. Run 'paddle login' or set PADDLE_API_KEY.")
    query = _json_object(args.query, "query")
    body = _body(args.body)
    client = PaddleClient(resolved.api_key, environment=resolved.environment)
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
        console.print(f"Removed the saved Paddle API key from {store.backend_name()}.")
    else:
        console.print("No saved Paddle API key found. Already logged out.")
    if os.environ.get("PADDLE_API_KEY"):
        console.print(
            "[yellow]PADDLE_API_KEY is still set for this process and overrides "
            "saved login.[/yellow]"
        )
    return 0


def _show_config(store: CredentialStore) -> int:
    details = Table.grid(padding=(0, 2))
    details.add_column(style="bold")
    details.add_column(overflow="fold")
    details.add_row("Credential storage", store.backend_name())
    details.add_row("Keychain service", SERVICE_NAME)
    details.add_row("Keychain account", ACCOUNT_NAME)
    try:
        saved_status = "Yes" if store.load() is not None else "No"
    except CredentialError:
        saved_status = "Unavailable"
    details.add_row("Saved credential", saved_status)
    console.print(Panel.fit(details, title="Paddle CLI configuration", border_style="cyan"))
    console.print(f"OpenAPI cache  {default_cache_path()}", soft_wrap=True)
    return 0


def _show_help(parser: argparse.ArgumentParser, topic: str | None) -> int:
    if topic is None:
        parser.print_help()
        return 0
    subparsers = next(
        (action for action in parser._actions if isinstance(action, argparse._SubParsersAction)),
        None,
    )
    command_parser = subparsers.choices.get(topic) if subparsers else None
    if command_parser is None:
        error_console.print(f"[red]Unknown command:[/red] {topic}")
        return 2
    command_parser.print_help()
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
