<!-- FIXTURE: an accurate-but-overlong draft for the "compress" eval case,
     modeled on a real field failure — an AI description whose every clause was
     true and diff-backed, but whose paragraph-sized, em-dash-chained bullets
     made it unabsorbable. Nothing here is false; the defect is pure density.
     The rewrite must come back inside the one-minute budget (one-line bullets,
     well under half these words) without losing the Why, the behavior change,
     or the verify steps. -->

## Make session expiry idle-based rather than absolute

### Summary

Active sessions were expiring exactly 30 minutes after login regardless of user
activity — the idle timer was in effect an absolute timer, because `last_seen`
was stamped once at login inside `session.py` and never touched again on any
subsequent authenticated request, which meant the value that `is_expired()`
compared against `IDLE_TIMEOUT` was frozen at its initial reading for the whole
lifetime of the session. This PR converts the expiry model into a genuinely
idle-based one: an actively used session now stays alive for as long as
requests keep arriving, while an idle session still expires on exactly the same
30-minute schedule it always did, so the security posture for abandoned
sessions is unchanged.

### What's in it

- **`auth.py`** — the `authenticate(request)` path now calls `session.touch()`
  on every authenticated request that passes the expiry check — this is the
  single write that keeps a live session alive, and it is deliberately placed
  after the `is_expired()` check so that an already-expired session can never
  resurrect itself by touching its own timestamp on the way out.
- **`session.py`** — a new `touch()` method stamps `last_seen = now()`, and
  `is_expired()` now measures the idle window against `last_seen` rather than
  `created_at` — note that `created_at` itself remains in place and untouched,
  both for audit purposes and for any future absolute-lifetime policy that
  might want to measure against it.
- **No schema change** — the `last_seen` column already existed on the session
  model; it was never written after login, which is the entire bug, so
  no migration is required and a rollback is a pure code revert with no data
  implications to reason about.

### What's deliberately missing

- No absolute-lifetime cap is added here — under the new model a continuously
  used session never expires, which matches the product decision recorded in
  SUPPORT-1421; if a cap is wanted later, `created_at` is still available to
  measure it against, and that follow-up is intentionally left out of this
  diff to keep it reviewable.

### Testing

- Stay active past the 30-minute mark and confirm no logout occurs.
- Go idle past the 30-minute mark and confirm the logout still happens.
