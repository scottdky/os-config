# Tests Current Status (Operational Checklist)

This file is intentionally kept as an evergreen checklist rather than a hard-coded pass/fail snapshot.

## What to trust as current

- Test discovery and markers from `pytest.ini`
- Shared options and gating from `tests/conftest.py`
- Integration execution flow from `tests/integration/run_tests.py`

## Fast status checks

```bash
# 1) Baseline run (unit + mock only)
pytest

# 2) Unit-only and mock-only slices
pytest -m unit
pytest -m mock

# 3) Safest integration subset
env/bin/python -m pytest -m integration

# 4) Chroot-inclusive integration subset
env/bin/python -m pytest -m integration --include-chroot-tests
```

## Real-device safety gates

```bash
# Auto-detect exactly one removable USB device
env/bin/python -m pytest -m integration --use-real-device

# Explicit device path
env/bin/python -m pytest -m integration --use-real-device=/dev/sdb
```

Interactive runner path:

```bash
cd tests/integration
./run_tests.py
```

## How to record point-in-time results

When you need exact totals for a PR/release:

1. Run the relevant commands above.
2. Capture results in CI output or PR notes.
3. Avoid committing durable numeric claims here unless they are immediately refreshed.

## Known high-level risk areas to watch

- Mock coverage for subprocess and filesystem boundary behavior
- Partition/mount detection behavior across loop, mmc, and USB device naming
- Chroot-specific tests only when `qemu-user-static` and sudo prerequisites are available
