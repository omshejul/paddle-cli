# Paddle CLI

A secure, interactive terminal client for the complete Paddle Billing API.

Paddle CLI reads Paddle's official OpenAPI 3.1 specification at runtime. New API
operations appear after a spec refresh, without waiting for a CLI release.

## Features

- Masked API-key prompt on interactive startup
- Automatic sandbox/live detection from modern Paddle API keys
- Operations grouped by Paddle resource, with fuzzy search
- Path, query, header, and JSON request-body input
- Request preview before execution
- Extra confirmation for writes, with an explicit `LIVE` gate in production
- Pretty JSON responses and Paddle request IDs
- Raw-request mode for endpoints not yet described by the specification
- Noninteractive request mode for scripts
- API keys remain in memory and are never cached or written by the CLI

Paddle CLI covers operations present in the official Paddle Billing OpenAPI
specification. Dashboard-only workflows are outside the Paddle API and therefore
outside this CLI.

## Install from this repository

Requires Python 3.11 or newer and [uv](https://docs.astral.sh/uv/).

```sh
uv tool install .
```

During development:

```sh
uv sync
uv run paddle
```

## Interactive usage

```sh
paddle
```

The CLI prompts for the key using a masked input. Modern keys select their own
environment:

- `pdl_sdbx_...` uses `https://sandbox-api.paddle.com`
- `pdl_live_...` uses `https://api.paddle.com`

Legacy keys do not encode an environment, so the CLI asks you to choose one.

The API reference is downloaded from
[`PaddleHQ/paddle-openapi`](https://github.com/PaddleHQ/paddle-openapi) and cached
under the operating system's user cache directory. The cache contains only the
public API specification, never credentials or responses.

## Scripted requests

Set the key in the process environment or let the CLI prompt for it:

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
