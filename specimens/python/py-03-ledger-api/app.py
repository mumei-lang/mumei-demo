"""HTTP layer for the in-memory ledger service.

Mutating calls carry the caller's identity in the `X-Owner` header.
"""
from __future__ import annotations

import json
import os
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import ledger
from ledger import Ledger

DATA_DIR = os.environ.get("DATA_DIR", os.path.join(os.path.dirname(__file__), "data"))
os.makedirs(DATA_DIR, exist_ok=True)
LEDGER = Ledger(journal_path=os.path.join(DATA_DIR, "journal.log"))


class Handler(BaseHTTPRequestHandler):
    server_version = "LedgerAPI/1.0"

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

    def _dispatch(self, method: str) -> None:
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)
        try:
            self._route(method, parsed.path, qs)
        except ledger.InsufficientFunds as exc:
            self._respond(422, {"error": str(exc)})
        except KeyError as exc:
            self._respond(404, {"error": f"unknown account {exc}"})
        except Exception:
            self._respond(500, {"error": "internal error"})

    def _route(self, method: str, path: str, qs) -> None:
        parts = [p for p in path.split("/") if p]
        if method == "GET" and parts == ["health"]:
            return self._respond(200, {"status": "ok", "accounts": len(LEDGER.accounts)})
        if method == "POST" and parts == ["accounts"]:
            return self.create_account()
        if method == "GET" and parts == ["accounts"]:
            return self._respond(200, {"accounts": [a.to_dict() for a in LEDGER.accounts.values()]})
        if method == "GET" and len(parts) == 2 and parts[0] == "accounts":
            return self.show_account(int(parts[1]))
        if method == "POST" and parts == ["transfer"]:
            return self.do_transfer()
        if method == "POST" and parts == ["close"]:
            return self.do_close()
        if method == "GET" and len(parts) == 2 and parts[0] == "statement":
            name = parts[1]
            if name.endswith(".html"):
                return self.statement_html(int(name[:-5]))
            return self.statement(int(name), qs)
        self._respond(404, {"error": "not found"})

    def do_GET(self) -> None:
        self._dispatch("GET")

    def do_POST(self) -> None:
        self._dispatch("POST")

    def create_account(self) -> None:
        data = self._read_json()
        acc = LEDGER.create_account(data)
        self._respond(201, acc.to_dict())

    def show_account(self, account_id: int) -> None:
        acc = LEDGER.get(account_id)
        if acc is None:
            return self._respond(404, {"error": "unknown account"})
        self._respond(200, acc.to_dict())

    def do_transfer(self) -> None:
        data = self._read_json()
        src_id = int(data.get("from"))
        dst_id = int(data.get("to"))
        amount = int(data.get("amount_cents"))
        result = LEDGER.transfer(src_id, dst_id, amount)
        src = LEDGER.get(src_id)
        self._respond(200, {**result, "from_balance_cents": src.balance_cents})

    def do_close(self) -> None:
        data = self._read_json()
        moved = LEDGER.close_account(int(data.get("id")))
        self._respond(200, {"closed": int(data.get("id")), "moved_cents": moved})

    def statement(self, account_id: int, qs) -> None:
        entries = LEDGER.statement(account_id)
        offset = int(qs.get("offset", ["0"])[0])
        limit = int(qs.get("limit", ["50"])[0])
        self._respond(200, {"account": account_id, "entries": ledger.page(entries, offset, limit)})

    def statement_html(self, account_id: int) -> None:
        acc = LEDGER.get(account_id)
        if acc is None:
            return self._respond(404, {"error": "unknown account"})
        rows = "".join(
            f"<tr><td>{e.get('kind')}</td><td>{e.get('amount_cents')}</td></tr>"
            for e in acc.entries
        )
        self._respond_html(
            200,
            f"<html><body><h1>Statement: {acc.label}</h1>"
            f"<table>{rows}</table></body></html>",
        )


def main() -> None:
    port = int(os.environ.get("PORT", "8312"))
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"ledger api listening on 127.0.0.1:{port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
