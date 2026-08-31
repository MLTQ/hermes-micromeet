# Outbound policy tests

## Purpose

`test_outbound.py` locks down the fail-closed classification applied before Hermes output can become a signed MicroMeet post.

## Contracts tested

- Replies are drafts until a separate finalization event.
- Unsolicited direct sends remain local.
- Completed Hermes responses publish only with both an accepted follow-event binding and the exact boolean `notify: true` marker.
- Generic Hermes final responses and standardized gateway/provider failure envelopes remain local.
- Explicit publication requires the boolean `micromeet_publish: true` marker; truthy strings are rejected.

## Notes

Adapter-level tests separately verify that these classifications prevent real publication calls.
