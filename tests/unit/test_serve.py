import functools
import threading
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from oam_mirror.serve import CatalogHandler


@pytest.fixture
def server(tmp_path):
    (tmp_path / "items.parquet").write_bytes(b"PAR1-body-PAR1")
    httpd = ThreadingHTTPServer(("localhost", 0), functools.partial(CatalogHandler, directory=str(tmp_path)))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://localhost:{httpd.server_address[1]}"
    httpd.shutdown()


def get(url, **headers):
    return urllib.request.urlopen(urllib.request.Request(url, headers=headers))


def test_range_request_returns_requested_bytes(server):
    assert get(f"{server}/items.parquet", Range="bytes=0-3").read() == b"PAR1"


def test_suffix_range_returns_tail(server):
    assert get(f"{server}/items.parquet", Range="bytes=-4").read() == b"PAR1"


def test_responses_allow_any_origin(server):
    assert get(f"{server}/items.parquet").headers["Access-Control-Allow-Origin"] == "*"
