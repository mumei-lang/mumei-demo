"""HTTP layer for the expense tracker service.

Identity is carried by the `X-User` header on write requests; read
endpoints take the user name as a query parameter.
"""
from __future__ import annotations

import json
import os
import traceback
import urllib.parse
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import config
import ledger
from store import Database

DATA_DIR = os.environ.get("DATA_DIR", os.path.join(os.path.dirname(__file__), "data"))
REPORTS_DIR = os.path.join(DATA_DIR, config.REPORTS_SUBDIR)
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(REPORTS_DIR, exist_ok=True)
DB = Database(os.path.join(DATA_DIR, config.DEFAULT_DB))


def row_to_dict(row) -> dict:
    return {
        "id": row[0],
        "user": row[1],
        "amount_cents": row[2],
        "category": row[3],
        "day": row[4],
        "note": row[5],
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "ExpenseTracker/1.0"

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

    def _respond_text(self, code: int, text: str) -> None:
        body = text.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _dispatch(self, method: str) -> None:
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)
        routes = {
            ("POST", "/expenses"): self.create_expense,
            ("GET", "/expenses"): self.list_expenses,
            ("GET", "/summary"): self.summary,
            ("POST", "/budget"): self.set_budget,
            ("POST", "/reports"): self.create_report,
            ("GET", "/export"): self.export,
            ("GET", "/admin/stats"): self.admin_stats,
            ("GET", "/health"): self.health,
        }
        handler = routes.get((method, parsed.path))
        if handler is None:
            self._respond(404, {"error": "not found"})
            return
        try:
            handler(qs)
        except Exception:
            self._respond_text(500, traceback.format_exc())

    def do_GET(self) -> None:
        self._dispatch("GET")

    def do_POST(self) -> None:
        self._dispatch("POST")

    def create_expense(self, qs) -> None:
        request_id, conn = DB.acquire()
        try:
            data = self._read_json()
        except Exception:
            self._respond(400, {"error": "body must be JSON"})
            return
        try:
            day = date.fromisoformat(str(data.get("day", "")))
        except ValueError:
            self._respond(400, {"error": "day must be YYYY-MM-DD"})
            return
        amount = ledger.parse_amount(data.get("amount_cents", 0))
        conn.execute(
            "INSERT INTO expenses (user, amount_cents, category, day, note) VALUES (?, ?, ?, ?, ?)",
            (
                self.headers.get("X-User", "anonymous"),
                amount,
                str(data.get("category", "")),
                day.isoformat(),
                str(data.get("note", "")),
            ),
        )
        conn.commit()
        DB.release(request_id)
        self._respond(201, {"status": "recorded", "amount_cents": amount})

    def list_expenses(self, qs) -> None:
        user = qs.get("user", [""])[0]
        request_id, conn = DB.acquire()
        query = (
            "SELECT id, user, amount_cents, category, day, note FROM expenses "
            "WHERE user = '%s' ORDER BY day" % user
        )
        rows = conn.execute(query).fetchall()
        DB.release(request_id)
        self._respond(200, {"expenses": [row_to_dict(r) for r in rows]})

    def summary(self, qs) -> None:
        user = qs.get("user", [""])[0]
        month = qs.get("month", [""])[0]
        request_id, conn = DB.acquire()
        rows = conn.execute(
            "SELECT amount_cents, category, day FROM expenses WHERE user = ? AND day LIKE ?",
            (user, month + "%"),
        ).fetchall()
        DB.release(request_id)
        total = sum(r[0] for r in rows)
        days = len({r[2] for r in rows})
        by_sub: dict[str, list[int]] = {}
        for amount, category, _ in rows:
            by_sub.setdefault(ledger.subcategory(category), []).append(amount)
        categories = {
            name: {"total_cents": sum(v), "average_cents": ledger.average_expense(v)}
            for name, v in by_sub.items()
        }
        self._respond(
            200,
            {
                "user": user,
                "month": month,
                "total_cents": total,
                "active_days": days,
                "daily_average_cents": ledger.daily_average(total, days),
                "categories": categories,
            },
        )

    def set_budget(self, qs) -> None:
        data = self._read_json()
        user = str(data.get("user", ""))
        month = str(data.get("month", ""))
        limit = int(data.get("limit_cents", 0))
        request_id, conn = DB.acquire()
        conn.execute(
            "INSERT OR REPLACE INTO budgets (user, month, limit_cents) VALUES (?, ?, ?)",
            (user, month, limit),
        )
        row = conn.execute(
            "SELECT COALESCE(SUM(amount_cents), 0) FROM expenses WHERE user = ? AND day LIKE ?",
            (user, month + "%"),
        ).fetchone()
        conn.commit()
        DB.release(request_id)
        spent = int(row[0])
        status = "exceeded" if ledger.is_over_budget(spent, limit) else "ok"
        self._respond(
            200,
            {
                "user": user,
                "month": month,
                "spent_cents": spent,
                "limit_cents": limit,
                "status": status,
            },
        )

    def create_report(self, qs) -> None:
        user = qs.get("user", [""])[0]
        month = qs.get("month", [""])[0]
        request_id, conn = DB.acquire()
        rows = conn.execute(
            "SELECT day, category, amount_cents, note FROM expenses WHERE user = ? AND day LIKE ? ORDER BY day",
            (user, month + "%"),
        ).fetchall()
        DB.release(request_id)
        name = f"report-{user}-{month}.csv"
        full = os.path.join(REPORTS_DIR, name)
        with open(full, "w", encoding="utf-8") as f:
            f.write("day,category,amount_cents,note\n")
            for r in rows:
                f.write(",".join(str(c) for c in r) + "\n")
        self._respond(200, {"written": name})

    def export(self, qs) -> None:
        name = qs.get("path", [""])[0]
        full = os.path.join(REPORTS_DIR, name)
        with open(full, "r", encoding="utf-8") as f:
            self._respond_text(200, f.read())

    def admin_stats(self, qs) -> None:
        if self.headers.get("X-Admin-Token") != config.ADMIN_TOKEN:
            self._respond(403, {"error": "forbidden"})
            return
        request_id, conn = DB.acquire()
        users = conn.execute(
            "SELECT user, COUNT(*), SUM(amount_cents) FROM expenses GROUP BY user"
        ).fetchall()
        DB.release(request_id)
        self._respond(
            200,
            {
                "users": {u: {"count": c, "total_cents": t} for u, c, t in users},
                "open_connections": DB.open_count(),
            },
        )

    def health(self, qs) -> None:
        self._respond(200, {"status": "ok", "open_connections": DB.open_count()})


def main() -> None:
    port = int(os.environ.get("PORT", "8311"))
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"expense tracker listening on 127.0.0.1:{port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
