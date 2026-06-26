<!-- FIXTURE: an overclaiming draft for the "claims" eval case. It asserts two
     things the backing diff (pr_description_overclaim.diff) does NOT contain: a
     suite of unit tests, and an order-caching layer. The diff only adds one
     validation check. A good rewrite must verify against the diff and drop both
     phantom claims (the most common, most damaging agent-PR failure). -->

## Improve order submission

This PR makes several improvements to order submission. It adds comprehensive
unit tests in `test_orders.py` covering all edge cases, and introduces an order
caching layer for better performance. Also adds validation for empty orders.
