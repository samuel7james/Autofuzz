# AutoFuzz v2.0 — Task Tracker

Status legend: `[ ]` pending · `[~]` in progress · `[x]` done · `[!]` blocked

This file is updated continuously as phases are implemented. See
`PROJECT_PLAN.md` for the architecture and rationale behind each phase.
**No phase begins until the previous one is reviewed and approved**, and
implementation does not start on any phase until this roadmap itself is
approved.

---

## Phase 0 — Audit (complete)

- [x] Inventory repository contents
- [x] Read and understand `autofuzz.py` end-to-end
- [x] Read Docker lab (`docker/Dockerfile`, `docker/vsftpd.conf`)
- [x] Identify strengths to preserve
- [x] Identify weaknesses/technical debt
- [x] Resolve v1-vs-master-prompt identity conflict with user (→ dual-engine: protocol fuzzing + web assessment)
- [x] Write `PROJECT_PLAN.md`
- [x] Write `TASKS.md`
- [ ] **Await roadmap approval before starting Phase 2**

---

## Phase 2 — Foundation (complete, pending user review)

- [x] Create `pyproject.toml` (hatchling backend, `autofuzz` console script)
- [x] Establish `src/autofuzz/` package layout per `PROJECT_PLAN.md` §7 (core + cli fully implemented; protocol_fuzzing/web/plugins/reporting/utils are placeholder packages for Phases 3–6)
- [x] `core/config.py`: pydantic `ScanProfile`/`SchedulerConfig`/`WebEngineConfig`/`ProtocolEngineConfig` + YAML profile loader (`load_profile`)
- [x] `core/logging.py`: structlog-based structured + console logging (`configure_logging`, `get_logger`)
- [x] `core/errors.py`: exception hierarchy (`AutoFuzzError` + 5 subclasses; replaces bare `except:`)
- [x] CLI skeleton (`cli/app.py`): Typer root app, `--version`, `--help`, `web`/`proto` stub commands, `--verbose`/`--quiet`
- [x] Implicit engine dispatch: `autofuzz <target>` auto-inserts `web` (URL) or `proto` (anything else) before Click parses argv — verified end-to-end with the installed console script
- [x] Relocate v1 root `autofuzz.py` → `legacy/autofuzz_v1.py` (content unchanged; done *during* this phase, not deferred — it was actively colliding with the new `autofuzz` package on `sys.path` and blocking `pytest` collection, so the swap couldn't wait for Phase 5's full logic migration). `readme.md` updated to point at the new path with a note.
- [x] Move `docker/Dockerfile` + `docker/vsftpd.conf` → `docker/labs/ftp-vsftpd/`; `readme.md` build path updated to match
- [x] Baseline `tests/` (16 tests): CLI smoke tests + implicit-dispatch unit tests, config/profile loading + validation, logging setup
- [x] Add `.gitignore` (Python/venv/tooling caches/AutoFuzz runtime artifacts)
- [x] Full-repo self-review before marking phase complete (see verification results below)

**Verification run this phase** (`.venv`, Python 3.13.2):
- `ruff check` — all checks passed
- `ruff format --check` — 21 files already formatted
- `mypy --strict` (on `autofuzz.core`, `autofuzz.cli`) — no issues
- `pytest` — 16 passed
- `coverage` — 92% on implemented modules (100% on `core/`)
- `python -m build --wheel` — builds cleanly
- Manual CLI smoke test: `autofuzz --version`, `autofuzz --help`, `autofuzz https://target.example` (dispatches to the `web` stub as designed)

**Deviation from the original checklist:** v1's relocation moved up from "during Phase 5" to "during Phase 2" — see note above. Its logic is still fully intact and unported; Phase 5 still does the real migration into `protocol_fuzzing/`.

## Phase 3 — Core Engine (complete, pending user review)

- [x] `core/scheduler.py`: `WorkerPool` — asyncio worker pool with configurable concurrency (`asyncio.Semaphore`)
- [x] `RateLimiter`: token-bucket rate limiter integrated into `WorkerPool`
- [x] `RetryPolicy`: exponential backoff + jitter, `max_retries`/`retry_backoff_seconds` sourced from `SchedulerConfig`; per-attempt timeout via `request_timeout_seconds`
- [x] `core/scan.py`: `ScanSession` lifecycle (`created → running → paused → completed/failed`) as an explicit state machine (invalid transitions raise `EngineError`), with JSON persistence (`save`/`load`)
- [x] Resume support: `ScanSession.resume(directory, scan_id)` reloads from disk and moves `paused/created → running`
- [x] `core/target_controller.py`: `TargetController` `Protocol` (`is_alive()`, `recover()`); `DockerTargetController` generalizes v1's `restart_docker()` (any container name, async subprocess, `docker inspect`-based liveness); `NoOpTargetController` is the default (always alive, recovery logs a warning and takes no action)
- [x] Config profiles: `examples/configs/web-default.yaml`, `web-thorough.yaml`, `ftp-lab.yaml` — all ship with `authorized: false` except `ftp-lab.yaml` (points only at the tool's own disposable lab container)
- [x] CLI wiring: `autofuzz web/proto --profile <path>` loads and validates the profile, checks it matches the invoked engine, and enforces the `authorized: true` gate before proceeding (still a stub past that point — Phase 4/5 land the engines)
- [x] Unit tests: scheduler (pool concurrency/ordering/exception handling, retry policy, rate limiter), scan lifecycle (transitions, persistence round-trip, resume, invalid-state errors), target controller (both implementations, mocked subprocess), CLI profile/authorization gate (valid, unauthorized, mismatched-engine, missing-file cases)

**Verification run this phase** (same `.venv`):
- `ruff check` / `ruff format --check` — clean
- `mypy --strict` (`autofuzz.core`, `autofuzz.cli`) — no issues
- `pytest` — 40/40 passing, 97% coverage
- `python -m build --wheel` — builds cleanly
- Manual smoke test: `autofuzz proto 127.0.0.1:21 --profile examples/configs/ftp-lab.yaml` (loads, authorized, proceeds to stub) vs. `autofuzz web https://target.example --profile examples/configs/web-default.yaml` (correctly rejected: `authorized: false`)

**Note:** found and fixed a non-ASCII (em dash) character in a user-facing CLI error message that rendered as `�` on a Windows console codepage — replaced with a plain period.

## Phase 4 — Discovery Engine (complete, pending user review)

- [x] `web/http_client.py`: `HttpClient` wraps `httpx.AsyncClient` (timeout, user agent, redirect policy from config; injectable transport for testing)
- [x] `web/crawler.py`: `Crawler` — breadth-first, level-by-level crawl using `WorkerPool` per level, same-origin scope check, `max_crawl_depth`/`max_pages` enforced, link extraction via BeautifulSoup (`a[href]`, `link[href]`, `script[src]`, `img[src]`)
- [x] `discovery/sitemap.py`: `parse_sitemap_xml`/`discover_sitemap` — urlset + sitemapindex, via `defusedxml` (not stdlib ElementTree) since sitemap content is untrusted target-supplied input
- [x] `discovery/robots.py`: `parse_robots_txt`/`discover_robots_txt` — Disallow/Allow/Sitemap as discovery hints; crawler does not auto-enforce exclusions (intentional — see module docstring)
- [x] `discovery/endpoints.py`: `enumerate_endpoints` — dedupes/sorts successfully fetched crawl results
- [x] `discovery/params.py`: `discover_params` — query-string params (`parse_qs`) + HTML form fields (`input`/`textarea`/`select`, via BeautifulSoup)
- [x] `discovery/fingerprint.py`: `fingerprint_response` — rule-based detection from `Server`/`X-Powered-By`/`X-AspNet-Version`/`X-Drupal-Cache` headers and HTML body signatures (WordPress, Django, Laravel, ASP.NET WebForms), deduplicated
- [x] `discovery/graph.py`: `RequestGraph` — nodes are discovered URLs, edges record which page linked to which; `discovered_via(url)` for reporting/plugins later
- [x] Integration tests against a real local static HTTP server (`http.server.ThreadingHTTPServer` on an ephemeral port, not mocked) covering the full crawl → endpoints → params → graph → robots → sitemap → fingerprint pipeline

**New dependencies:** `beautifulsoup4` (HTML parsing — regex-based link/form extraction was judged too fragile for a crawler), `defusedxml` (XXE/entity-expansion-safe XML parsing for sitemap content, which is untrusted target input). Both ship type stubs (`types-beautifulsoup4`, `types-defusedxml`) so `mypy --strict` needed no ignore overrides. `autofuzz.web` added to the mypy strict package list.

**Verification run this phase** (same `.venv`):
- `ruff check` / `ruff format --check` — clean
- `mypy --strict` (`autofuzz.core`, `autofuzz.cli`, `autofuzz.web`) — no issues, no overrides needed
- `pytest` (unit + integration) — 81/81 passing, 96% coverage
- `python -m build --wheel` — builds cleanly
- Manual end-to-end smoke test: spun up a real local HTTP server, ran `Crawler.crawl()` against it, confirmed pages/endpoints/params/graph edges all matched expectations

**Not done in this phase (by design, deferred to Phase 5):** the CLI's `autofuzz web <url>` still reports "not implemented yet" — wiring the discovery engine into an actual runnable, reportable scan happens once the plugin/assessment framework and `ScanSession` are connected in Phase 5, not before.

## Phase 5 — Assessment Framework

- [ ] `plugins/base.py`: shared `Plugin` + `Finding` contracts (used by both engines)
- [ ] `core/plugin.py`: plugin registry/loader (discovery via entry points or package scan)
- [ ] Port v1 mutation corpus into `protocol_fuzzing/mutators/` as discrete, documented, unit-tested mutators
- [ ] `protocol_fuzzing/fsm.py`: generalized FSM/sequence builder (replaces hardcoded `BASE_SEQUENCE`)
- [ ] `protocol_fuzzing/adapters/ftp.py`: FTP transport adapter (v1 successor, async)
- [ ] `protocol_fuzzing/crash_classifier.py`: distinguishes real faults from timeouts/protocol rejections (replaces "any exception = crash")
- [ ] Built-in web plugins: passive header analysis, metadata/response inspection, protocol-level checks (non-intrusive only, per plan §12)
- [ ] Plugin configuration (enable/disable, per-plugin options via profile)
- [ ] Tests for plugin registry + at least one plugin per engine

## Phase 6 — Reporting

- [ ] `reporting/models.py`: `Finding`, `RiskScore`, `ScanReport` dataclasses
- [ ] `reporting/renderers/html.py` (Jinja2 template: executive summary, findings, evidence, stats, timeline, recommendations)
- [ ] `reporting/renderers/markdown.py`
- [ ] `reporting/renderers/json.py`
- [ ] `reporting/renderers/csv.py`
- [ ] Streaming result writes during a scan (fixes v1's "lose everything on mid-run crash")
- [ ] Risk scoring model
- [ ] Tests for each renderer against a fixture `ScanReport`

## Phase 7 — UX & CLI

- [ ] Rich progress bars for both engines' scan loops
- [ ] Colored console output (severity-based)
- [ ] `autofuzz resume <scan-id>`
- [ ] `autofuzz history` (list past scans)
- [ ] Interactive mode (prompt for target/profile when none given)
- [ ] Config profile management commands
- [ ] Actionable error messages (replace stack-trace-only failures)
- [ ] Logging verbosity flags (`-v`/`-vv`/`--quiet`)

## Phase 8 — Performance

- [ ] Concurrency tuning + safe defaults (avoid accidental target overload)
- [ ] Memory profiling under large crawls / long fuzzing runs
- [ ] CPU profiling of mutation/hot loops
- [ ] Response caching within a scan session (discovery phase)
- [ ] Startup time check (CLI cold start)
- [ ] Benchmark harness + published comparison vs. v1 baseline

## Phase 9 — DevSecOps

- [ ] `.github/workflows/ci.yml`: ruff check + format check, mypy, pytest+coverage, build
- [ ] `.github/workflows/codeql.yml`
- [ ] Semgrep integration
- [ ] `pip-audit` dependency scanning
- [ ] Trivy Docker image scanning
- [ ] Enable GitHub secret scanning + push protection (repo setting, not code)
- [ ] SBOM generation (CycloneDX via syft) on release
- [ ] `.github/workflows/release.yml`: tag-triggered build + changelog + SBOM + GitHub Release

## Phase 10 — Infrastructure

- [ ] `docker/Dockerfile` (multi-stage, app image)
- [ ] `docker/docker-compose.yml` (app + `labs/ftp-vsftpd`, easy local dev)
- [ ] Environment/config management docs (`.env.example`)
- [ ] Example deployment configuration
- [ ] Secure-by-default configuration handling review

## Phase 11 — Documentation

- [ ] `README.md` rewrite (v2 quickstart, both engines, authorized-use notice)
- [ ] `docs/architecture.md`
- [ ] `docs/developer-guide.md` (how to add a plugin/mutator/adapter)
- [ ] `docs/user-guide.md`
- [ ] `docs/ethics.md` (authorized-use policy)
- [ ] `CONTRIBUTING.md`
- [ ] `CHANGELOG.md`
- [ ] Example configs in `examples/configs/`
- [ ] Verify docs match implementation (no drift)

## Phase 12 — Final Engineering Review

- [ ] Full dead-code sweep
- [ ] Naming/consistency pass across both engines
- [ ] Documentation accuracy pass
- [ ] Full test suite + coverage report
- [ ] Build verification (clean install from sdist/wheel)
- [ ] Report generation verification (all 4 formats, both engines)
- [ ] Confirm every phase's checklist above is fully checked
- [ ] Final summary for user

---

## Notes / Open Decisions

- Ruff proposed as the single lint+format tool (replacing Black) — flagged
  in `PROJECT_PLAN.md` §8 for confirmation, not yet decided.
- PyPI publishing is out of scope unless requested — release workflow
  produces GitHub Releases only by default.
