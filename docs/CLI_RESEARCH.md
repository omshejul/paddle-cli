# CLI implementation review

Reviewed on 2026-08-04. All repositories were active on the review date. The
comparison focuses on structure, authentication UX, testing, and distribution
rather than feature count.

| CLI | Implementation | Command and release structure | Relevant lesson |
| --- | --- | --- | --- |
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

- `paddle` performs one obvious action, validates one key, reports safe identity
  information, and exits.
- The full API navigator remains available as `paddle interactive`.
- A successful check exits with `0`, a rejected key exits with `1`, and user
  cancellation exits with `130`.
- The API secret is masked at input, kept in memory, and never printed or saved.
- The check uses Paddle's permissionless `GET /event-types` endpoint and does not
  download the OpenAPI specification.
- Output distinguishes verified facts from dashboard-only metadata.
- HTTP behavior is isolated from terminal rendering and tested with mock
  transports.

## Release implications

The strongest distribution pattern is a tagged release with CI-built artifacts,
checksums, an installation smoke test, and package-manager metadata generated
from the same version. For this Python implementation, the practical sequence is
PyPI and `uv tool install`, a custom Homebrew tap using immutable checksummed
resources, then standalone binaries if users need installation without Python.
