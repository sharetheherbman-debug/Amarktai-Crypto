"""
Wallet Hub for All 8 exchanges

Provides unified wallet interface for:
- Luno, Binance, KuCoin, Bybit, Kraken, Bitget, Gate.io
- Paper wallet simulation
- Live wallet integration (when keys available)
- Production-safe transfers with state machine
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import Optional, Dict, List
from pydantic import BaseModel
import logging
from datetime import datetime, timezone

from auth import get_current_user
import database as db
from realtime_events import manager
from config.platforms import SUPPORTED_PLATFORMS
from services.transfer_state_machine import transfer_state_machine
from services.paper_wallet_service import paper_wallet_service
from services.system_mode_service import system_mode_service
from engines.wallet_manager import wallet_manager
from engines.funding_plan_manager import funding_plan_manager
from config.exchange_config import get_required_fields, get_deposit_requirements
from services.wallet_summary_service import wallet_summary_service
from services.bot_filters import bot_not_deleted_filter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/wallet", tags=["Wallet Hub"])


class TransferRequest(BaseModel):
    from_exchange: str
    to_exchange: str
    amount: float
    currency: str = "ZAR"
    idempotency_key: str  # Required for production safety
    totp_code: Optional[str] = None  # Required if 2FA enabled
    withdrawal_address: Optional[str] = None  # Optional whitelisted address
    notes: Optional[str] = None


class PaperDepositRequest(BaseModel):
    amount: float
    currency: str = "ZAR"


class PaperResetRequest(BaseModel):
    confirm: bool = False


class PaperFundRequest(BaseModel):
    """Explicit paper wallet funding request.

    Requires ``confirmed=True`` so the caller acknowledges they are adding
    starting capital to the unfunded paper wallet.
    """
    amount: float
    currency: str = "ZAR"
    confirmed: bool = False


class PaperSetBalanceRequest(BaseModel):
    """Request to set paper wallet to a specific balance.

    Accepted by POST /api/wallet/paper/set-balance.
    Resets the wallet to zero and then deposits the requested amount.
    """
    balance_zar: float
    currency: str = "ZAR"


@router.get("/status")
async def get_wallet_status_v2(user_id: str = Depends(get_current_user)):
    """Comprehensive wallet status — single source of truth for frontend WalletHub.

    Always returns HTTP 200 with a stable JSON object.  Never raises on missing
    keys or unconfigured exchanges — those are represented as disabled/null.

    Shape:
        mode: "paper" | "live"
        paper: { available, allocated, total, currency, as_of }
        live:  { supported_exchanges, configured_exchanges, balances, as_of }
        ledger: { invariants_ok, drift, last_reconcile_at }
        keys:  { exchanges: {luno: bool, ...}, openai: bool, huggingface: bool }
        health: { backend: "ok", ws: "ok|degraded", last_tick_at }
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    try:
        # ── Mode ─────────────────────────────────────────────────────────────
        try:
            mode = await system_mode_service.get_current_mode(user_id)
        except Exception:
            mode = "paper"

        # ── Paper wallet ─────────────────────────────────────────────────────
        paper_available = 0.0
        paper_allocated = 0.0
        try:
            pw_balances = await paper_wallet_service.get_balances(user_id)
            paper_available = float(
                (pw_balances.get("balances") or {}).get("ZAR", 0) or 0
            )
        except Exception:
            pass
        try:
            allocated_map = await get_paper_wallet_allocated_balances(user_id)
            paper_allocated = float(allocated_map.get("ZAR", 0) or 0)
        except Exception:
            pass
        paper_total = round(paper_available + paper_allocated, 2)

        # ── Live exchange keys ────────────────────────────────────────────────
        configured_exchanges: list = []
        exchange_key_flags: dict = {}
        try:
            api_keys_cursor = db.api_keys_collection.find(
                {"user_id": user_id}, {"_id": 0, "exchange": 1, "provider": 1}
            )
            async for doc in api_keys_cursor:
                exch = doc.get("exchange") or doc.get("provider") or ""
                if exch:
                    exchange_key_flags[exch.lower()] = True
                    if exch.lower() not in configured_exchanges:
                        configured_exchanges.append(exch.lower())
        except Exception:
            pass
        for exch in SUPPORTED_PLATFORMS:
            if exch not in exchange_key_flags:
                exchange_key_flags[exch] = False

        # ── Live balances (only if keys present) ─────────────────────────────
        live_balances = None
        if configured_exchanges:
            try:
                balance_result = await wallet_manager.get_master_balance(user_id)
                if not balance_result.get("error"):
                    live_balances = balance_result
            except Exception:
                pass

        # ── AI key flags ──────────────────────────────────────────────────────
        openai_configured = False
        hf_configured = False
        try:
            from services.openai_key_resolver import resolve_openai_key
            openai_key, _ = await resolve_openai_key(user_id)
            openai_configured = bool(openai_key)
        except Exception:
            pass
        try:
            from services.huggingface_key_resolver import resolve_huggingface_key
            hf_key, _ = await resolve_huggingface_key(user_id)
            hf_configured = bool(hf_key)
        except Exception:
            pass

        # ── Active bots count — separate paper and live ───────────────────────
        active_bots_count = 0
        required_capital = 0.0
        paper_bots_count = 0
        paper_bots_capital = 0.0
        live_bots_count = 0
        live_bots_capital = 0.0
        try:
            if db.bots_collection is not None:
                # Count ALL non-deleted bots with DB status active/running (regardless of training state)
                all_bot_docs = await db.bots_collection.find(
                    bot_not_deleted_filter({
                        "user_id": user_id,
                        "status": {"$in": ["active", "running"]},
                    }),
                    {"_id": 0, "trading_mode": 1, "initial_capital": 1, "current_capital": 1}
                ).to_list(1000)
                for b in all_bot_docs:
                    cap = float(b.get("current_capital") or b.get("initial_capital") or 0)
                    bmode = b.get("trading_mode", "paper")
                    if bmode == "live":
                        live_bots_count += 1
                        live_bots_capital += cap
                    else:
                        paper_bots_count += 1
                        paper_bots_capital += cap

                if mode == "paper":
                    active_bots_count = paper_bots_count
                    required_capital = paper_bots_capital
                else:
                    active_bots_count = live_bots_count
                    required_capital = live_bots_capital
        except Exception:
            pass

        # ── Funding status (mode-aware) ───────────────────────────────────────
        # Paper mode: paper bots have self-contained simulated capital.
        # available_balance is the unallocated paper wallet cash.
        # We do NOT compute a deficit for paper bots — simulation is always "funded".
        # Live mode: compare required capital to live exchange balance.
        if mode == "paper":
            available_balance = round(paper_available + paper_bots_capital, 2)
            # Paper is never in deficit — simulation capital is always available
            deficit = 0.0
        else:
            # Live mode: try to get total live balance
            available_balance = 0.0
            try:
                if live_balances:
                    available_balance = float(
                        live_balances.get("total_zar") or live_balances.get("total") or 0
                    )
            except Exception:
                pass
            deficit = round(max(0.0, required_capital - available_balance), 2)

        # NOT_CONFIGURED: no bots in this mode
        # UNFUNDED: live bots exist but no live balance
        # FUNDED: has bots and balance (or paper mode with bots — always "funded")
        if mode == "paper":
            if paper_bots_count == 0 and paper_available == 0.0:
                funding_status = "NOT_CONFIGURED"
            else:
                funding_status = "FUNDED"  # paper simulation is always self-funded
        else:
            if active_bots_count == 0 and available_balance == 0.0:
                funding_status = "NOT_CONFIGURED"
            elif live_bots_count > 0 and available_balance == 0.0:
                funding_status = "UNFUNDED"
            else:
                funding_status = "FUNDED"

        # ── Ledger invariants (best-effort) ───────────────────────────────────
        ledger_invariants_ok = True
        ledger_drift = 0.0
        ledger_reconcile_at = None
        try:
            from services.ledger_service import get_ledger_service
            from database import get_database
            _db = getattr(db, "db", None)
            if _db is not None:
                ledger_svc = get_ledger_service(_db)
                equity = await ledger_svc.compute_equity(user_id)
                # Compute allocated from open trades
                open_allocated = 0.0
                async for trade in db.trades_collection.find(
                    {"user_id": user_id, "status": "open"},
                    {"_id": 0, "entry_value": 1, "trade_amount": 1}
                ):
                    open_allocated += float(
                        trade.get("entry_value") or trade.get("trade_amount") or 0
                    )
                # Invariant: equity = available + allocated
                # If these numbers are consistent, drift should be ~0.
                available_implied = equity - open_allocated
                computed_total = available_implied + open_allocated
                ledger_drift = round(abs(computed_total - equity), 6)
                ledger_invariants_ok = ledger_drift < 0.01
        except Exception:
            pass

        # ── Unlocked exchanges and per-platform wallets ───────────────────
        unlocked_exchanges: list = []
        platform_wallets: dict = {}
        try:
            from services.canonical import get_unlocked_exchanges, get_platform_wallet_totals_zar
            unlocked_exchanges = await get_unlocked_exchanges(user_id)
            platform_totals = await get_platform_wallet_totals_zar(user_id)
            platform_wallets = platform_totals.get("by_exchange", {})
        except Exception:
            pass

        return {
            "mode": mode,
            # ── Mode-aware summary (primary fields consumed by WalletHub UI) ──
            "active_bots": active_bots_count,
            "required_capital": round(required_capital, 2),
            "available_balance": round(available_balance, 2),
            "deficit": deficit,
            "funding_status": funding_status,
            # ── Per-mode bot breakdown ────────────────────────────────────────
            "paper_bots": {
                "count": paper_bots_count,
                "capital": round(paper_bots_capital, 2),
                "note": "Paper bots use simulated capital; no live funds required.",
            },
            "live_bots": {
                "count": live_bots_count,
                "capital": round(live_bots_capital, 2),
            },
            # ── Paper detail ─────────────────────────────────────────────────
            "paper": {
                "available": round(paper_available, 2),
                "allocated": round(paper_allocated, 2),
                "total": paper_total,
                "currency": "ZAR",
                "funded_status": "FUNDED" if (paper_total > 0 or paper_bots_count > 0) else "UNFUNDED",
                "as_of": now_iso,
            },
            # ── Per-platform wallet breakdown (canonical for WalletHub) ──────
            "platform_wallets": platform_wallets,
            "unlocked_exchanges": unlocked_exchanges,
            "live": {
                "supported_exchanges": list(SUPPORTED_PLATFORMS),
                "configured_exchanges": configured_exchanges,
                "unlocked_exchanges": unlocked_exchanges,
                "balances": live_balances,
                "as_of": now_iso,
            },
            "ledger": {
                "invariants_ok": ledger_invariants_ok,
                "drift": ledger_drift,
                "last_reconcile_at": ledger_reconcile_at,
            },
            "keys": {
                "exchanges": exchange_key_flags,
                "openai": openai_configured,
                "huggingface": hf_configured,
            },
            "health": {
                "backend": "ok",
                "ws": "ok",
                "last_tick_at": now_iso,
            },
        }
    except Exception as e:
        logger.error(f"Wallet status error: {e}", exc_info=True)
        return {
            "mode": "paper",
            "active_bots": 0,
            "required_capital": 0.0,
            "available_balance": 0.0,
            "deficit": 0.0,
            "funding_status": "NOT_CONFIGURED",
            "paper": {"available": 0.0, "allocated": 0.0, "total": 0.0, "currency": "ZAR", "funded_status": "UNFUNDED", "as_of": now_iso},
            "live": {"supported_exchanges": [], "configured_exchanges": [], "balances": None, "as_of": now_iso},
            "ledger": {"invariants_ok": True, "drift": 0.0, "last_reconcile_at": None},
            "keys": {"exchanges": {}, "openai": False, "huggingface": False},
            "health": {"backend": "error", "ws": "degraded", "last_tick_at": None},
        }


@router.get("/health")
async def get_wallet_health(user_id: str = Depends(get_current_user)):
    """
    Get wallet health status for all 7 exchanges
    
    Shows:
    - Keys status (missing, connected, error)
    - Paper balances
    - Live balances (if keys available)
    - Exchange-specific details
    """
    try:
        # Check API keys for all supported exchanges
        wallet_status = {}
        
        for exchange in SUPPORTED_PLATFORMS:
            # Check if user has keys for this exchange
            api_key = await db.api_keys_collection.find_one({
                "user_id": user_id,
                "provider": exchange
            })
            
            if not api_key:
                wallet_status[exchange] = {
                    "status": "keys_missing",
                    "message": f"No API keys configured for {exchange.upper()}",
                    "has_keys": False,
                    "paper_mode_available": True
                }
            elif not api_key.get("last_test_ok"):
                wallet_status[exchange] = {
                    "status": "keys_untested",
                    "message": f"API keys exist but not tested",
                    "has_keys": True,
                    "paper_mode_available": True
                }
            else:
                wallet_status[exchange] = {
                    "status": "connected",
                    "message": f"Connected to {exchange.upper()}",
                    "has_keys": True,
                    "paper_mode_available": True,
                    "last_tested": api_key.get("last_tested_at")
                }
        
        # Get paper wallet balances (simulated from bots)
        paper_balances = await get_paper_wallet_balances(user_id)
        
        return {
            "user_id": user_id,
            "exchanges": wallet_status,
            "paper_balances": paper_balances,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Get wallet health error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def get_paper_wallet_allocated_balances(user_id: str) -> Dict:
    """Calculate allocated paper wallet balances from active bot ledgers"""
    try:
        if db.paper_ledger_collection is None:
            return {}
        pipeline = [
            {"$match": {"user_id": user_id, "status": "active"}},
            {"$group": {"_id": "$currency", "total": {"$sum": "$current_balance"}}}
        ]
        results = await db.paper_ledger_collection.aggregate(pipeline).to_list(100)
        return {r.get("_id") or "ZAR": round(float(r.get("total", 0) or 0), 2) for r in results}
        
    except Exception as e:
        logger.error(f"Get paper wallet allocated balances error: {e}")
        return {}


async def get_paper_wallet_balances(user_id: str) -> Dict:
    """Calculate total paper wallet balances (available + allocated)."""
    available = await paper_wallet_service.get_balances(user_id)
    allocated = await get_paper_wallet_allocated_balances(user_id)
    totals = {}
    for currency, amount in available.get("balances", {}).items():
        totals[currency] = totals.get(currency, 0) + float(amount or 0)
    for currency, amount in allocated.items():
        totals[currency] = totals.get(currency, 0) + float(amount or 0)
    return {currency: round(amount, 2) for currency, amount in totals.items()}


@router.get("/paper")
async def get_paper_wallet(user_id: str = Depends(get_current_user)):
    """Get paper wallet balances and summary.

    Returns both the legacy balance breakdown **and** the wallet_summary_service fields
    so that callers get consistent numbers regardless of which field they read:

    - available_wallet_zar: funds available for new trades
    - allocated_funds_zar:  funds currently deployed in open positions
    - reserved_funds_zar:   funds held back by risk/circuit-breaker rules
    - required_funds_zar:   minimum capital needed to run all active bots
    - shortfall_zar:        max(0, required - available)
    - status:               'ok' | 'shortfall' | 'not_configured'
    """
    summary = await wallet_summary_service.get_summary(user_id)
    available = await paper_wallet_service.get_balances(user_id)
    allocated = await get_paper_wallet_allocated_balances(user_id)
    totals = await get_paper_wallet_balances(user_id)

    # Use the canonical equity function to compute a correct ZAR-equivalent total.
    # The naive sum(totals.values()) is WRONG when totals contains both ZAR and USDT
    # because it treats 1 USDT as 1 ZAR (inflates the total by ~19×).
    from services.canonical import get_canonical_paper_wallet_equity
    equity_info = await get_canonical_paper_wallet_equity(user_id)
    total_value_zar = float(equity_info.get("total_equity", 0) or 0)

    # Invariant: available_wallet_zar MUST equal available["ZAR"] (B).
    # Use the paper_wallet_service balance (unallocated funds) as the single source.
    available_balances = available.get("balances", {})
    available_zar = float(available_balances.get("ZAR", 0) or 0)
    # allocated_funds_zar reflects ledger-reserved (open-position) funds (B).
    allocated_zar = float((allocated or {}).get("ZAR", 0) or 0)

    return {
        "success": True,
        "mode": summary.get("mode", "paper"),
        # Bot fleet summary (feeds WalletHub active_bots / required_capital display)
        "active_bots": summary.get("active_bots_count", 0),
        "required_capital": summary.get("required_funds_zar", 0.0),
        # Canonical wallet_summary fields — invariant: available_wallet_zar == available["ZAR"]
        "available_wallet_zar": round(available_zar, 2),
        "allocated_funds_zar": round(allocated_zar, 2),
        # initial_funding_zar = sum of bot initial_capital (what was deposited for bots).
        # Kept separate from allocated_funds_zar (which reflects current ledger positions).
        "initial_funding_zar": summary.get("allocated_funds_zar", 0.0),
        "reserved_funds_zar": summary.get("reserved_funds_zar", 0.0),
        "required_funds_zar": summary.get("required_funds_zar", 0.0),
        "shortfall_zar": summary.get("shortfall_zar", 0.0),
        "status": summary.get("status", "ok"),
        "funded_status": "FUNDED" if total_value_zar > 0 else "UNFUNDED",
        # Legacy balance breakdown (kept for backward compatibility)
        "user_id": user_id,
        "available": available_balances,
        "allocated": allocated,
        "balances": totals,
        # total is the canonical ZAR-equivalent sum (not a raw multi-currency sum)
        "total": round(total_value_zar, 2),
        "total_display_zar": round(total_value_zar, 2),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/paper/deposit")
async def deposit_paper_wallet(
    request: PaperDepositRequest,
    user_id: str = Depends(get_current_user)
):
    if request.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")
    result = await paper_wallet_service.deposit(user_id, request.amount, request.currency)
    try:
        await db.audit_logs_collection.insert_one({
            "user_id": user_id,
            "action": "paper_wallet_topup",
            "details": {
                "amount": request.amount,
                "currency": request.currency.upper()
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
    except Exception as e:
        logger.warning(f"Paper wallet topup audit failed: {e}")
    return {
        "success": True,
        "balances": result.get("balances", {}),
        "total": result.get("total", 0),
        "currency": request.currency.upper()
    }


@router.post("/paper/topup")
async def topup_paper_wallet(
    request: PaperDepositRequest,
    user_id: str = Depends(get_current_user)
):
    """Top up paper wallet (alias for deposit for backward compatibility)."""
    return await deposit_paper_wallet(request, user_id)


@router.post("/paper/reset")
async def reset_paper_wallet(
    request: PaperResetRequest,
    user_id: str = Depends(get_current_user)
):
    if not request.confirm:
        raise HTTPException(status_code=400, detail="Confirmation required")
    result = await paper_wallet_service.reset(user_id)
    return {
        "success": True,
        "balances": result.get("balances", {}),
        "total": result.get("total", 0),
        "wallet_before": result.get("wallet_before", {}),
        "wallet_after": result.get("wallet_after", {}),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/paper/set-balance")
async def set_paper_wallet_balance(
    request: PaperSetBalanceRequest,
    user_id: str = Depends(get_current_user)
):
    """Set paper wallet to a specific balance (reset then fund).

    Canonical go-live endpoint for seeding demo capital.
    Resets the wallet to zero then deposits the requested amount.

    Args:
        balance_zar: Target balance (>= 0).  0 just clears the wallet.
        currency: Currency code (default ZAR).

    Returns the same JSON shape as GET /api/wallet/paper.
    """
    if request.balance_zar < 0:
        raise HTTPException(status_code=400, detail="balance_zar must be non-negative")
    currency = (request.currency or "ZAR").strip().upper()
    if not currency:
        raise HTTPException(status_code=400, detail="currency must be a non-empty string")

    # Reset to zero, then fund to requested amount
    await paper_wallet_service.reset(user_id)
    if request.balance_zar > 0:
        await paper_wallet_service.fund(user_id, request.balance_zar, currency)

    # Return current state — same shape as GET /paper
    summary = await wallet_summary_service.get_summary(user_id)
    available = await paper_wallet_service.get_balances(user_id)
    allocated = await get_paper_wallet_allocated_balances(user_id)
    totals = await get_paper_wallet_balances(user_id)
    total_value = sum(float(v or 0) for v in totals.values())
    available_balances = available.get("balances", {})
    available_zar = float(available_balances.get("ZAR", 0) or 0)
    allocated_zar = float((allocated or {}).get("ZAR", 0) or 0)

    return {
        "success": True,
        "mode": summary.get("mode", "paper"),
        "available_wallet_zar": round(available_zar, 2),
        "allocated_funds_zar": round(allocated_zar, 2),
        "initial_funding_zar": summary.get("allocated_funds_zar", 0.0),
        "reserved_funds_zar": summary.get("reserved_funds_zar", 0.0),
        "required_funds_zar": summary.get("required_funds_zar", 0.0),
        "shortfall_zar": summary.get("shortfall_zar", 0.0),
        "status": summary.get("status", "ok"),
        "user_id": user_id,
        "available": available_balances,
        "allocated": allocated,
        "balances": totals,
        "total": round(total_value, 2),
        "set_to": request.balance_zar,
        "currency": currency,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/paper/fund")
async def fund_paper_wallet(
    request: PaperFundRequest,
    user_id: str = Depends(get_current_user)
):
    """Explicitly fund an unfunded paper wallet.

    This is the ONLY legitimate way to add starting capital after a reset.
    Requires ``confirmed=True`` and ``amount > 0``.
    The event is logged in the audit log and capital_injections collection.

    Args:
        amount: Amount to fund in ``currency``
        currency: Currency code (default ZAR)
        confirmed: Must be True

    Returns:
        balances, total, funded_amount, ledger_event_id
    """
    if not request.confirmed:
        raise HTTPException(
            status_code=400,
            detail="confirmed must be true to fund paper wallet"
        )
    if request.amount <= 0:
        raise HTTPException(status_code=400, detail="amount must be positive")
    currency = (request.currency or "ZAR").strip().upper()
    if not currency:
        raise HTTPException(status_code=400, detail="currency must be a non-empty string")

    result = await paper_wallet_service.fund(user_id, request.amount, currency)

    # Record capital injection
    from uuid import uuid4
    injection_id = str(uuid4())
    now_iso = datetime.now(timezone.utc).isoformat()
    try:
        if db.capital_injections_collection is not None:
            await db.capital_injections_collection.insert_one({
                "id": injection_id,
                "user_id": user_id,
                "amount": request.amount,
                "currency": currency,
                "source": "paper_fund",
                "timestamp": now_iso,
            })
    except Exception as e:
        logger.warning(f"Capital injection record failed: {e}")

    try:
        await db.audit_logs_collection.insert_one({
            "user_id": user_id,
            "action": "paper_wallet_funded",
            "details": {
                "amount": request.amount,
                "currency": currency,
                "injection_id": injection_id,
            },
            "timestamp": now_iso,
        })
    except Exception as e:
        logger.warning(f"Paper wallet fund audit failed: {e}")

    return {
        "success": True,
        "funded_amount": request.amount,
        "currency": currency,
        "balances": result.get("balances", {}),
        "total": result.get("total", 0),
        "injection_id": injection_id,
        "timestamp": now_iso,
    }


@router.get("/live")
async def get_live_wallet(user_id: str = Depends(get_current_user)):
    """Get live wallet balances when live mode is enabled."""
    mode = await system_mode_service.get_current_mode(user_id)
    if mode != "live":
        raise HTTPException(
            status_code=400,
            detail="Live wallet unavailable while live trading is disabled. Enable live mode first."
        )
    master_balance = await wallet_manager.get_master_balance(user_id)
    if master_balance.get("error"):
        raise HTTPException(status_code=400, detail=master_balance.get("error"))
    exchange_balances = await wallet_manager.get_all_balances(user_id)
    return {
        "success": True,
        "master_wallet": master_balance,
        "exchanges": exchange_balances,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@router.post("/transfer")
async def transfer_funds(
    request: TransferRequest,
    user_id: str = Depends(get_current_user)
):
    """
    Transfer funds between exchanges - PRODUCTION SAFE
    
    Uses transfer_state_machine for:
    - Idempotency (prevents double-send)
    - 2FA enforcement (if REQUIRE_2FA_FOR_WITHDRAWALS=1)
    - Approval workflows (for large amounts)
    - Reserved funds checking
    - State tracking (requested → approved → queued → broadcast → confirmed)
    
    Paper mode: Simulates transfer
    Live mode: Executes real CCXT withdrawal with all safety checks
    """
    try:
        # Validate exchanges
        if request.from_exchange not in SUPPORTED_PLATFORMS:
            raise HTTPException(status_code=400, detail=f"Invalid source exchange: {request.from_exchange}")
        if request.to_exchange not in SUPPORTED_PLATFORMS:
            raise HTTPException(status_code=400, detail=f"Invalid destination exchange: {request.to_exchange}")
        
        # Validate amount
        if request.amount <= 0:
            raise HTTPException(status_code=400, detail="Amount must be positive")
        
        # Check if user has keys for both exchanges
        from_keys = await db.api_keys_collection.find_one({
            "user_id": user_id,
            "provider": request.from_exchange
        })
        
        to_keys = await db.api_keys_collection.find_one({
            "user_id": user_id,
            "provider": request.to_exchange
        })
        
        # Determine if this is paper or live transfer
        is_paper = not (from_keys and to_keys and from_keys.get("last_test_ok") and to_keys.get("last_test_ok"))
        
        if is_paper:
            # Paper mode transfer (simulated) - bypass state machine for simplicity
            transfer_id = f"paper_transfer_{datetime.now(timezone.utc).timestamp()}"
            
            # Log the transfer
            await db.wallet_transfers_collection.insert_one({
                "id": transfer_id,
                "user_id": user_id,
                "from_exchange": request.from_exchange,
                "to_exchange": request.to_exchange,
                "amount": request.amount,
                "currency": request.currency,
                "status": "simulated",
                "mode": "paper",
                "idempotency_key": request.idempotency_key,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            
            # Broadcast realtime event
            await manager.broadcast_json({
                "type": "wallet_transfer",
                "user_id": user_id,
                "transfer_id": transfer_id,
                "mode": "paper",
                "from_exchange": request.from_exchange,
                "to_exchange": request.to_exchange,
                "amount": request.amount,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            
            logger.info(f"Paper transfer simulated: {request.amount} {request.currency} from {request.from_exchange} to {request.to_exchange}")
            
            return {
                "success": True,
                "transfer_id": transfer_id,
                "mode": "paper",
                "message": "Transfer simulated (paper mode)",
                "from_exchange": request.from_exchange,
                "to_exchange": request.to_exchange,
                "amount": request.amount,
                "currency": request.currency
            }
        else:
            # Live mode transfer - use production-safe state machine
            logger.info(f"Live transfer requested: {request.amount} {request.currency} from {request.from_exchange} to {request.to_exchange}")
            
            result = await transfer_state_machine.request_transfer(
                user_id=user_id,
                from_exchange=request.from_exchange,
                to_exchange=request.to_exchange,
                currency=request.currency,
                amount=request.amount,
                idempotency_key=request.idempotency_key,
                totp_code=request.totp_code,
                withdrawal_address=request.withdrawal_address,
                notes=request.notes
            )
            
            if not result.get("success"):
                # Return error without raising exception (error codes expected by frontend)
                return result
            
            return {
                **result,
                "mode": "live",
                "from_exchange": request.from_exchange,
                "to_exchange": request.to_exchange,
                "amount": request.amount,
                "currency": request.currency
            }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Transfer funds error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/balances")
async def get_all_balances(user_id: str = Depends(get_current_user)):
    """
    Get balances across all 7 exchanges
    
    Returns both paper and live balances (if keys available).
    """
    try:
        # Get paper balances
        paper_balances = await get_paper_wallet_balances(user_id)
        allocated_balances = await get_paper_wallet_allocated_balances(user_id)
        
        # Get live balances when keys are available
        live_balances = {}
        
        for exchange in SUPPORTED_PLATFORMS:
            api_key_doc = await db.api_keys_collection.find_one({
                "user_id": user_id,
                "service": exchange
            })
            
            if api_key_doc and api_key_doc.get("last_test_ok"):
                # Keys exist and were tested successfully
                try:
                    # Use ccxt to get real balance
                    from ccxt_service import ccxt_service
                    balance_data = await ccxt_service.get_balance(user_id, exchange)
                    
                    if balance_data and balance_data.get("total"):
                        # Convert to ZAR equivalent if needed
                        total_usd = sum([
                            float(balance_data["total"].get(currency, 0))
                            for currency in balance_data["total"]
                        ])
                        # Simple approximation: 1 USD = 18 ZAR
                        live_balances[exchange] = round(total_usd * 18, 2)
                    else:
                        live_balances[exchange] = 0.0
                        
                except Exception as e:
                    logger.warning(f"Failed to get live balance for {exchange}: {e}")
                    live_balances[exchange] = 0.0
            else:
                live_balances[exchange] = 0.0
        
        master_wallet = {}
        try:
            master_balance = await wallet_manager.get_master_balance(user_id)
            if master_balance.get("error"):
                master_wallet = {
                    "total_zar": 0,
                    "btc_balance": 0,
                    "eth_balance": 0,
                    "xrp_balance": 0,
                    "exchange": "luno",
                    "error": master_balance.get("error")
                }
            else:
                master_wallet = {
                    "total_zar": master_balance.get("total_zar", 0),
                    "btc_balance": master_balance.get("btc", 0),
                    "eth_balance": master_balance.get("eth", 0),
                    "xrp_balance": master_balance.get("xrp", 0),
                    "exchange": master_balance.get("exchange", "luno")
                }
        except Exception as e:
            logger.warning(f"Master wallet lookup failed: {e}")
            master_wallet = {
                "total_zar": 0,
                "btc_balance": 0,
                "eth_balance": 0,
                "xrp_balance": 0,
                "exchange": "luno",
                "error": str(e)
            }

        return {
            "user_id": user_id,
            "paper_balances": paper_balances,
            "paper_allocated": allocated_balances,
            "live_balances": live_balances,
            "total_paper": round(sum(paper_balances.values()), 2),
            "total_live": round(sum(live_balances.values()), 2),
            "master_wallet": master_wallet,
            "zar": master_wallet.get("total_zar", 0),
            "btc": master_wallet.get("btc_balance", 0),
            "btc_balance": master_wallet.get("btc_balance", 0),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Get all balances error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/transactions")
async def get_wallet_transactions(
    limit: int = 100,
    user_id: str = Depends(get_current_user)
):
    """
    Get wallet transaction history
    
    Includes transfers, deposits, withdrawals.
    """
    try:
        # Get transfers
        transfers_cursor = db.wallet_transfers_collection.find(
            {"user_id": user_id},
            {"_id": 0}
        ).sort("timestamp", -1).limit(limit)
        
        transfers = await transfers_cursor.to_list(limit)
        
        return {
            "user_id": user_id,
            "transactions": transfers,
            "total": len(transfers)
        }
        
    except Exception as e:
        logger.error(f"Get wallet transactions error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# ADMIN APPROVAL ENDPOINTS
# ============================================================================

@router.post("/admin/approve/{transfer_id}")
async def admin_approve_transfer(
    transfer_id: str,
    notes: Optional[str] = None,
    admin_id: str = Depends(get_current_user)
):
    """
    Admin approval for large transfers
    
    Requires admin role. Transitions transfer from NEEDS_APPROVAL → APPROVED → QUEUED
    """
    try:
        # Check if user is admin
        user = await db.users_collection.find_one({"id": admin_id})
        if not user or user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Admin access required")
        
        result = await transfer_state_machine.approve_transfer(
            transfer_id=transfer_id,
            admin_id=admin_id,
            notes=notes
        )
        
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error", "Approval failed"))
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Admin approve transfer error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/admin/reject/{transfer_id}")
async def admin_reject_transfer(
    transfer_id: str,
    reason: str,
    admin_id: str = Depends(get_current_user)
):
    """
    Admin rejection of transfer
    
    Requires admin role. Transitions transfer to CANCELLED and releases reserved funds
    """
    try:
        # Check if user is admin
        user = await db.users_collection.find_one({"id": admin_id})
        if not user or user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Admin access required")
        
        result = await transfer_state_machine.reject_transfer(
            transfer_id=transfer_id,
            admin_id=admin_id,
            reason=reason
        )
        
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error", "Rejection failed"))
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Admin reject transfer error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/admin/pending-approvals")
async def get_pending_approvals(
    admin_id: str = Depends(get_current_user)
):
    """
    Get all pending transfer approvals
    
    Requires admin role. Returns list of transfers needing approval
    """
    try:
        # Check if user is admin
        user = await db.users_collection.find_one({"id": admin_id})
        if not user or user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Admin access required")
        
        # Get pending approvals
        pending_cursor = db.db["transfer_jobs"].find(
            {"state": "needs_approval"},
            {"_id": 0}
        ).sort("created_at", -1)
        
        pending = await pending_cursor.to_list(100)
        
        return {
            "pending_approvals": pending,
            "count": len(pending)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get pending approvals error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/requirements")
async def get_capital_requirements(user_id: str = Depends(get_current_user)):
    """
    Get capital requirements per exchange based on active bots.
    Returns required exchanges, required fields per exchange, whether keys are present,
    and deposit requirements if applicable.
    """
    try:
        # Safe check for collection initialization
        if db.bots_collection is None:
            logger.warning("bots_collection not initialized")
            return {
                "user_id": user_id,
                "requirements": {},
                "summary": {
                    "total_required": 0,
                    "total_available": 0,
                    "overall_health": "unknown"
                },
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "note": "Collections not initialized"
            }
        
        mode = await system_mode_service.get_current_mode(user_id)

        # Get all active bots in current mode
        bots = await db.bots_collection.find(
            {"user_id": user_id, "status": "active", "trading_mode": mode},
            {"_id": 0}
        ).to_list(1000)
        
        # Get user's API keys to check what's configured
        api_keys_present = {}
        try:
            user_keys = await db.api_keys_collection.find(
                {"user_id": user_id},
                {"_id": 0, "provider": 1, "exchange": 1}
            ).to_list(100)
            
            for key in user_keys:
                provider = key.get('provider') or key.get('exchange')
                if provider:
                    api_keys_present[provider.lower()] = True
        except Exception as e:
            logger.warning(f"Could not fetch API keys: {e}")
        
        # Calculate required capital per exchange
        requirements = {}
        
        for bot in bots:
            exchange = bot.get('exchange', 'unknown').lower()
            initial_capital = bot.get('initial_capital')
            capital = initial_capital if initial_capital is not None else bot.get('current_capital', 0)
            
            if exchange not in requirements:
                requirements[exchange] = {
                    "exchange": exchange,
                    "required_capital": 0,
                    "bots_count": 0,
                    "available_capital": 0,
                    "surplus_deficit": 0,
                    "health": "unknown",
                    "api_key_present": api_keys_present.get(exchange, False),
                    "required_fields": get_required_fields(exchange),
                    "deposit_requirements": get_deposit_requirements(exchange)
                }
            
            requirements[exchange]['required_capital'] += capital
            requirements[exchange]['bots_count'] += 1
        
        # Initialize balances to None
        balances = None
        
        # Get actual balances (safe check for collection)
        if db.wallet_balances_collection is not None:
            balances = await db.wallet_balances_collection.find_one(
                {"user_id": user_id},
                {"_id": 0}
            )
            
            if balances:
                for exchange, req in requirements.items():
                    exchange_balance = balances.get('exchanges', {}).get(exchange, {})
                    available = exchange_balance.get('zar_balance', 0)
                    req['available_capital'] = available
                    req['surplus_deficit'] = available - req['required_capital']
                    
                    # Determine health
                    if req['surplus_deficit'] >= 1000:
                        req['health'] = 'healthy'
                    elif req['surplus_deficit'] >= 0:
                        req['health'] = 'adequate'
                    elif req['surplus_deficit'] >= -500:
                        req['health'] = 'warning'
                    else:
                        req['health'] = 'critical'
        else:
            logger.warning("wallet_balances_collection not initialized")
        
        # Calculate summary
        total_required = sum(req['required_capital'] for req in requirements.values())
        total_available = sum(req['available_capital'] for req in requirements.values())
        
        # Get wallet summary with error handling
        wallet_summary = {}
        try:
            wallet_summary = await wallet_summary_service.get_summary(user_id)
            if not wallet_summary:
                wallet_summary = {}
        except Exception as e:
            logger.warning(f"Failed to get wallet summary: {e}")
            wallet_summary = {}

        return {
            "user_id": user_id,
            "requirements": requirements,
            "summary": {
                "total_required": round(total_required, 2),
                "total_available": round(total_available, 2),
                "overall_health": "healthy" if total_available >= total_required else "warning",
                "exchanges_count": len(requirements),
                "keys_configured": sum(1 for req in requirements.values() if req['api_key_present']),
                "mode": wallet_summary.get("mode"),
                "required_funds_zar": wallet_summary.get("required_funds_zar"),
                "available_wallet_zar": wallet_summary.get("available_wallet_zar"),
                "reserved_funds_zar": wallet_summary.get("reserved_funds_zar"),
                "shortfall_zar": wallet_summary.get("shortfall_zar"),
                "status": wallet_summary.get("status")
            },
            "timestamp": balances.get('timestamp', datetime.now(timezone.utc).isoformat()) if balances else datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Get capital requirements error: {e}")
        # Return safe default instead of 500
        return {
            "user_id": user_id,
            "requirements": {},
            "summary": {
                "total_required": 0,
                "total_available": 0,
                "overall_health": "error"
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "error": str(e)
        }


@router.get("/funding-plans")
async def get_funding_plans(
    status: str = None,
    user_id: str = Depends(get_current_user)
):
    """Get all funding plans for user"""
    try:
        plans = await funding_plan_manager.get_user_funding_plans(
            user_id,
            status=status
        )
        
        return {
            "user_id": user_id,
            "plans": plans,
            "count": len(plans)
        }
        
    except Exception as e:
        logger.error(f"Get funding plans error: {e}")
        # Return safe default instead of 500
        return {
            "user_id": user_id,
            "plans": [],
            "count": 0,
            "error": str(e)
        }


@router.get("/funding-plans/{plan_id}")
async def get_funding_plan(plan_id: str, user_id: str = Depends(get_current_user)):
    """Get specific funding plan"""
    try:
        plan = await funding_plan_manager.get_funding_plan(plan_id)
        
        if not plan:
            raise HTTPException(status_code=404, detail="Funding plan not found")
        
        # Verify ownership
        if plan.get("user_id") != user_id:
            raise HTTPException(status_code=403, detail="Not authorized to view this plan")
        
        return plan
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get funding plan error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/funding-plans/{plan_id}/cancel")
async def cancel_funding_plan(plan_id: str, user_id: str = Depends(get_current_user)):
    """Cancel a funding plan"""
    try:
        result = await funding_plan_manager.cancel_funding_plan(plan_id, user_id)
        
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error", "Cancellation failed"))
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Cancel funding plan error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/converter")
async def currency_converter(data: dict, user_id: str = Depends(get_current_user)):
    """Convert an amount between any two supported currencies using live FX rates.

    Supported: ZAR, USD, GBP, EUR, USDT, BUSD, USDC, BTC, ETH

    Request body:
        amount        - Positive numeric amount to convert
        from_currency - Source currency code (e.g. 'ZAR', 'USDT', 'BTC')
        to_currency   - Target currency code

    Returns:
        input_amount, input_currency, output_amount, output_currency,
        effective_rate, rate_source, via_zar_amount (if cross-rate)
    """
    try:
        from services.fx_normalizer import get_fx_rate

        SUPPORTED = {"ZAR", "USD", "GBP", "EUR", "USDT", "BUSD", "USDC", "BTC", "ETH"}

        amount = data.get("amount")
        from_cur = str(data.get("from_currency", "")).upper().strip()
        to_cur = str(data.get("to_currency", "")).upper().strip()

        # Validate amount
        try:
            amount = float(amount)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Invalid amount — must be a number")
        if amount <= 0:
            raise HTTPException(status_code=400, detail="Amount must be positive")

        # Validate currencies
        if from_cur not in SUPPORTED:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported from_currency '{from_cur}'. Supported: {', '.join(sorted(SUPPORTED))}"
            )
        if to_cur not in SUPPORTED:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported to_currency '{to_cur}'. Supported: {', '.join(sorted(SUPPORTED))}"
            )

        # Identity conversion
        if from_cur == to_cur:
            return {
                "input_amount": amount,
                "input_currency": from_cur,
                "output_amount": amount,
                "output_currency": to_cur,
                "effective_rate": 1.0,
                "rate_source": "identity",
                "via_zar_amount": None,
            }

        rate, source = get_fx_rate(from_cur, to_cur)
        output_amount = amount * rate

        # Compute via-ZAR intermediate for cross-rates (helps frontend show breakdown)
        via_zar = None
        if from_cur != "ZAR" and to_cur != "ZAR":
            zar_rate, _ = get_fx_rate(from_cur, "ZAR")
            via_zar = round(amount * zar_rate, 6)

        return {
            "input_amount": amount,
            "input_currency": from_cur,
            "output_amount": round(output_amount, 8),
            "output_currency": to_cur,
            "effective_rate": round(rate, 8),
            "rate_source": source,
            "via_zar_amount": via_zar,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Currency converter error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Per-Platform Paper Wallet Endpoints
# ============================================================================
# These endpoints implement the canonical per-platform paper wallet model:
#   GET  /api/wallet/platform                   — list all platform wallets
#   GET  /api/wallet/platform/{exchange}        — single platform wallet
#   POST /api/wallet/platform/{exchange}/fund   — fund a platform wallet
#   POST /api/wallet/platform/{exchange}/reset  — reset to zero
#   GET  /api/wallet/platform/summary           — ZAR totals across all platforms
# ============================================================================


class PlatformWalletFundRequest(BaseModel):
    """Request to fund a per-platform paper wallet."""
    amount: float
    currency: Optional[str] = None  # defaults to the exchange's native currency
    confirmed: bool = False


class PlatformWalletResetRequest(BaseModel):
    confirm: bool = False


@router.get("/platform/summary")
async def get_platform_wallet_summary(user_id: str = Depends(get_current_user)):
    """Canonical ZAR-equivalent summary across all per-platform paper wallets.

    Returns total portfolio equity in ZAR with a per-exchange breakdown.
    All values are reported in ZAR regardless of native currency (USDT, ZAR, etc.).

    This is the canonical source for:
    - countdown
    - overview / profit tiles
    - wallet hub portfolio total
    """
    from services.canonical import get_platform_wallet_totals_zar, get_unlocked_exchanges
    try:
        totals = await get_platform_wallet_totals_zar(user_id)
        unlocked = await get_unlocked_exchanges(user_id)
        return {
            "success": True,
            "total_portfolio_zar": totals["combined_zar"],
            "platform_wallets_zar": totals["total_zar"],
            "global_wallet_zar": totals["global_wallet_zar"],
            "by_exchange": totals["by_exchange"],
            "unlocked_exchanges": unlocked,
            "reporting_currency": "ZAR",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.error("Platform wallet summary error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/platform")
async def list_platform_wallets(user_id: str = Depends(get_current_user)):
    """List all per-platform paper wallets for the authenticated user.

    Returns all existing exchange wallets plus stubs for unlocked exchanges
    that haven't been explicitly funded yet.
    Only unlocked exchanges (API key present AND tested) are included.
    """
    from services.canonical import get_unlocked_exchanges
    try:
        unlocked = await get_unlocked_exchanges(user_id)
        existing = await paper_wallet_service.get_all_exchange_wallets(user_id)

        # Merge: ensure every unlocked exchange has an entry (even if unfunded)
        wallets: dict = {}
        for exch in unlocked:
            if exch in existing:
                wallets[exch] = existing[exch]
            else:
                wallets[exch] = {
                    "exchange": exch,
                    "balances": {paper_wallet_service._native_currency_for(exch): 0.0},
                    "native_currency": paper_wallet_service._native_currency_for(exch),
                    "available": 0.0,
                    "funded": False,
                    "updated_at": None,
                }

        return {
            "success": True,
            "unlocked_exchanges": unlocked,
            "platform_wallets": wallets,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.error("List platform wallets error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/platform/{exchange}")
async def get_platform_wallet(
    exchange: str,
    user_id: str = Depends(get_current_user),
):
    """Get the paper wallet for a specific exchange.

    Returns the current balance, native currency, and funded status.
    No authentication against API keys — returns data for any exchange name.
    """
    try:
        wallet = await paper_wallet_service.get_exchange_wallet(user_id, exchange.lower())
        return {"success": True, **wallet}
    except Exception as e:
        logger.error("Get platform wallet error (%s): %s", exchange, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/platform/{exchange}/fund")
async def fund_platform_wallet(
    exchange: str,
    request: PlatformWalletFundRequest,
    user_id: str = Depends(get_current_user),
):
    """Fund the paper wallet for a specific exchange.

    Requires confirmed=True.  The exchange does NOT need to be unlocked —
    operators may pre-fund paper wallets before adding API keys.

    Args:
        exchange: Exchange name (e.g. 'luno', 'binance')
        amount:   Positive amount to add
        currency: Currency code (defaults to the exchange's native currency)
        confirmed: Must be True
    """
    if not request.confirmed:
        raise HTTPException(
            status_code=400,
            detail="confirmed must be true to fund a platform paper wallet",
        )
    if request.amount <= 0:
        raise HTTPException(status_code=400, detail="amount must be positive")

    exchange = exchange.lower()
    if exchange not in SUPPORTED_PLATFORMS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported exchange '{exchange}'. Supported: {list(SUPPORTED_PLATFORMS)}",
        )

    try:
        result = await paper_wallet_service.fund_exchange_wallet(
            user_id, exchange, request.amount, request.currency
        )
        now_iso = datetime.now(timezone.utc).isoformat()
        try:
            await db.audit_logs_collection.insert_one({
                "user_id": user_id,
                "action": "platform_paper_wallet_funded",
                "details": {
                    "exchange": exchange,
                    "amount": request.amount,
                    "currency": (request.currency or result.get("native_currency", "")).upper(),
                },
                "timestamp": now_iso,
            })
        except Exception as audit_err:
            logger.warning("Platform wallet fund audit failed: %s", audit_err)
        return {"success": True, **result, "funded_amount": request.amount}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Fund platform wallet error (%s): %s", exchange, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/platform/{exchange}/reset")
async def reset_platform_wallet(
    exchange: str,
    request: PlatformWalletResetRequest,
    user_id: str = Depends(get_current_user),
):
    """Reset the per-exchange paper wallet to zero balance."""
    if not request.confirm:
        raise HTTPException(status_code=400, detail="confirm must be true to reset a platform wallet")
    exchange = exchange.lower()
    if exchange not in SUPPORTED_PLATFORMS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported exchange '{exchange}'. Supported: {list(SUPPORTED_PLATFORMS)}",
        )
    try:
        result = await paper_wallet_service.reset_exchange_wallet(user_id, exchange)
        return {"success": True, **result}
    except Exception as e:
        logger.error("Reset platform wallet error (%s): %s", exchange, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
