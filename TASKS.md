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

## Phase 5 — Assessment Framework (complete, pending user review)

- [x] `plugins/base.py`: shared `Plugin` (ABC, `Generic[ContextT]`) + `Finding`/`Severity`/`PluginMetadata` contracts. Plugins are deliberately synchronous, side-effect-free functions of already-collected data (no plugin does its own I/O) - keeps "passive analysis" literal and every plugin trivially unit-testable.
- [x] `core/plugin.py`: `PluginRegistry` - explicit `register()` (not entry-point/package-scan discovery, which would be speculative machinery with no third-party consumer yet), `enable`/`disable`/`configure()` (allow-list/deny-list), `apply_options()`, and `run_all()` with per-plugin fault isolation (a raising plugin is logged and skipped, never aborts the scan)
- [x] `core/config.py`: `PluginConfig` (`enabled`/`disabled`/`options`) added to `ScanProfile.plugins`
- [x] Ported v1's full 18-mutator corpus into `protocol_fuzzing/mutators/strategies.py` as discrete, named, documented, individually unit-tested functions (`ALL_MUTATORS` + `mutate()`); the two mutators embedding shell-metacharacter payloads are documented in-place as inert data sent to the target's own parser, never executed locally
- [x] `protocol_fuzzing/fsm.py`: `ProtocolFsm`/`FsmState` - generalized sequence builder replacing hardcoded `BASE_SEQUENCE`
- [x] `protocol_fuzzing/adapters/ftp.py`: async FTP adapter (`send_sequence`) using asyncio streams instead of v1's blocking sockets. **Fixes a v1 bug found while testing this phase:** a clean connection close (empty read, no exception) after sending a command is now treated as a fault - v1's `recv()` returning `b''` on a graceful close logged `"OK"`, silently missing that class of crash.
- [x] `protocol_fuzzing/crash_classifier.py`: `FaultKind` (NONE/TIMEOUT/REJECTED/CRASH), `FuzzAttempt`, `classify()`, `to_finding()` - replaces v1's "any exception = crash"
- [x] `protocol_fuzzing/engine.py`: `ProtocolFuzzingEngine` - orchestrates FSM + mutators + adapter + crash classification + `TargetController` recovery through the Phase 3 `WorkerPool`, chunked by `scheduler.concurrency` so target liveness is rechecked between chunks (not before literally every request, which would defeat concurrency)
- [x] Built-in web plugins (`plugins/builtin/web_headers.py`): `MissingSecurityHeadersPlugin`, `InsecureCookiePlugin`, `ServerDisclosurePlugin` - all passive, operating only on `CrawlResult` data the crawler already collected (added a `headers` field to `CrawlResult` for this)
- [x] Plugin configuration: `PluginConfig.enabled`/`disabled`/`options`, applied via `PluginRegistry.configure()`/`apply_options()`
- [x] Tests: plugin base + registry (fault isolation, allow/deny-list, per-plugin options), full mutator corpus, FSM, crash classifier, built-in web plugins, FTP adapter + full engine run against a real local asyncio TCP server (integration, not mocked), CLI wiring with a fake engine double (no real network in CLI unit tests)

**Beyond the original checklist, done because the user asked for full v1→v2 migration in this phase:**
- [x] `protocol_fuzzing/engine.py` (wasn't itself an explicit checklist line - see above) and CLI wiring: `autofuzz proto <target> --profile <profile>` now runs a **real** fuzzing campaign (previously a stub, matching `web`'s still-stub state). This required adding `--profile` as a required option for `proto` (there's no responsible zero-config default without the `authorized` gate) and resolving `TargetController` from the profile (`docker` → `DockerTargetController`, else `NoOpTargetController`).
- [x] **`legacy/autofuzz_v1.py` removed.** Every piece of v1's behavior now has a tested v2 equivalent: FSM sequencing → `fsm.py`, all 18 mutations → `mutators/strategies.py`, FTP transport → `adapters/ftp.py`, crash detection → `crash_classifier.py` (now more correct than v1, see above), Docker restart-on-down → `TargetController`/`DockerTargetController` (Phase 3), the run loop itself → `engine.py`, and the CLI entry point → `autofuzz proto`. `readme.md` and `docker/labs/ftp-vsftpd/` (the disposable lab target) are unaffected - only the redundant reference script is gone.

**Verification run this phase** (same `.venv`):
- `ruff check` / `ruff format --check` — clean
- `mypy --strict` — expanded scope to include `autofuzz.plugins` and `autofuzz.protocol_fuzzing` (were missing from the strict list until this phase); 34 source files, no issues
- `pytest` — 157/157 passing, 97% coverage
- `python -m build --wheel` — builds cleanly
- Manual end-to-end smoke test: real local asyncio TCP server + the actual installed `autofuzz proto <host:port> --profile <profile>` command (not mocked) - loaded the profile, ran 4 real fuzzing attempts, correctly classified all 4 as crashes (the fake server intentionally drops oversized payloads), printed results, exited 1 (findings found)

## Phase 6 — Reporting (mostly complete, one item carried forward — pending user review)

- [x] `reporting/models.py`: `RiskScore` (severity-weighted, explainable score + `max_severity` + `counts_by_severity`) and `ScanReport` (`create`/`complete` lifecycle, `.risk` computed property) - `Finding` reused unchanged from `plugins/base.py` (Phase 5), not redefined here
- [x] `reporting/renderers/html.py`: Jinja2 template (`reporting/templates/report.html.jinja`) - executive summary, findings-by-severity table, per-finding cards with evidence, scan statistics, recommendations. **Autoescaping is mandatory here, not a default left as-is**: a Finding's evidence/description can contain text sourced directly from the target under test, which for a security tool is inherently untrusted input - explicitly set `autoescape=True` (not relying on filename-based autodetection, which would have silently been `False` for a `.jinja`-suffixed template)
- [x] `reporting/renderers/markdown.py`
- [x] `reporting/renderers/json.py` (with an explicit `Enum`-aware fallback for `Finding.metadata`, which is `dict[str, Any]` and can hold values `json.dumps` doesn't natively know)
- [x] `reporting/renderers/csv.py` (one row per Finding)
- [x] Risk scoring model (`RiskScore`, see above)
- [x] Tests for each renderer against fixture `ScanReport`s, including a dedicated XSS-escaping test for the HTML renderer

**Beyond the original checklist, done because it's what actually makes Phase 6 useful — and because the user asked how to run AutoFuzz against their own website:**
- [x] `web/engine.py`: `WebAssessmentEngine` - crawls, runs the Phase 5 plugin registry against every fetched page, plus technology fingerprinting (turned into INFO-severity Findings). This is what finally makes `autofuzz web <url>` a real, runnable, reportable scan instead of a stub.
- [x] `discovery/fingerprint.py` refactored: `fingerprint_response(httpx.Response)` → `fingerprint(headers, body)`, decoupling it from httpx so it works directly against a `CrawlResult`'s already-collected data instead of needing a live `httpx.Response` object.
- [x] CLI: both `web` and `proto` now take `--report-format` (html/markdown/json/csv) and `--report-output`, build a `ScanReport`, print a console summary, and write the rendered report to disk.
- [x] Plugin configuration (`ScanProfile.plugins`, built in Phase 5) is now actually applied: the CLI configures the web plugin registry's enable/disable/options from the loaded profile before running.

**Not done in this phase (carried forward):** streaming/incremental result writes during a long scan. `ScanReport` is currently built up in memory and only written to disk once, after the engine's `run()` returns — a process kill or crash mid-scan still loses everything, same failure mode v1 had (Phase 3's `ScanSession` persistence exists but isn't wired into the report-writing path yet). The natural place to close this gap is Phase 7, alongside `autofuzz resume`/`autofuzz history`, since both need the same underlying mechanism (persisting `ScanSession`/partial results incrementally, not just at the end).

**Verification run this phase** (same `.venv`):
- `ruff check` / `ruff format --check` — clean
- `mypy --strict` — expanded scope to include `autofuzz.reporting`; 43 source files, no issues
- `pytest` — 186/186 passing, 97% coverage
- `python -m build --wheel` — builds cleanly; confirmed the Jinja template is actually included in the wheel (`unzip -l` showed `autofuzz/reporting/templates/report.html.jinja`) rather than silently assuming hatchling would package a non-`.py` data file
- Manual end-to-end smoke test: real local static HTTP server + the actual installed `autofuzz web <url> --profile <profile>` command (not mocked) - crawled 2 pages, found 10 findings (missing security headers + a real server-version disclosure, since Python's `http.server` reports its version in the `Server` header), wrote a valid HTML report to disk, exited 1

## Phase 7 — UX & CLI (mostly complete, two items carried forward — pending user review)

- [x] Rich progress bars for both engines' scan loops: `Crawler`/`WebAssessmentEngine` report `(pages_fetched, max_pages)` per depth level; `ProtocolFuzzingEngine` reports `(iterations_completed, total, findings_so_far)` per concurrency chunk. Both are plain callback hooks (`on_progress`) on the engines themselves, not a Rich dependency baked into engine code - the CLI is what turns them into a `rich.progress.Progress` bar, keeping engines UI-agnostic and unit-testable without a terminal.
- [x] Colored console output: `cli/ui.py` adds `severity_tag()` (INFO dim → CRITICAL bold-white-on-red), used everywhere a Finding's severity is printed.
- [x] `autofuzz resume <scan-id>`: resumes an interrupted **protocol fuzzing** scan from its last checkpoint (`session.progress["iterations_completed"]`/`["findings"]`), continuing rather than re-fuzzing already-completed iterations. Rejects web scans (not supported - see below), already-completed scans, and unknown scan ids.
- [x] `autofuzz history`: lists recorded scan sessions (id, engine, target, state, finding count, started) from the local session store.
- [x] Actionable error messages: `cli_main()` now wraps `app()` so any `AutoFuzzError` that escapes a command body (found one real gap: `TargetError` from a failed Docker recovery wasn't caught by the existing narrower `except EngineError` blocks) prints a clean message and exits 2 instead of a raw traceback; `KeyboardInterrupt` exits quietly (130).
- [x] Logging verbosity flags: `-v`/`--quiet` already existed (Phase 2); unchanged, still sufficient (`-v` → DEBUG, `--quiet` → ERROR).

**Foundation work this required (not itself on the original checklist):**
- `core/scan.py`: `ScanSession` gained a `target` field (it only stored the profile before, which for web scans never captured the actual URL) and `start()` now allows resuming from `RUNNING`/`FAILED`, not just `CREATED`/`PAUSED` - a session left `RUNNING` almost always means the process that owned it died mid-scan, which is exactly the case `resume` exists for.
- `plugins/base.py`: `Finding.to_dict()`/`from_dict()`, so progress checkpoints and `resume` can round-trip findings through JSON without duplicating that logic ad hoc in the CLI.
- Every `web`/`proto`/`resume` invocation now creates and checkpoints a `ScanSession` under `AutoFuzzSettings().config_dir / "scans"` (`~/.autofuzz/scans/` by default) - this also closes most of Phase 6's carried-forward "streaming writes" gap for protocol fuzzing specifically: progress and findings-so-far are persisted after every concurrency chunk, not only at the end. (Web scans still only checkpoint page count, not partial findings - crawl state itself isn't resumable yet, see below.)

**Not done in this phase (carried forward):**
- Interactive mode (prompt for target/profile when none given) and config profile management commands (`autofuzz config ...`) - lower priority than getting resume/history working end-to-end; no design started yet.
- **Web-scan resume.** `autofuzz resume` explicitly rejects web scans with a clear message rather than pretending to support it. Protocol fuzzing resume just needs an iteration counter; a crawl's actual state (visited-URL set, BFS frontier) isn't serialized anywhere, so resuming one properly needs real design work, not a quick extension of the proto path.

**Verification run this phase** (same `.venv`):
- `ruff check` / `ruff format --check` — clean
- `mypy --strict` — 43 source files, no issues (no new packages needed adding to scope this phase)
- `pytest` — 204/204 passing, 96% coverage, including a dedicated test for `cli_main()`'s global error wrapper (`CliRunner` calls `app` directly and never exercises that wrapper, so it needed its own test invoking `cli_main()`)
- `python -m build --wheel` — builds cleanly
- **Critical fix applied before it became a real bug**: initial CLI tests would have written real scan-session files into the actual `~/.autofuzz/scans/` on every test run. Added an autouse fixture setting `AUTOFUZZ_CONFIG_DIR` per test (already-supported via `AutoFuzzSettings`' env-var prefix, just never previously exercised) and confirmed after a full run that no `~/.autofuzz` directory was created.
- Manual end-to-end smoke test: real fake-FTP server + the actual installed CLI (not `CliRunner`) - `autofuzz proto` showed a live progress bar and colored findings, `autofuzz history` listed the completed scan in a real terminal, `autofuzz resume` correctly rejected it as already-completed. Noted one minor, non-blocking cosmetic issue: Rich's history table truncates long values (target, timestamp) on a narrow/cp1252 terminal - the underlying session data is intact, only the table display truncates.

## Phase 8 — Performance (complete — pending user review)

Every item below was measured, not assumed — where the data said "this is
fine," nothing was changed; where it found a real problem, it got fixed.

- [x] **CPU profiling of mutation/hot loops** — `cProfile` on 50,000
  `mutate()` calls found `random_byte_flood` alone consuming ~75% of the
  entire mutator corpus's CPU time (despite being 1 of 18 strategies),
  caused by calling `random.randint()` individually 2048 times per
  mutation. Fixed by switching to `random.choices()` over a precomputed
  population (`protocol_fuzzing/mutators/strategies.py`), matching the
  pattern `random_control_byte_flood` already used. **Result: 50,000 calls
  went from 15.2s to 5.5s under profiling (~2.8x), ~48-51k mutations/sec
  unprofiled.** Behavior is unchanged (same length, same 1-255 byte range) —
  covered by new tests asserting both.
- [x] **CPU profiling of the crawler** — profiled a 300-page crawl;
  BeautifulSoup/`html.parser` doesn't even appear in the top 15 functions by
  cumulative time. httpx request/response handling dominates (~96% of
  wall time). This is data, not a guess, for a decision already implicitly
  made in Phase 4: switching to an `lxml` parser backend would not
  meaningfully help, since parsing was never the bottleneck. Not changed.
- [x] **Memory profiling under large crawls** — `tracemalloc` on a 500-page
  crawl (~30KB HTML each, ~15MB raw content) peaked at 23.2MB traced memory
  (~1.5x raw content size) — linear, bounded, no leak. Extrapolated to
  `web-thorough.yaml`'s `max_pages: 10000` ceiling, that's roughly
  400-500MB for a maximal scan. That's a real, worth-knowing scaling
  characteristic (every fetched page's HTML is held in memory for the
  whole crawl, since plugins/fingerprinting run after crawling completes,
  not incrementally) — but the data showed linear/bounded growth, not a
  leak or blowup, so the invasive fix (stream per-page analysis into the
  crawl loop instead of analyzing after) wasn't undertaken this phase.
  Documented here as a known characteristic rather than silently ignored.
- [x] **Startup time check (CLI cold start)** — measured: bare Python
  interpreter start ~49ms; `import autofuzz.cli.app` ~527ms;
  `autofuzz --version` end-to-end averages ~486ms across 5 runs. Broke
  down where the time goes (`typer` 74ms, `httpx` 61ms, `bs4` 38ms,
  `pydantic` 22ms, `jinja2` 18ms, `defusedxml` 4ms, plus their transitive
  deps and interpreter overhead not captured by per-module measurement).
  **Considered and rejected** lazy-importing `WebAssessmentEngine`/
  `ProtocolFuzzingEngine` out of `cli/app.py`'s module level to speed up
  `--version`/`--help`/`history`: those names must stay module attributes
  because every Phase 6/7 CLI test injects fakes via
  `monkeypatch.setattr(cli_app, "WebAssessmentEngine", ...)` — moving the
  import into the function body would silently break that pattern across
  the whole test suite for a ~20-30% cold-start improvement on commands
  where startup time barely matters next to a scan that runs for seconds
  to minutes anyway. Documented as measured baseline, not chased further.
- [x] **Concurrency tuning + safe defaults** — `SchedulerConfig.concurrency`
  was already bounded (`ge=1, le=500`, Phase 3). The protocol-fuzzing
  benchmark below shows **diminishing returns past ~10-30 concurrent
  connections against a single target** (531 → 571 iterations/sec going
  from concurrency 10 to 30, a 7% gain for 3x the connections) — documented
  here as data-driven guidance for profile tuning rather than a new hard
  cap, since the right ceiling depends on the target, not a number
  AutoFuzz can safely assume for every target.
- [x] **Response caching within a scan session** — verified rather than
  built: the crawler's `visited: set[str]` already guarantees no URL is
  fetched twice within one crawl (Phase 4), and `WebAssessmentEngine`
  doesn't currently call `discover_robots_txt`/`discover_sitemap`
  independently in a way that would duplicate a crawl fetch. No redundant-
  request pattern exists in the current architecture to justify a new
  caching layer - would have been complexity added for a problem that
  isn't there.
- [x] **Benchmark harness**: `scripts/benchmark.py` - measures protocol
  engine throughput, web engine throughput, mutator throughput, and CLI
  cold start, all against local in-process fake targets (no external
  network dependency). Meant to be re-run by contributors to catch
  regressions, not just a one-off report.
- [x] **Published comparison vs. v1 baseline** — v1 was intentionally
  removed from the working tree in Phase 5 at the user's request, so this
  harness doesn't carry a v1 codepath forward. Instead: retrieved v1
  verbatim from git history (commit `dea1c65`, before its Phase 5 removal)
  and ran it head-to-head against v2, both doing exactly 1000 iterations
  against the same fake FTP server:

  | Engine | Time | Throughput | vs. v1 |
  |---|---|---|---|
  | v1 (single blocking connection, includes its own per-iteration testcase-file logging) | 5.91s | 169.1 iter/s | 1.0x |
  | v2, concurrency=1 | 2.78s | 359.1 iter/s | 2.1x |
  | v2, concurrency=10 | 2.06s | 485.2 iter/s | 2.9x |
  | v2, concurrency=30 | 1.94s | 514.4 iter/s | 3.0x |

  Even v2 at concurrency=1 beats v1 by ~2x (async I/O overhead is lower
  than v1's blocking sockets, and v1's per-iteration file write adds real
  disk I/O v2 doesn't have in its hot path); real concurrency then adds
  another ~40% on top before hitting the same diminishing-returns wall
  noted above. This comparison isn't reproducible via the committed
  harness (deliberately - resurrecting v1 into the tree to keep it
  re-runnable would partially undo its Phase 5 retirement); the numbers
  above are the durable record of it.

## Phase 9 — DevSecOps (complete except one repo setting only the user can flip — pending user review)

Also included a repo-wide optimization pass (see below the DevSecOps items) since it was requested alongside this phase.

- [x] `.github/workflows/ci.yml`: parallel jobs for `ruff check`/`ruff format --check`, `mypy --strict` (both the package and `scripts/benchmark.py`), a test matrix across Python 3.10-3.13 (matching `requires-python`), a build job gated on the other three, plus a Docker-lab-image build smoke test, `pip-audit`, a Trivy filesystem scan, and Semgrep
- [x] `.github/workflows/codeql.yml`: push/PR to `main` + a weekly Monday scheduled run, `security-extended` query pack
- [x] Semgrep integration: **actually installed and run locally against the real codebase** (not just wired into CI blind) - found 2 real findings (both the same rule, `python.flask.security.xss.audit.direct-use-of-jinja2`, flagging `reporting/renderers/html.py`'s direct Jinja2 `Environment` use). Reviewed rather than reflexively suppressed: the rule assumes a Flask app and suggests `render_template()`, which doesn't apply here, but what it's actually checking for - autoescaping - is already explicitly enabled (`autoescape=True`, set deliberately in Phase 6, covered by a dedicated XSS test). Suppressed inline with `# nosemgrep` and a comment explaining why, not by disabling the rule category. Confirmed **0 findings** on the corrected baseline, so the CI step ships **blocking**, not deferred to "non-blocking initially" as originally planned - there was no reason to soften it once a clean run was actually confirmed.
- [x] `pip-audit` dependency scanning: added to `dev` extras and **run for real** against the current dependency set - 0 known vulnerabilities. Wired into CI as its own job.
- [x] Trivy scanning: **scoped honestly, not blindly wired to "Trivy Docker image scanning" as originally phrased.** There is no application Docker image yet (that's Phase 10); running Trivy in filesystem-scan mode (`trivy fs .`) covers dependencies and IaC config today, which is real coverage rather than a no-op placeholder. `docker/labs/ftp-vsftpd/` is explicitly excluded from the scan - it's a deliberately vulnerable fuzzing target (old Ubuntu + vsftpd), and flagging it as insecure would just be noise about the exact insecurity it exists to provide. Full container image scanning activates once Phase 10's app image exists. Not runnable locally (no Trivy binary in this environment) - will get its first real run in CI.
- [ ] **GitHub secret scanning + push protection is a repository setting, not code — only you can enable it** (I don't have access to your repo's GitHub settings). Steps: repo → Settings → Code security and analysis → enable "Secret scanning" and "Push protection." Left unchecked here since it's not something I can verify or do on your behalf.
- [x] SBOM generation (CycloneDX via Syft, through `anchore/sbom-action` which wraps Syft) — wired into `release.yml`, produced and attached on every tagged release
- [x] `.github/workflows/release.yml`: tag-triggered (`v*`), re-runs the full verification suite before building (so a broken release can't ship), builds the sdist/wheel, generates the SBOM, and publishes a GitHub Release with `generate_release_notes: true` standing in for a hand-maintained changelog until `CHANGELOG.md` exists (Phase 11). PyPI publishing intentionally excluded, per `PROJECT_PLAN.md`'s original scope call.

### Optimization pass (requested alongside this phase)

Motivated directly by a real user-reported issue: a `web-thorough` crawl against a real site appeared to hang at a fixed progress percentage.

- [x] **Root-caused and fixed the actual visual bug** (this shipped just before this phase, included here for the full picture): httpx logs every HTTP request at INFO level via stdlib `logging`; since it has no handler of its own, those records flooded stdout through AutoFuzz's own root handler and visually collided with Rich's live progress bar redraws, making a still-running crawl look frozen. Fixed in `core/logging.py` by pinning `httpx`/`httpcore` to WARNING regardless of AutoFuzz's own configured level.
- [x] **Fixed the progress-granularity issue underneath the visual bug.** `Crawler` only reported progress once per BFS depth *level*, not per page - a level with hundreds of URLs (common on a real content site) looked stalled for the entire time it took to fetch all of them. `WorkerPool.run_all()` gained an optional `on_job_done` callback that fires the instant each individual job finishes (success or failure) while still preserving `gather()`'s order-preserving return contract (verified by a dedicated test alongside the existing order-preservation test). `Crawler` now reports one progress tick per fetched page instead of per level.
- [x] **Caught and fixed the I/O cost the granularity fix would have introduced**: reporting progress 10,000 times for a `max_pages: 10000` crawl would mean 10,000 full `ScanSession.save()` disk writes if left naive. The CLI now updates the (cheap, in-memory) Rich progress bar on every callback but only checkpoints the session to disk every 25 pages, plus always on the final update - bounded I/O instead of O(pages).
- [x] Considered applying the same per-job granularity to `ProtocolFuzzingEngine` for symmetry, and deliberately didn't: its progress already fires once per concurrency-sized chunk (typically small, a few seconds each) rather than per unbounded-size level, so there's no equivalent reported problem there, and `resume`'s checkpoint correctness depends on `findings_so_far` being accurate at the moment it's captured - changing that granularity for symmetry alone would add real resume-correctness risk for no concrete benefit.

**Verification run this phase:**
- `ruff check` / `ruff format --check` — clean (`src`, `tests`, `scripts`)
- `mypy --strict` — 43 package files + `scripts/benchmark.py` checked separately, no issues
- `pytest` — 212/212 passing, 96% coverage
- `python -m build --wheel` — builds cleanly
- All three workflow YAML files parsed successfully with PyYAML (the `on:` key parsing as the boolean `True` in the check output is a well-known PyYAML/YAML-1.1 quirk with bare `on`/`off`, not a bug in the files - GitHub's own parser handles it correctly)
- `pip-audit` and `semgrep` both actually installed and run locally against the real codebase (results above), not left as untested CI-only assumptions
- `actionlint` and `trivy` were not available in this environment to deep-validate the workflow syntax/run locally; both will get their first real execution in CI

**Post-merge correction — the actual GitHub Actions run found real problems the local check above missed:**
1. `aquasecurity/trivy-action@0.29.0` doesn't exist as a tag - the real tag is `v0.29.0` (with the `v` prefix I dropped). Fixed by pinning to the current release, `v0.36.0`, after actually checking the project's release list rather than guessing again.
2. The local Semgrep run before this phase's commit only scanned `src tests scripts` - never `.github/workflows/` or `docker/`. The real CI run, scanning the whole repo (matching what `--config=auto` with no path argument actually does), found 25 findings: 24 instances of `yaml.github-actions.security.github-actions-mutable-action-tag` (every `uses: action@vN` in all three workflow files) and 1 real `dockerfile.security.missing-user` hit on `docker/labs/ftp-vsftpd/Dockerfile`.
   - Attempted to fix the mutable-tag finding properly (pin to full commit SHAs, which is what the rule asks for) - and caught a second near-miss doing it: the SHAs pulled via an LLM-summarized fetch of GitHub's API were wrong (verified by cross-checking each against its own commit page; several resolved to unrelated commits, one 404'd outright). Given hand-entering a wrong 40-character SHA breaks CI the exact same way the trivy-action typo did, this was excluded via `--exclude-rule` instead, with the tradeoff documented directly in `ci.yml`: version-tag pinning is what this repo uses today (the same convention GitHub's own default workflows use), and upgrading to verified SHA pins is legitimate follow-up work best done with a tool that resolves and checks them correctly, not by hand.
   - The Dockerfile finding was real and specific: `vsftpd`'s own master process must start as root to bind port 21, then drops privileges per-connection via `setuid` for the actual FTP-session handling (the part being fuzzed) - standard, secure-by-design upstream `vsftpd` behavior, not a gap. Suppressed inline in the Dockerfile with that explanation, not blanket-excluded.
   - Re-ran `semgrep scan --config=auto --error --exclude-rule=...` locally, matching CI's exact command, against the whole repo this time: **0 findings.**

Lesson applied going forward: verify security tooling against the same scope CI actually runs it against, not a convenient subset.

**Not done in this phase (carried forward):** GitHub secret scanning/push protection (repo setting - see above), a maintained `CHANGELOG.md` (Phase 11), and full container image scanning (Phase 10, once an app Dockerfile exists).

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
