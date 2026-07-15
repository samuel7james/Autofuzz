"""Unit tests for the protocol fuzzing mutation corpus (Phase 5)."""

from __future__ import annotations

from unittest.mock import patch

from autofuzz.protocol_fuzzing.mutators import strategies as m

_INPUT = "USER vulnftp"


def test_buffer_overflow_suffix() -> None:
    result = m.buffer_overflow_suffix(_INPUT)
    assert result == _INPUT + "A" * 10000


def test_null_byte_flood() -> None:
    result = m.null_byte_flood(_INPUT)
    assert result == _INPUT + "\x00" * 1000


def test_path_traversal_flood() -> None:
    result = m.path_traversal_flood(_INPUT)
    assert result.startswith(_INPUT)
    assert "../../" in result


def test_injection_probe_with_shell_metacharacters() -> None:
    result = m.injection_probe_with_shell_metacharacters(_INPUT)
    assert result.startswith(_INPUT)
    assert "rm -rf" in result


def test_random_control_byte_flood_length_and_charset() -> None:
    result = m.random_control_byte_flood(_INPUT)
    suffix = result[len(_INPUT) :]
    assert len(suffix) == 2048
    assert all(c in m.BAD_CHARS for c in suffix)


def test_case_amplification() -> None:
    result = m.case_amplification("user")
    assert result == "USER" * 100


def test_reversed_duplication() -> None:
    result = m.reversed_duplication("abc")
    assert result == ("cbacba") * 50


def test_bom_prefix_duplication() -> None:
    result = m.bom_prefix_duplication("x")
    assert result == "\xff\xfex" * 100


def test_deadbeef_marker_flood() -> None:
    result = m.deadbeef_marker_flood(_INPUT)
    assert result == _INPUT + "\xde\xad\xbe\xef" * 500


def test_format_string_probe_ignores_input() -> None:
    result = m.format_string_probe(_INPUT)
    assert result == "%%s%%x%%n%%p" * 1000


def test_random_byte_flood_length() -> None:
    result = m.random_byte_flood(_INPUT)
    assert len(result) == len(_INPUT) + 2048


def test_random_byte_flood_charset_matches_byte_range() -> None:
    # Every appended char must be a valid single byte 1-255 (never NUL,
    # matching the original randint(1, 255) semantics this replaced).
    suffix = m.random_byte_flood(_INPUT)[len(_INPUT) :]
    assert all(1 <= ord(c) <= 255 for c in suffix)


def test_all_byte_chars_population_is_1_to_255() -> None:
    assert len(m._ALL_BYTE_CHARS) == 255
    assert m._ALL_BYTE_CHARS[0] == chr(1)
    assert m._ALL_BYTE_CHARS[-1] == chr(255)


def test_keyword_strip_and_flood_removes_user() -> None:
    result = m.keyword_strip_and_flood("USER vulnftp")
    assert not result.startswith("USER")
    assert "vulnftp" in result[:20]


def test_marker_token_flood() -> None:
    result = m.marker_token_flood(_INPUT)
    assert result == _INPUT + "CRASHME_NOW" * 300


def test_newline_and_high_byte_flood() -> None:
    result = m.newline_and_high_byte_flood(_INPUT)
    assert result == _INPUT + "\n" * 1000 + "\xff" * 1000


def test_credential_injection_flood_ignores_input() -> None:
    result = m.credential_injection_flood(_INPUT)
    assert result == "USER root\r\nPASS toor\r\n" * 500


def test_shell_metacharacter_probe() -> None:
    result = m.shell_metacharacter_probe(_INPUT)
    assert result.startswith(f"{_INPUT} || echo hacked ||")


def test_massive_buffer_overflow_ignores_input() -> None:
    result = m.massive_buffer_overflow(_INPUT)
    assert result == "A" * 50000


def test_line_repetition_flood() -> None:
    result = m.line_repetition_flood("cmd")
    assert result == "\r\n".join(["cmd"] * 100)


def test_all_mutators_registered() -> None:
    assert len(m.ALL_MUTATORS) == 18


def test_mutate_applies_a_mutator_chosen_via_random_choice() -> None:
    with patch.object(m.random, "choice", return_value=m.case_amplification):
        result = m.mutate(_INPUT)

    assert result == m.case_amplification(_INPUT)


def test_mutate_can_be_restricted_to_a_subset() -> None:
    result = m.mutate(_INPUT, mutators=(m.case_amplification,))
    assert result == _INPUT.upper() * 100
