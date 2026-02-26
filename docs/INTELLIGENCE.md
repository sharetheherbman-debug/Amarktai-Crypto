# Market Intelligence

## Overview

The Market Intelligence pipeline fetches crypto news from CoinStats on a configurable
schedule, classifies sentiment, detects risk events, and produces a plain-English
market brief.  No manual input is required — it runs automatically in the background.

## Architecture

```
CoinStats News API
       │
       ▼
services/news_coinstats.py  (CoinStatsNewsProvider)
       │
       ▼
services/market_intelligence_service.py  (scheduler loop)
       │
       ▼
routes/intelligence.py  (GET /api/intelligence/status | /latest)
```

## CoinStats Key Resolution

Keys are resolved in priority order:

1. **Per-user key** — saved via API Setup (`/api/keys/save`, provider=`coinstats`)
2. **Environment variable** — `COINSTATS_API_KEY`
3. **None** — no key; fetch may still work on the free tier but is rate-limited

The resolution is performed by `services/news_coinstats.resolve_coinstats_key(user_id)`.

## Bug Fix (2026-02): `fetch_status: key_missing` for valid keys

**Symptom:** `/api/intelligence/status` returned `fetch_status: "key_missing"` even
though `/api/keys/list` showed `coinstats` as `configured_valid`.

**Root cause:** The background scheduler ran `_fetch_and_process()` without a `user_id`
context.  If `_resolve_scheduler_user_id()` returned `None` (e.g. collection not ready
at startup), `resolve_coinstats_key(None)` fell back to the env-var, and if no env-var
was set the brief was stored with `fetch_status="key_missing"`.  Subsequent calls to
`/api/intelligence/status` returned this cached brief unmodified.

**Fix:**

1. `routes/intelligence.py` — `get_intelligence_status` now calls
   `resolve_coinstats_key(user_id)` for the authenticated caller.  If the user has a
   valid key, `fetch_status` is overridden to `"ok"` (or `"pending"` if no run has
   happened yet) and `block_reason` is cleared.

2. `services/market_intelligence_service.py` — `get_latest_intelligence` and
   `_fetch_and_process` now accept an optional `user_id` parameter.  When a user hits
   the status endpoint and the cached brief says `key_missing`, an immediate per-user
   fetch is triggered so the brief is refreshed with the correct key.

## Response Fields

`GET /api/intelligence/status`:

| Field                | Type    | Description |
|----------------------|---------|-------------|
| `running`            | bool    | Pipeline is active |
| `hf_enabled`         | bool    | HuggingFace enrichment active |
| `source`             | string  | `"CoinStats"` |
| `mood`               | string  | `positive` / `negative` / `neutral` |
| `last_run_at`        | string? | ISO timestamp of last fetch |
| `next_run_in_seconds`| int?    | Seconds until next refresh |
| `fetch_status`       | string  | `ok` / `pending` / `key_missing` / `error` |
| `coinstats_configured`| bool  | Whether key is resolved for the caller |
| `key_source`         | string  | `user` / `env` / `none` |
| `resolved_for_user_id`| string | User ID the key was resolved for |
| `block_reason`       | string? | Only set when key is not configured |

## Configuration

| Env var                          | Default | Description |
|----------------------------------|---------|-------------|
| `COINSTATS_API_KEY`              | —       | Global fallback key |
| `MARKET_INTEL_REFRESH_SECONDS`   | `60`    | How often to poll CoinStats |
| `NEWS_CACHE_TTL_SECONDS`         | `300`   | Article cache TTL |
| `HF_ENABLED`                     | `true`  | Enable HuggingFace sentiment |
| `HUGGINGFACE_API_KEY` / `HF_API_KEY` | — | HuggingFace key |
