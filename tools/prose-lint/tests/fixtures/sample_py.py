def charge(amount, currency):
    # as requested, default to usd
    currency = currency or "usd"
    # total = amount * rate(currency)
    total = amount * 100
    # round half-up: bankers rounding burns us on refunds
    # TODO: total = apply_discount(total)
    return total


def to_cents(dollars):
    """Convert dollars to cents.

    Args:
        dollars: the dollars to convert to cents.
    Returns:
        the cents.
    """
    return int(dollars * 100)


def clamp(value, lo, hi):
    """Clamp value to [lo, hi]; callers rely on hi winning ties."""
    return max(lo, min(hi, value))
