# Notice projection

## Purpose

`messages.py` turns a small inbox notice into a complete, gateway-ready post by reading the corresponding thread from MicroMeet's already verified local index.

## Components

- `ProjectedMessage`: immutable boundary object used by the gateway adapter, carrying both authored and locally observed receive times.
- `project_notice`: validates IDs and signature verdicts, matches the announced object, and carries trust metadata forward.

## Contracts

- Topic-root notices do not become agent turns.
- The notice author must match the hydrated post author and the local signature verdict must be true.
- Authored time comes from the signed post; receive time comes from the local inbox notice and must remain distinguishable.
- Attachment tickets are exposed as inert JSON metadata only; no file is fetched.
- Remote body text remains untrusted data.

## Notes

MicroMeet thread reads return at most 100 recent posts. Watch notices are emitted only after local indexing, so live posts are present in that bounded view. A post older than the hydration window is classified separately so the adapter can advance without permanently wedging on a large offline backlog; other mismatches fail closed.
