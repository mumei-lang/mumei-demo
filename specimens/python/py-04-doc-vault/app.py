"""HTTP layer for the token-gated document vault.

Callers authenticate uploads with a per-user `X-Api-Key` header; shared
read access is granted through share tokens.
"""
from __future__ import annotations

import json
import os
import random
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import vault
from vault import DocumentStore

DATA_DIR = os.environ.get("DATA_DIR", os.path.join(os.path.dirname(__file__), "data"))
STORE = DocumentStore(DATA_DIR)


class Handler(BaseHTTPRequestHandler):
    server_version = "DocVault/1.0"

    def log_message(self, *args):
        pass

    def _read_json(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        return json.loads(raw)

    def _respond(self, code: int, obj) -> None:
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _respond_html(self, code: int, html: str) -> None:
        body = html.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _respond_text(self, code: int, text: str) -> None:
        body = text.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _api_key(self) -> str:
        return self.headers.get("X-Api-Key", "")

    def _dispatch(self, method: str) -> None:
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)
        try:
            self._route(method, parsed.path, qs)
        except vault.QuotaExceeded as exc:
            self._respond(413, {"error": str(exc)})
        except vault.Forbidden as exc:
            self._respond(403, {"error": str(exc)})
        except KeyError as exc:
            self._respond(404, {"error": f"unknown document {exc}"})
        except Exception:
            self._respond(500, {"error": "internal error"})

    def _route(self, method: str, path: str, qs) -> None:
        routes = {
            ("POST", "/upload"): self.upload,
            ("GET", "/doc"): self.get_doc,
            ("POST", "/share"): self.share,
            ("GET", "/fetch"): self.fetch,
            ("POST", "/admin/purge"): self.purge,
            ("GET", "/go"): self.go,
            ("GET", "/docs.html"): self.docs_html,
            ("GET", "/quota"): self.quota,
            ("GET", "/health"): lambda qs: self._respond(200, {"status": "ok", "docs": len(STORE.docs)}),
        }
        handler = routes.get((method, path))
        if handler is None:
            return self._respond(404, {"error": "not found"})
        handler(qs)

    def do_GET(self) -> None:
        self._dispatch("GET")

    def do_POST(self) -> None:
        self._dispatch("POST")

    def upload(self, qs) -> None:
        data = self._read_json()
        payload = STORE.decode_body(data)
        doc = STORE.save_upload(self._api_key(), str(data.get("title", "")), payload)
        self._respond(201, {"id": doc["id"], "title": doc["title"], "bytes": len(payload)})

    def get_doc(self, qs) -> None:
        doc_id = qs.get("id", [""])[0]
        token = qs.get("token", [None])[0]
        doc = STORE.get(doc_id)
        if not vault.can_read(doc, self._api_key(), token):
            return self._respond(403, {"error": "cannot read this document"})
        self._respond_text(200, doc["body"].decode("utf-8", errors="replace"))

    def share(self, qs) -> None:
        data = self._read_json()
        ttl = int(data.get("ttl_seconds", 3600))
        share = STORE.create_share(str(data.get("id", "")), self._api_key(), ttl)
        self._respond(200, share)

    def fetch(self, qs) -> None:
        url = qs.get("url", [""])[0]
        doc = STORE.fetch_remote(self._api_key(), url)
        self._respond(200, {"id": doc["id"], "title": doc["title"], "bytes": len(doc["body"])})

    def purge(self, qs) -> None:
        if "X-Admin-Key" not in self.headers:
            return self._respond(403, {"error": "admin key required"})
        count = STORE.purge()
        self._respond(200, {"purged": count})

    def go(self, qs) -> None:
        target = qs.get("next", ["/"])[0]
        self.send_response(302)
        self.send_header("Location", target)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def docs_html(self, qs) -> None:
        items = "".join(
            f'<li><a href="/doc?id={d["id"]}">{d["title"]}</a></li>' for d in STORE.docs.values()
        )
        self._respond_html(200, f"<html><body><h1>Documents</h1><ul>{items}</ul></body></html>")

    def quota(self, qs) -> None:
        used = STORE.usage_for(self._api_key())
        self._respond(
            200,
            {
                "used_bytes": used,
                "quota_bytes": vault.QUOTA_BYTES,
                "remaining_bytes": vault.remaining_quota(used, vault.QUOTA_BYTES),
            },
        )


def main() -> None:
    random.seed(int(time.time()))
    port = int(os.environ.get("PORT", "8313"))
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"doc vault listening on 127.0.0.1:{port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
