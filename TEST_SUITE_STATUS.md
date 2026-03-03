# Test Suite Status Overview

This document tracks the current test architecture and how to evaluate status without relying on stale pass/fail snapshots.

## Current Structure

- `tests/unit/`: Pure logic tests
- `tests/mock/`: Tests with mocked system behavior
- `tests/integration/`: Real mount/chroot/device workflows
- `tests/integration/fixtures/`: Integration test images and fixture data

## Current Defaults

- `pytest` runs unit + mock tests by default (`-m "not integration"`)
- Integration tests are opt-in and require sudo for privileged operations
- Real-device tests are additionally gated by `--use-real-device`
- Chroot execution tests are additionally gated by `--include-chroot-tests`

## Canonical Commands

Run from repository root (with virtualenv active):

```bash
# Default (unit + mock only)
pytest

# Explicit unit or mock
pytest -m unit
pytest -m mock

# Integration safest subset (no device, no chroot)
env/bin/python -m pytest -m integration

# Include chroot integration tests
env/bin/python -m pytest -m integration --include-chroot-tests

# Real-device integration tests
env/bin/python -m pytest -m integration --use-real-device
env/bin/python -m pytest -m integration --use-real-device=/dev/sdb
```

Interactive integration runner:

```bash
cd tests/integration
./run_tests.py
```

## Status Discipline

To keep this file accurate over time:

1. Treat numeric pass/fail counts as per-run data, not durable documentation.
2. Store transient totals in CI logs or PR descriptions.
3. Keep this file focused on architecture, safety gates, and execution entry points.

## Related Docs

- `tests/README.md` for general test commands and markers
- `tests/integration/README.md` for integration prerequisites and safety flow
- `tests/integration/run_tests.py` for menu-based integration execution
