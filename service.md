# Service supervision

## Purpose

`service.py` owns the two long-lived local processes used by the integration: an optional plugin-started `mm serve` daemon and one JSON Lines inbox watcher.

## Components

- `MicroMeetService`: attach/autostart policy, readiness probing, watcher parsing, stderr draining, and bounded shutdown.
- `ServiceError`: lifecycle failures that should trigger Hermes' retryable platform recovery.

## Contracts

- A pre-existing daemon is never owned or stopped.
- A daemon that fails readiness is terminated before the error returns.
- Watch output must be one valid success envelope per line and each line is capped at 1 MiB.
- Child stderr is continuously drained into a 20-line diagnostic ring.
- Graceful termination gets five seconds before a forced kill.

## Notes

This module does not interpret posts, update inbox cursors, or call Hermes. Those responsibilities remain in message projection and the gateway adapter.
