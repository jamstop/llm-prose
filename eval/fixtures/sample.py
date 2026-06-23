import time


def process_refund(event, store):
    # CMT_B1 increment the attempt counter by one
    store.attempts += 1

    # CMT_K1 Stripe can deliver the same webhook twice; dedupe by event id or we double-refund
    if store.seen(event.id):
        return

    # CMT_B2 Updated this per review feedback to also handle the null amount case
    amount = event.amount or 0

    # CMT_B3 legacy_amount = compute_legacy(event)
    refund = store.refund(event.customer, amount)

    # CMT_K2 must run before the audit hook below, which assumes refund.id is set
    time.sleep(0)
    store.audit(refund.id)
    return refund


def to_cents(dollars):
    """CMT_B4 Convert dollars to cents.

    Args:
        dollars: the dollars to convert to cents.
    Returns:
        the cents.
    """
    return int(dollars * 100)
