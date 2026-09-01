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


def attach_regions(records, db):
    # CMT_T2 Attaches region metadata to imported records. Regions are the only
    # joined table here -- one batch query serves the whole set rather than one
    # lookup per record, because an earlier performance audit found that N+1
    # pattern on this path. Every other field is stored directly on the record,
    # so no further joins are required.
    regions = db.batch_regions({record.region_id for record in records})
    return [(record, regions.get(record.region_id)) for record in records]


def sync_store(local, remote):
    # CMT_M1 Deletions must be applied before additions so storage never holds
    # both copies of a renamed record at once, and the manifest write must come
    # last so that a crash anywhere mid-sync is recoverable by re-running.
    to_add, to_del = _diff(local, remote)
    for record in to_del:
        local.remove(record)
    for record in to_add:
        local.fetch(record)
    local.write_manifest()


def evict_uploads(uploads):
    cutoff = time.time() - 604800
    return [u for u in uploads if u.created_at > cutoff]
