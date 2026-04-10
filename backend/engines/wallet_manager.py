"""
Cross-Exchange Wallet Manager
- Luno as master wallet
- Track balances across all platforms
- Paper mode: allocation ledger
- Live mode: balance checks only, NO automatic transfers
- Manual approval workflow required for fund transfers

SAFETY CONSTRAINTS:
- NO automatic withdrawals/transfers between exchanges
- Live mode wallet transfers HARD-FAIL with clear error
- Future: manual approval workflow implementation required
"""

import asyncio
from typing import Dict, List, Optional
from datetime import datetime, timezone
from decimal import Decimal
import logging

import database as db
from ccxt_service import CCXTService
from utils.env_utils import env_bool
from services.ledger_service import get_ledger_service
from routes.api_key_management import get_decrypted_key

logger = logging.getLogger(__name__)

class WalletManager:
    def __init__(self):
        self.ccxt_service = CCXTService()
        self.master_exchange = 'luno'  # Luno is the master wallet
        # Import supported exchanges from canonical source
        from config.platforms import SUPPORTED_PLATFORMS
        self.supported_exchanges = SUPPORTED_PLATFORMS  # All 8 exchanges
        
        # Track allocated funds per exchange
        self.exchange_allocations = {
            exchange: {'allocated': 0, 'available': 0}
            for exchange in SUPPORTED_PLATFORMS
        }
    
    async def get_master_balance(self, user_id: str) -> Dict:
        """Get balance from Luno (master wallet)"""
        try:
            # Get Luno API keys using decrypted key helper
            from routes.api_key_management import get_decrypted_key
            
            luno_creds = await get_decrypted_key(user_id, "luno")
            
            if not luno_creds:
                return {"error": "Luno API keys not configured. Please add Luno API keys in Settings."}
            
            # Initialize Luno exchange
            exchange = self.ccxt_service.init_exchange(
                'luno',
                luno_creds['api_key'],
                luno_creds['api_secret']
            )
            
            # Fetch balances
            balance = await asyncio.to_thread(exchange.fetch_balance)
            
            # Get ZAR and crypto balances
            zar_balance = balance.get('ZAR', {}).get('free', 0)
            btc_balance = balance.get('BTC', {}).get('free', 0)
            eth_balance = balance.get('ETH', {}).get('free', 0)
            xrp_balance = balance.get('XRP', {}).get('free', 0)
            
            # Calculate total in ZAR (simplified)
            btc_price = await self.get_btc_price_zar(exchange)
            total_zar = zar_balance + (btc_balance * btc_price) if btc_price else zar_balance
            
            return {
                "exchange": "luno",
                "zar": zar_balance,
                "btc": btc_balance,
                "eth": eth_balance,
                "xrp": xrp_balance,
                "total_zar": total_zar,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to get Luno balance: {e}")
            error_detail = str(e)
            if "authentication" in error_detail.lower() or "invalid" in error_detail.lower():
                return {"error": f"Luno authentication failed. Please check your API credentials: {error_detail}"}
            else:
                return {"error": f"Failed to fetch Luno balance: {error_detail}"}
    
    async def get_btc_price_zar(self, exchange) -> Optional[float]:
        """Get BTC/ZAR price - uses XBTZAR for Luno"""
        try:
            # Luno uses XBTZAR, not BTC/ZAR
            ticker = await asyncio.to_thread(exchange.fetch_ticker, 'XBT/ZAR')
            return ticker.get('last', 0)
        except:
            return None
    
    async def get_all_balances(self, user_id: str) -> Dict:
        """Get balances from all configured exchanges"""
        balances = {}
        
        from routes.api_key_management import get_decrypted_key
        
        # Get all API keys for user
        api_keys = await db.api_keys_collection.find(
            {"user_id": str(user_id)},
            {"_id": 0, "provider": 1, "exchange": 1}
        ).to_list(100)
        
        for key_doc in api_keys:
            provider = key_doc.get('provider') or key_doc.get('exchange')
            if not provider:
                continue
                
            exchange_name = provider.lower()
            
            # Skip non-exchange providers
            if exchange_name not in self.supported_exchanges:
                continue
            
            try:
                # Get decrypted credentials
                creds = await get_decrypted_key(user_id, provider)
                if not creds:
                    logger.warning(f"Could not decrypt keys for {exchange_name}")
                    balances[exchange_name] = {"error": "Could not decrypt API keys"}
                    continue
                
                exchange = self.ccxt_service.init_exchange(
                    exchange_name,
                    creds['api_key'],
                    creds['api_secret'],
                    passphrase=creds.get('passphrase')
                )
                
                balance = await asyncio.to_thread(exchange.fetch_balance)
                
                # Extract key currencies
                balances[exchange_name] = {
                    "zar": balance.get('ZAR', {}).get('free', 0),
                    "usdt": balance.get('USDT', {}).get('free', 0),
                    "btc": balance.get('BTC', {}).get('free', 0),
                    "eth": balance.get('ETH', {}).get('free', 0)
                }
                
            except Exception as e:
                logger.error(f"Failed to get balance for {exchange_name}: {e}")
                error_detail = str(e)
                if "authentication" in error_detail.lower() or "invalid" in error_detail.lower():
                    balances[exchange_name] = {"error": f"Authentication failed: {error_detail}"}
                else:
                    balances[exchange_name] = {"error": f"Failed to fetch balance: {error_detail}"}
        
        return balances
    
    async def calculate_allocation_per_bot(self, user_id: str, total_bots: int = 65) -> float:
        """Calculate how much capital to allocate per bot"""
        try:
            master_balance = await self.get_master_balance(user_id)
            
            if "error" in master_balance:
                return 0
            
            total_capital = master_balance.get('total_zar', 0)
            
            # Allocate 80% of total capital across bots (keep 20% reserve)
            allocatable = total_capital * 0.8
            
            # Divide by target number of bots
            per_bot = allocatable / total_bots
            
            return per_bot
            
        except Exception as e:
            logger.error(f"Allocation calculation error: {e}")
            return 0
    
    async def allocate_funds_for_bot(self, user_id: str, bot_id: str, 
                                    exchange: str, amount: float) -> Dict:
        """
        Allocate funds for a bot (paper mode) or check balance (live mode)
        
        PAPER MODE:
        - Write allocation event to allocation ledger
        - Track bot capital allocation
        - No actual funds moved
        
        LIVE MODE:
        - Read-only balance sufficiency check
        - NO fund transfers
        - Returns INSUFFICIENT_BALANCE if insufficient
        
        Args:
            user_id: User ID
            bot_id: Bot ID
            exchange: Target exchange
            amount: Amount to allocate
            
        Returns:
            dict with success/error status
        """
        try:
            is_paper_mode = env_bool('PAPER_TRADING', False)
            is_live_mode = env_bool('LIVE_TRADING', False)
            
            # Determine trading mode
            if is_paper_mode:
                # PAPER MODE: Write allocation to ledger
                ledger = get_ledger_service(await db.get_db())
                
                allocation_event = {
                    "user_id": user_id,
                    "bot_id": bot_id,
                    "event_type": "allocation",
                    "exchange": exchange,
                    "amount": amount,
                    "mode": "paper",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "reason": "bot_capital_allocation"
                }
                
                await ledger.record_event(allocation_event)
                
                # Track in-memory allocation
                self.exchange_allocations[exchange]['allocated'] += amount
                
                logger.info(f"💰 [PAPER] Allocated R{amount:.2f} to {exchange} for bot {bot_id[:8]}")
                
                return {
                    "success": True,
                    "mode": "paper",
                    "bot_id": bot_id,
                    "exchange": exchange,
                    "amount": amount,
                    "message": "Paper mode allocation recorded in ledger",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
                
            elif is_live_mode:
                # LIVE MODE: Balance check only, NO transfers
                logger.warning(f"⚠️  [LIVE] Balance check for R{amount:.2f} on {exchange} for bot {bot_id[:8]}")
                
                # Get exchange balance
                exchange_creds = await get_decrypted_key(user_id, exchange)
                
                if not exchange_creds:
                    return {
                        "success": False,
                        "error": "EXCHANGE_NOT_CONFIGURED",
                        "message": f"{exchange} API keys not configured"
                    }
                
                # Initialize exchange and check balance
                ccxt_exchange = self.ccxt_service.init_exchange(
                    exchange,
                    exchange_creds['api_key'],
                    exchange_creds['api_secret']
                )
                
                balance = await asyncio.to_thread(ccxt_exchange.fetch_balance)
                available_zar = balance.get('ZAR', {}).get('free', 0)
                
                if available_zar < amount:
                    return {
                        "success": False,
                        "error": "INSUFFICIENT_BALANCE",
                        "message": f"Insufficient balance on {exchange}. Available: R{available_zar:.2f}, Required: R{amount:.2f}",
                        "available": available_zar,
                        "required": amount,
                        "exchange": exchange
                    }
                
                # Balance sufficient - record allocation event
                ledger = get_ledger_service(await db.get_db())
                
                allocation_event = {
                    "user_id": user_id,
                    "bot_id": bot_id,
                    "event_type": "allocation_check",
                    "exchange": exchange,
                    "amount": amount,
                    "mode": "live",
                    "available_balance": available_zar,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "reason": "bot_capital_allocation_verified"
                }
                
                await ledger.record_event(allocation_event)
                
                return {
                    "success": True,
                    "mode": "live",
                    "bot_id": bot_id,
                    "exchange": exchange,
                    "amount": amount,
                    "available": available_zar,
                    "message": f"Balance verified on {exchange} (NO funds transferred)",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            
            else:
                # Neither paper nor live mode enabled
                return {
                    "success": False,
                    "error": "NO_TRADING_MODE",
                    "message": "Neither PAPER_TRADING nor LIVE_TRADING is enabled"
                }
            
        except Exception as e:
            logger.error(f"Fund allocation error: {e}", exc_info=True)
            return {"success": False, "error": "INTERNAL_ERROR", "message": str(e)}
    
    async def get_allocation_status(self, user_id: str) -> Dict:
        """Get current allocation status across all exchanges"""
        try:
            # Get bots per exchange
            bots = await db.bots_collection.find(
                {"user_id": user_id},
                {"_id": 0, "exchange": 1, "current_capital": 1}
            ).to_list(1000)
            
            allocation_summary = {}
            
            for exchange in self.supported_exchanges:
                exchange_bots = [b for b in bots if b.get('exchange', '').lower() == exchange]
                total_allocated = sum(b.get('current_capital', 0) for b in exchange_bots)
                
                allocation_summary[exchange] = {
                    "bot_count": len(exchange_bots),
                    "allocated_capital": total_allocated
                }
            
            return {
                "allocations": allocation_summary,
                "total_bots": len(bots),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            logger.error(f"Allocation status error: {e}")
            return {"error": str(e)}
    
    async def rebalance_funds(self, user_id: str, top_performers: List[str]) -> Dict:
        """Rebalance funds to top 5 performing bots"""
        try:
            # Get all bots
            bots = await db.bots_collection.find(
                {"user_id": user_id},
                {"_id": 0}
            ).to_list(1000)
            
            # Calculate total profit available for reinvestment
            total_profit = sum(b.get('total_profit', 0) for b in bots if b.get('total_profit', 0) > 0)
            
            if total_profit < 500:  # Minimum R500 to rebalance
                return {
                    "success": False,
                    "message": f"Insufficient profit for rebalancing (R{total_profit:.2f} < R500)"
                }
            
            # Distribute profit to top 5 performers
            per_bot_allocation = total_profit / 5
            
            for bot_id in top_performers[:5]:
                await db.bots_collection.update_one(
                    {"id": bot_id},
                    {"$inc": {"current_capital": per_bot_allocation}}
                )
            
            logger.info(f"💰 Rebalanced R{total_profit:.2f} to top 5 bots (R{per_bot_allocation:.2f} each)")
            
            return {
                "success": True,
                "total_profit": total_profit,
                "per_bot": per_bot_allocation,
                "recipients": top_performers[:5]
            }
            
        except Exception as e:
            logger.error(f"Rebalancing error: {e}")
            return {"success": False, "error": str(e)}
    
    async def transfer_funds_between_exchanges(self, user_id: str, from_exchange: str, 
                                              to_exchange: str, amount: float, currency: str = "ZAR") -> Dict:
        """
        Fund transfers between exchanges using production-safe state machine
        
        If ENABLE_WALLET_TRANSFERS_ENHANCED=1 or ENABLE_REALTIME_TRANSFERS=1:
            Routes through transfer_state_machine for safety
        Else:
            BLOCKED with clear error message
        
        Args:
            user_id: User ID
            from_exchange: Source exchange
            to_exchange: Destination exchange
            amount: Amount to transfer
            currency: Currency code (default ZAR)
            
        Returns:
            dict with success status or error
        """
        import config
        from utils.env_utils import env_bool
        
        # Check if enhanced transfers are enabled
        enhanced_enabled = env_bool('ENABLE_WALLET_TRANSFERS_ENHANCED', False) or \
                          env_bool('ENABLE_REALTIME_TRANSFERS', False)
        
        if enhanced_enabled:
            # Route through transfer state machine
            try:
                from services.transfer_state_machine import transfer_state_machine
                import uuid
                
                # Generate idempotency key for this transfer
                idempotency_key = f"auto_{user_id[:8]}_{from_exchange}_{to_exchange}_{uuid.uuid4().hex[:8]}"
                
                result = await transfer_state_machine.request_transfer(
                    user_id=user_id,
                    from_exchange=from_exchange,
                    to_exchange=to_exchange,
                    currency=currency,
                    amount=amount,
                    idempotency_key=idempotency_key,
                    notes="Automated transfer via wallet_manager"
                )
                
                return result
                
            except Exception as e:
                logger.error(f"Transfer via state machine failed: {e}")
                return {
                    "success": False,
                    "error": "TRANSFER_FAILED",
                    "message": f"Transfer failed: {str(e)}"
                }
        else:
            # Legacy blocked behavior
            logger.critical(
                f"🚨 BLOCKED TRANSFER ATTEMPT: User {user_id} tried to transfer "
                f"R{amount:.2f} from {from_exchange} to {to_exchange} "
                f"(Enhanced transfers disabled)"
            )
            
            return {
                "success": False,
                "error": "TRANSFER_BLOCKED",
                "message": (
                    "Automatic fund transfers between exchanges are BLOCKED for safety. "
                    "Enable ENABLE_WALLET_TRANSFERS_ENHANCED=1 to use production-safe state machine, "
                    "or transfer funds manually through exchange interfaces."
                ),
                "from_exchange": from_exchange,
                "to_exchange": to_exchange,
                "amount": amount,
                "blocked_at": datetime.now(timezone.utc).isoformat(),
                "enable_enhanced_transfers": "Set ENABLE_WALLET_TRANSFERS_ENHANCED=1 in .env"
            }

# Global instance
wallet_manager = WalletManager()
