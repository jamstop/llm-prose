<!-- FIXTURE: the crafted counterpart to pr_description_stately.md — same change,
     written to the "beautiful" bar in the pr-description-review skill: strong
     lead, scannable structure, a real Why, and a behavior-change callout (the
     thing a reviewer most needs for this change). The description pass should
     leave this essentially alone — it's the target, not a thing to fix.

     NOTE: the specifics (SUPPORT-1421, file names, the 30-minute timeout) are
     invented for the fixture — there's no real ticket or code behind them. The
     point is the *shape* of a great description, not the facts. A real PR must
     cite a real Why; don't read this as license to fabricate one. -->

## Make session expiry idle-based, not absolute

Active sessions expired 30 minutes after login regardless of activity, logging
users out mid-task. The idle timer was never reset on authenticated requests, so
the timeout was effectively absolute. This makes it idle-based: an active session
stays alive, an idle one still expires.

**Why:** SUPPORT-1421 — users on long forms lost work to surprise logouts. Root
cause: `session.py` stamped `last_seen` only at login, never on later requests.

**How**
- `auth.py` updates `last_seen` on every authenticated request.
- `session.py` measures the timeout against `last_seen` instead of `created_at`.
- No schema change — `last_seen` already existed, it just wasn't being written.

**Behavior change**
- No API changes. An active session no longer expires at 30 minutes; idle sessions
  still expire as before. No migration needed.

**Verify**
- Stay active for >30 min — confirm no logout.
- Go idle for >30 min — confirm logout.
