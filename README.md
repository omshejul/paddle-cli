# Paddle CLI

A secure API-key validator and interactive terminal client for the complete
Paddle Billing API.

Paddle CLI reads Paddle's official OpenAPI 3.1 specification at runtime. New API
operations appear after a spec refresh, without waiting for a CLI release.

## Features

- Explicit login with masked API-key validation and secure storage
- Root help, local `whoami`, and networked `doctor` commands
- Automatic sandbox/live detection from modern Paddle API keys
- Operations grouped by Paddle resource, with fuzzy search
- Path, query, header, and JSON request-body input
- Request preview before execution
- Extra confirmation for writes, with an explicit `LIVE` gate in production
- Pretty JSON responses and Paddle request IDs
- Raw-request mode for endpoints not yet described by the specification
- Noninteractive request mode for scripts
- Validated API keys stored in the operating system's secure credential manager

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
