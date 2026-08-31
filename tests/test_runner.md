# Process boundary tests

## Purpose

`test_runner.py` locks down the security-sensitive CLI boundary.

## Contracts tested

- Global JSON and data-directory options are positioned consistently.
- Follow notifications default on and honor platform or environment overrides.
- Arbitrary post text is passed byte-for-byte over stdin with `shell=False`.
- Invalid JSON and timeouts become structured failures.

## Notes

The tests mock only process execution; command construction and response parsing are real.
