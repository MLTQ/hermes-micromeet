# Gateway adapter

## Purpose

`adapter.py` makes MicroMeet a Hermes messaging platform. It attaches to one local daemon (or starts it), tails verified inbox notices, maps one MicroMeet thread to one Hermes chat, and posts Hermes replies back into that thread.

## Components

- `MicroMeetAdapter`: daemon ownership, optional notification watcher lifecycle, cursor handling, inbound event construction, and outbound delivery.
- `InboxCursor`: profile-local durable resume policy supplied by `cursor.py`.
- `classify_outbound`: fail-closed publication policy supplied by `outbound.py`.

## Contracts

- Existing daemons are never stopped by the plugin; only a child it started is terminated.
- The first connection starts at the current inbox head unless `replay_existing` is explicitly enabled. Subsequent starts replay messages after the committed cursor.
- Follow notifications are enabled by default. Disabling them keeps outbound platform delivery available without starting an inbox watcher.
- A cursor is committed only after a notice is intentionally skipped or Hermes accepts the projected event.
- Local-author notices are suppressed to prevent reply loops.
- Remote text is prefixed with an untrusted follow-notification frame, so a leading slash cannot invoke Hermes gateway commands.
- Follow events carry explicit untrusted-content, object, author, topic, thread, authored-time, and receive-time data in the Hermes source/raw event record.
- MicroMeet thread IDs are Hermes chat IDs; Ed25519 author IDs are Hermes user IDs.
- Automatic replies are authorized only when their reply object maps to an inbound follow event this adapter accepted for the same MicroMeet thread. At most 256 recent bindings are retained.
- Hermes streaming previews remain in memory and only the finalized answer becomes an immutable MicroMeet post.
- Completed non-streaming responses publish when the accepted event/thread binding is present and Hermes supplies its exact boolean `notify: true` final-response marker. Standardized operational/provider failure envelopes are still suppressed.
- Other direct gateway output is suppressed unless its metadata contains the exact boolean `micromeet_publish: true`; setup prompts, commentary, and unfinalized replies therefore remain local.
- At most 64 unfinalized drafts are retained; the oldest is discarded when the bound is reached.
- Publication is serialized through one local lock. Identical finalized deliveries in the same thread within five seconds reuse the first signed post while allowing later intentional repetition.

## Notes

Hermes authorization remains authoritative. Configure `MICROMEET_ALLOWED_AUTHORS` or deliberately set `MICROMEET_ALLOW_ALL_AUTHORS=true`; following a route controls replication but is not an identity claim. Set `MICROMEET_NOTIFICATIONS=false` for tool-only operation. If more than 100 posts accumulated in one thread while Hermes was offline, notices outside MicroMeet's bounded read window are logged and skipped rather than wedging delivery forever.
