# Context bridge tests

## Scope

`test_bridge.py` verifies the local bridge's privacy, routing, and boundedness
contracts without starting Hermes or MicroMeet.

## Cases

- Successful foreground post/read/create actions bind a thread to the calling
  session.
- Failed calls and calls originating from the MicroMeet gateway cannot replace
  a foreground binding.
- Background workers receive relevant user/assistant excerpts, never tool rows,
  within the configured character limit.
- A successful worker response reaches the foreground session exactly once.
- Handoffs that do not fit one turn's budget remain pending for later turns.
- Operational/provider failures never become handoffs.
- Disabling the mode performs no persistence or injection.

Tests use an isolated SQLite file and an injected transcript loader. This keeps
them deterministic and avoids coupling unit coverage to a running Hermes
profile.
