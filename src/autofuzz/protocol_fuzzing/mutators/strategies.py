"""Mutation corpus for protocol fuzzing.

Ported from v1's inline lambda list (formerly ``autofuzz.py``, now
``legacy/autofuzz_v1.py``) into discrete, named, independently testable
functions. Each mutator is documented with the fault class it targets.

All payloads are literal *data* sent to the fuzzed target's own protocol
parser - including the two that look like shell commands
(``injection_probe_with_shell_metacharacters``,
``shell_metacharacter_probe``) - AutoFuzz never executes them locally. They
exist to probe whether the target unsafely passes fuzzed protocol input
into a local shell. See PROJECT_PLAN.md Section 10 (Security Plan).
"""

from __future__ import annotations

import random
from collections.abc import Callable

Mutator = Callable[[str], str]

BAD_CHARS: list[str] = [chr(i) for i in [*range(0, 32), *range(127, 256)]]


def buffer_overflow_suffix(command: str) -> str:
    """Append a large run of 'A's - a classic length-overflow probe."""
    return command + "A" * 10000


def null_byte_flood(command: str) -> str:
    """Append 1000 NUL bytes - probes null-byte truncation/handling bugs."""
    return command + "\x00" * 1000


def path_traversal_flood(command: str) -> str:
    """Append repeated '../' sequences - probes path traversal handling."""
    return command + "../../" * 500


def injection_probe_with_shell_metacharacters(command: str) -> str:
    """Append quote characters and a destructive-looking shell command string.

    Inert data sent to the target's own command parser - never executed
    locally. Probes whether the target passes fuzzed protocol input into a
    local shell without sanitization.
    """
    return command + "'" * 1000 + "; rm -rf / --no-preserve-root"


def random_control_byte_flood(command: str) -> str:
    """Append 2048 random control/high bytes drawn from BAD_CHARS."""
    return command + "".join(random.choices(BAD_CHARS, k=2048))


def case_amplification(command: str) -> str:
    """Uppercase the command and repeat it 100 times."""
    return command.upper() * 100


def reversed_duplication(command: str) -> str:
    """Reverse the command, duplicate it, and repeat 50 times."""
    return (command[::-1] + command[::-1]) * 50


def bom_prefix_duplication(command: str) -> str:
    """Prefix with a UTF-16 byte-order-mark-like sequence and repeat."""
    return f"\xff\xfe{command}" * 100


def deadbeef_marker_flood(command: str) -> str:
    """Append a repeated 0xDEADBEEF byte marker, useful for spotting the
    payload in a crash dump or memory inspection."""
    return command + "\xde\xad\xbe\xef" * 500


def format_string_probe(command: str) -> str:
    """Replace the command with repeated printf-style format specifiers -
    probes format-string vulnerabilities."""
    del command
    return "%%s%%x%%n%%p" * 1000


_ALL_BYTE_CHARS: list[str] = [chr(i) for i in range(1, 256)]


def random_byte_flood(command: str) -> str:
    """Append 2048 fully random bytes (1-255).

    Uses ``random.choices`` over a precomputed population rather than 2048
    individual ``random.randint`` calls - profiling showed the naive form
    dominating the entire mutator corpus's CPU time (~75% of it, despite
    being 1 of 18 strategies) purely from per-call Python overhead.
    """
    return command + "".join(random.choices(_ALL_BYTE_CHARS, k=2048))


def keyword_strip_and_flood(command: str) -> str:
    """Strip the literal 'USER' keyword, then append a random byte flood -
    probes keyword-dependent parsing logic."""
    return command.replace("USER", "") + "".join(random.choices(BAD_CHARS, k=1024))


def marker_token_flood(command: str) -> str:
    """Append a human-readable marker token, repeated - easy to grep for in
    target-side logs when correlating a crash."""
    return command + "CRASHME_NOW" * 300


def newline_and_high_byte_flood(command: str) -> str:
    """Append 1000 newlines followed by 1000 high (0xFF) bytes."""
    return command + "\n" * 1000 + "\xff" * 1000


def credential_injection_flood(command: str) -> str:
    """Replace the command with a repeated hardcoded login attempt - probes
    command-sequence/state confusion rather than the original text."""
    del command
    return "USER root\r\nPASS toor\r\n" * 500


def shell_metacharacter_probe(command: str) -> str:
    """Append shell pipe/echo metacharacters and a random byte flood.

    Like ``injection_probe_with_shell_metacharacters``, this is inert data
    sent to the target's parser, never executed locally.
    """
    return f"{command} || echo hacked ||" + "".join(random.choices(BAD_CHARS, k=1000))


def massive_buffer_overflow(command: str) -> str:
    """Replace the command with 50000 'A's."""
    del command
    return "A" * 50000


def line_repetition_flood(command: str) -> str:
    """Repeat the command 100 times, joined by CRLF."""
    return "\r\n".join([command] * 100)


ALL_MUTATORS: tuple[Mutator, ...] = (
    buffer_overflow_suffix,
    null_byte_flood,
    path_traversal_flood,
    injection_probe_with_shell_metacharacters,
    random_control_byte_flood,
    case_amplification,
    reversed_duplication,
    bom_prefix_duplication,
    deadbeef_marker_flood,
    format_string_probe,
    random_byte_flood,
    keyword_strip_and_flood,
    marker_token_flood,
    newline_and_high_byte_flood,
    credential_injection_flood,
    shell_metacharacter_probe,
    massive_buffer_overflow,
    line_repetition_flood,
)


def mutate(command: str, mutators: tuple[Mutator, ...] = ALL_MUTATORS) -> str:
    """Apply one randomly chosen mutator to ``command`` (v1's ``mutate_command``)."""
    return random.choice(mutators)(command)
