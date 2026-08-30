# Adapter tests

## Purpose

`test_adapter.py` verifies the impedance match between Hermes' mutable streaming previews and MicroMeet's immutable signed posts.

## Contracts tested

- Initial and progressive preview content remains in memory.
- Finalization publishes exactly once and clears the draft.
- Immediate duplicate gateway text reuses one signed post even if reply metadata differs.

## Notes

The test uses the real adapter methods and replaces only the final network publication boundary.
