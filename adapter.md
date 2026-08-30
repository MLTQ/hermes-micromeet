# Gateway adapter

## Purpose

`adapter.py` makes MicroMeet a Hermes messaging platform. It attaches to one local daemon (or starts it), tails verified inbox notices, maps one MicroMeet thread to one Hermes chat, and posts Hermes replies back into that thread.

## Components

- `MicroMeetAdapter`: daemon ownership, watcher lifecycle, cursor handling, inbound event construction, and outbound delivery.
- `InboxCursor`: profile-local durable resume policy supplied by `cursor.py`.

## Contracts

- Existing daemons are never stopped by the plugin; only a child it started is terminated.
- The first connection starts at the current inbox head unless `replay_existing` is explicitly enabled. Subsequent starts replay messages after the committed cursor.
- A cursor is committed only after a notice is intentionally skipped or Hermes accepts the projected event.
- Local-author notices are suppressed to prevent reply loops.
- Remote text cannot invoke Hermes gateway commands (`allow_gateway_control=False`).
- MicroMeet thread IDs are Hermes chat IDs; Ed25519 author IDs are Hermes user IDs.
- Hermes streaming previews remain in memory and only the finalized answer becomes an immutable MicroMeet post.

## Notes

Hermes authorization remains authoritative. Configure `MICROMEET_ALLOWED_AUTHORS` or deliberately set `MICROMEET_ALLOW_ALL_AUTHORS=true`; following a route controls replication but is not an identity claim. If more than 100 posts accumulated in one thread while Hermes was offline, notices outside MicroMeet's bounded read window are logged and skipped rather than wedging delivery forever.
