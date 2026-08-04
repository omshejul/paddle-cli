# Paddle CLI

A secure API-key validator and interactive terminal client for the complete
Paddle Billing API.

Paddle CLI reads Paddle's official OpenAPI 3.1 specification at runtime. New API
operations appear after a spec refresh, without waiting for a CLI release.

## Features

- **Use the complete Paddle API from one command.** Browse and call every operation
  in Paddle's official OpenAPI specification, then refresh the specification when
  Paddle adds new endpoints.
- **Works for both people and automation.** Explore resources interactively, run
  direct commands in a terminal, or use the same CLI in scripts and CI jobs.
- **Safer sandbox and live workflows.** The CLI detects the environment, previews
  requests, confirms writes, and requires an explicit `LIVE` confirmation for
  production changes.
- **Your API key stays on your machine.** Keys are validated before saving and
  stored in macOS Keychain, Windows Credential Locker, or Linux Secret Service.
- **Deterministic and inspectable.** A command always maps to a visible HTTP
  method, path, query, and body, with Paddle's response and request ID shown back
  to you.
- **Useful even before the CLI is updated.** Raw requests let you call a new API
  endpoint immediately, while specification refresh makes it browsable without a
  package release.

### Paddle CLI compared with MCP

| Capability | Paddle CLI | Paddle MCP server |
| --- | --- | --- |
| Run directly from a terminal | Yes, with one `paddle` command | No, requires an MCP client |
| Use without an AI model | Yes | Possible with development tools, but not the normal workflow |
| Use in shell scripts and CI | Native commands, exit codes, and standard input | Requires an MCP client or adapter |
| Repeat and review an action | Save the exact command in code or shell history | Depends on the MCP client retaining the tool call |
| Keep the API key in the operating system credential manager | Built in | Depends on how the MCP server stores credentials |
| Preview requests and protect live writes | Built-in request preview, write confirmation, and `LIVE` gate | Depends on the MCP server implementation |
| Call an endpoint not yet modeled by the tool | Yes, using a raw request | Only if the server exposes a generic request tool |
| Pick and combine actions from natural language | No built-in model | Native use case for MCP and AI clients |
| Provide structured tools to an AI agent | Possible through shell access | Native MCP capability |
| Browse Paddle operations interactively | Built-in terminal navigator and fuzzy search | Usually handled through the AI client |

#### What both can do

| Shared capability | Notes |
| --- | --- |
| Call Paddle sandbox and live APIs | Both ultimately send requests to Paddle's API endpoints. |
| Read and change Paddle resources | Available operations depend on the API key's permissions. |
| Work with products, prices, customers, subscriptions, and transactions | Both can cover resources exposed by the Paddle API. |
| Use Paddle API keys | Paddle authenticates and authorizes every request. |
| Return Paddle responses and request IDs | The presentation differs, but the underlying response comes from Paddle. |
| Be used by an AI agent | An agent can run CLI commands or invoke MCP tools. |
| Access only API-supported workflows | Neither can perform dashboard-only actions unless separate browser automation is added. |

Use the CLI for direct control, local credentials, scripts, and reproducible
operations. Use MCP when natural-language discovery and multi-tool AI workflows
matter more than terminal-native execution.

Paddle CLI covers operations present in the official Paddle Billing OpenAPI
specification. Dashboard-only workflows are outside the Paddle API and therefore
outside this CLI.

## Install from the private repository

Requires Python 3.11 or newer and [uv](https://docs.astral.sh/uv/).
Private-repository collaborators should first configure GitHub authentication for
Git, then install the CLI:

```sh
gh auth setup-git
uv tool install "git+https://github.com/omshejul/paddle-cli.git@main"
```

Running the same install command again does not reinstall an unchanged tool. To
fetch current `main` and replace the existing installation:

```sh
uv tool install --force-reinstall \
  "git+https://github.com/omshejul/paddle-cli.git@main"
```

For a reproducible installation, replace `main` with a full commit SHA. Remove
the tool with `uv tool uninstall paddle-api-cli`.

During local development:

```sh
uv sync
uv run paddle
```

## Get started

```sh
paddle login
```

`paddle login` prompts for a key using masked input, verifies it with Paddle's
permissionless `GET /event-types` endpoint, and saves it in macOS Keychain,
Windows Credential Locker, or a supported Linux Secret Service. The CLI never
displays the secret or writes it to a plain-text configuration file.

Running `paddle` without a command shows help and examples. It never prompts or
makes a network request.

```sh
paddle
paddle whoami
paddle doctor
```

- `paddle whoami` reports the local credential source without calling Paddle.
- `paddle doctor` validates the credential and Paddle API connectivity.

Modern keys select their own environment:

- `pdl_sdbx_...` uses `https://sandbox-api.paddle.com`
- `pdl_live_...` uses `https://api.paddle.com`

Legacy keys do not encode an environment, so the CLI asks you to choose one.

Paddle does not expose the current key's dashboard name, description,
permissions, or expiration through the API. The validator labels those fields as
dashboard-only instead of guessing.

Replace or remove the saved key explicitly:

```sh
paddle login
paddle logout
```

For noninteractive setup, `paddle login --key ...` is available, but the masked
prompt is safer because command arguments may be retained in shell history.
Automation can avoid process arguments by sending the key on standard input:

```sh
security find-generic-password -w -s your-paddle-key | paddle login --key-stdin
```

## Authentication precedence

API commands resolve credentials in this order:

1. `PADDLE_API_KEY` for the current process.
2. The API key saved by `paddle login`.

An environment variable is a temporary override and is never saved. If neither
source exists, authenticated commands return an error directing the user to
`paddle login`; they do not open a surprise prompt.

## Configuration and storage

```sh
paddle config
```

This reports the secure credential backend, Keychain service and account names,
whether a saved credential exists, and the OpenAPI cache path. It never prints
the API key. There is no plaintext credential configuration file.

## Interactive API navigator

```sh
paddle interactive
```

The API reference is downloaded from
[`PaddleHQ/paddle-openapi`](https://github.com/PaddleHQ/paddle-openapi) and cached
under the operating system's user cache directory. The cache contains only the
public API specification, never credentials or responses.

## Scripted requests

The request command uses the saved key by default. `PADDLE_API_KEY` overrides it
for one process:

```sh
PADDLE_API_KEY='pdl_sdbx_...' paddle request GET /products
PADDLE_API_KEY='pdl_sdbx_...' paddle request GET /prices \
  --query '{"status":"active","per_page":20}'
PADDLE_API_KEY='pdl_sdbx_...' paddle request POST /customers \
  --body '{"email":"sam@example.com","name":"Sam Miller"}'
```

Use `--body @request.json` to read a JSON body from a file. Writes ask for
confirmation unless `--yes` is explicitly passed.

Do not put API keys directly in command arguments, checked-in `.env` files,
shell history, or chat messages.

## Other commands

```sh
paddle interactive
paddle login
paddle logout
paddle whoami
paddle doctor
paddle config
paddle help request
paddle operations
paddle operations --search subscription
paddle spec update
paddle --version
```

## API permissions

Paddle enforces the permissions assigned to the API key. A read-only key can
browse resources but cannot create or update them. Start with the smallest set
of permissions needed, especially for live accounts.

## Development

```sh
uv sync
uv run ruff check .
uv run pytest
```

The test suite uses mocked HTTP transports and does not require or call a real
Paddle account.

Maintainers can route-check the current cached Paddle specification against a
logged-in sandbox account. The harness forces sandbox, uses deliberately invalid
IDs and bodies, suppresses response content, and stops immediately if a write
unexpectedly succeeds:

```sh
uv run python scripts/e2e_sandbox.py
uv run python scripts/e2e_sandbox.py --include-write-probes
```

This proves safe route, authentication, and CLI coverage. It does not prove the
business behavior of successful create, update, or delete operations.
