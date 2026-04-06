# Paper Wallet — Multi-Currency Funding (ZAR & USDT)

## Overview

The Amarktai paper wallet supports multiple currencies to allow bots on
different exchanges to train simultaneously.

| Exchange | Quote currency | Typical pair |
|----------|---------------|--------------|
| Luno     | ZAR           | BTC/ZAR, ETH/ZAR |
| Binance  | USDT          | BTC/USDT, ETH/USDT |
| KuCoin   | USDT          | BTC/USDT |
| Bybit    | USDT          | BTC/USDT |
| Bitget   | USDT          | BTC/USDT |
| Gate.io  | USDT          | BTC/USDT |
| Kraken   | USDT          | BTC/USDT |

---

## Funding the Paper Wallet

### Fund with ZAR (for Luno bots)

```http
POST /api/wallet/paper/fund
{
  "amount": 10000,
  "currency": "ZAR",
  "confirmed": true
}
```

### Fund with USDT (for Binance / KuCoin / Bybit / etc. bots)

```http
POST /api/wallet/paper/fund
{
  "amount": 500,
  "currency": "USDT",
  "confirmed": true
}
```

### Fund via AI chat

The AI assistant also accepts:
> "Fund my paper wallet with 500 USDT"
> "Add R10,000 to my paper wallet"

---

## Auto-Conversion Policy (ZAR → USDT)

When a bot tries to reserve USDT funds but only ZAR is available, the
wallet service **automatically converts** ZAR to USDT using a deterministic
paper FX rate.

### FX Rate Resolution

1. **Live rate** (preferred): derived from live Luno `BTC/ZAR` ÷ Binance `BTC/USDT`
2. **Static fallback**: `PAPER_ZAR_PER_USDT` environment variable (default `18.5`)

The rate is re-derived on every conversion attempt; it is never cached across
bot ticks.

### Example

```
Bot requires: 50 USDT
ZAR balance:  2000 ZAR
FX rate:      18.50 ZAR/USDT
ZAR required: 50 × 18.50 = 925 ZAR   ← deducted from ZAR balance
```

### Configuring the FX Rate

```env
# backend/.env
PAPER_ZAR_PER_USDT=18.5   # Default; override for custom paper FX rate
```

---

## Error Messages

| Error code | Meaning | Fix |
|------------|---------|-----|
| `WALLET_UNFUNDED` | Paper wallet balance is 0 (no currency at all) | Fund via dashboard or POST /api/wallet/paper/fund |
| `WALLET_UNFUNDED_CURRENCY` | Required currency (e.g. USDT) is missing | Fund with that currency or rely on auto-conversion from ZAR |
| `INSUFFICIENT_BALANCE` | Insufficient balance for trade amount | Add more funds or reduce bot capital |

---

## How Bot Creation Checks Currency

When creating a paper bot for a USDT exchange:

1. Bot creation checks `required_quote_currency` for the exchange.
2. Calls `paper_wallet_service.get_available_balance(user_id, currency)`.
3. If balance < `bot.capital`:
   - Returns `{"error": "WALLET_UNFUNDED_CURRENCY", "currency": "USDT", "required": <amount>, "how_to_fund": "POST /api/wallet/paper/fund with currency=USDT"}`

---

## Wallet Invariant

The wallet always satisfies:

```
available[currency] + allocated[currency] == total_funded[currency]
```

- `available` = funds in paper wallet not yet deployed in active bot ledgers
- `allocated` = sum of capital assigned to currently active bots / open trades
- `total_funded` = `available + allocated`

No currency balance will go negative.

---

## Checking Balances

```http
GET /api/wallet/paper
```

Returns:

```json
{
  "balances": { "ZAR": 7000.0, "USDT": 300.0 },
  "allocated": { "ZAR": 3000.0, "USDT": 200.0 },
  "total": { "ZAR": 10000.0, "USDT": 500.0 }
}
```
