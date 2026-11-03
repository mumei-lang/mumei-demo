"""Native replay driver for the Python specimens.

Usage: python3 python.py <specimen tree>  (JSON lines {"case", "values"} on stdin)
Prints one JSON line per input: {"case", "violates", "observed"}. `violates` is the
requirement from contract.json checked on the native call; a crash counts as a violation
unless the requirement models that exception as a rejection.
"""
from __future__ import annotations

import importlib
import json
import sys


def call(fn, *args):
    """(ok, value) where ok is False for a ValueError rejection; other exceptions propagate."""
    try:
        return True, fn(*args)
    except ValueError as error:
        return False, f"ValueError: {error}"


def py01(case, v):
    ledger = importlib.import_module("ledger")
    if case == "PY01-D03":
        r = ledger.daily_average(v["total_cents"], v["days"])
        want = 0 if v["days"] <= 0 else v["total_cents"] // v["days"]
        return r != want, f"daily_average -> {r!r}"
    if case == "PY01-D05":
        r = ledger.is_over_budget(v["spent_cents"], v["limit_cents"])
        return r != (v["spent_cents"] >= v["limit_cents"]), f"is_over_budget -> {r!r}"
    if case == "PY01-D08":
        label = ":".join(f"p{x}" for x in v["parts"])
        r = ledger.subcategory(label)
        want = label.partition(":")[2] if ":" in label else label
        return r != want, f"subcategory({label!r}) -> {r!r}"
    if case == "PY01-D10":
        ok, r = call(ledger.parse_amount, v["value"])
        bad = (ok and not (r > 0 and r == v["value"])) or (v["value"] > 0 and not ok)
        return bad, f"parse_amount({v['value']}) -> {r!r}"
    raise KeyError(case)


def py02(case, v):
    timesheet = importlib.import_module("timesheet")
    if case == "PY02-D02":
        r = timesheet.share_of_total(v["part"], v["whole"])
        return v["whole"] == 0 and r != 0, f"share_of_total -> {r!r}"
    if case == "PY02-D04":
        report = importlib.import_module("report")
        row = ["worker", "2024-01-02", "project", "30m", "note"][: v["n"]]
        row += ["x"] * (v["n"] - len(row))
        ok, r = call(report.parse_row, row)
        return ok != (v["n"] >= 4), f"parse_row({row!r}) -> {'ok' if ok else r}"
    if case == "PY02-D05":
        r = timesheet.overtime_minutes(list(v["daily"]), v["threshold"])
        first = v["daily"][0] - v["threshold"]
        return r < 0 or (first > 0 and r < first), f"overtime_minutes -> {r!r}"
    if case == "PY02-D08":
        text = f"{v['hours']}h{v['minutes']}m"
        ok, r = call(timesheet.parse_duration, text)
        return ok and r <= 0, f"parse_duration({text!r}) -> {r!r}"
    raise KeyError(case)


def py03(case, v):
    ledger = importlib.import_module("ledger")
    if case == "PY03-D05":
        entries = list(range(v["n"]))
        ok, r = call(ledger.page, entries, v["offset"], v["limit"])
        # The window must start at `offset` (or be empty past the end); a negative offset never does.
        bad = ok and (v["offset"] < 0 or (bool(r) and r[0] != v["offset"]))
        return bad, f"page(range({v['n']}), {v['offset']}, {v['limit']}) -> {r!r}"
    book = ledger.Ledger()
    if case == "PY03-D03":
        acc = ledger.Account(1, "a", "main", v["balance"])
        acc.closed = v["closed"]
        book.accounts[1] = acc
        ok, r = call(book.close_account, 1)
        return v["closed"] and ok, f"close_account(closed={v['closed']}) -> {r!r}"
    book.accounts[ledger.HOUSE_ID].balance_cents = v["house"]
    book.accounts[1] = ledger.Account(1, "a", "src", v["src"])
    dst_id = 2 if v["dst_exists"] else 99
    if v["dst_exists"]:
        book.accounts[2] = ledger.Account(2, "b", "dst", v["dst"])
        book.accounts[2].closed = not v["distinct_open"]
    try:
        book.transfer(1, dst_id, v["amount"])
        ok = True
    except (ValueError, KeyError, ledger.InsufficientFunds) as error:
        ok, err = False, type(error).__name__
    after = {"src": book.accounts[1].balance_cents, "house": book.accounts[ledger.HOUSE_ID].balance_cents,
             "dst": book.accounts[2].balance_cents if v["dst_exists"] else v["dst"]}
    observed = f"transfer -> {'ok' if ok else err}, balances {after}"
    if case == "PY03-D01":
        return ok and v["amount"] <= 0, observed
    if case == "PY03-D02":
        return ok and after["src"] < 0, observed
    if case == "PY03-D06":
        return (not ok) and after != {"src": v["src"], "dst": v["dst"], "house": v["house"]}, observed
    raise KeyError(case)


def py04(case, v):
    vault = importlib.import_module("vault")
    if case == "PY04-D10":
        ok, r = call(vault.share_expiry, v["now"], v["ttl_seconds"])
        return ok and r <= v["now"], f"share_expiry -> {r!r}"
    if case == "PY04-D11":
        doc = {"owner": "owner-key", "share": None} if v["doc_present"] else None
        key = "owner-key" if v["owner_matches"] else "other-key"
        r = vault.can_read(doc, key, None)
        return (not v["doc_present"]) and r, f"can_read -> {r!r}"
    raise KeyError(case)


SPECIMENS = {"PY01": py01, "PY02": py02, "PY03": py03, "PY04": py04}


def main() -> int:
    sys.path.insert(0, sys.argv[1])
    for line in sys.stdin:
        if not line.strip():
            continue
        req = json.loads(line)
        case = req["case"]
        try:
            violates, observed = SPECIMENS[case[:4]](case, req["values"])
        except KeyError:
            raise
        except Exception as error:  # a crash breaks a requirement that promises an answer
            violates, observed = True, f"raised {type(error).__name__}: {error}"
        print(json.dumps({"case": case, "violates": bool(violates), "observed": observed[:300]}), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
