# Paddle CLI

A fast, agent-native CLI for the complete Paddle Billing API.

[Website](https://omshejul.github.io/paddle-cli/) ·
[PyPI](https://pypi.org/project/paddle-api-cli/) ·
[Homebrew](https://github.com/omshejul/homebrew-tap)

## Built for agents

**2× faster agent runs. 39% fewer input tokens. 46× smaller discovery payload.**

| Measured task | Paddle CLI | Paddle MCP |
| --- | ---: | ---: |
| Repeated API read | **9.2s** | 18.5s |
| Input tokens | **35.5k** | 58.5k |
| Operation discovery | **541 chars** | 24.8k chars |

Paddle CLI keeps discovery local, turns every action into an inspectable command,
and works anywhere an agent has a shell. It reads Paddle's official OpenAPI
specification, supports raw paths for new endpoints, stores credentials in the
system credential manager, and gates live writes.

## Install

Paddle CLI is installed with [uv](https://docs.astral.sh/uv/):

```sh
uv tool install paddle-api-cli
paddle login
```

### macOS with Homebrew

```sh
brew install omshejul/tap/paddle-api-cli
paddle login
```

### Windows with WinGet

```powershell
winget install --id astral-sh.uv --exact
uv tool install paddle-api-cli
paddle login
```

### Linux

```sh
curl -LsSf https://astral.sh/uv/install.sh | sh
uv tool install paddle-api-cli
paddle login
```

Upgrade or uninstall a uv installation with:

```sh
uv tool upgrade paddle-api-cli
uv tool uninstall paddle-api-cli
```

For a Homebrew installation, use:

```sh
brew upgrade paddle-api-cli
brew uninstall paddle-api-cli
```

To install the latest development version directly from the public repository:

```sh
uv tool install --force-reinstall \
  "git+https://github.com/omshejul/paddle-cli.git@main"
```

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
paddle skill install
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

## AI agent skill

The package includes a compact, reusable agent skill at
[`skills/paddle-cli/SKILL.md`](skills/paddle-cli/SKILL.md). It teaches AI agents
how to discover operations, use noninteractive commands, protect credentials,
and handle sandbox and live writes safely without copying the full API reference
into their context.

After an interactive login, Paddle CLI offers to install one shared copy at
`~/.agents/skills/paddle-cli`. Codex, Cursor, Gemini CLI, GitHub Copilot, and
OpenCode read that standard location directly. If Claude Code is present, Paddle
CLI links its `~/.claude/skills/paddle-cli` entry to the same copy. On systems
that cannot create the link, it keeps a second synchronized copy instead. Run
`paddle skill install` to update the setup. Updates never overwrite a skill that
you edited.

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
