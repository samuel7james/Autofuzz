# Contributing to AutoFuzz

AutoFuzz is a dual-engine (protocol fuzzing + web assessment) security
testing framework, built for authorized use only — read
[docs/ethics.md](docs/ethics.md) before contributing changes that affect
how the tool sends traffic to a target.

## Development setup

```bash
git clone https://github.com/samuel7james/Autofuzz.git
cd Autofuzz
pip install -e ".[dev]"
```

See [docs/developer-guide.md](docs/developer-guide.md) for the full setup,
extension points (plugins, mutators, protocol adapters), and project
layout.

## Before opening a PR

Run everything CI runs:

```bash
ruff check src tests scripts
ruff format --check src tests scripts
mypy
coverage run -m pytest
```

If your change touches `.github/workflows/`, `docker/`, or dependencies,
also run Semgrep, pip-audit, and (for Dockerfile changes) a local Trivy
scan — see [docs/developer-guide.md](docs/developer-guide.md#running-the-checks-ci-runs)
for the exact commands. Verify against the same tool versions/images CI
uses, not just whatever's installed locally — version and scope mismatches
between local checks and CI have caused real, avoidable failures in this
project's history.

## Guidelines

- **Tests**: new behavior needs a test. Unit tests
  (`tests/unit/`) should not perform real I/O; integration tests
  (`tests/integration/`) run real engines against real local targets
  (the FTP lab, a local static HTTP server) — see existing tests for the
  pattern.
- **Type checking**: the codebase runs `mypy --strict`. New code should
  be fully typed, no `# type: ignore` without a comment explaining why.
- **No bare `except:`**: use a specific exception type, or `except
  Exception` if genuinely broad — a bare `except:` also catches
  `KeyboardInterrupt`/`SystemExit` and silently swallows them, which is
  never what you want in a CLI tool. See `core/errors.py`'s docstring.
- **Plugins are synchronous and side-effect-free**: they analyze data an
  engine already collected, never make their own network requests. See
  [docs/architecture.md](docs/architecture.md#plugins-autofuzzplugins).
- **Protocol adapters never raise**: capture exceptions on the returned
  `FuzzAttempt` instead, so `crash_classifier` can interpret them. See
  [docs/developer-guide.md](docs/developer-guide.md#adding-a-protocol-adapter).
- **Docs must match implementation.** If you add a CLI option, config
  field, plugin, mutator, or adapter, update the relevant doc
  (`docs/user-guide.md`, `docs/developer-guide.md`,
  `docs/architecture.md`) in the same PR.
- **Commit messages**: describe what changed and why, not just what.
  Update [CHANGELOG.md](CHANGELOG.md) under an "Unreleased" section for
  user-visible changes.

## Reporting issues

Use GitHub Issues for bugs and feature requests. For a security issue in
AutoFuzz's own code (not a target you scanned with it), see
[docs/ethics.md](docs/ethics.md#reporting-a-vulnerability-in-autofuzz-itself).

## Project status

AutoFuzz is under active development. [CHANGELOG.md](CHANGELOG.md) tracks
notable changes; check open issues and pull requests on GitHub for
in-progress work.
