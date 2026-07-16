# Developer Guide

Read [architecture.md](architecture.md) first for how the pieces fit
together. This guide covers dev setup and the three most common extension
points: adding a web plugin, a protocol mutator, and a protocol adapter.

## Development setup

```bash
git clone https://github.com/samuel7james/Autofuzz.git
cd Autofuzz
pip install -e ".[dev]"
```

Requires Python 3.10+ (CI tests against 3.10–3.13).

## Running the checks CI runs

```bash
ruff check src tests scripts
ruff format --check src tests scripts
mypy
mypy --strict scripts/benchmark.py
coverage run -m pytest
coverage report -m
```

All four (lint, format, mypy --strict, tests) must pass before merging —
see [.github/workflows/ci.yml](../.github/workflows/ci.yml). If you're
touching `.github/workflows/`, `docker/`, or anything Semgrep scans, also
run it locally against the whole repo (not just `src tests scripts` — that
narrower scope missed real findings once already):

```bash
docker run --rm -v "$(pwd):/src" semgrep/semgrep semgrep scan --config=auto --error
```

Use the actual `semgrep/semgrep` container image, not a locally pip-installed
CLI — different versions have flagged different things in this repo, and
the container image is what CI actually runs.

## Adding a web plugin

Plugins live in `src/autofuzz/plugins/builtin/` and implement
`Plugin[CrawlResult]` from `plugins/base.py`:

```python
from autofuzz.plugins.base import Finding, Plugin, PluginMetadata, Severity
from autofuzz.web.crawler import CrawlResult


class MyPlugin(Plugin[CrawlResult]):
    metadata = PluginMetadata(
        id="web.my-check",
        name="My Check",
        description="What this plugin flags.",
        engine="web",
    )

    def applies_to(self, context: CrawlResult) -> bool:
        return context.status_code is not None

    def run(self, context: CrawlResult) -> list[Finding]:
        # Analyze context.headers / context.html / context.status_code —
        # never make your own network request here (see architecture.md's
        # note on why plugins are synchronous and side-effect-free).
        return []
```

Register it in `default_web_plugin_registry()` in
`src/autofuzz/web/engine.py`:

```python
registry.register(MyPlugin())
```

A plugin id must be unique (`PluginRegistry.register` raises `PluginError`
otherwise), and a plugin that raises during `run()` is logged and skipped
rather than aborting the scan — you don't need your own try/except for
that. If your plugin takes options, implement `configure(self, options)`
(see `MissingSecurityHeadersPlugin`'s `ignore_headers` option in
`plugins/builtin/web_headers.py` for an example) — operators set them via
a profile's `plugins.options.<plugin-id>`.

Add a unit test in `tests/unit/` following the pattern in
`test_web_headers_plugins.py`: construct a `CrawlResult` directly (no
crawler needed) and assert on the `Finding`s your plugin returns.

## Adding a protocol mutator

Mutators live in `src/autofuzz/protocol_fuzzing/mutators/strategies.py` as
plain `str -> str` functions:

```python
def my_mutator(command: str) -> str:
    """One line: the fault class this targets."""
    return command + "..."
```

Add it to the `ALL_MUTATORS` tuple. `mutate()` picks one at random per
command, so every mutator should be fast and side-effect-free — it runs
once per fuzzed command, potentially thousands of times per scan. If a
mutator does non-trivial work per call (see `random_byte_flood`'s
docstring for a real example of a naive version dominating the corpus's
CPU time), profile it before shipping.

Add a unit test in `tests/unit/test_mutators.py` asserting the specific
transformation your mutator makes.

## Adding a protocol adapter

A protocol adapter is a transport: given a host, port, and mutated command
sequence, it sends the sequence and reports what happened. The contract
(`SendSequence` in `src/autofuzz/protocol_fuzzing/engine.py`):

```python
async def send_sequence(
    host: str, port: int, sequence: list[str], *, test_id: int, timeout: float
) -> FuzzAttempt:
    ...
```

**Never raise.** Capture any exception on the returned `FuzzAttempt`
instead — `crash_classifier.classify()` is what turns a captured exception
into a `FaultKind` (timeout / rejected / crash), and a raised exception
would just be logged and dropped by the engine instead of classified. See
`src/autofuzz/protocol_fuzzing/adapters/ftp.py` for the reference
implementation, including the subtlety that a clean connection close
(EOF, no exception) after sending a command is itself worth reporting as
a fault, not silently treated as an "OK".

Register your adapter in the `ADAPTERS` dict in
`src/autofuzz/protocol_fuzzing/engine.py`:

```python
from autofuzz.protocol_fuzzing.adapters.my_protocol import send_sequence as my_send_sequence

ADAPTERS: dict[str, ProtocolAdapter] = {
    "ftp": ProtocolAdapter(default_sequence=_FTP_DEFAULT_SEQUENCE, send_sequence=ftp_send_sequence),
    "my-protocol": ProtocolAdapter(
        default_sequence=["HELLO", "AUTH guest", "QUIT"],
        send_sequence=my_send_sequence,
    ),
}
```

A profile then selects it via `protocol.adapter: my-protocol`. The engine
validates `protocol_config.adapter` against this registry at construction
time (`EngineError` if unknown) and dispatches every attempt through the
registered adapter's own `send_sequence` — there's no protocol-specific
branching anywhere else in the engine.

Add a unit test following `test_engine.py`'s
`test_run_dispatches_to_the_configured_adapters_send_sequence`: register a
fake adapter via `monkeypatch.setitem(ADAPTERS, ...)` and assert your
adapter's `send_sequence` is actually invoked with the expected arguments
— this is specifically the pattern that guards against a hardcoded
transport call bypassing the registry.

For a real end-to-end test against a live target (not a fake), see
`tests/integration/test_protocol_engine.py`, which runs the FTP adapter
against `docker/labs/ftp-vsftpd/`.

## Project layout reference

```
src/autofuzz/
  core/               shared scheduler, config, scan session, plugin registry, errors, logging
  protocol_fuzzing/    FSM, mutators, adapters, crash classifier, engine
  web/                 crawler, http client, discovery, engine
  plugins/             Finding/Plugin base contracts, built-in web plugins
  reporting/           ScanReport/RiskScore models and format renderers
  cli/                 Typer app, console/UI helpers
tests/
  unit/                one test module per source module, fast, no real I/O
  integration/          real engine runs against real local targets
docker/
  Dockerfile            AutoFuzz's own image (non-root, multi-stage)
  docker-compose.yml     AutoFuzz + disposable FTP lab
  labs/ftp-vsftpd/       the intentionally vulnerable fuzzing target
examples/configs/        sample scan profiles referenced in the README
scripts/benchmark.py      performance benchmarking harness (Phase 8)
```
