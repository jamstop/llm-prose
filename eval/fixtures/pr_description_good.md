<!-- FIXTURE: the tightened counterpart to pr_description_stately.md — same change,
     written to be useful to a reviewer. Leads with what + why, surfaces the
     behavior change, drops the file list. The description pass should leave this
     essentially alone.

     NOTE: the specifics (SUPPORT-1421, file names, the 30-minute timeout) are
     invented for the fixture — there's no real ticket or code behind them. The
     point is the *shape* of a good description, not the facts. A real PR must
     cite a real Why; don't read this as license to fabricate one. -->


## Summary

Active sessions were expiring after 30 minutes and logging users out mid-task.
The idle timer was never reset on authenticated requests, so the timeout was
effectively absolute. This makes it idle-based: an active session stays alive.

## Why

SUPPORT-1421 — users on long forms lost work to surprise logouts. Root cause:
`session.py` stamped `last_seen` only at login, never on later requests.

## How

`auth.py` now updates `last_seen` on every authenticated request, and `session.py`
measures the timeout against `last_seen` instead of `created_at`. No schema change.

## Interface / behavior change

No API changes. Behavior change: an active session no longer expires at 30 minutes;
idle sessions still expire as before.

## Test plan

- Log in, stay active for >30 minutes — confirm no logout.
- Log in, go idle for >30 minutes — confirm logout.
