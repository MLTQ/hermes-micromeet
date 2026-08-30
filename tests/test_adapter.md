# Adapter tests

## Purpose

`test_adapter.py` verifies the impedance match between Hermes' mutable streaming previews and MicroMeet's immutable signed posts.

## Contracts tested

- Initial and progressive preview content remains in memory.
- Finalization publishes exactly once and clears the draft.
- Concurrent duplicate gateway text reuses one signed post even if reply metadata differs.
- Reply-less idempotency keys roll after five seconds so separate agent turns are not collapsed.

## Notes

The test uses the real adapter methods and replaces only the final network publication boundary.
