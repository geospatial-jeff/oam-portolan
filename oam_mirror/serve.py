"""Serve the built catalog locally for Portolan Browser or STAC Browser.

Usage: python -m oam_mirror.serve catalog/ [--port 8000]

Adds the CORS headers the Portolan spec asks of a host, and single-range
`Range` support, which Python's http.server lacks and which browsers need to
read items.parquet. For local review only.
"""

import argparse
import functools
import os
import re
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

RANGE = re.compile(r"bytes=(\d*)-(\d*)$")


class CatalogHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Range, If-Match, If-Modified-Since, If-None-Match, If-Unmodified-Since")
        self.send_header("Access-Control-Expose-Headers", "Content-Type, Content-Length, Content-Range, Accept-Ranges, ETag")
        self.send_header("Accept-Ranges", "bytes")
        # Chrome's private-network rule: a public https page may read localhost only with this.
        self.send_header("Access-Control-Allow-Private-Network", "true")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()

    def do_GET(self):
        match = RANGE.match(self.headers.get("Range", ""))
        path = self.translate_path(self.path)
        if not match or not os.path.isfile(path):
            return super().do_GET()
        size = os.path.getsize(path)
        start, end = match.groups()
        if start == "":  # suffix range: last N bytes
            start, end = max(size - int(end), 0), size - 1
        else:
            start, end = int(start), min(int(end) if end else size - 1, size - 1)
        if start >= size or start > end:
            self.send_response(416)
            self.send_header("Content-Range", f"bytes */{size}")
            self.end_headers()
            return
        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(path))
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(end - start + 1))
        self.end_headers()
        with open(path, "rb") as f:
            f.seek(start)
            self.wfile.write(f.read(end - start + 1))


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("catalog")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    handler = functools.partial(CatalogHandler, directory=os.path.abspath(args.catalog))
    print(f"Serving {args.catalog} at http://localhost:{args.port}/catalog.json")
    ThreadingHTTPServer(("localhost", args.port), handler).serve_forever()


if __name__ == "__main__":
    main()
