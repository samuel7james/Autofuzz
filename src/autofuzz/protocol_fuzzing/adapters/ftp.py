"""Async FTP transport adapter: v1's successor.

Sends a mutated command sequence over a raw TCP connection using asyncio
streams instead of v1's blocking sockets, so an attempt can run inside the
shared ``WorkerPool`` alongside other concurrent fuzzing attempts. Also
fixes a gap in v1's crash detection: a clean connection close (an empty
read, no exception raised) after sending a command is treated as a fault
here, whereas v1's ``recv()``-returns-nothing case silently logged "OK".
"""

from __future__ import annotations

import asyncio

from autofuzz.protocol_fuzzing.crash_classifier import FuzzAttempt

_RECV_BUFFER_SIZE = 4096


async def send_sequence(
    host: str, port: int, sequence: list[str], *, test_id: int, timeout: float
) -> FuzzAttempt:
    """Connect to ``host:port``, send each command in ``sequence``, and
    return the outcome as a ``FuzzAttempt``.

    Never raises: any exception (connection refused, reset, timeout, ...)
    is captured on the returned attempt for ``crash_classifier`` to
    interpret, rather than propagating out of a worker pool job.
    """
    target = f"{host}:{port}"
    last_response: str | None = None
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=timeout
        )
        try:
            banner = await asyncio.wait_for(reader.read(_RECV_BUFFER_SIZE), timeout=timeout)
            if not banner:
                raise ConnectionError("Connection closed before sending a banner")
            last_response = banner.decode("latin1", errors="replace")
            for command in sequence:
                writer.write((command + "\r\n").encode("latin1", errors="replace"))
                await writer.drain()
                data = await asyncio.wait_for(reader.read(_RECV_BUFFER_SIZE), timeout=timeout)
                if not data:
                    # A clean close (EOF, no exception) after we sent a
                    # command is itself a fault worth reporting - v1 missed
                    # this case too, since a graceful peer close is not an
                    # exception from recv()/read() either.
                    raise ConnectionError(
                        f"Connection closed unexpectedly after sending: {command!r}"
                    )
                last_response = data.decode("latin1", errors="replace")
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass  # cleanup failures must never mask the attempt's real outcome
    except Exception as exc:
        return FuzzAttempt(
            test_id=test_id,
            target=target,
            sequence=sequence,
            response=last_response,
            exception=exc,
        )
    return FuzzAttempt(test_id=test_id, target=target, sequence=sequence, response=last_response)
