"""Shared fixtures for web-engine integration tests."""

from __future__ import annotations

import functools
import http.server
import threading
from collections.abc import Iterator

import pytest


@pytest.fixture
def static_site(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    site_dir = tmp_path_factory.mktemp("static_site")

    (site_dir / "index.html").write_text(
        "<html><body>"
        '<a href="/about.html">About</a>'
        '<a href="/contact.html?ref=home">Contact</a>'
        '<form method="POST" action="/submit">'
        '<input name="email"><textarea name="message"></textarea>'
        "</form>"
        "</body></html>",
        encoding="utf-8",
    )
    (site_dir / "about.html").write_text(
        "<html><body>"
        '<a href="/index.html">Home</a>'
        '<a href="https://external.example/">External</a>'
        "</body></html>",
        encoding="utf-8",
    )
    (site_dir / "contact.html").write_text("<html><body>Contact us</body></html>", encoding="utf-8")
    (site_dir / "robots.txt").write_text(
        "User-agent: *\nDisallow: /admin\nSitemap: /sitemap.xml\n", encoding="utf-8"
    )
    (site_dir / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        "<url><loc>http://127.0.0.1/index.html</loc></url>"
        "</urlset>",
        encoding="utf-8",
    )

    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(site_dir))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join(timeout=5)
