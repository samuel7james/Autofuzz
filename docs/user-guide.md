# User Guide

## Installation

```bash
pip install -e .
```

Requires Python 3.10+. See the [readme](../readme.md) for the Docker
Compose alternative.

## Global options

```
autofuzz [--version] [-v/--verbose] [-q/--quiet] <command> ...
```

- `--version` — print the installed version and exit.
- `-v`/`--verbose` (repeatable) — sets log level to `DEBUG`.
- `-q`/`--quiet` — sets log level to `ERROR`, suppressing non-essential
  output.
- With neither flag, the log level defaults to `AUTOFUZZ_LOG_LEVEL`
  (`INFO` unless set) — see [.env.example](../.env.example).

## Commands

### `autofuzz web <target> --profile <path>`

Runs the Web Assessment Engine against `<target>` (a URL, e.g.
`https://target.example`).

| Option | Default | Description |
|---|---|---|
| `--profile`, `-p` (required) | — | Path to a YAML scan profile with `engine: web`. |
| `--report-format` | `html` | `html`, `markdown`, `json`, or `csv`. |
| `--report-output`, `-o` | `autofuzz-report-<scan-id>.<ext>` | Report file path. |

Exits `0` if no findings, `1` if the scan produced at least one finding,
`2` on a configuration/authorization error.

### `autofuzz proto <target> --profile <path>`

Runs the Protocol Fuzzing Engine against `<target>` (`host:port`, e.g.
`127.0.0.1:21`).

Same `--report-format`/`--report-output` options as `web`. If `<target>`
differs from the profile's own `protocol.target_host:target_port`, AutoFuzz
warns and uses the profile's target (the profile is the source of truth;
the CLI argument is mostly documentation of intent). Same exit codes as
`web`.

### `autofuzz <target> --profile <path>`

Shorthand: infers `web` if `<target>` starts with `http://`/`https://`,
otherwise `proto`. Equivalent to typing the explicit subcommand.

### `autofuzz history [--limit N]`

Lists past scans (default limit 20, most recent first): scan ID, engine,
target, state, finding count, start time. Reads from the local session
store (`AUTOFUZZ_CONFIG_DIR/scans/`, default `~/.autofuzz/scans/`).

### `autofuzz resume <scan-id>`

Resumes an interrupted **protocol fuzzing** scan from its last checkpoint
(iteration count and findings so far). Web-scan resume isn't supported
yet — start a new `autofuzz web` scan instead. Fails if the scan is
already `completed` or already reached its configured iteration count.
Same `--report-format`/`--report-output` options as `web`/`proto`.

## Scan profiles

A scan profile is a YAML file validated against `ScanProfile`. See
`examples/configs/` for working examples (`web-default.yaml`,
`web-thorough.yaml`, `ftp-lab.yaml`, `ftp-lab-compose.yaml`).

```yaml
name: my-scan            # required, free-form
engine: web               # required: "web" or "proto"
authorized: true          # required to be true, or the CLI refuses to run

scheduler:
  concurrency: 10               # 1-500, default 10
  rate_limit_per_second: 20.0   # > 0, default 20.0
  max_retries: 2                # 0-10, default 2
  retry_backoff_seconds: 1.0    # > 0, default 1.0
  request_timeout_seconds: 10.0 # > 0, default 10.0

web:                       # only relevant when engine: web
  max_crawl_depth: 3        # 0-20, default 3
  max_pages: 500             # >= 1, default 500
  follow_redirects: true      # default true
  respect_robots_txt: true     # default true (informational only — see note below)
  user_agent: "AutoFuzz/2.0 (+authorized-security-assessment)"

protocol:                   # only relevant when engine: proto
  adapter: ftp                 # registered adapter id, default "ftp"
  target_host: 127.0.0.1
  target_port: 21
  iterations: 1000               # >= 1, default 1000
  target_controller: none          # "docker" or "none", default "none"
  docker_container_name: null        # required if target_controller: docker

plugins:
  enabled: null    # allow-list of plugin ids; null (default) = all registered plugins run
  disabled: []     # deny-list of plugin ids
  options: {}       # per-plugin options, e.g. {web.missing-security-headers: {ignore_headers: [...]}}
```

Notes:

- **`authorized: true` is mandatory.** A profile with `authorized: false`
  (or missing) makes the CLI exit with an error before running anything.
  See [ethics.md](ethics.md).
- **`respect_robots_txt`** is currently informational — the crawler does
  not yet enforce robots.txt exclusions either way. It's included in
  profiles to record assessment intent (see the comments in
  `examples/configs/web-thorough.yaml`).
- **`target_controller: docker`** requires `docker_container_name` and
  restarts that container via `docker restart` when the target goes
  down between fuzzing chunks. Only use this for a container AutoFuzz
  itself provisions (e.g. the FTP lab) — never point it at infrastructure
  you don't control the lifecycle of.
- The built-in web plugin ids are `web.missing-security-headers`,
  `web.insecure-cookies`, and `web.server-version-disclosure`. Technology
  fingerprinting findings use `plugin_id: web.technology-fingerprint` but
  are not a registered `Plugin` (always on, not subject to
  `enabled`/`disabled`).

## Report formats

`--report-format` selects the renderer: `html` (a browsable report),
`markdown`, `json` (machine-readable, includes the full `Finding` list and
`RiskScore`), or `csv` (one row per finding). The risk score is a simple,
explainable sum of severity-weighted finding counts (info=0, low=1,
medium=4, high=9, critical=16).

## Environment variables

See [.env.example](../.env.example) for `AUTOFUZZ_CONFIG_DIR`,
`AUTOFUZZ_LOG_LEVEL`, and `AUTOFUZZ_LOG_JSON` — all optional, all have
working defaults, all read directly from the process environment (AutoFuzz
does not load a `.env` file itself).
