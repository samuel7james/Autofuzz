# Authorized-Use Policy

AutoFuzz is built for **authorized security testing and research only**:
sanctioned penetration tests, security research on systems you own or
control, CTF competitions, and educational lab environments. It is not a
tool for testing systems you don't have explicit permission to test.

## What AutoFuzz actually does to a target

- **Protocol Fuzzing Engine** — sends large volumes of aggressively
  mutated, malformed protocol commands (buffer overflows, null-byte
  floods, format-string probes, and more — see
  [architecture.md](architecture.md#protocol-fuzzing-engine-autofuzzprotocol_fuzzing))
  at a real network service, concurrently, by design intended to crash or
  destabilize it. This is not a passive check.
- **Web Assessment Engine** — crawls a target and runs passive analysis
  (missing security headers, insecure cookie attributes, server version
  disclosure, technology fingerprinting). It does not attempt exploitation,
  but a crawl at meaningful concurrency and depth is still real traffic
  against a real target's infrastructure, logging, and rate limits.

Both can be indistinguishable from an actual attack to the target's
owner, its monitoring systems, and any upstream network it sits behind.

## The authorization gate

Every scan profile requires an explicit `authorized: true` field
(`ScanProfile.authorized` in `core/config.py`). The CLI refuses to run
without it — `_load_and_authorize()` in `cli/app.py` exits with an error
before any engine starts if this flag is false or missing. This is
enforced in code, not just documented, per the project's Security Plan
(`PROJECT_PLAN.md` §10).

**This flag is not authorization.** It is a speed bump against
accidentally running a profile you copied from someone else, or against a
target you meant to double-check first. Setting it to `true` should
happen only after you have actual, documented permission to test the
target — a signed engagement letter, a bug bounty program's published
scope, your own infrastructure, or a lab you built yourself.

The example profiles in `examples/configs/` (`ftp-lab.yaml`,
`ftp-lab-compose.yaml`) ship with `authorized: true` because they only
ever target a local, disposable container AutoFuzz's own Docker setup
provisions and controls — never a stand-in for authorizing any other
target. Copying one of these profiles to point at a different host does
not carry that authorization with it.

## Target recovery is opt-in and scoped

`protocol.target_controller: docker` (see
[architecture.md](architecture.md#core-autofuzzcore)) will restart a named
Docker container when it goes down mid-scan. This defaults to `none` and
must be explicitly configured with a specific container name. Never point
it at infrastructure AutoFuzz did not itself provision — restarting a
service you don't own the lifecycle of, even to "help," is an action
outside the scope of most authorizations.

## The mutation corpus's literal-looking payloads

Two mutators in `protocol_fuzzing/mutators/strategies.py`
(`injection_probe_with_shell_metacharacters`, `shell_metacharacter_probe`)
append strings that look like destructive shell commands (e.g.
`rm -rf / --no-preserve-root`). These are **inert data sent to the fuzzed
target's own protocol parser** — AutoFuzz never executes them locally.
They exist to test whether the target unsafely passes fuzzed protocol
input into a local shell. See the docstrings on those functions for
detail.

## Lab-only credentials

`docker/labs/ftp-vsftpd/` ships a disposable, intentionally vulnerable
vsftpd target with hardcoded default credentials, for local fuzzing
practice only. These credentials and this container image are not
hardened and must never be exposed to a network you don't fully control.

## Reporting a vulnerability in AutoFuzz itself

If you find a security issue in AutoFuzz's own code (not in a target you
scanned with it), please open a GitHub issue or contact the maintainers
directly rather than filing a public exploit — see
[CONTRIBUTING.md](../CONTRIBUTING.md).
