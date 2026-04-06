# Backend Production Gate

This document explains how to gate the backend before every production deployment.

---

## Single-Command Production Gate

```bash
./backend/scripts/prod_gate.sh [BASE_URL]
```

**Examples:**

```bash
# Local VPS (default URL)
AMK_EMAIL=admin@example.com AMK_PASSWORD=secret ./backend/scripts/prod_gate.sh

# Custom base URL
AMK_EMAIL=admin@example.com AMK_PASSWORD=secret \
  BASE_URL=https://api.yoursite.com ./backend/scripts/prod_gate.sh
```

**The script performs three steps (in order):**

| Step | Check | Failure action |
|------|-------|----------------|
| 1 | `pytest -q` (plugin auto-load disabled) | Exit non-zero |
| 2 | `scripts/go_live_smoke.sh` | Exit non-zero |
| 3 | `backend/scripts/smoke_bodyguard_loop.sh` | Exit non-zero |

The script exits **0** only when all three steps pass.

---

## Why `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` is Required

The project's venv may contain `web3`, which registers a pytest plugin via the
`pytest11` setuptools entry-point (`ethereum = web3.tools.pytest_ethereum`).  
That module transitively imports `eth_typing.ContractName`, which does not exist
in all `eth_typing` versions, causing an **`ImportError` before any test runs**:

```
ImportError: cannot import name 'ContractName' from 'eth_typing'
```

### How it is applied

Two complementary guards are in place:

1. **`pytest.ini` → `addopts = … -p no:ethereum`**  
   Prevents pytest from activating the `ethereum` entry-point plugin.  
   Works even when `PYTEST_DISABLE_PLUGIN_AUTOLOAD` is not set.

2. **`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` env var (set in `prod_gate.sh`)**  
   Instructs pytest ≥ 7.2 to skip loading *all* `pytest11` entry-points from
   installed packages, providing a belt-and-suspenders guarantee that no other
   third-party plugin can crash the session.

Running `pytest` directly in the repo venv will be safe because of rule (1).  
The production gate script enforces rule (2) in addition.

---

## Pass / Fail Criteria

| Result | Meaning |
|--------|---------|
| **PASS** | All pytest tests pass, go_live_smoke checks pass, bodyguard loop check passes |
| **FAIL** | Any test fails, any smoke assertion fails, script exits non-zero for any step |

---

## Running Tests Locally

```bash
# Minimal – just unit tests, no smoke scripts
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q

# With explicit plugin guard (belt-and-suspenders)
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q -p no:ethereum
```

---

## Queue Hardening

`trading_scheduler.py` and `engines/trade_staggerer.py` now guard every
queue-item access with `.get()` and validate `bot_id`/`exchange` before
enqueueing.  Malformed items are **dropped with a `WARNING` log** (including
the full payload) instead of raising a `KeyError` and crashing the scheduler
loop.

Regression coverage: `tests/test_queue_hardening.py`
