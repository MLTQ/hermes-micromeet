# Contributing

Keep the integration small. MicroMeet owns protocol, storage, signing, networking, and blob semantics; this repository owns only Hermes registration, safe CLI invocation, message projection, and gateway lifecycle.

Before submitting a change:

```console
python -m unittest discover -s tests -v
hermes plugins doctor . --ci
```

Every Python module has a same-name Markdown companion describing its responsibility and contracts. Update both when behavior changes. Prefer narrow tools over free-form command execution, preserve stdin for message bodies, and add a regression test for every bug fix.

By contributing, you agree that your work is licensed under Apache-2.0.
