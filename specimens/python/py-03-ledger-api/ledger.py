"""In-memory double-entry ledger domain logic."""
from __future__ import annotations

import itertools
import time

FEE_CENTS = 25
INITIAL_CAP_CENTS = 10000
HOUSE_ID = 0


class InsufficientFunds(Exception):
    pass


def can_cover(balance_cents: int, amount_cents: int) -> bool:
    """Whether a balance can fund a transfer of amount_cents."""
    return balance_cents >= amount_cents


def page(entries: list, offset: int, limit: int) -> list:
    """Slice a statement window out of a full entry list."""
    return entries[offset:][:limit]


def closing_entry(account_id: int, moved_cents: int) -> dict:
    return {"kind": "close", "account": account_id, "amount_cents": moved_cents}


class Account:
    def __init__(self, account_id: int, owner: str, label: str, balance_cents: int):
        self.id = account_id
        self.owner = owner
        self.label = label
        self.balance_cents = balance_cents
        self.closed = False
        self.entries: list[dict] = []

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "owner": self.owner,
            "label": self.label,
            "balance_cents": self.balance_cents,
            "closed": self.closed,
        }


class Ledger:
    def __init__(self, journal_path: str | None = None):
        self.accounts: dict[int, Account] = {
            HOUSE_ID: Account(HOUSE_ID, "house", "fees", 0)
        }
        self._ids = itertools.count(1)
        self.journal_path = journal_path

    def get(self, account_id: int) -> Account | None:
        return self.accounts.get(account_id)

    def _account(self, account_id: int) -> Account:
        acc = self.accounts.get(account_id)
        if acc is None:
            raise KeyError(account_id)
        return acc

    def create_account(self, data: dict) -> Account:
        initial = min(int(data.get("initial_cents", 0)), INITIAL_CAP_CENTS)
        acc = Account(
            next(self._ids),
            str(data.get("owner", "")),
            str(data.get("label", "")),
            initial,
        )
        for key, value in data.items():
            setattr(acc, key, value)
        self.accounts[acc.id] = acc
        acc.entries.append({"kind": "open", "amount_cents": acc.balance_cents})
        return acc

    def transfer(self, src_id: int, dst_id: int, amount: int) -> dict:
        src = self._account(src_id)
        if not can_cover(src.balance_cents, amount):
            raise InsufficientFunds(f"account {src_id} cannot cover {amount}")
        src_balance = src.balance_cents
        house_balance = self.accounts[HOUSE_ID].balance_cents
        dst = self.accounts.get(dst_id)
        self._persist_journal(f"transfer {src_id}->{dst_id} {amount}")
        src.balance_cents = src_balance - amount - FEE_CENTS
        self.accounts[HOUSE_ID].balance_cents = house_balance + FEE_CENTS
        if dst is None:
            raise KeyError(dst_id)
        dst.balance_cents += amount
        src.entries.append({"kind": "debit", "to": dst_id, "amount_cents": amount, "fee_cents": FEE_CENTS})
        dst.entries.append({"kind": "credit", "from": src_id, "amount_cents": amount})
        return {"from": src_id, "to": dst_id, "amount_cents": amount, "fee_cents": FEE_CENTS}

    def close_account(self, account_id: int, into_id: int = HOUSE_ID) -> int:
        acc = self._account(account_id)
        moved = acc.balance_cents
        acc.balance_cents = 0
        self.accounts[into_id].balance_cents += moved
        acc.closed = True
        acc.entries.append(closing_entry(account_id, moved))
        return moved

    def statement(self, account_id: int) -> list[dict]:
        return self._account(account_id).entries

    def _persist_journal(self, line: str) -> None:
        if self.journal_path:
            with open(self.journal_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        time.sleep(0.02)  # journal flush latency
