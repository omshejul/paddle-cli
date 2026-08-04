---
name: paddle-cli
description: Use the Paddle CLI to inspect, query, and manage Paddle Billing from a terminal, script, CI job, or AI agent. Trigger for Paddle catalog, customer, subscription, transaction, notification, reporting, authentication, sandbox or live environment, and raw Paddle API tasks that should use the `paddle` command.
---

# Paddle CLI

Use scripted commands for agent work. Use `paddle interactive` only when the user explicitly wants a human-driven terminal session.

## Establish context

1. Check that `paddle` is available. If it is missing, direct the user to install it with `uv tool install paddle-api-cli`.
2. Run `paddle whoami` to identify the saved credential source and sandbox or live environment without making a network request.
3. Run `paddle doctor` only when the task needs credential or API connectivity validation.
4. If authentication is missing, ask the user to run `paddle login` themselves. Never ask them to paste a key into chat.
5. Treat live as production. Prefer reads and sandbox experiments unless the user explicitly requests a live change.

## Discover operations

- Search the bundled API specification before guessing a path:

  ```sh
  paddle operations --search subscription
  ```

- Read command-specific help when syntax is unclear:

  ```sh
  paddle help request
  ```

- Refresh discovery only when a current endpoint is missing:

  ```sh
  paddle spec update
  ```

The `request` command can call a relative API path even when that operation is not in the cached specification.

## Make requests

Pin the intended environment in commands so the target is obvious:

```sh
paddle request GET /products --environment sandbox
paddle request GET /prices --environment live \
  --query '{"status":"active","per_page":20}'
paddle request GET /subscriptions/sub_123 --environment sandbox
```

Use a file for a nontrivial or reusable body:

```sh
paddle request POST /customers --environment sandbox \
  --body @request.json --yes
```

Before a write:

1. Confirm the environment, method, path, entity identifiers, and body.
2. Ensure the requested action is within the user's explicit authorization.
3. For live writes, state the exact intended change before executing it.
4. Add `--yes` only after those checks. Noninteractive writes require it.

Follow Paddle response pagination metadata when the user requests a complete collection rather than a sample.

## Protect credentials and live data

- Prefer the key saved by `paddle login`. For CI, supply `PADDLE_API_KEY` from the CI secret manager, never as a literal in source or logs.
- Never pass an API key with `--key` in an agent command, print it, log it, commit it, or place it in chat.
- Never use `--yes` for an unapproved write.
- Never delete, archive, cancel, or mutate a live entity unless the user explicitly requests that action and identifies its scope.
- Do not widen API-key permissions to work around a `403`. Report the required permission instead.
- Stop on unexpected `401`, `403`, `429`, or `5xx` responses. Explain the error and preserve the Paddle request ID.
- Do not claim that dashboard-only settings are available through the API.

## Report results

Summarize the environment, HTTP method and path, outcome, important resource IDs, pagination status when relevant, and Paddle request ID. Exclude credentials and sensitive response fields. Clearly distinguish completed API changes from instructions the user must finish in the Paddle dashboard.
