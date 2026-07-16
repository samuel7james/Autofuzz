# Changelog

All notable changes to AutoFuzz are documented here. Format loosely
follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased] — AutoFuzz v2

A ground-up rebuild of v1's single-file FTP fuzzer into a modular,
dual-engine framework. See [PROJECT_PLAN.md](PROJECT_PLAN.md) for the
full roadmap and [TASKS.md](TASKS.md) for a detailed, phase-by-phase
build log (including what was deliberately left out and why).

### Added

- **Web Assessment Engine**: bounded breadth-first crawler, passive
  plugins (missing security headers, insecure cookie attributes, server
  version disclosure), technology fingerprinting, endpoint/parameter
  discovery, robots.txt/sitemap parsing.
- **Protocol Fuzzing Engine (v2)**: FSM-guided command sequencing, an 18
  mutator corpus (ported and expanded from v1), a pluggable transport
  adapter registry (FTP shipped), and crash classification that
  distinguishes real faults from timeouts and protocol-level rejections.
- **Shared core**: `ScanProfile` (typed, YAML-loadable, per-scan
  configuration replacing v1's module-level constants), `WorkerPool` /
  `RateLimiter` / `RetryPolicy` (bounded concurrency, rate limiting,
  retries shared by both engines), `ScanSession` (state machine + JSON
  persistence powering `autofuzz history` / `autofuzz resume`),
  `PluginRegistry`, and a common `Finding` output type both engines
  produce.
- **CLI**: `autofuzz web`, `autofuzz proto`, `autofuzz history`,
  `autofuzz resume`, plus an implicit shorthand (`autofuzz <target>`
  infers the engine). Live Rich progress bars, `--report-format`
  (HTML/Markdown/JSON/CSV), `-v`/`-q` verbosity, `--version`.
- **Reporting**: `ScanReport` with a severity-weighted `RiskScore`,
  rendered to HTML, Markdown, JSON, or CSV.
- **Authorized-use gating**: every scan profile requires an explicit
  `authorized: true`; the CLI refuses to run without it.
- **Docker**: a hardened, non-root, multi-stage AutoFuzz image; a
  Docker Compose stack (AutoFuzz + a disposable, intentionally
  vulnerable vsftpd lab target) with automatic lab-container restart on
  crash via Compose's own `restart` policy.
- **CI/CD**: lint (`ruff`), format check, `mypy --strict`, a test matrix
  across Python 3.10–3.13, build verification, Docker lab image build,
  `pip-audit` (dependency CVEs), Trivy (filesystem scan), Semgrep (SAST),
  CodeQL, and a tag-triggered release workflow (sdist/wheel + SBOM +
  GitHub Release).
- **Documentation**: architecture, developer guide, user guide, and
  authorized-use policy (this directory, `docs/`), plus this changelog
  and `CONTRIBUTING.md`.
- `scripts/benchmark.py`: a performance benchmarking harness used to
  compare v1 and v2 and to catch mutator/crawler performance regressions.

### Changed

- Crash detection now distinguishes an ordinary timeout or a deliberate
  protocol-level rejection from a real target fault — v1 treated any
  exception as a crash.
- The FTP transport adapter now treats a clean connection close (EOF, no
  exception) after sending a command as a fault worth reporting — v1's
  equivalent silently logged "OK" in that case.
- Target recovery (Docker container restart) is now opt-in and scoped to
  a specific, named container — v1 hardcoded a single container name and
  always attempted recovery.

### Fixed

- httpx/httpcore's own per-request `INFO` logging no longer floods the
  console and visually corrupts the live progress bar during a crawl.
- Web crawl progress now reports per fetched page instead of per BFS
  depth level, so a large depth level no longer looks frozen for its
  entire duration.
- `ScanSession` checkpoint writes are throttled (every 25 progress
  updates, plus always on completion) instead of hitting disk on every
  single page/iteration.
- `AUTOFUZZ_CONFIG_DIR=~/...` now resolves to the user's home directory
  instead of silently creating a literal `~` directory.
- A protocol adapter's own transport function is now actually invoked for
  every fuzzing attempt — the engine previously hardcoded a direct call
  to the FTP adapter's `send_sequence` regardless of which adapter a
  profile configured.

### Security

- Scan session files are written owner-only (`chmod 700`/`600` on
  POSIX), since they can contain evidence scraped from a target (response
  headers, form field values).
- The AutoFuzz Docker image runs as a non-root user.
- Dependency and container image scanning (`pip-audit`, Trivy) and static
  analysis (Semgrep, CodeQL) run in CI on every change.

## [1.0.0] — Legacy FTP fuzzer

The original AutoFuzz: a single-script, synchronous FTP protocol fuzzer.
FSM-based command sequencing, a mutation corpus targeting buffer
overflows and malformed input, crash detection via exception handling,
and automatic Docker container restart on crash. Superseded by v2's
Protocol Fuzzing Engine; retired from the codebase once v2 reached
feature parity.
