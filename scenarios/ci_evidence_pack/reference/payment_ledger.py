"""Small stdlib-only payment ledger fixture for the audit golden path.

This is an intentionally small adoption fixture, not a production-safe ledger.
"""


def opening_accounts() -> dict[str, int]:
    """Return deterministic opening balances in cents."""
    return {"operating": 10_000, "merchant": 0, "fees": 0}


def transfer_cents(
    balances: dict[str, int],
    source: str,
    destination: str,
    amount_cents: int,
) -> dict[str, int]:
    """Move amount_cents from source to destination and return updated balances."""
    updated = dict(balances)
    updated[source] = updated.get(source, 0) - amount_cents
    updated[destination] = updated.get(destination, 0) + amount_cents
    return updated


def fee_cents(amount_cents: int, basis_points: int) -> int:
    """Return the integer fee for amount_cents at basis_points."""
    return amount_cents * basis_points // 10_000


def split_cents(amount_cents: int, recipient_count: int) -> int:
    """Return each recipient's integer share of amount_cents."""
    return amount_cents // recipient_count


def post_payment(balances: dict[str, int], amount_cents: int, fee_basis_points: int) -> dict[str, int]:
    """Post a merchant payment and its fee."""
    fee = fee_cents(amount_cents, fee_basis_points)
    updated = transfer_cents(balances, "operating", "merchant", amount_cents)
    return transfer_cents(updated, "merchant", "fees", fee)


def payout_summary(amount_cents: int, recipient_count: int, fee_basis_points: int) -> dict[str, int]:
    """Return fee, per-recipient share, and undistributed remainder for a payout."""
    fee = fee_cents(amount_cents, fee_basis_points)
    distributable = amount_cents - fee
    share = split_cents(distributable, recipient_count)
    return {
        "fee_cents": fee,
        "share_cents": share,
        "remainder_cents": distributable - share * recipient_count,
    }
