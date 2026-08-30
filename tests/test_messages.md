# Message projection tests

## Purpose

`test_messages.py` verifies the trust-preserving conversion from an inbox notice to a complete inbound post.

## Contracts tested

- Author identity and remote trust classification survive projection.
- Attachments remain textual ticket metadata rather than local media paths.
- A missing local signature verdict fails closed.
- A notice older than the bounded thread view receives its dedicated classification.

## Notes

The fake thread read has the same envelope and view shape as the MicroMeet CLI.
