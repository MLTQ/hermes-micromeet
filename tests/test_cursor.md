# Cursor tests

## Purpose

`test_cursor.py` verifies safe first-run behavior and durable resume precedence.

## Contracts tested

- Existing Hermes plugin state prevents a head scan and replays missed posts.
- A fresh installation scans bounded inbox pages and persists the current head.

## Notes

Only the local inbox response is mocked; cursor policy and state writes are real.
