# CLI implementation review

Reviewed on 2026-08-05. All repositories were active on the review date. The
comparison focuses on structure, authentication UX, testing, and distribution
rather than feature count.

| CLI | Implementation | Command and release structure | Relevant lesson |
| --- | --- | --- | --- |
| [Upstash CLI](https://github.com/upstash/cli) | TypeScript with Commander | Thin entrypoint, explicit login/logout, flag and environment overrides, JSON output, resource commands, and direct API client | Keep authentication resolution predictable and make root help useful to humans and agents |
| [Resend CLI](https://github.com/resend/resend-cli) | TypeScript with Commander | Explicit login/logout, secure credential backends, local `whoami`, networked `doctor`, profiles, JSON output, Homebrew, npm, and standalone binaries | Prompt only during login; separate local identity from live connectivity checks |
| [GitHub CLI](https://github.com/cli/cli) | Go with Cobra | Small `cmd/gh` entrypoint, package-oriented commands, acceptance tests, GoReleaser, immutable multi-platform releases, package managers, and provenance attestations | Keep commands independently testable and make release artifacts verifiable |
| [Stripe CLI](https://github.com/stripe/stripe-cli) | Go with Cobra | Dedicated root command, API operations informed by an OpenAPI spec, install tests, GoReleaser, Homebrew, npm wrapper, and precompiled binaries | A spec-driven API client still needs deliberate auth and release UX |
| [Supabase CLI](https://github.com/supabase/cli) | TypeScript/Bun with a Go sidecar | pnpm/Nx monorepo, platform-specific packages, core and end-to-end tests, release smoke tests, npm, Homebrew tap, Scoop, and Linux packages | Test the packaged command, not only its internal functions |
| [Sentry CLI](https://github.com/getsentry/sentry-cli) | Rust with Clap | Typed subcommands, Cargo workspace, npm installer, containers, and automated release workflows | Keep a strong typed boundary between parsing, configuration, and API calls |
| [uv](https://github.com/astral-sh/uv) | Rust with Clap | Cargo workspace, extensive integration tests, standalone installers, PyPI, Homebrew, WinGet, and cross-platform release automation | One obvious command can coexist with explicit advanced subcommands and many installers |
| [AWS CLI](https://github.com/aws/aws-cli) | Python | Thin executable entrypoint, service models, pinned runtime dependencies, large unit and integration suites, and bundled installers | Python is viable for a serious CLI when dependency and installer behavior are controlled |
| [Vercel CLI](https://github.com/vercel/vercel/tree/main/packages/cli) | TypeScript/Node | Package-local entrypoint, explicit command modules, Vitest, npm distribution, and a separate binary release workflow | Keep package entrypoints thin and preserve a path to standalone binaries |
| [Wrangler](https://github.com/cloudflare/workers-sdk/tree/main/packages/wrangler) | TypeScript/Node | pnpm monorepo, explicit executable shims, bundled builds, generated schemas, and Vitest | Generate repetitive API/config surfaces, but keep user-facing flows intentional |
| [GitLab CLI](https://github.com/gitlabhq/cli) | Go with Cobra | Command packages, API client boundary, cross-platform release packaging, and package-manager installation | Auth status should be explicit, concise, scriptable, and safe to paste into support requests |
| [flyctl](https://github.com/superfly/flyctl) | Go with Cobra | Thin main package, grouped commands, release workflow, install script, and Homebrew distribution | A stable executable name and predictable exit behavior matter more than framework choice |

## Patterns applied to Paddle CLI

- `paddle` with no subcommand shows help without prompting or making a network
  request.
- `paddle login` is the only authentication prompt. It validates before saving
  the secret in the operating system's secure credential manager.
- `paddle whoami` reports local credential metadata without a network call, while
  `paddle doctor` explicitly verifies Paddle connectivity.
- Credential resolution is predictable: `PADDLE_API_KEY` overrides the saved
  credential for one process and is never persisted.
- Authenticated commands fail with an actionable login instruction when no
  credential exists instead of opening an unexpected prompt.
- The full API navigator remains available as `paddle interactive`.
- A successful command exits with `0`, a rejected credential exits with `1`, and
  user cancellation exits with `130`.
- Output distinguishes verified facts from dashboard-only metadata.
- HTTP behavior is isolated from terminal rendering and tested with mock
  transports.

## Release implications

The strongest distribution pattern is a tagged release with CI-built artifacts,
checksums, an installation smoke test, and package-manager metadata generated
from the same version. For this Python implementation, the practical sequence is
PyPI and `uv tool install`, a custom Homebrew tap using immutable checksummed
resources, then standalone binaries if users need installation without Python.
