# AUDIT REPORT

## Frontend audit findings and fixes

### Issues found
- Landing page used outdated/incorrect command-center copy and CTA naming.
- Footer text/branding was inconsistent with required brand format.
- Login/Register visual style had bright/white panel tones inconsistent with dark crypto theme.
- Theme variables were split across multiple files, causing inconsistent look and contrast.
- Dashboard topbar still showed "Executive Command Center" wording.
- App route table still listed legacy redirect routes beyond the 4 intended pages.

### Changes made
- Implemented unified theme variables in `frontend/src/styles/theme.css` and imported it globally from `frontend/src/index.js`.
- Updated `Landing.js` copy/branding and CTA buttons to exactly `Login` and `Register`.
- Updated `Landing.css` and `Auth.css` for consistent 50/50 media + dark overlay aesthetic with readable contrast and no white panel styling.
- Updated footer copy in `frontend/src/components/SiteFooter.js` to:
  - `© {YEAR} Amarktai Crypto — part of Amarktai Network`
- Updated dashboard topbar title in `frontend/src/pages/Dashboard.js` to `Amarktai Crypto`.
- Removed extra explicit redirect routes in `frontend/src/App.js` so app routing is limited to Landing/Login/Register/Dashboard (+ fallback).
- Adjusted dashboard shell overflow behavior in `DashboardV3.css` to avoid scrolling at shell level while preserving section-level scrolling.

## Backend audit findings and fixes (bodyguard/quarantine/MODE_DISABLED)

### Issues found
- Quarantine service defaulted to long first quarantine (1 hour) for all reasons, including paper non-strategy reasons.
- Quarantine lacked structured source/rule/reason-code diagnostics.
- Bodyguard could intervene too aggressively for paper mode (non-catastrophic threshold breaches).
- Pause/quarantine records were not consistently storing structured intervention context.
- Circuit-breaker quarantines did not explicitly tag intervention source/rule metadata.

### Changes made
- `backend/services/bot_quarantine.py`
  - Added optional metadata input for quarantine source/rule/threshold/reason code.
  - Added hard skip for paper bot quarantine on `MODE_DISABLED`.
  - Added short quarantine cap (`<=60s`) for paper non-strategy reason codes.
  - Persisted structured diagnostic fields (`quarantine_source`, `quarantine_rule`, `quarantine_threshold`, `quarantine_reason_code`, `last_intervention`).
- `backend/trading_scheduler.py`
  - Preserved existing behavior where paper bots continue when pause reason is `MODE_DISABLED`.
  - Added structured `pause_reason_code` + `last_intervention` metadata for scheduler pauses.
  - Passed structured metadata into quarantine calls.
- `backend/services/bodyguard_service.py`
  - Normalized mode checks for `mode`/`trading_mode` string consistency.
  - In paper mode, made bodyguard informational for non-catastrophic drawdown breaches (no immediate pause/quarantine).
  - Added `pause_reason_code` and structured `last_intervention` when bodyguard actually intervenes.
  - Passed structured metadata to quarantine service for bodyguard-triggered quarantines.
- `backend/engines/circuit_breaker.py`
  - Added `pause_reason_code` and structured `last_intervention` metadata.
  - Passed `source=circuit_breaker` metadata into quarantine service.
- `backend/routes/quarantine.py`
  - Extended quarantine status/history response payload with diagnostic context fields.

## Risky/intentional non-changes
- Did **not** rename or remove existing backend API endpoints; only additive diagnostic fields were introduced.
- Did **not** restructure dashboard logic/section composition; only branding/theme/overflow polish and wording updates.
- Did **not** alter bot-creation business rules/capital validator behavior outside requested paper-quarantine bodyguard flow.
- Did **not** remove legacy page component files from codebase; route exposure was minimized while avoiding broader cleanup risk.

## Verification assets added
- Added `scripts/verify_ui_and_paper_trading.sh` to validate:
  - Frontend build
  - API register/login
  - Creation of 5 Luno paper bots
  - Delay for scheduler ticks
  - No immediate `MODE_DISABLED` quarantine for current-user paper bots
  - Filtered last-200 log lines for quarantine/bodyguard diagnostics
