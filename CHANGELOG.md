# Changelog

All notable changes to AutoFuzz are documented here. Format loosely
follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- **Web Assessment Engine**: bounded breadth-first crawler, passive
  plugins (missing security headers, insecure cookie attributes, server
  version disclosure), technology fingerprinting, endpoint/parameter
  discovery, robots.txt/sitemap parsing.
- **Protocol Fuzzing Engine**: FSM-guided command sequencing, an 18
  mutator corpus, a pluggable transport adapter registry (FTP shipped),
  and crash classification that distinguishes real faults from timeouts
  and protocol-level rejections.
- **Shared core**: `ScanProfile` (typed, YAML-loadable, per-scan
  configuration), `WorkerPool` / `RateLimiter` / `RetryPolicy` (bounded
  concurrency, rate limiting, retries shared by both engines),
  `ScanSession` (state machine + JSON persistence powering
  `autofuzz history` / `autofuzz resume`), `PluginRegistry`, and a
  common `Finding` output type both engines produce.
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
  authorized-use policy (`docs/`), plus this changelog and
  `CONTRIBUTING.md`.
- `scripts/benchmark.py`: a performance benchmarking harness for catching
  mutator/crawler performance regressions.

### Security

- Scan session files are written owner-only (`chmod 700`/`600` on
  POSIX), since they can contain evidence scraped from a target (response
  headers, form field values).
- The AutoFuzz Docker image runs as a non-root user.
- Dependency and container image scanning (`pip-audit`, Trivy) and static
  analysis (Semgrep, CodeQL) run in CI on every change.
