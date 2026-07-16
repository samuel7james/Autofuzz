# Architecture

AutoFuzz is two engines — **Protocol Fuzzing** and **Web Assessment** — built
on one shared core. Both engines produce the same output unit (`Finding`),
run under the same scheduler, and are checkpointed by the same scan-session
mechanism, so the CLI, reporting, and DevOps tooling never need to
special-case which engine produced a result.

```
                        ┌─────────────────────────┐
                        │          CLI            │
                        │  (autofuzz/cli/app.py)  │
                        └───────────┬─────────────┘
                                    │
              ┌─────────────────────┴─────────────────────┐
              │                                            │
   ┌──────────▼───────────┐                    ┌───────────▼───────────┐
   │ ProtocolFuzzingEngine │                    │  WebAssessmentEngine  │
   │  (FSM + mutators +    │                    │  (crawler + plugins + │
   │   transport adapter)  │                    │   discovery)          │
   └──────────┬───────────┘                    └───────────┬───────────┘
              │                                             │
              └─────────────────────┬───────────────────────┘
                                    │
                        ┌───────────▼────────────┐
                        │        Core            │
                        │  WorkerPool/RateLimiter │
                        │  ScanSession            │
                        │  PluginRegistry         │
                        │  ScanProfile / config   │
                        └───────────┬────────────┘
                                    │
                        ┌───────────▼────────────┐
                        │       Reporting         │
                        │  Finding → RiskScore →  │
                        │  HTML/Markdown/JSON/CSV │
                        └─────────────────────────┘
```

## Core (`autofuzz/core/`)

- **`config.py`** — `ScanProfile`, the single typed, YAML-loadable object
  that configures a scan: which engine, scheduler tuning
  (`SchedulerConfig`), engine-specific settings (`WebEngineConfig`,
  `ProtocolEngineConfig`), plugin enable/disable/options
  (`PluginConfig`), and the `authorized` gate. `AutoFuzzSettings` holds
  process-wide, environment-sourced settings (`AUTOFUZZ_*`).
- **`scheduler.py`** — `WorkerPool`, `RateLimiter` (token bucket), and
  `RetryPolicy` (exponential backoff with jitter). Both engines submit
  jobs to a `WorkerPool` instead of managing their own concurrency,
  rate limiting, or retries.
- **`scan.py`** — `ScanSession`: a small state machine
  (`created → running → paused/failed → completed`) with JSON
  persistence, engine-agnostic so `autofuzz history`/`resume` work the
  same way for a web crawl or a protocol fuzzing run. Session files are
  written owner-only (`chmod 700`/`600` on POSIX) since they can contain
  scraped evidence.
- **`plugin.py`** — `PluginRegistry`: holds a set of `Plugin` instances
  for one engine, applies a `ScanProfile`'s enable/disable list and
  per-plugin options, and runs them against a stream of contexts. A
  plugin that raises is logged and skipped — never aborts the scan.
- **`target_controller.py`** — `TargetController` protocol for checking
  liveness and recovering a target. `NoOpTargetController` (default) never
  touches anything; `DockerTargetController` restarts a named container
  AutoFuzz itself provisioned. Recovery is opt-in per profile
  (`protocol.target_controller`) — a target AutoFuzz doesn't own is never
  "recovered" automatically.
- **`errors.py`** — one `AutoFuzzError` hierarchy so the CLI can catch a
  single base type and print a clean message instead of a traceback.
- **`logging.py`** — `structlog`-based structured logging, configured
  once from the CLI's `--verbose`/`--quiet` flags or `AUTOFUZZ_LOG_LEVEL`/
  `AUTOFUZZ_LOG_JSON`. Pins `httpx`/`httpcore`'s own loggers to `WARNING`
  regardless of AutoFuzz's configured level, since their per-request INFO
  logging otherwise floods the console and corrupts Rich's live progress
  bar.

## Protocol Fuzzing Engine (`autofuzz/protocol_fuzzing/`)

`ProtocolFuzzingEngine` (`engine.py`) runs `protocol_config.iterations`
mutated attempts against a target in concurrency-sized chunks, checking
target liveness between chunks so a recovering target gets a chance to
come back before the next batch.

- **`fsm.py`** — `ProtocolFsm`: the base command sequence an adapter sends
  before mutation (e.g. FTP's `USER`/`PASS`/`PWD`/`TYPE`/`LIST`/`QUIT`).
- **`mutators/strategies.py`** — 18 independent mutation functions (buffer
  overflow suffixes, null-byte floods, path traversal, format-string
  probes, shell-metacharacter probes, and more), each targeting a specific
  fault class. `mutate()` picks one at random per command. The two
  mutators that look like shell commands are inert data sent to the
  *target's own protocol parser* — AutoFuzz never executes them locally;
  they exist to probe whether the target unsafely shells out on fuzzed
  input.
- **`adapters/`** — one module per protocol, each exposing an async
  `send_sequence(host, port, sequence, *, test_id, timeout) -> FuzzAttempt`
  that never raises (exceptions are captured on the returned
  `FuzzAttempt` for classification instead). `ftp.py` is the reference
  implementation. New protocols register via the `ADAPTERS` dict in
  `engine.py` — see
  [developer-guide.md](developer-guide.md#adding-a-protocol-adapter).
- **`crash_classifier.py`** — turns a `FuzzAttempt` into a `FaultKind`
  (`none`/`timeout`/`rejected`/`crash`), distinguishing a real fault from
  an ordinary timeout or a deliberate protocol-level rejection, and turns
  a classified crash into a `Finding`.

## Web Assessment Engine (`autofuzz/web/`)

`WebAssessmentEngine` (`engine.py`) crawls a target, then runs the plugin
registry and technology fingerprinting against every fetched page.

- **`crawler.py`** — `Crawler`: bounded breadth-first crawl. Fetches one
  full depth level through the shared `WorkerPool`, extracts links from
  HTML, and only advances into same-origin, not-yet-visited links.
  Bounded by `max_crawl_depth` and `max_pages`. Progress is reported per
  fetched page (not per depth level), since a single level can hold
  hundreds of URLs and per-level reporting made a long level look frozen.
- **`http_client.py`** — thin `httpx`-based async client used by the
  crawler.
- **`discovery/`** — passive analysis over crawl results:
  `endpoints.py` (distinct endpoints found), `params.py` (form/query
  parameters discovered), `fingerprint.py` (technology detection from
  headers/HTML), `robots.py`/`sitemap.py` (robots.txt/sitemap parsing),
  `graph.py` (link graph).

## Plugins (`autofuzz/plugins/`)

- **`base.py`** — the shared contract: `Finding` (the universal output
  unit — a web observation and a protocol crash both produce the same
  type), `Severity`, `PluginMetadata`, and the abstract `Plugin` base.
  Plugins are deliberately synchronous and side-effect-free: they analyze
  data an engine already collected rather than making their own network
  requests.
- **`builtin/web_headers.py`** — the three built-in web plugins:
  `MissingSecurityHeadersPlugin`, `InsecureCookiePlugin`,
  `ServerDisclosurePlugin`.

Plugin registration is explicit (`registry.register(...)` in
`web/engine.py`'s `default_web_plugin_registry()`), not entry-point or
package-scan discovery — AutoFuzz isn't hosting third-party plugin
packages yet, so that machinery would be speculative ahead of a real need.

## Reporting (`autofuzz/reporting/`)

- **`models.py`** — `RiskScore` (severity-weighted aggregate score) and
  `ScanReport` (scan metadata, timing, findings, stats).
- **`renderers/`** — one module per output format (`html.py`,
  `markdown.py`, `json.py`, `csv.py`), dispatched by `ReportFormat`
  through `render_report()`.

## CLI (`autofuzz/cli/`)

`app.py` wires everything above into `autofuzz web`, `autofuzz proto`,
`autofuzz history`, and `autofuzz resume`, plus an implicit-command
shorthand (`autofuzz <target>` infers `web` for a URL, `proto` otherwise)
implemented as an argv rewrite before Typer/Click parses it. Every scan:
loads and validates a `ScanProfile`, enforces the `authorized: true` gate,
creates and checkpoints a `ScanSession`, runs the engine with a live Rich
progress bar, builds and prints a `ScanReport` summary, and writes the
report file. See [user-guide.md](user-guide.md) for the full command
reference.

## Why a shared core

v1 was a single script with FTP-specific globals (`TARGET_HOST`,
`BASE_SEQUENCE`, a hardcoded `restart_docker()`) and a synchronous fuzzing
loop. Every structural decision above exists to let a second engine (web
assessment) reuse that same machinery instead of duplicating it:
`ScanProfile` replaces module-level constants with a typed, per-scan
object; `WorkerPool` replaces the ad hoc synchronous loop with something
both engines can submit concurrent, rate-limited, retried jobs to;
`Finding`/`ScanReport` replace protocol-specific print statements with a
renderable, engine-agnostic report; and `ScanSession` replaces "just
rerun the script" with real resume/history support.
