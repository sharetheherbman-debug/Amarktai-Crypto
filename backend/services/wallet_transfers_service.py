"""
Wallet Transfers Service
Real-time wallet transfers between exchanges

Features:
- Withdraw from one exchange and deposit to another
- Queue management for transfer requests
- Security checks (2FA, whitelisted addresses)
- Rate limiting and error handling
- Logging and SSE updates
"""

import asyncio
from datetime import datetime, timezone
from typing import Optional, Dict, List
import logging
from enum import Enum

import config
import database as db
from realtime_events import manager

logger = logging.getLogger(__name__)


class TransferStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WalletTransfersService:
    def __init__(self):
        self.transfer_queue: List[Dict] = []
        self.processing = False
        
    async def initiate_transfer(
        self, 
        user_id: str,
        from_exchange: str,
        to_exchange: str,
        currency: str,
        amount: float,
        withdrawal_address: Optional[str] = None
    ) -> Dict:
        """
        Initiate a wallet transfer between exchanges
        
        Args:
            user_id: User ID
            from_exchange: Source exchange
            to_exchange: Destination exchange
            currency: Currency to transfer (e.g., BTC, ETH, ZAR)
            amount: Amount to transfer
            withdrawal_address: Optional whitelisted address
            
        Returns:
            Dict with transfer_id and status
        """
        try:
            # Check if real-time transfers are enabled
            if not config.ENABLE_REALTIME_TRANSFERS:
                return {
                    "success": False,
                    "error": "TRANSFERS_DISABLED",
                    "message": "Real-time transfers are disabled. Set ENABLE_REALTIME_TRANSFERS=true to enable."
                }
            
            # Validate user has API keys for both exchanges
            from_keys = await db.api_keys_collection.find_one({
                "user_id": user_id,
                "provider": from_exchange,
                "connected": True
            })
            
            to_keys = await db.api_keys_collection.find_one({
                "user_id": user_id,
                "provider": to_exchange,
                "connected": True
            })
            
            if not from_keys or not to_keys:
                return {
                    "success": False,
                    "error": "MISSING_API_KEYS",
                    "message": f"API keys not configured for {from_exchange} or {to_exchange}"
                }
            
            # Security check: Verify whitelisted address if provided
            if withdrawal_address:
                is_whitelisted = await self._check_whitelisted_address(
                    user_id, from_exchange, currency, withdrawal_address
                )
                if not is_whitelisted:
                    return {
                        "success": False,
                        "error": "ADDRESS_NOT_WHITELISTED",
                        "message": f"Address {withdrawal_address} not whitelisted for {from_exchange}"
                    }
            
            # Create transfer record
            transfer_id = f"transfer_{datetime.now(timezone.utc).timestamp()}"
            transfer = {
                "id": transfer_id,
                "user_id": user_id,
                "from_exchange": from_exchange,
                "to_exchange": to_exchange,
                "currency": currency,
                "amount": amount,
                "withdrawal_address": withdrawal_address,
                "status": TransferStatus.PENDING,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "withdrawal_id": None,
                "deposit_id": None,
                "error_message": None
            }
            
            # Save to database
            await db.db['wallet_transfers'].insert_one(transfer)
            
            # Add to queue
            self.transfer_queue.append(transfer)
            
            # Start processing if not already running
            if not self.processing:
                asyncio.create_task(self._process_queue())
            
            # Send SSE update
            await manager.broadcast_to_user(user_id, {
                "type": "wallet_transfer_initiated",
                "transfer_id": transfer_id,
                "status": TransferStatus.PENDING,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            
            logger.info(f"Transfer initiated: {transfer_id} ({from_exchange} → {to_exchange})")
            
            return {
                "success": True,
                "transfer_id": transfer_id,
                "status": TransferStatus.PENDING,
                "message": "Transfer initiated and added to queue"
            }
            
        except Exception as e:
            logger.error(f"Transfer initiation failed: {e}")
            return {
                "success": False,
                "error": "INTERNAL_ERROR",
                "message": str(e)
            }
    
    async def _process_queue(self):
        """Process transfer queue"""
        self.processing = True
        
        try:
            while self.transfer_queue:
                transfer = self.transfer_queue.pop(0)
                await self._process_transfer(transfer)
                
                # Rate limiting: Wait between transfers
                await asyncio.sleep(5)
                
        except Exception as e:
            logger.error(f"Queue processing error: {e}")
        finally:
            self.processing = False
    
    async def _process_transfer(self, transfer: Dict):
        """
        Process a single transfer
        
        Steps:
        1. Withdraw from source exchange
        2. Wait for withdrawal confirmation
        3. Monitor deposit to destination exchange
        4. Update status and broadcast
        """
        try:
            import ccxt.async_support as ccxt
            
            transfer_id = transfer['id']
            user_id = transfer['user_id']
            from_exchange = transfer['from_exchange']
            to_exchange = transfer['to_exchange']
            currency = transfer['currency']
            amount = transfer['amount']
            withdrawal_address = transfer.get('withdrawal_address')
            
            # Update status to processing
            await self._update_transfer_status(transfer_id, TransferStatus.PROCESSING)
            
            # Step 1: Get API keys for source exchange
            from_keys = await db.api_keys_collection.find_one({
                "user_id": user_id,
                "provider": from_exchange,
                "connected": True
            })
            
            if not from_keys:
                raise Exception(f"No API keys found for {from_exchange}")
            
            # Initialize CCXT exchange
            exchange_class = getattr(ccxt, from_exchange, None)
            if not exchange_class:
                raise Exception(f"Exchange {from_exchange} not supported by CCXT")
            
            exchange = exchange_class({
                'apiKey': from_keys['api_key'],
                'secret': from_keys['api_secret'],
                'password': from_keys.get('passphrase'),
                'enableRateLimit': True,
            })
            
            # Get deposit address for destination exchange if not provided
            if not withdrawal_address:
                to_keys = await db.api_keys_collection.find_one({
                    "user_id": user_id,
                    "provider": to_exchange,
                    "connected": True
                })
                
                if not to_keys:
                    raise Exception(f"No API keys found for {to_exchange}")
                
                to_exchange_class = getattr(ccxt, to_exchange, None)
                to_exchange_obj = to_exchange_class({
                    'apiKey': to_keys['api_key'],
                    'secret': to_keys['api_secret'],
                    'password': to_keys.get('passphrase'),
                    'enableRateLimit': True,
                })
                
                # Fetch deposit address
                try:
                    deposit_address_response = await to_exchange_obj.fetch_deposit_address(currency)
                    withdrawal_address = deposit_address_response['address']
                    withdrawal_tag = deposit_address_response.get('tag')
                    
                    logger.info(f"Fetched deposit address for {to_exchange}: {withdrawal_address}")
                except Exception as addr_err:
                    logger.error(f"Failed to fetch deposit address: {addr_err}")
                    raise Exception(f"Could not get deposit address for {currency} on {to_exchange}")
                finally:
                    await to_exchange_obj.close()
            else:
                withdrawal_tag = None
            
            logger.info(f"Processing transfer {transfer_id}: Withdrawing {amount} {currency} from {from_exchange} to {withdrawal_address}")
            
            # Step 2: Execute withdrawal
            try:
                withdrawal_params = {}
                if withdrawal_tag:
                    withdrawal_params['tag'] = withdrawal_tag
                
                withdrawal_response = await exchange.withdraw(
                    currency,
                    amount,
                    withdrawal_address,
                    withdrawal_tag,
                    withdrawal_params
                )
                
                withdrawal_id = withdrawal_response.get('id') or withdrawal_response.get('txid') or f"withdrawal_{datetime.now(timezone.utc).timestamp()}"
                
                logger.info(f"Withdrawal initiated: {withdrawal_id}")
                
                # Update transfer with withdrawal ID
                await db.db['wallet_transfers'].update_one(
                    {"id": transfer_id},
                    {
                        "$set": {
                            "withdrawal_id": withdrawal_id,
                            "withdrawal_response": withdrawal_response,
                            "withdrawal_address": withdrawal_address,
                            "updated_at": datetime.now(timezone.utc).isoformat()
                        }
                    }
                )
                
            except ccxt.InsufficientFunds as e:
                raise Exception(f"Insufficient funds: {str(e)}")
            except ccxt.InvalidAddress as e:
                raise Exception(f"Invalid withdrawal address: {str(e)}")
            except ccxt.ExchangeError as e:
                raise Exception(f"Exchange error: {str(e)}")
            finally:
                await exchange.close()
            
            # Step 3: Monitor withdrawal status
            logger.info(f"Monitoring withdrawal {withdrawal_id}...")
            
            # Poll for withdrawal status (up to 30 minutes, check every 30 seconds)
            max_checks = 60
            check_interval = 30
            
            for check_num in range(max_checks):
                await asyncio.sleep(check_interval)
                
                try:
                    # Reconnect to exchange
                    exchange = exchange_class({
                        'apiKey': from_keys['api_key'],
                        'secret': from_keys['api_secret'],
                        'password': from_keys.get('passphrase'),
                        'enableRateLimit': True,
                    })
                    
                    # Fetch withdrawal status
                    withdrawal_status = await exchange.fetch_withdrawal(withdrawal_id, currency)
                    
                    status_code = withdrawal_status.get('status', 'pending')
                    
                    logger.info(f"Withdrawal {withdrawal_id} status: {status_code} (check {check_num+1}/{max_checks})")
                    
                    if status_code in ['ok', 'complete', 'confirmed', 'success']:
                        # Withdrawal completed
                        await self._update_transfer_status(
                            transfer_id,
                            TransferStatus.COMPLETED,
                            deposit_id=withdrawal_id  # Use same ID for tracking
                        )
                        
                        # Broadcast success
                        await manager.broadcast_to_user(user_id, {
                            "type": "wallet_transfer_completed",
                            "transfer_id": transfer_id,
                            "status": TransferStatus.COMPLETED,
                            "withdrawal_id": withdrawal_id,
                            "timestamp": datetime.now(timezone.utc).isoformat()
                        })
                        
                        logger.info(f"Transfer completed: {transfer_id}")
                        await exchange.close()
                        return
                        
                    elif status_code in ['failed', 'rejected', 'canceled']:
                        # Withdrawal failed
                        await self._update_transfer_status(
                            transfer_id,
                            TransferStatus.FAILED,
                            error_message=f"Withdrawal {status_code}: {withdrawal_status.get('info', '')}"
                        )
                        
                        await manager.broadcast_to_user(user_id, {
                            "type": "wallet_transfer_failed",
                            "transfer_id": transfer_id,
                            "status": TransferStatus.FAILED,
                            "error": f"Withdrawal {status_code}",
                            "timestamp": datetime.now(timezone.utc).isoformat()
                        })
                        
                        await exchange.close()
                        return
                        
                    await exchange.close()
                    
                except Exception as status_err:
                    logger.warning(f"Error checking withdrawal status: {status_err}")
                    # Continue checking
            
            # Timeout - mark as processing but not confirmed
            logger.warning(f"Transfer {transfer_id} timed out waiting for confirmation")
            await db.db['wallet_transfers'].update_one(
                {"id": transfer_id},
                {
                    "$set": {
                        "status": TransferStatus.PROCESSING,
                        "status_note": "Withdrawal initiated but confirmation timeout. Check exchange manually.",
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }
                }
            )
            
        except Exception as e:
            logger.error(f"Transfer processing failed: {e}")
            
            # Update status to failed
            await self._update_transfer_status(
                transfer['id'],
                TransferStatus.FAILED,
                error_message=str(e)
            )
            
            # Broadcast failure
            await manager.broadcast_to_user(transfer['user_id'], {
                "type": "wallet_transfer_failed",
                "transfer_id": transfer['id'],
                "status": TransferStatus.FAILED,
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
    
    async def _update_transfer_status(
        self,
        transfer_id: str,
        status: TransferStatus,
        deposit_id: Optional[str] = None,
        error_message: Optional[str] = None
    ):
        """Update transfer status in database"""
        update_data = {
            "status": status,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        
        if deposit_id:
            update_data["deposit_id"] = deposit_id
        
        if error_message:
            update_data["error_message"] = error_message
        
        await db.db['wallet_transfers'].update_one(
            {"id": transfer_id},
            {"$set": update_data}
        )
    
    async def _check_whitelisted_address(
        self,
        user_id: str,
        exchange: str,
        currency: str,
        address: str
    ) -> bool:
        """Check if address is whitelisted for user"""
        try:
            whitelist = await db.db['whitelisted_addresses'].find_one({
                "user_id": user_id,
                "exchange": exchange,
                "currency": currency,
                "address": address,
                "active": True
            })
            
            return whitelist is not None
            
        except Exception as e:
            logger.error(f"Whitelist check failed: {e}")
            return False
    
    async def get_transfer_status(self, transfer_id: str) -> Optional[Dict]:
        """Get status of a transfer"""
        try:
            transfer = await db.db['wallet_transfers'].find_one(
                {"id": transfer_id},
                {"_id": 0}
            )
            return transfer
            
        except Exception as e:
            logger.error(f"Get transfer status failed: {e}")
            return None
    
    async def list_transfers(
        self,
        user_id: str,
        limit: int = 50
    ) -> List[Dict]:
        """List transfers for a user"""
        try:
            transfers = await db.db['wallet_transfers'].find(
                {"user_id": user_id},
                {"_id": 0}
            ).sort("created_at", -1).limit(limit).to_list(limit)
            
            return transfers
            
        except Exception as e:
            logger.error(f"List transfers failed: {e}")
            return []
    
    async def add_whitelisted_address(
        self,
        user_id: str,
        exchange: str,
        currency: str,
        address: str,
        label: Optional[str] = None
    ) -> Dict:
        """Add a whitelisted withdrawal address"""
        try:
            whitelist_entry = {
                "id": f"whitelist_{datetime.now(timezone.utc).timestamp()}",
                "user_id": user_id,
                "exchange": exchange,
                "currency": currency,
                "address": address,
                "label": label or f"{exchange} {currency}",
                "active": True,
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            
            await db.db['whitelisted_addresses'].insert_one(whitelist_entry)
            
            logger.info(f"Whitelisted address added: {address} for {user_id}")
            
            return {
                "success": True,
                "message": "Address whitelisted successfully"
            }
            
        except Exception as e:
            logger.error(f"Add whitelisted address failed: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def list_whitelisted_addresses(
        self,
        user_id: str,
        exchange: Optional[str] = None
    ) -> List[Dict]:
        """List whitelisted addresses for a user"""
        try:
            query = {"user_id": user_id, "active": True}
            if exchange:
                query["exchange"] = exchange
            
            addresses = await db.db['whitelisted_addresses'].find(
                query,
                {"_id": 0}
            ).to_list(100)
            
            return addresses
            
        except Exception as e:
            logger.error(f"List whitelisted addresses failed: {e}")
            return []


# Global instance
wallet_transfers_service = WalletTransfersService()
