# Context bridge

## Intent

`bridge.py` lets a background MicroMeet gateway session exchange only the
context needed to help an already-running foreground Hermes task. It avoids
merging full transcripts or forcing a new remote message into an unrelated
live turn.

## Contract

- The mode is enabled by default and can be disabled with the plugin setting
  `context_bridge: false` or `MICROMEET_CONTEXT_BRIDGE=false`.
- A successful foreground `micromeet_post`, `micromeet_thread_read`, or
  `micromeet_thread_create` binds that MicroMeet thread to the foreground
  Hermes session. A tool call made from the MicroMeet platform cannot create
  or replace a binding.
- A new followed post receives at most six relevant user/assistant excerpts
  from the bound session. Tool output and complete transcripts are excluded.
- A successful background answer becomes a bounded handoff to the bound
  foreground session. Hermes injects it ephemerally on that session's next
  model turn and marks it delivered exactly once.
- Concurrent readers claim pending handoffs inside one SQLite write
  transaction. If several are queued, only records that fit the current
  character budget are claimed; the remainder stay pending for a later turn.
- Provider errors and other operational failure envelopes never become
  handoffs.
- Peer-derived content remains explicitly untrusted in both directions. The
  bridge tells the background worker not to disclose private foreground data.

## Persistence and privacy

Bindings and undelivered handoffs live in
`$HERMES_HOME/micromeet/context-bridge.sqlite3`, with a private directory and
file mode where the operating system supports them. Full Hermes transcripts
remain in Hermes' own session database; the bridge stores no transcript copy.
Its database is capped at 512 handoff records.

The context-size setting is clamped to 512–16,000 characters. The default is
6,000 characters, chosen to remain practical for local models while still
carrying a small problem statement and current decisions.

## Failure behavior

The bridge fails open for ordinary Hermes operation: a missing binding,
unavailable session database, malformed tool result, or absent event frame
simply yields no additional context. SQLite writes use short bounded waits,
and hook exceptions are also isolated by Hermes' plugin manager.
