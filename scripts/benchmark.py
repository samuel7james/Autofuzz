#!/usr/bin/env python3
"""AutoFuzz performance benchmark harness.

Measures throughput of both engines and the mutator corpus against local,
in-process fake targets (no external network dependency, no fixed hardware
assumptions baked in - numbers will vary by machine). Run it yourself:

    python scripts/benchmark.py

This is a developer tool, not part of the installed package - it imports
autofuzz from an editable/dev install and is meant to be run from a repo
checkout to catch performance regressions across changes, not shipped to
end users.
"""

from __future__ import annotations

import asyncio
import functools
import http.server
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from autofuzz.core.config import (  # noqa: E402
    ProtocolEngineConfig,
    SchedulerConfig,
    WebEngineConfig,
)
from autofuzz.protocol_fuzzing.engine import ProtocolFuzzingEngine  # noqa: E402
from autofuzz.protocol_fuzzing.mutators.strategies import mutate  # noqa: E402
from autofuzz.web.engine import WebAssessmentEngine  # noqa: E402

PROTO_ITERATIONS = 1000
WEB_PAGE_COUNT = 300
MUTATOR_CALLS = 50_000


async def _ftp_handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    """Always responds OK - measures throughput, not crash-finding rate."""
    writer.write(b"220 fake FTP ready\r\n")
    await writer.drain()
    try:
        while True:
            chunk = await reader.read(4096)
            if not chunk:
                break
            writer.write(b"200 OK\r\n")
            await writer.drain()
    except OSError:
        pass  # benchmark noise only - a mutated payload aborting the connection
        # mid-write is expected and irrelevant to a throughput measurement
    finally:
        if not writer.is_closing():
            writer.close()


def _start_ftp_server() -> tuple[str, int]:
    loop = asyncio.new_event_loop()
    holder: dict[str, tuple[str, int]] = {}

    def run() -> None:
        asyncio.set_event_loop(loop)
        server = loop.run_until_complete(asyncio.start_server(_ftp_handle, "127.0.0.1", 0))
        holder["addr"] = server.sockets[0].getsockname()[:2]
        loop.run_forever()

    threading.Thread(target=run, daemon=True).start()
    while "addr" not in holder:
        time.sleep(0.02)
    return holder["addr"]


def _build_static_site(site_dir: Path) -> None:
    body = "<p>lorem ipsum</p>" * 50
    for i in range(WEB_PAGE_COUNT):
        (site_dir / f"page{i}.html").write_text(
            f"<html><body>{body}</body></html>", encoding="utf-8"
        )
    links = "".join(f'<a href="/page{i}.html">page{i}</a>' for i in range(WEB_PAGE_COUNT))
    (site_dir / "index.html").write_text(f"<html><body>{links}</body></html>", encoding="utf-8")


def _start_static_server(site_dir: Path) -> tuple[str, int]:
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(site_dir))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    host, port = server.server_address[:2]
    return str(host), int(port)


def benchmark_proto_engine() -> None:
    print(f"\n== Protocol Fuzzing Engine ({PROTO_ITERATIONS} iterations) ==")
    host, port = _start_ftp_server()

    for concurrency in (1, 10, 30):
        protocol_config = ProtocolEngineConfig(
            adapter="ftp", target_host=host, target_port=port, iterations=PROTO_ITERATIONS
        )
        scheduler_config = SchedulerConfig(
            concurrency=concurrency,
            rate_limit_per_second=100_000,
            max_retries=0,
            request_timeout_seconds=3.0,
        )
        engine = ProtocolFuzzingEngine(protocol_config, scheduler_config)
        start = time.perf_counter()
        asyncio.run(engine.run())
        elapsed = time.perf_counter() - start
        print(
            f"  concurrency={concurrency:<3} {elapsed:6.2f}s  "
            f"{PROTO_ITERATIONS / elapsed:8.1f} iterations/sec"
        )


def benchmark_web_engine() -> None:
    print(f"\n== Web Assessment Engine ({WEB_PAGE_COUNT} pages) ==")
    site_dir = Path(tempfile.mkdtemp())
    _build_static_site(site_dir)
    host, port = _start_static_server(site_dir)

    for concurrency in (5, 20):
        web_config = WebEngineConfig(max_crawl_depth=3, max_pages=WEB_PAGE_COUNT + 5)
        scheduler_config = SchedulerConfig(
            concurrency=concurrency, rate_limit_per_second=100_000, max_retries=0
        )
        engine = WebAssessmentEngine(web_config, scheduler_config)
        start = time.perf_counter()
        _findings, stats = asyncio.run(engine.run(f"http://{host}:{port}/index.html"))
        elapsed = time.perf_counter() - start
        pages = stats["pages_crawled"]
        print(f"  concurrency={concurrency:<3} {elapsed:6.2f}s  {pages / elapsed:8.1f} pages/sec")


def benchmark_mutators() -> None:
    print(f"\n== Mutator corpus ({MUTATOR_CALLS} calls) ==")
    start = time.perf_counter()
    for _ in range(MUTATOR_CALLS):
        mutate("USER vulnftp")
    elapsed = time.perf_counter() - start
    print(f"  {elapsed:6.2f}s  {MUTATOR_CALLS / elapsed:8.1f} mutations/sec")


def benchmark_cli_startup() -> None:
    print("\n== CLI cold start (`autofuzz --version`) ==")
    times = []
    for _ in range(5):
        start = time.perf_counter()
        subprocess.run(
            [sys.executable, "-m", "autofuzz", "--version"],
            capture_output=True,
            check=True,
            cwd=str(Path(__file__).resolve().parent.parent),
        )
        times.append(time.perf_counter() - start)
    print(f"  min={min(times):.3f}s  max={max(times):.3f}s  avg={sum(times) / len(times):.3f}s")


def main() -> None:
    benchmark_mutators()
    benchmark_cli_startup()
    benchmark_proto_engine()
    benchmark_web_engine()


if __name__ == "__main__":
    main()
