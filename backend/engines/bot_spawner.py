"""
Autonomous Bot Spawner
- Auto-spawns bots until 65 total
- Distributes across exchanges
- AI-controlled allocation
- Uses wallet_manager for funding
"""

import asyncio
from typing import Dict, List
from datetime import datetime, timezone
from uuid import uuid4
import logging

import database as db
from engines.wallet_manager import wallet_manager
from utils.trading_gates import check_trading_mode_enabled
from config import *

logger = logging.getLogger(__name__)

class BotSpawner:
    def __init__(self):
        self.max_bots = 65
        # SUPPORTED EXCHANGES: All 7 platforms
        self.exchange_distribution = {
            'luno': 10,     # 10 total on Luno (5 normal + 5 scalper)
            'binance': 10,  # 10 bots on Binance
            'kucoin': 10,   # 10 bots on KuCoin
            'bybit': 10,    # 10 bots on Bybit
            'kraken': 10,   # 10 bots on Kraken
            'bitget': 10,   # 10 bots on Bitget
            'gate': 10,     # 10 bots on Gate.io
        }
        
        self.risk_distribution = {
            'safe': 0.3,        # 30% safe bots
            'balanced': 0.4,    # 40% balanced
            'risky': 0.2,       # 20% risky
            'aggressive': 0.1   # 10% aggressive
        }
    
    async def get_bot_count(self, user_id: str) -> Dict:
        """Get current bot count per exchange"""
        try:
            bots = await db.bots_collection.find(
                {"user_id": user_id},
                {"_id": 0, "exchange": 1, "status": 1}
            ).to_list(1000)
            
            by_exchange = {}
            for exchange in self.exchange_distribution.keys():
                exchange_bots = [b for b in bots if b.get('exchange', '').lower() == exchange]
                by_exchange[exchange] = {
                    "total": len(exchange_bots),
                    "active": len([b for b in exchange_bots if b.get('status') == 'active'])
                }
            
            return {
                "total_bots": len(bots),
                "by_exchange": by_exchange,
                "remaining_slots": self.max_bots - len(bots)
            }
            
        except Exception as e:
            logger.error(f"Get bot count error: {e}")
            return {"error": str(e)}
    
    async def determine_next_bot_config(self, user_id: str, allowed_exchanges: List[str] = None) -> Dict:
        """Determine config for next bot to spawn.

        Args:
            user_id: The user to spawn for.
            allowed_exchanges: Optional whitelist of exchange IDs.  When provided,
                only exchanges in this list are considered for spawning.  This
                prevents auto_spawn_to_target from silently expanding to exchanges
                that were not part of the user's intended run (e.g. Bybit/Bitget/
                KuCoin when the user only wants Luno + Binance).
        """
        try:
            bot_count = await self.get_bot_count(user_id)
            
            if bot_count['total_bots'] >= self.max_bots:
                return {"error": "Maximum bot count reached"}
            
            # Build the effective exchange distribution — filtered to allowed_exchanges
            # when that restriction is supplied by the caller.
            effective_distribution = {
                ex: cnt
                for ex, cnt in self.exchange_distribution.items()
                if allowed_exchanges is None or ex in allowed_exchanges
            }
            if not effective_distribution:
                return {"error": "No exchanges available after applying allowed_exchanges filter"}

            # Find exchange with most remaining slots
            by_exchange = bot_count['by_exchange']
            target_exchange = None
            max_remaining = 0
            
            for exchange, target_count in effective_distribution.items():
                current = by_exchange.get(exchange, {}).get('total', 0)
                remaining = target_count - current
                
                if remaining > max_remaining:
                    max_remaining = remaining
                    target_exchange = exchange
            
            if not target_exchange:
                return {"error": "No available exchange slots"}
            
            # Determine risk mode deterministically based on the current distribution
            # of existing bots so that the portfolio always trends toward the target
            # risk distribution without relying on random selection.
            existing_bots = await db.bots_collection.find(
                {"user_id": user_id, "exchange": target_exchange},
                {"_id": 0, "risk_mode": 1}
            ).to_list(1000)
            existing_by_mode: dict = {}
            for b in existing_bots:
                m = b.get("risk_mode", "balanced")
                existing_by_mode[m] = existing_by_mode.get(m, 0) + 1
            # Use actual count; when zero bots exist every mode has deficit = target_fraction
            total_existing = len(existing_bots) if existing_bots else 0

            # Choose the mode most under-represented relative to target distribution
            deficit = {}
            for mode, target_fraction in self.risk_distribution.items():
                actual_fraction = (
                    existing_by_mode.get(mode, 0) / total_existing
                    if total_existing > 0
                    else 0.0
                )
                deficit[mode] = target_fraction - actual_fraction
            risk_mode = max(deficit, key=lambda m: (deficit[m], m))  # tie-break alphabetically
            
            # Calculate capital allocation
            capital = await wallet_manager.calculate_allocation_per_bot(user_id, self.max_bots)
            
            return {
                "exchange": target_exchange,
                "risk_mode": risk_mode,
                "capital": capital,
                "name": f"Bot-{bot_count['total_bots'] + 1:02d}"
            }
            
        except Exception as e:
            logger.error(f"Next bot config error: {e}")
            return {"error": str(e)}
    
    async def spawn_bot(self, user_id: str, config: Dict) -> Dict:
        """Spawn a single bot with capital validation"""
        try:
            # TRADING MODE GATE: Check if any trading mode is enabled before spawning bots
            trading_enabled, mode_or_reason = check_trading_mode_enabled()
            if not trading_enabled:
                logger.warning(f"Bot spawn blocked: {mode_or_reason}")
                return {
                    "success": False,
                    "error": mode_or_reason,
                    "error_code": "TRADING_MODE_DISABLED"
                }
            
            from services.capital_validator import capital_validator
            from services.reserved_funds_service import reserved_funds_service
            
            # Check available funds before spawning (includes reserved funds tracking)
            has_funds, available = await reserved_funds_service.check_available_funds(
                user_id, config['exchange'], "ZAR", config['capital']
            )
            
            if not has_funds:
                reserved_summary = await reserved_funds_service.get_reserved_summary(user_id)
                exchange_reserved = (
                    ((reserved_summary.get("by_exchange") or {}).get(config['exchange']) or {}).get("total_reserved", 0)
                    if isinstance(reserved_summary, dict) else 0
                )
                shortfall = max(0.0, float(config['capital']) - float(available))
                detail_message = (
                    f"Bot spawn blocked — minimum required: R{config['capital']:.2f}, "
                    f"available: R{available:.2f}, reserved: R{exchange_reserved:.2f}, "
                    f"shortfall: R{shortfall:.2f}"
                )
                logger.warning(
                    detail_message
                )
                return {
                    "success": False,
                    "error": detail_message,
                    "error_code": "INSUFFICIENT_AVAILABLE_FUNDS",
                    "min_required": round(float(config['capital']), 2),
                    "available": round(float(available), 2),
                    "reserved": round(float(exchange_reserved), 2),
                    "shortfall": round(float(shortfall), 2),
                    "block_reason": "insufficient_available_funds",
                }
            
            # Validate funding FIRST before attempting to spawn
            is_valid, error_code, error_msg = await capital_validator.validate_bot_funding(
                user_id, config['capital']
            )
            
            if not is_valid:
                logger.warning(f"Bot spawn blocked: {error_msg} (code: {error_code})")
                return {
                    "success": False,
                    "error": error_msg,
                    "error_code": error_code
                }
            
            bot_id = str(uuid4())
            
            # Allocate funds from master wallet
            allocation = await wallet_manager.allocate_funds_for_bot(
                user_id,
                bot_id,
                config['exchange'],
                config['capital']
            )
            
            if not allocation.get('success'):
                return {"success": False, "error": "Fund allocation failed"}
            
            # Reserve funds atomically
            reserve_success, reserve_msg = await reserved_funds_service.reserve_funds(
                user_id, config['exchange'], "ZAR", config['capital'], bot_id
            )
            
            if not reserve_success:
                logger.error(f"Failed to reserve funds: {reserve_msg}")
                # Note: Continue anyway since wallet_manager already allocated
                # This is a tracking issue, not a blocker
            
            # Create bot document
            bot_doc = {
                "id": bot_id,
                "user_id": user_id,
                "name": config['name'],
                "exchange": config['exchange'],
                "risk_mode": config['risk_mode'],
                "initial_capital": config['capital'],
                "current_capital": config['capital'],
                "allocated_capital": config['capital'],  # Track allocated capital
                "total_profit": 0,
                "trades_count": 0,
                "win_count": 0,
                "loss_count": 0,
                "mode": "paper",  # Always start in paper mode
                "paper_start_date": datetime.now(timezone.utc).isoformat(),
                "status": "active",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "daily_trade_count": 0,
                "last_trade_time": None,
                "auto_spawned": True,  # Mark as auto-spawned
                "deleted_at": None,  # Explicit null so partial index uidx_bot_identity covers this bot
                "bot_type": config.get("bot_type", "normal"),
            }
            
            await db.bots_collection.insert_one(bot_doc)
            
            # Atomically allocate capital using capital validator
            success, alloc_msg = await capital_validator.allocate_capital_to_bot(
                user_id, bot_id, config['capital']
            )
            
            if not success:
                # Rollback: delete bot and release reserved funds if allocation failed
                await db.bots_collection.delete_one({"id": bot_id})
                await reserved_funds_service.release_funds(
                    user_id, config['exchange'], "ZAR", config['capital'], bot_id
                )
                return {"success": False, "error": f"Capital allocation failed: {alloc_msg}"}
            
            logger.info(f"🤖 Spawned {config['name']} on {config['exchange']} with R{config['capital']:.2f} allocated")
            
            return {
                "success": True,
                "bot_id": bot_id,
                "bot": bot_doc
            }
            
        except Exception as e:
            logger.error(f"Bot spawn error: {e}")
            return {"success": False, "error": str(e)}
    
    async def auto_spawn_to_target(self, user_id: str, allowed_exchanges: List[str] = None) -> Dict:
        """Auto-spawn bots until target reached.

        Args:
            user_id: The user to spawn for.
            allowed_exchanges: Optional list of exchange IDs to restrict spawning to.
                Pass ``['luno', 'binance']`` to prevent silent expansion to Bybit /
                Bitget / KuCoin etc.  When None, derives from ``get_user_paper_exchanges``
                so spawning NEVER silently expands to exchanges outside the user's
                current run selection (preventing ghost bots on unintended exchanges).
        """
        try:
            # Resolve allowed_exchanges from canonical source when not explicitly provided.
            if allowed_exchanges is None:
                try:
                    from services.canonical import get_user_paper_exchanges
                    allowed_exchanges = await get_user_paper_exchanges(user_id)
                except Exception as _ex_err:
                    logger.warning("auto_spawn_to_target: get_user_paper_exchanges failed: %s", _ex_err)
                    allowed_exchanges = ["luno"]

            bot_count = await self.get_bot_count(user_id)
            total_bots = bot_count['total_bots']
            
            spawned = []
            
            while total_bots < self.max_bots:
                # Determine config for next bot — respects allowed_exchanges
                config = await self.determine_next_bot_config(user_id, allowed_exchanges=allowed_exchanges)
                
                if "error" in config:
                    break
                
                # Spawn the bot
                result = await self.spawn_bot(user_id, config)
                
                if result.get('success'):
                    spawned.append(result['bot'])
                    total_bots += 1
                else:
                    logger.error(f"Failed to spawn bot: {result.get('error')}")
                    break
                
                # Small delay to avoid overwhelming the system
                await asyncio.sleep(0.5)
            
            return {
                "success": True,
                "spawned_count": len(spawned),
                "total_bots": total_bots,
                "target": self.max_bots,
                "bots": spawned
            }
            
        except Exception as e:
            logger.error(f"Auto-spawn error: {e}")
            return {"success": False, "error": str(e)}
    
    async def spawn_single_bot_smart(self, user_id: str) -> Dict:
        """Spawn a single bot with AI-determined optimal config.

        Uses ``get_user_paper_exchanges`` as the canonical allowed-exchanges source
        so spawning never silently expands to exchanges outside the user's run
        selection.  If the call fails, falls back to ``["luno"]``.
        """
        try:
            # Use canonical paper-exchange resolver — NOT existing bot exchanges.
            # Using existing bot exchanges would perpetuate ghost exchanges (a ghost
            # bot already on bybit would keep generating new bybit bots).
            try:
                from services.canonical import get_user_paper_exchanges
                allowed_exchanges = await get_user_paper_exchanges(user_id)
            except Exception as _ex_err:
                logger.warning("spawn_single_bot_smart: get_user_paper_exchanges failed: %s", _ex_err)
                allowed_exchanges = ["luno"]

            config = await self.determine_next_bot_config(user_id, allowed_exchanges=allowed_exchanges)

            if "error" in config:
                return {"success": False, "error": config["error"]}

            return await self.spawn_bot(user_id, config)

        except Exception as e:
            logger.error(f"Smart spawn error: {e}")
            return {"success": False, "error": str(e)}

# Global instance
bot_spawner = BotSpawner()
