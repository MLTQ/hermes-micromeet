# Tool tests

## Purpose

`test_tools.py` verifies the narrow agent surface and the body/attachment command mapping.

## Contracts tested

- Message bodies never enter the argument vector.
- Multiple attachments become repeated explicit arguments.
- Every declared tool has exactly one registered handler.

## Notes

The fake client records the boundary call while leaving handler construction and JSON serialization unchanged.
