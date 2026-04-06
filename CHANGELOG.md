# Changelog

## [Phase 1] — 2026-02-27

### Added

- **`GET /api/diagnostics/paper-close-proof`** (auth required) — deterministic paper-trading
  close evidence derived from DB records. Returns `open_trades_count`,
  `oldest_open_trade_age_minutes`, `closes_attempted_last_5m`, `closes_done_last_5m`,
  `last_close_at`, and `last_10_closes` with trade id + close_reason.

- **`GET /api/diagnostics/news-sources`** (auth required) — provider diagnostics for
  CoinStats and all configured news providers. Returns per-provider `fetch_status`,
  `last_error`, `last_articles_count`, and `cache_age_seconds`.

- **`GET /api/market/intelligence`** (auth required) — cached market intelligence brief
  with mood, `why_it_matters`, `what_amarktai_is_doing`, `last_updated`,
  `articles_count`, `top_headlines`, and `block_reason`. Never returns 404 or 500.

- **`closes_failed`** field added to `GET /api/diagnostics/last-tick-summary` response.

- **`top_articles`** list stored in `_last_brief` by `market_intelligence_service` so
  `/api/market/intelligence` can return top headlines even after a backend restart.

- **`NEWS_PROVIDER`** env var (`coinstats` | `gdelt`, default `coinstats`) for
  selecting the primary news provider.

### Fixed

- **CoinStats "fetched 0 articles"**: `services/news_coinstats.py` now logs the actual
  response keys when HTTP 200 is returned but no articles are found, enabling faster
  diagnosis of API schema changes. Duplicate warning suppression prevents log spam.

- **CoinStats response parsing**: extended to handle `result` and `items` response keys
  in addition to the existing `news` and `data` variants. Non-dict items in the raw list
  are now safely skipped.

### Tests

- `tests/test_phase1_endpoints.py`: 13 new tests covering all Phase 1 endpoints,
  CoinStats parsing (happy path, empty 200, alternate keys, unknown schema),
  and `market_intelligence_service` top_articles storage.

### Docs

- `docs/INTELLIGENCE.md`: updated with Phase 1 endpoint reference, new config table,
  troubleshooting section, and Phase 1 verification curl checklist.
