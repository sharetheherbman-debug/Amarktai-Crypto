# Canonical Multi-Exchange Profitability Policy (v2)

**Policy version:** `v2`  
**Source of truth:** `backend/services/trading_brain_v2/entry_thresholds.py`  
**Function:** `compute_min_net_profit_required()`

---

## Summary

The profitability policy determines the minimum net profit required for any trade to be approved.
It replaces the old flat `MIN_PROJECTED_NET_PROFIT` floor (`$1.50 USDT / R25 ZAR`) which blocked
valid small-cap trades.

The new policy scales with capital tier and ensures:
- Small-cap bots can trade meaningful setups that were previously over-blocked.
- Large-cap bots still require proportionally larger absolute profits.
- All trades must clear round-trip costs plus a safety buffer.
- Paper and live modes use **the same formula** — no fake paper relaxations.

---

## Formula

```
min_required = max(
    cost_coverage_floor,   # notional × (all_in_cost_bps + safety_buffer_bps) / 10 000
    strategy_floor,        # ABS_PROFIT_MIN_QUOTE[strategy_class, capital_tier, venue_class]
)
```

Both components are venue-aware, strategy-aware, and capital-tier-aware.

---

## Capital Tiers

| Tier   | USDT range       | ZAR range         |
|--------|-----------------|-------------------|
| micro  | < $100          | < R1 000          |
| small  | $100 – $499     | R1 000 – R4 999   |
| medium | $500 – $4 999   | R5 000 – R49 999  |
| large  | ≥ $5 000        | ≥ R50 000         |

---

## ABS_PROFIT_MIN_QUOTE (strategy floor by tier)

| Strategy      | Tier   | ZAR    | USDT  |
|---------------|--------|--------|-------|
| normal        | micro  | R 0.75 | $0.10 |
| normal        | small  | R 3.00 | $0.50 |
| normal        | medium | R12.00 | $1.50 |
| normal        | large  | R40.00 | $5.00 |
| scalper       | micro  | R 0.30 | $0.04 |
| scalper       | small  | R 1.50 | $0.20 |
| scalper       | medium | R 5.00 | $0.50 |
| scalper       | large  | R15.00 | $1.50 |
| mean_reversion| micro  | R 0.60 | $0.08 |
| mean_reversion| small  | R 3.00 | $0.40 |
| mean_reversion| medium | R10.00 | $1.20 |
| mean_reversion| large  | R30.00 | $4.00 |

---

## Venue Cost Profiles

| Exchange | Round-trip cost (BPS) | Safety buffer (BPS) |
|----------|----------------------|---------------------|
| Luno     | 35                   | 10                  |
| Binance  | 20                   |  8                  |
| KuCoin   | 20                   |  8                  |
| Bybit    | 20                   |  8                  |
| Kraken   | 30                   | 10                  |
| Bitget   | 20                   |  8                  |
| Gate     | 22                   | 10                  |

---

## Diagnostic Fields

Every evaluated trade now exposes:

| Field                        | Description                                             |
|------------------------------|---------------------------------------------------------|
| `min_net_profit_quote_required` | Required minimum net profit (policy output)          |
| `cost_floor_quote`           | Component: cost coverage floor                         |
| `safety_buffer_quote`        | Component: safety buffer above round-trip costs        |
| `strategy_floor_quote`       | Component: per-tier/strategy/venue floor               |
| `capital_tier`               | micro / small / medium / large                         |
| `strategy_class`             | normal / scalper / mean_reversion                      |
| `venue_class`                | usdt / zar                                             |
| `policy_version`             | Always "v2"                                            |
| `policy_source`              | `entry_thresholds.compute_min_net_profit_required`     |
| `projected_net_profit_quote` | Actual projected net profit for this trade             |

Rejection logs include `projected=X required=Y` for clear diagnosis.

---

## Compounding / Capital Growth

As a bot's capital grows:
1. Larger capital → larger position size → larger absolute notional deployed.
2. Larger notional × same-quality edge BPS → larger absolute net profit.
3. Policy floors scale up with tier to ensure quality doesn't degrade.
4. Result: bots naturally compound — higher capital earns more per signal.

---

## What Changed from Policy v1

| Behaviour            | v1 (old)                            | v2 (new)                                |
|----------------------|-------------------------------------|-----------------------------------------|
| USDT profit floor    | Flat $1.50 for **all** accounts     | Tier-aware: $0.10 micro → $5.00 large  |
| ZAR profit floor     | Flat R25.00 for **all** accounts    | Tier-aware: R0.75 micro → R40.00 large |
| `micro` capital tier | Not supported                       | Added (<$100 USDT / <R1000 ZAR)        |
| Bitget support       | No venue cost profile               | Added (20 BPS round-trip)              |
| Gate support         | No venue cost profile               | Added (22 BPS round-trip)              |
| Gate step 8 + 8b     | Two separate checks                 | Unified into one canonical policy call |
| Paper vs live        | Same formula                        | Same formula (no change)               |

---

## Files

| File                                                          | Role                              |
|---------------------------------------------------------------|-----------------------------------|
| `backend/services/trading_brain_v2/entry_thresholds.py`      | **Single source of truth**        |
| `backend/services/trading_brain_v2/trade_feasibility_gate.py`| Hard gate — uses canonical policy |
| `backend/services/trade_worth_filter.py`                     | Worth filter — uses same policy   |
| `tests/test_trading_brain_v2.py`                             | All profitability tests           |
