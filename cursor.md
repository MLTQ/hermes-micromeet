# Inbox cursor

## Purpose

`cursor.py` owns the adapter's durable resume position and its special first-run policy.

## Components

- `InboxCursor`: reads/writes Hermes plugin state and scans to the current local inbox head when history replay is disabled.

## Contracts

- Stored cursors are non-negative integers and monotonic in normal watcher order.
- First run starts at zero only when `replay_existing` is explicit; otherwise it walks bounded pages to the current head.
- Existing state always wins so posts received while Hermes was offline are replayed.
- The head scan is capped at 1,000 pages of at most 100 notices.

## Notes

Cursor commits happen in the adapter only after Hermes handles a message or the adapter makes an intentional skip decision.
