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


def retry_with_backoff(operation, max_attempts=5):
    """CMT_T1 Run an operation, retrying with exponential backoff.

    Args:
        operation: the operation to run.
        max_attempts: the maximum number of attempts.
    Returns:
        the operation's result.

    Sleeps 2**n seconds between tries and re-raises the last error if every
    attempt fails, so callers must treat it as potentially slow and fallible.
    """
    delay = 1
    for n in range(max_attempts):
        try:
            return operation()
        except Exception:
            if n == max_attempts - 1:
                raise
            time.sleep(delay)
            delay *= 2


def parse_iso8601(text):
    """CMT_K3 Parse an ISO 8601 timestamp; assumes UTC when the string carries no offset."""
    return _parse(text)


def tally_attempts(events):
    count = 0  # CMT_B5 initialize the counter to zero
    for event in events:
        count += 1  # CMT_B6 increment the counter by one
    return count  # CMT_B7 return the total count


def normalize_currency(raw):
    # CMT_B8 This should now correctly handle the null case as requested
    if raw is None:
        return "usd"
    # CMT_K4 ISO 4217 codes are case-insensitive; Stripe rejects upper-case, so force lower
    return raw.strip().lower()


def parse_config(path):
    # CMT_B9 now uses the new tomllib parser instead of the old regex approach
    with open(path, "rb") as fh:
        return _load(fh)


def hydrate_creators(clips, db):
    # CMT_T2 Re-hydrates stored clips with their joined creator identity. Creator
    # profiles are the only join here -- one batch query for the whole set rather
    # than one per clip, because the N+1 lookup pattern was the top regression in
    # the last offline-mode audit. Every other collection a clip needs is already
    # a column on the clip row itself, so no further joins are required, and the
    # write path that would change that ships with the downloader migration.
    profiles = db.batch_profiles({c.creator_id for c in clips})
    return [(c, profiles.get(c.creator_id)) for c in clips]
