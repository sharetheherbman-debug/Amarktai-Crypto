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
routes/market_api.py    (GET /api/market/intelligence)
routes/diagnostics.py   (GET /api/diagnostics/news-sources)
                        (GET /api/diagnostics/paper-close-proof)
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

## API Endpoints (Phase 1)

### GET /api/intelligence/status (existing)

Returns pipeline running status, mood, and key configuration.

### GET /api/intelligence/latest (existing)

Returns full market brief with mood, risk, and headline summary.

### GET /api/market/intelligence (NEW — Phase 1)

Returns the cached intelligence brief with top headlines.  Never returns 404 or 500.

```json
{
  "success": true,
  "source": "CoinStats",
  "mood": "neutral",
  "why_it_matters": "...",
  "what_amarktai_is_doing": "...",
  "last_updated": "2026-02-27T08:00:00+00:00",
  "articles_count": 10,
  "top_headlines": ["BTC hits ATH", "..."],
  "block_reason": null,
  "fetch_status": "ok"
}
```

### GET /api/diagnostics/news-sources (NEW — Phase 1, auth required)

Returns provider diagnostics for CoinStats and all configured providers.

```json
{
  "success": true,
  "providers": [
    {
      "provider": "coinstats",
      "configured": true,
      "key_source": "env",
      "last_run_at": "2026-02-27T08:00:00+00:00",
      "last_ok_at": "2026-02-27T08:00:00+00:00",
      "last_error": null,
      "fetch_status": "ok",
      "last_articles_count": 25,
      "cache_age_seconds": 42,
      "http_status_last": null
    },
    {
      "provider": "gdelt",
      "configured": false,
      "fetch_status": "not_primary",
      ...
    }
  ],
  "timestamp": "2026-02-27T08:00:00+00:00"
}
```

### GET /api/diagnostics/paper-close-proof (NEW — Phase 1, auth required)

Returns deterministic paper-trading close evidence from the DB.

```json
{
  "success": true,
  "open_trades_count": 2,
  "oldest_open_trade_age_minutes": 14.3,
  "closes_attempted_last_5m": 3,
  "closes_done_last_5m": 3,
  "last_close_at": "2026-02-27T07:59:55+00:00",
  "last_10_closes": [
    {"id": "trade_abc", "close_reason": "time_exit", "pair": "BTC/ZAR", "closed_at": "..."},
    ...
  ],
  "timestamp": "2026-02-27T08:00:00+00:00"
}
```

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

| Env var                          | Default      | Description |
|----------------------------------|--------------|-------------|
| `COINSTATS_API_KEY`              | —            | Global fallback key |
| `NEWS_PROVIDER`                  | `coinstats`  | Primary news provider (`coinstats` or `gdelt`) |
| `MARKET_INTEL_REFRESH_SECONDS`   | `60`         | How often to poll CoinStats |
| `NEWS_CACHE_TTL_SECONDS`         | `300`        | Article cache TTL |
| `HF_ENABLED`                     | `true`       | Enable HuggingFace sentiment |
| `HUGGINGFACE_API_KEY` / `HF_API_KEY` | —        | HuggingFace key |

## Troubleshooting

### "fetched 0 articles" in logs

1. Check `/api/coinstats/test-connection` returns `http_status=200`.
2. Check `/api/diagnostics/news-sources` — look at `fetch_status` and `last_error`.
3. If `fetch_status=no_articles` and HTTP 200: the CoinStats response changed shape.
   The service now logs the response keys to help diagnose. Set `NEWS_PROVIDER=gdelt`
   as a fallback while investigating.
4. If `fetch_status=key_missing`: add `COINSTATS_API_KEY` env var or save a key via
   the API Setup page.

### Phase 1 Verification Checklist

Run these curl commands against your deployment (replace `$TOKEN` with a valid JWT):

```bash
# 1. Intelligence status (must show running=true)
curl -H "Authorization: Bearer $TOKEN" https://your-vps/api/intelligence/status

# 2. New market intelligence endpoint (must return 200 + mood field)
curl -H "Authorization: Bearer $TOKEN" https://your-vps/api/market/intelligence

# 3. News sources diagnostic (must include coinstats provider)
curl -H "Authorization: Bearer $TOKEN" https://your-vps/api/diagnostics/news-sources

# 4. Paper close proof (must return closes_done_last_5m when trades are closing)
curl -H "Authorization: Bearer $TOKEN" https://your-vps/api/diagnostics/paper-close-proof

# 5. CoinStats connection test (must show http_status=200)
curl -H "Authorization: Bearer $TOKEN" https://your-vps/api/coinstats/test-connection

# 6. Last tick summary (includes closes_failed field)
curl -H "Authorization: Bearer $TOKEN" https://your-vps/api/diagnostics/last-tick-summary
```

