from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from InquirerPy import inquirer
from InquirerPy.base.control import Choice
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from paddle_cli.agent_skill import agent_skill_targets, ensure_agent_skills
from paddle_cli.client import PaddleClient, PaddleCliError, inspect_api_key
from paddle_cli.credentials import CredentialError, CredentialStore
from paddle_cli.spec import Operation, PaddleSpec, Parameter, SpecError, SpecStore

console = Console()
error_console = Console(stderr=True)


def run_login(
    store: CredentialStore,
    *,
    api_key: str | None = None,
    environment: str | None = None,
    prompt_for_skill: bool = False,
) -> int:
    console.print(
        Panel.fit(
            "[bold]Paddle Authentication[/bold]\nValidate and securely save an API key.",
            border_style="cyan",
        )
    )
    try:
        if api_key is None:
            api_key, environment = _prompt_api_key(environment)
        client = PaddleClient(api_key, environment=environment)
        with console.status("Validating with Paddle..."):
            response = client.verify()
        if not response.succeeded:
            error_console.print(
                Panel.fit(
                    f"[bold red]API key is not valid[/bold red]\n"
                    f"Paddle returned {response.status_code} {response.reason}.",
                    border_style="red",
                )
            )
            return 1

        store.save(api_key, client.key_info.environment)
        _render_key_details(client, response)
        if prompt_for_skill:
            _offer_agent_skill_install()
        console.print(
            "[green]API key saved in your system credential manager.[/green]\n\n"
            "Next steps:\n"
            "  [cyan]paddle whoami[/cyan]      Show local authentication status\n"
            "  [cyan]paddle interactive[/cyan] Open the API navigator\n"
            "  [cyan]paddle operations[/cyan]  List available API operations"
        )
        return 0
    except (KeyboardInterrupt, EOFError):
        console.print("\n[dim]Login canceled.[/dim]")
        return 130
    except (CredentialError, PaddleCliError) as exc:
        error_console.print(f"[red]Login failed:[/red] {exc}")
        return 1


def run_skill_install() -> int:
    """Prompt for agent targets and install the bundled Paddle skill."""
    try:
        _install_agent_skill()
        return 0
    except (KeyboardInterrupt, EOFError):
        console.print("\n[dim]Skill installation canceled.[/dim]")
        return 130


def _offer_agent_skill_install() -> None:
    try:
        answer = inquirer.text(
            message="Install the Paddle skill for your AI agents?",
            instruction="(Y/n)",
            validate=_is_yes_no_answer,
            invalid_message="Enter y or n.",
            mandatory=False,
        ).execute()
        if _yes_no_answer(answer, default=True):
            _install_agent_skill()
        else:
            console.print(
                "[dim]Skipped. Run [bold]paddle skill install[/bold] whenever you want.[/dim]"
            )
    except (KeyboardInterrupt, EOFError):
        console.print(
            "\n[dim]Skipped skill installation. Your API key is already saved.[/dim]"
        )


def _is_yes_no_answer(answer: str) -> bool:
    return answer.strip().lower() in {"", "y", "yes", "n", "no"}


def _yes_no_answer(answer: str, *, default: bool) -> bool:
    normalized = answer.strip().lower()
    if not normalized:
        return default
    return normalized in {"y", "yes"}


def _install_agent_skill() -> None:
    targets = agent_skill_targets()
    has_detected_agent = any(target.detected for target in targets)
    choices = [
        Choice(
            value=target.agent,
            name=f"{target.agent}{' (detected)' if target.detected else ''}",
            enabled=target.detected
            or (target.agent == "Universal Agents" and not has_detected_agent),
        )
        for target in targets
    ]
    selected = inquirer.checkbox(
        message="Which agents should use the Paddle skill?",
        choices=choices,
        instruction="Space to select, Enter to install",
    ).execute()
    if not selected:
        console.print("[dim]No agents selected. Nothing was installed.[/dim]")
        return

    installed = ensure_agent_skills(agents=selected)
    if installed:
        names = ", ".join(item.agent for item in installed)
        console.print(f"[green]Installed the Paddle skill for {names}.[/green]")
    else:
        console.print("[green]The Paddle skill is already up to date for those agents.[/green]")


def run_whoami(store: CredentialStore, *, environment: str | None = None) -> int:
    try:
        resolved = store.resolve(environment)
        if resolved is None:
            error_console.print(
                "[red]Not authenticated.[/red]\nRun [bold]paddle login[/bold] to get started."
            )
            return 1
        client = PaddleClient(resolved.api_key, environment=resolved.environment)
        details = Table.grid(padding=(0, 2))
        details.add_column(style="bold")
        details.add_column()
        details.add_row("Status", "[bold green]Configured[/bold green]")
        details.add_row("Environment", client.key_info.environment.title())
        details.add_row("Key ID", client.key_info.entity_id or "Legacy key")
        details.add_row("Source", resolved.source)
        if resolved.source == "system credential manager":
            details.add_row("Storage", store.backend_name())
        details.add_row("API endpoint", client.base_url)
        console.print(Panel.fit(details, title="Paddle credential", border_style="green"))
        console.print("Run [bold]paddle doctor[/bold] to validate this credential with Paddle.")
        return 0
    except (CredentialError, PaddleCliError) as exc:
        error_console.print(f"[red]Authentication error:[/red] {exc}")
        return 1


def run_doctor(store: CredentialStore, *, environment: str | None = None) -> int:
    try:
        resolved = store.resolve(environment)
        if resolved is None:
            error_console.print(
                "[red]Not authenticated.[/red]\nRun [bold]paddle login[/bold] to get started."
            )
            return 1
        client = PaddleClient(resolved.api_key, environment=resolved.environment)
        with console.status("Checking Paddle API connectivity..."):
            response = client.verify()
        if not response.succeeded:
            error_console.print(
                Panel.fit(
                    f"[bold red]Paddle API check failed[/bold red]\n"
                    f"Paddle returned {response.status_code} {response.reason}.",
                    border_style="red",
                )
            )
            return 1
        _render_key_details(client, response, source=resolved.source)
        return 0
    except (CredentialError, PaddleCliError) as exc:
        error_console.print(f"[red]Paddle API check failed:[/red] {exc}")
        return 1


def _render_key_details(client: PaddleClient, response: Any, *, source: str | None = None) -> None:
    details = Table.grid(padding=(0, 2))
    details.add_column(style="bold")
    details.add_column()
    details.add_row("Status", "[bold green]Valid[/bold green]")
    details.add_row("Environment", client.key_info.environment.title())
    details.add_row("Name", "Available in Paddle dashboard")
    details.add_row("Key ID", client.key_info.entity_id or "Legacy key")
    details.add_row("Format", "Modern" if client.key_info.modern else "Legacy")
    if source:
        details.add_row("Source", source)
    details.add_row("Permissions", "Available in Paddle dashboard")
    details.add_row("Expires", "Available in Paddle dashboard")
    details.add_row("API endpoint", client.base_url)
    if response.request_id:
        details.add_row("Request ID", response.request_id)
    console.print(Panel.fit(details, title="API key is valid", border_style="green"))


def _prompt_api_key(environment: str | None = None) -> tuple[str, str | None]:
    api_key = inquirer.secret(
        message="Paddle API key:",
        instruction="(input is hidden and saved after validation)",
    ).execute()
    try:
        inspect_api_key(api_key, environment)
    except PaddleCliError as exc:
        if "does not identify an environment" not in str(exc):
            raise
        environment = inquirer.select(
            message="API environment:",
            choices=["sandbox", "live"],
        ).execute()
    return api_key, environment


def run_interactive(
    spec_store: SpecStore,
    credential_store: CredentialStore,
    *,
    environment: str | None = None,
) -> int:
    console.print(
        Panel.fit(
            "[bold]Paddle CLI[/bold]\nExplore and call the complete Paddle Billing API.",
            border_style="cyan",
        )
    )
    try:
        client = _authenticate(credential_store, environment=environment)
        spec = _load_spec(spec_store)
        while True:
            result = _main_menu(spec, client)
            if result == "quit":
                return 0
            if result == "refresh":
                spec = _load_spec(spec_store, refresh=True)
    except (KeyboardInterrupt, EOFError):
        console.print("\n[dim]Exited without changing credentials or local configuration.[/dim]")
        return 130
    except (CredentialError, PaddleCliError, SpecError) as exc:
        error_console.print(f"[red]Error:[/red] {exc}")
        return 1


def _load_spec(store: SpecStore, *, refresh: bool = False) -> PaddleSpec:
    message = "Refreshing Paddle API reference..." if refresh else "Loading Paddle API reference..."
    with console.status(message):
        spec = store.load(refresh=refresh)
    count = len(spec.operations())
    console.print(f"[dim]Loaded {count} operations from Paddle's OpenAPI specification.[/dim]")
    return spec


def _authenticate(store: CredentialStore, *, environment: str | None = None) -> PaddleClient:
    resolved = store.resolve(environment)
    if resolved is None:
        raise PaddleCliError("Authentication required. Run 'paddle login' to save an API key.")
    client = PaddleClient(resolved.api_key, environment=resolved.environment)
    with console.status(f"Checking {client.key_info.environment} credentials..."):
        response = client.verify()
    if not response.succeeded:
        raise PaddleCliError(
            f"Paddle rejected the current credential with "
            f"{response.status_code} {response.reason}. Run 'paddle login' to replace it."
        )
    color = "red" if client.key_info.environment == "live" else "green"
    console.print(
        f"Connected to [{color}]{client.key_info.environment}[/{color}] using {resolved.source}."
    )
    return client


def _main_menu(spec: PaddleSpec, client: PaddleClient) -> str:
    while True:
        action = inquirer.select(
            message=f"Paddle {client.key_info.environment}:",
            choices=[
                Choice("browse", "Browse by resource"),
                Choice("search", "Search all operations"),
                Choice("raw", "Send a raw API request"),
                Choice("refresh", "Refresh API reference"),
                Choice("quit", "Quit"),
            ],
        ).execute()
        if action in {"quit", "refresh"}:
            return action
        if action == "browse":
            operation = _browse(spec)
            if operation:
                _run_operation(spec, client, operation)
        elif action == "search":
            operation = _search(spec)
            if operation:
                _run_operation(spec, client, operation)
        elif action == "raw":
            _run_raw(client)


def _browse(spec: PaddleSpec) -> Operation | None:
    grouped: dict[str, list[Operation]] = {}
    for operation in spec.operations():
        grouped.setdefault(operation.tags[0], []).append(operation)
    tag = inquirer.fuzzy(
        message="Resource:",
        choices=[Choice(name, f"{name} ({len(items)})") for name, items in sorted(grouped.items())],
        mandatory=False,
    ).execute()
    if not tag:
        return None
    return inquirer.fuzzy(
        message="Operation:",
        choices=[{"value": operation, "name": operation.label} for operation in grouped[tag]],
        mandatory=False,
    ).execute()


def _search(spec: PaddleSpec) -> Operation | None:
    phrase = inquirer.text(message="Search:").execute().strip().lower()
    if not phrase:
        return None
    matches = [
        operation
        for operation in spec.operations()
        if phrase
        in " ".join(
            [
                operation.operation_id,
                operation.summary,
                operation.path,
                *operation.tags,
            ]
        ).lower()
    ]
    if not matches:
        console.print("[yellow]No matching operations.[/yellow]")
        return None
    return inquirer.fuzzy(
        message=f"Operation ({len(matches)} matches):",
        choices=[{"value": operation, "name": operation.label} for operation in matches],
        mandatory=False,
    ).execute()


def _run_operation(spec: PaddleSpec, client: PaddleClient, operation: Operation) -> None:
    _show_operation(operation)
    path_parameters: dict[str, Any] = {}
    query: dict[str, Any] = {}
    headers: dict[str, str] = {}
    by_location = {"path": path_parameters, "query": query, "header": headers}
    for location, target in by_location.items():
        parameters = [item for item in operation.parameters if item.location == location]
        selected = _choose_parameters(parameters)
        for parameter in selected:
            target[parameter.name] = _prompt_parameter(parameter)

    body = None
    if operation.request_body is not None:
        body = _prompt_body(spec, operation)
        if body is _CANCEL:
            return

    _show_preview(client, operation, path_parameters, query, headers, body)
    if not confirm_execution(operation, client.key_info.environment):
        console.print("[dim]Request canceled.[/dim]")
        return
    with console.status("Calling Paddle..."):
        try:
            response = client.request(
                operation,
                path_parameters=path_parameters,
                query=query,
                headers=headers,
                body=body,
            )
        except PaddleCliError as exc:
            console.print(f"[red]Request failed:[/red] {exc}")
            return
    render_response(response)
    while (
        response.next_url
        and inquirer.confirm(message="Fetch the next page?", default=True).execute()
    ):
        try:
            with console.status("Fetching the next page..."):
                response = client.request(
                    operation,
                    path_parameters=path_parameters,
                    query=pagination_query(response.next_url),
                    headers=headers,
                    body=body,
                )
        except PaddleCliError as exc:
            console.print(f"[red]Request failed:[/red] {exc}")
            return
        render_response(response)


def _show_operation(operation: Operation) -> None:
    details = Text()
    details.append(f"{operation.method} ", style="bold cyan")
    details.append(operation.path, style="bold")
    details.append(f"\n{operation.summary}")
    if operation.permission:
        details.append(f"\nPermission: {operation.permission}", style="yellow")
    if operation.docs_url:
        details.append(f"\nDocs: {operation.docs_url}", style="dim")
    console.print(Panel(details, title=operation.tags[0]))
    if operation.description:
        console.print(Markdown(operation.description))


def _choose_parameters(parameters: list[Parameter]) -> list[Parameter]:
    required = [item for item in parameters if item.required]
    optional = [item for item in parameters if not item.required]
    if not optional:
        return required
    choices = [
        {
            "value": item,
            "name": f"{item.name}"
            + (f"  {shorten(item.description, 70)}" if item.description else ""),
        }
        for item in optional
    ]
    selected = inquirer.checkbox(
        message=f"Optional {optional[0].location} parameters:",
        choices=choices,
        instruction="(space to select, enter to continue)",
    ).execute()
    return [*required, *selected]


def _prompt_parameter(parameter: Parameter) -> Any:
    schema = parameter.schema
    enum = schema.get("enum")
    message = f"{parameter.name}{' (required)' if parameter.required else ''}:"
    if enum:
        return inquirer.select(message=message, choices=list(enum)).execute()
    if schema.get("type") == "boolean":
        return inquirer.select(message=message, choices=[True, False]).execute()
    default = parameter.example
    if default is None:
        default = schema.get("default", "")
    while True:
        raw = inquirer.text(
            message=message, default=str(default) if default != "" else ""
        ).execute()
        if parameter.required and not raw.strip():
            console.print("[red]A value is required.[/red]")
            continue
        try:
            return parse_typed_value(raw, schema)
        except ValueError as exc:
            console.print(f"[red]{exc}[/red]")


_CANCEL = object()


def _prompt_body(spec: PaddleSpec, operation: Operation) -> Any:
    example = spec.example_for(operation.request_body)
    if example not in (None, "", {}, []):
        console.print("[bold]Request body template[/bold]")
        console.print(Syntax(json.dumps(example, indent=2), "json", word_wrap=True))
    choices = [Choice("inline", "Enter JSON")]
    choices.append(Choice("file", "Load JSON from a file"))
    if not operation.request_body_required:
        choices.append(Choice("none", "Send no request body"))
    choices.append(Choice("cancel", "Cancel"))
    mode = inquirer.select(message="Request body:", choices=choices).execute()
    if mode == "cancel":
        return _CANCEL
    if mode == "none":
        return None
    if mode == "file":
        path = Path(inquirer.filepath(message="JSON file:", only_files=True).execute()).expanduser()
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            console.print(f"[red]Could not read JSON body:[/red] {exc}")
            return _CANCEL
    default = json.dumps(example, separators=(",", ":")) if example not in (None, "") else "{}"
    while True:
        raw = inquirer.text(message="JSON:", default=default).execute()
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            console.print(f"[red]Invalid JSON at character {exc.pos}: {exc.msg}[/red]")


def _show_preview(
    client: PaddleClient,
    operation: Operation,
    path_parameters: dict[str, Any],
    query: dict[str, Any],
    headers: dict[str, str],
    body: Any,
) -> None:
    path = operation.path
    for name, value in path_parameters.items():
        path = path.replace("{" + name + "}", str(value))
    preview = {
        "method": operation.method,
        "url": client.base_url + path,
        "query": query or None,
        "headers": headers or None,
        "body": body,
    }
    console.print(Panel(Syntax(json.dumps(preview, indent=2), "json"), title="Request preview"))


def confirm_execution(operation: Operation, environment: str, *, assume_yes: bool = False) -> bool:
    if not operation.is_write:
        return True
    if assume_yes:
        return True
    if environment == "live":
        console.print("[bold red]This request can change live Paddle data.[/bold red]")
        typed = inquirer.text(message="Type LIVE to execute:").execute()
        return typed == "LIVE"
    return bool(inquirer.confirm(message="Execute this sandbox write?", default=False).execute())


def render_response(response: Any) -> None:
    color = "green" if response.succeeded else "red"
    title = f"{response.status_code} {response.reason} · {response.elapsed_ms} ms"
    if response.request_id:
        title += f" · request {response.request_id}"
    if isinstance(response.body, (dict, list)):
        content: Any = Syntax(json.dumps(response.body, indent=2), "json", word_wrap=True)
    else:
        content = str(response.body)
    console.print(Panel(content, title=title, border_style=color))


def _run_raw(client: PaddleClient) -> None:
    method = inquirer.select(
        message="HTTP method:", choices=["GET", "POST", "PATCH", "PUT", "DELETE"]
    ).execute()
    path = inquirer.text(
        message="API path (for example /products):",
        default="",
    ).execute().strip()
    query = _prompt_json_object("Query JSON (blank for none):", allow_blank=True)
    if query is _CANCEL:
        return
    body: Any = None
    if method not in {"GET", "DELETE"}:
        body = _prompt_json_object("Body JSON (blank for none):", allow_blank=True)
        if body is _CANCEL:
            return
    operation = Operation(
        method=method,
        path=path,
        operation_id="raw-request",
        summary="Raw API request",
        description="",
        tags=("Raw",),
    )
    _show_preview(client, operation, {}, query, {}, body)
    if not confirm_execution(operation, client.key_info.environment):
        console.print("[dim]Request canceled.[/dim]")
        return
    try:
        with console.status("Calling Paddle..."):
            response = client.request(operation, query=query, body=body)
    except PaddleCliError as exc:
        console.print(f"[red]Request failed:[/red] {exc}")
        return
    render_response(response)


def _prompt_json_object(message: str, *, allow_blank: bool) -> dict[str, Any] | object:
    while True:
        raw = inquirer.text(message=message).execute().strip()
        if allow_blank and not raw:
            return {}
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            console.print(f"[red]Invalid JSON at character {exc.pos}: {exc.msg}[/red]")
            continue
        if isinstance(value, dict):
            return value
        console.print("[red]Enter a JSON object.[/red]")


def parse_typed_value(raw: str, schema: dict[str, Any]) -> Any:
    schema_type = schema.get("type")
    if schema_type == "integer":
        try:
            return int(raw)
        except ValueError as exc:
            raise ValueError("Enter a whole number.") from exc
    if schema_type == "number":
        try:
            return float(raw)
        except ValueError as exc:
            raise ValueError("Enter a number.") from exc
    if schema_type == "boolean":
        if raw.lower() in {"true", "1", "yes"}:
            return True
        if raw.lower() in {"false", "0", "no"}:
            return False
        raise ValueError("Enter true or false.")
    if schema_type in {"array", "object"}:
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError("Enter valid JSON.") from exc
        if schema_type == "array" and not isinstance(value, list):
            raise ValueError("Enter a JSON array.")
        if schema_type == "object" and not isinstance(value, dict):
            raise ValueError("Enter a JSON object.")
        return value
    return raw


def pagination_query(next_url: str) -> dict[str, Any]:
    parsed = urlparse(next_url)
    return {name: values[-1] for name, values in parse_qs(parsed.query).items()}


def shorten(value: str, length: int) -> str:
    normalized = " ".join(value.split())
    return normalized if len(normalized) <= length else normalized[: length - 1] + "…"


def operations_table(operations: list[Operation]) -> Table:
    table = Table(show_header=True, header_style="bold")
    table.add_column("Method", no_wrap=True)
    table.add_column("Resource")
    table.add_column("Operation")
    table.add_column("Path")
    for operation in operations:
        table.add_row(operation.method, operation.tags[0], operation.summary, operation.path)
    return table
