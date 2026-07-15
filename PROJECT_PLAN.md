# AutoFuzz v2.0 — Project Plan

**Status:** Draft — awaiting approval. No implementation has started.

---

## 1. Executive Summary

AutoFuzz v1 is a 148-line single-file Python script that FSM-fuzzes an FTP
server (`autofuzz.py`) against a purpose-built, deliberately vulnerable
`vsftpd` Docker container. It was written to support an academic paper on
automated network protocol fuzzing. It has no tests, no packaging, no CLI
beyond "run the script," no configuration system, and hardcodes its target
(`127.0.0.1:21`) and command sequence.

AutoFuzz v2 keeps that identity — FSM-guided, mutation-driven, crash-seeking
fuzzing of live targets in **authorized** test environments — but rebuilds it
as a modular, async, plugin-based framework with two front ends sharing one
core engine:

1. **Protocol Fuzzing Engine** — the generalized successor to v1: FSM-based
   mutation fuzzing of text/binary protocols (FTP first, pluggable adapters
   for others), with target liveness monitoring and automated recovery.
2. **Web Assessment Engine** — new: `autofuzz https://target.example`
   crawls, discovers, and runs passive/protocol/metadata assessment plugins
   against an authorized HTTP(S) target, producing a professional report.

Both sit on a shared core: async request/connection scheduling, worker
pools, rate limiting, retry logic, scan lifecycle management, a plugin
registry, structured logging, and multi-format reporting.

This plan covers the audit, target architecture, and an 11-phase roadmap
(Phases 2–12, matching the master prompt's numbering). **No code changes
occur until this plan and `TASKS.md` are approved.**

---

## 2. Current Architecture (v1)

```
autofuzz.py          # everything: config, mutation, transport, logging, CLI
docker/Dockerfile     # vsftpd 20.04 image, hardcoded creds (vulnftp:1234)
docker/vsftpd.conf     # matching vsftpd config
readme.md, LICENSE
```

Execution model: `python3 autofuzz.py` runs `fuzz()`, a synchronous loop of
1000 iterations. Each iteration:

- Checks `is_ftp_alive()` via a raw blocking `socket` connect.
- Builds a 6-command sequence from `BASE_SEQUENCE`, applying one of 18
  mutation lambdas to each command.
- Opens a new blocking TCP socket, sends each mutated command, reads up to
  1024 bytes per response, logs the result.
- On any exception, counts it as a "crash" and continues.
- If the server is down, calls `docker restart <container>` and sleeps 5s.

Output: `mutated_inputs/testcase_*.txt`, `fuzz_log.txt`,
`fuzz_results.csv`, `restart_log.txt` — all relative to CWD.

## 3. Repository Audit

| Area | Finding |
|---|---|
| **Structure** | Single file, no package, no `src/` layout, no `pyproject.toml`/`requirements.txt`. Cannot be `pip install`ed or imported. |
| **Config** | Every parameter (host, port, timeout, container name, sequence, iteration count) is a module-level constant. No CLI args, no env vars, no profiles. |
| **Concurrency** | Fully synchronous, single connection at a time. `time.sleep(5)` blocks the whole process on every restart. |
| **Transport** | Raw sockets only, FTP-specific (`\r\n` framing, fixed 1024-byte reads — will silently truncate/misparse larger or multi-line responses). No protocol abstraction. |
| **Mutation engine** | 18 hardcoded lambdas mixing legitimate fuzzing primitives (length overflow, format strings, encoding edge cases) with **destructive payloads embedded as literal data** (e.g. `"; rm -rf / --no-preserve-root"`) that are sent to the target FTP server as command text, not executed locally — but the pattern is confusing and worth clarifying/removing as dead weight (see §4). |
| **Crash detection** | Any exception (including a normal `TimeoutError` on a slow response) is logged as `"CRASH"` — no distinction between a real fault, a timeout, and a protocol-level rejection. High false-positive rate. |
| **State/globals** | `results` list and `restart_counter` are module globals mutated by top-level functions — not reentrant, not testable in isolation. |
| **Error handling** | Bare `except:` in `is_ftp_alive()` swallows everything including `KeyboardInterrupt`. |
| **Logging** | Two overlapping mechanisms (text log + in-memory list flushed to CSV only at the very end — a crash before completion loses the CSV). |
| **Docker integration** | Shells out to `docker restart` via `subprocess.run`; assumes Docker CLI is on `PATH` and the container already exists and is named exactly `autofuzz-ftp-container`. No error handling if the container is missing. |
| **Security posture of the lab image** | `docker/Dockerfile` bakes in a static, weak credential (`vulnftp:1234`) — acceptable for a disposable local lab, but should be clearly documented as lab-only and not reused as a pattern elsewhere. |
| **Tests** | None. |
| **CI/CD** | None. |
| **Docs** | `readme.md` covers setup/usage but nothing on architecture, extension points, or contribution. |
| **Dependencies** | Zero third-party packages — entirely stdlib. Simple, but also means no async I/O, no rich CLI, no structured config validation. |
| **Portability** | Windows-hostile in one detail: relies on `docker` CLI and Unix-style paths conceptually fine, but nothing OS-specific breaks today — this is more a growth constraint than a bug. |

## 4. Strengths to Preserve

- **FSM-based sequencing** — building a realistic command sequence rather
  than fuzzing single commands in isolation is the right idea for protocol
  fuzzing and should be generalized, not discarded.
- **Aggressive, purpose-built mutation strategies** — the mutation *shapes*
  (length overflow, null bytes, path traversal tokens, format-string
  tokens, encoding flips, case/reversal transforms) are a legitimate,
  reusable mutation corpus. They should be extracted into a real mutation
  library, not rewritten from scratch.
- **Crash → auto-restart → keep going** loop — this is the core value
  proposition of a crash-seeking fuzzer and must survive the rewrite,
  generalized beyond `docker restart` of one hardcoded container name.
- **Self-contained lab target** — shipping a deliberately vulnerable Docker
  image alongside the fuzzer (so `autofuzz` is usable out of the box against
  something authorized) is a strength worth extending to a small library of
  lab targets, not just FTP.
- **Minimal dependency footprint** — a good instinct; v2 should add
  dependencies deliberately (async HTTP, CLI/UX, validation) rather than
  accumulating them by default.
- **Plain, readable mutation code** — no cleverness for its own sake; keep
  that ethos in the rewrite.

## 5. Weaknesses (Summary)

Everything in §3, distilled to what actually blocks the v2 vision:

1. No architecture to build a plugin system, reporting, or a second (web)
   front end on top of.
2. No async foundation — required for both worker-pool protocol fuzzing and
   any HTTP crawling/discovery at reasonable speed.
3. No config/profile system — required for "simple default, powerful when
   asked" UX (`autofuzz https://target.example` vs. advanced flags).
4. No test harness — required before any refactor can be trusted.
5. Crash detection is unreliable (exception-as-crash) and must be redesigned
   with explicit fault classification.
6. No target abstraction — "restart docker container" needs to become a
   pluggable `TargetController` (Docker today; process supervisor, k8s pod,
   or no-op for real client environments, tomorrow).

## 6. Proposed Architecture (v2)

Single Python package, `autofuzz`, installable via `pip`, exposing one CLI
entry point (`autofuzz`) that dispatches to one of two **engines** sharing a
common **core**:

```
┌─────────────────────────────── CLI (Typer + Rich) ───────────────────────────────┐
│  autofuzz <target>            → auto-detect engine (URL → web, host:port → proto) │
│  autofuzz web <url> [flags]   → Web Assessment Engine                             │
│  autofuzz proto <profile>     → Protocol Fuzzing Engine                           │
│  autofuzz report / resume / history / config                                      │
└─────────────────────────────────────────────────────────────────────────────────┘
                │                                                │
                ▼                                                ▼
   ┌─────────────────────────┐                     ┌─────────────────────────────┐
   │   Web Assessment Engine  │                     │   Protocol Fuzzing Engine    │
   │  crawler → discovery →   │                     │  FSM builder → mutator →     │
   │  plugin pipeline          │                     │  transport adapter → target  │
   │                           │                     │  monitor                    │
   └─────────────┬─────────────┘                     └───────────────┬─────────────┘
                 │                                                    │
                 └───────────────────────┬────────────────────────────┘
                                          ▼
                     ┌──────────────────────────────────────────┐
                     │                CORE                       │
                     │  scheduler (async worker pool, rate       │
                     │  limit, retry) · scan lifecycle & resume  │
                     │  · plugin registry · config/profiles      │
                     │  · structured logging · reporting engine  │
                     └──────────────────────────────────────────┘
```

Key design decisions:

- **Plugin contract is shared.** A `Plugin` base class (id, metadata,
  `applies_to(context)`, `run(context) -> list[Finding]`) is used by both
  engines. Web plugins receive an HTTP context; protocol plugins/mutators
  receive a connection context. This is what lets Phase 5 stay "one
  framework," not two codebases glued together.
- **`Finding` is the universal output unit** for both a web assessment
  observation and a protocol fuzzing crash — both flow into the same
  reporting engine (Phase 6).
- **`TargetController`** generalizes `restart_docker()`: a small interface
  (`is_alive()`, `recover()`) with a Docker implementation shipped, and a
  no-op implementation for targets the user doesn't control (client
  environments must never be "restarted" without explicit opt-in).
- **Scan lifecycle** (Phase 3) is engine-agnostic: `created → running →
  paused → completed/failed`, persisted so `autofuzz resume <id>` works for
  both a long protocol fuzzing run and a large web crawl.

## 7. Folder Structure

```
autofuzz/
├── pyproject.toml
├── README.md
├── CHANGELOG.md
├── CONTRIBUTING.md
├── LICENSE
├── PROJECT_PLAN.md
├── TASKS.md
├── docs/
│   ├── architecture.md
│   ├── developer-guide.md
│   ├── user-guide.md
│   └── ethics.md              # authorized-use policy, scope-of-use statement
├── examples/
│   └── configs/
│       ├── web-default.yaml
│       ├── web-thorough.yaml
│       └── ftp-lab.yaml
├── src/
│   └── autofuzz/
│       ├── __init__.py
│       ├── __main__.py
│       ├── cli/
│       │   ├── app.py               # Typer root app, engine auto-detection
│       │   ├── commands/            # web.py, proto.py, report.py, resume.py, config.py
│       │   └── ui.py                # Rich progress/console helpers
│       ├── core/
│       │   ├── config.py            # pydantic settings + profile loader
│       │   ├── logging.py           # structured (structlog) + console logging
│       │   ├── scheduler.py         # asyncio worker pool, rate limiter, retry policy
│       │   ├── scan.py              # ScanSession lifecycle, persistence, resume
│       │   ├── plugin.py            # Plugin base class + registry/discovery
│       │   ├── target_controller.py # is_alive()/recover() interface + Docker impl
│       │   └── errors.py
│       ├── protocol_fuzzing/
│       │   ├── engine.py
│       │   ├── fsm.py               # sequence builder (generalized BASE_SEQUENCE)
│       │   ├── mutators/            # extracted v1 mutation corpus + new strategies
│       │   ├── adapters/            # ftp.py (v1 successor), raw_tcp.py, smtp.py
│       │   └── crash_classifier.py  # replaces "any exception = crash"
│       ├── web/
│       │   ├── engine.py
│       │   ├── crawler.py
│       │   ├── http_client.py       # httpx-based async client
│       │   └── discovery/           # sitemap.py, endpoints.py, params.py, robots.py, fingerprint.py
│       ├── plugins/
│       │   ├── base.py              # shared Plugin/Finding contracts
│       │   └── builtin/             # passive analysis, header/metadata checks, etc.
│       ├── reporting/
│       │   ├── models.py            # Finding, RiskScore, ScanReport
│       │   ├── renderers/           # html.py, markdown.py, json.py, csv.py
│       │   └── templates/           # Jinja2 HTML report template
│       └── utils/
├── tests/
│   ├── unit/
│   └── integration/
├── docker/
│   ├── Dockerfile                   # autofuzz application image
│   ├── docker-compose.yml           # autofuzz + lab targets for local dev
│   └── labs/
│       └── ftp-vsftpd/              # v1's Dockerfile + vsftpd.conf, relocated
└── .github/
    └── workflows/
        ├── ci.yml                   # lint, type-check, test, coverage
        ├── codeql.yml
        └── release.yml
```

## 8. Technology Decisions

| Concern | Choice | Rationale |
|---|---|---|
| Language/runtime | Python ≥3.10 | Keeps v1's language; 3.10+ for modern typing (`match`, `X \| Y`) |
| Packaging | `pyproject.toml`, `hatchling` build backend | Standard, no legacy `setup.py` |
| CLI framework | `Typer` + `Rich` | Typer gives subcommands/auto-help from type hints; Rich gives progress bars/colored output for Phase 7 |
| Config validation | `pydantic` v2 | Typed config, profile files validated at load, clear error messages |
| Async HTTP | `httpx` (async client) | First-class async, HTTP/2, used by ProjectDiscovery-style tools' Python peers |
| Protocol transport | `asyncio` streams | Native async sockets for the protocol engine's worker pool |
| Structured logging | `structlog` → stdlib `logging` backend | Machine-parseable logs + human console output from one call site |
| HTML templating (reports) | `Jinja2` | Simple, no build step, matches "self-contained HTML report" goal |
| Lint/format | `Ruff` (lint **and** format) | One tool replaces Ruff+Black+isort; avoids two formatters fighting each other. *Flagging this as a deviation from the master prompt's literal "Ruff, Black" — recommend confirming during review.* |
| Type checking | `mypy` (strict on `core/`, `reporting/`) | Master prompt asks for "strict typing" |
| Testing | `pytest` + `pytest-asyncio` + `coverage.py` | Needed before any refactor is trustworthy |
| Security scanning | `CodeQL`, `Semgrep`, `pip-audit`/`Trivy` (deps + image), GitHub secret scanning | Matches Phase 9 explicitly |
| SBOM | `syft` (CycloneDX output) in release workflow | Standard, CI-friendly |
| Containers | Multi-stage `Dockerfile` for the app; separate `docker/labs/` images for vulnerable targets | Keeps "the tool" and "the disposable target" clearly separated (v1 conflated them) |

## 9. Performance Plan

- Replace synchronous, one-connection-at-a-time execution with an
  `asyncio`-based worker pool for **both** engines (configurable
  concurrency, default conservative to avoid accidentally DoS'ing a target —
  see §10).
- Rate limiting and backoff/retry as first-class scheduler features, not
  ad-hoc `time.sleep`.
- Streaming CSV/JSONL result writes (v1 loses all CSV data on a mid-run
  crash because it's written once at the end) — Phase 3/6.
  cache HTTP responses within a scan session to avoid redundant discovery
  requests.
- Benchmark harness (Phase 8) comparing v1's ~1000 sequential iterations/run
  against v2's throughput at equivalent safety settings, published in
  `docs/`.

## 10. Security Plan

- **Authorized-use gating stays explicit and unavoidable.** Every scan
  (web or protocol) requires an acknowledgment step (config flag or CLI
  confirmation) that the target is authorized for testing — this is a UX
  requirement, not just a README disclaimer, and applies whether the target
  is `127.0.0.1` or a client URL.
- `TargetController.recover()` (Docker restart or otherwise) is opt-in and
  scoped — it must never run against a target the tool didn't provision
  itself, i.e., default-off for `web` scans and for any `proto` target not
  declared as a managed lab container.
- Destructive-looking literal payloads in the mutation corpus (e.g. the
  `rm -rf` string) are inert *data* sent to a fuzzed target's protocol
  parser, not executed locally — but v2 will document this explicitly next
  to the mutator definitions so it's unambiguous on read, and will keep the
  local disposable-lab default credentials (`docker/labs/ftp-vsftpd`)
  clearly labeled lab-only in docs and code comments.
- Secrets/config: no hardcoded credentials in source (v1's `vulnftp:1234`
  moves into the lab-only Dockerfile, stays out of the core package).
  Client-facing scan profiles support env-var/`.env`-sourced credentials for
  authenticated assessments.
- Dependency and container scanning wired into CI (Phase 9) so this
  security-tooling project doesn't itself ship vulnerable dependencies.

## 11. DevSecOps Plan

- `ci.yml`: on every PR — `ruff check` + `ruff format --check`, `mypy`,
  `pytest --cov`, build check.
- `codeql.yml`: scheduled + on PR, Python queries.
- Semgrep: custom + community ruleset in CI, non-blocking initially →
  blocking once the baseline is clean.
- `pip-audit` (dependency CVEs) and `Trivy` (Docker image scanning) in CI.
- Secret scanning: GitHub's native secret scanning + push protection
  enabled at the repo level (user action, not code).
- SBOM (CycloneDX via `syft`) generated and attached on release.
- `release.yml`: tag-triggered, builds sdist/wheel, generates changelog
  entry, attaches SBOM, publishes GitHub Release (PyPI publish only if/when
  the user wants the package public).

## 12. Feature Roadmap (maps to master-prompt phases)

| Phase | Deliverable |
|---|---|
| 2 — Foundation | Package layout, config system, logging, error hierarchy, dependency cleanup, base CLI skeleton |
| 3 — Core Engine | Async scheduler/worker pool, retry, rate limiting, scan lifecycle + resume, config profiles |
| 4 — Discovery Engine | Web crawler, sitemap, endpoint/parameter discovery, robots.txt parsing, tech fingerprinting |
| 5 — Assessment Framework | Shared `Plugin`/`Finding` contract, plugin registry/loader, first built-in plugins (passive header/metadata analysis), protocol mutator plugins generalized from v1 |
| 6 — Reporting | `Finding`/`ScanReport` models, HTML/Markdown/JSON/CSV renderers, risk scoring |
| 7 — UX & CLI | Rich progress bars, colored output, resume/history commands, interactive mode, config profiles UX |
| 8 — Performance | Concurrency tuning, memory/CPU profiling, large-target handling, startup time, benchmark report |
| 9 — DevSecOps | CI, CodeQL, Semgrep, Ruff, pytest+coverage, dependency/image scanning, SBOM, release automation |
| 10 — Infrastructure | Docker Compose (app + lab targets), env/config management, example deployment |
| 11 — Documentation | README rewrite, architecture guide, developer guide, user guide, CONTRIBUTING, CHANGELOG |
| 12 — Final Review | Dead-code sweep, naming/consistency pass, full verification |

## 13. Sprint Roadmap (proposed pacing)

One phase per sprint, matching the master prompt's "never work on multiple
phases simultaneously unless instructed":

1. Sprint 1 → Phase 2 (Foundation)
2. Sprint 2 → Phase 3 (Core Engine)
3. Sprint 3 → Phase 4 (Discovery Engine)
4. Sprint 4 → Phase 5 (Assessment Framework)
5. Sprint 5 → Phase 6 (Reporting)
6. Sprint 6 → Phase 7 (UX & CLI)
7. Sprint 7 → Phase 8 (Performance)
8. Sprint 8 → Phase 9 (DevSecOps)
9. Sprint 9 → Phase 10 (Infrastructure)
10. Sprint 10 → Phase 11 (Documentation)
11. Sprint 11 → Phase 12 (Final Review)

Each sprint ends with: format → lint → tests → build verification → docs
update → `TASKS.md` update → commit message proposal → summary → **stop for
approval**, exactly as the master prompt specifies.

## 14. Future Roadmap (post-v2, not scheduled)

- Additional protocol adapters (SMTP, raw TCP/binary framing, custom
  DSL-defined protocols).
- Additional web discovery: JS-rendered crawling, GraphQL/OpenAPI-aware
  discovery.
- Additional lab targets beyond FTP (one per protocol adapter).
- Optional coverage-guided mutation feedback loop for the protocol engine
  (a natural extension of the FSM/mutation foundation, out of scope for v2).
- Multi-target/batch scanning, team-oriented result storage.

## 15. Risks & Mitigation

| Risk | Mitigation |
|---|---|
| Scope is very large for one contributor to review per-phase | Strict one-phase-at-a-time gating (already required by the master prompt); each sprint is independently mergeable and shippable. |
| Dual-engine design doubles surface area vs. a single-purpose tool | Shared core (scheduler, plugin contract, reporting) minimizes duplicated logic; each engine is a thin adapter over the core. |
| Async rewrite could regress v1's working FTP fuzzing behavior | Port v1's mutation corpus and FSM sequencing with unit tests *before* the CLI/engine swap; keep `docker/labs/ftp-vsftpd` as the regression target. |
| New dependencies increase supply-chain surface | Pin versions, wire `pip-audit`/Trivy/CodeQL into CI from Phase 9 onward (not deferred to the end), minimal dependency count per §8. |
| "Web assessment" scope creep into active/intrusive scanning | Phase 5 stays scoped to passive analysis, protocol/metadata inspection, and configurable non-destructive checks, per the master prompt's own framing — no active exploitation modules. |
| Authorized-use boundary erosion as the tool gets more powerful | Explicit authorization acknowledgment stays a hard UX gate (§10), reviewed again at Phase 12. |

---

**Next step:** review this plan and `TASKS.md`. Implementation begins only
after explicit approval, one phase at a time, per the workflow above.
