def withdraw(balance: int, amount: int) -> int:
    """Withdraw amount from balance. Should fail if amount > balance."""
    return balance - amount  # Bug: no check for amount > balance
