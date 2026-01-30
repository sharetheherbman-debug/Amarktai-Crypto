"""
DeFi & DEX Trading
Decentralized exchange trading via WalletConnect and Web3

Features:
- WalletConnect integration
- DEX trading (Uniswap, PancakeSwap, etc.)
- Token swaps
- Liquidity provision
- Yield farming
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, Dict, List
import logging
from datetime import datetime, timezone

from auth import get_current_user
import database as db
from services.web3_service import web3_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/defi", tags=["DeFi Trading"])


class WalletConnectSession(BaseModel):
    wallet_address: str
    chain_id: int
    session_id: Optional[str] = None
    signature: Optional[str] = None  # For verification
    message: Optional[str] = None  # Message that was signed


class TokenSwap(BaseModel):
    from_token: str
    to_token: str
    amount: float
    slippage: float = 0.01  # 1% default slippage
    dex: str = "uniswap"  # uniswap, pancakeswap, quickswap
    chain: str = "ethereum"  # ethereum, bsc, polygon


@router.post("/walletconnect/connect")
async def walletconnect_connect(
    session: WalletConnectSession,
    user_id: str = Depends(get_current_user)
):
    """
    Connect wallet via WalletConnect
    
    Establishes connection to user's Web3 wallet with signature verification
    """
    try:
        logger.info(f"WalletConnect: Connecting wallet {session.wallet_address} for user {user_id}")
        
        # Verify wallet ownership via signature
        verified = False
        if session.signature and session.message:
            # Map chain_id to chain name
            chain_map = {1: 'ethereum', 56: 'bsc', 137: 'polygon'}
            chain = chain_map.get(session.chain_id, 'ethereum')
            
            verified = web3_service.verify_wallet_signature(
                session.wallet_address,
                session.message,
                session.signature,
                chain
            )
            
            if not verified:
                raise HTTPException(
                    status_code=401,
                    detail="Signature verification failed - wallet ownership not proven"
                )
        else:
            logger.warning(f"WalletConnect session created without signature verification")
        
        # Check if Web3 is connected
        chain_map = {1: 'ethereum', 56: 'bsc', 137: 'polygon'}
        chain = chain_map.get(session.chain_id, 'ethereum')
        is_connected = web3_service.is_connected(chain)
        
        session_record = {
            "id": f"wc_{datetime.now(timezone.utc).timestamp()}",
            "user_id": user_id,
            "wallet_address": session.wallet_address,
            "chain_id": session.chain_id,
            "chain": chain,
            "connected": is_connected,
            "verified": verified,
            "connected_at": datetime.now(timezone.utc).isoformat()
        }
        
        await db.db['walletconnect_sessions'].insert_one(session_record)
        
        return {
            "success": True,
            "message": "Wallet connected successfully" if verified else "Wallet connected (unverified)",
            "session_id": session_record['id'],
            "wallet_address": session.wallet_address,
            "verified": verified,
            "web3_connected": is_connected
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"WalletConnect connection error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/walletconnect/status")
async def walletconnect_status(user_id: str = Depends(get_current_user)):
    """
    Get WalletConnect connection status
    """
    try:
        session = await db.db['walletconnect_sessions'].find_one(
            {"user_id": user_id, "connected": True},
            {"_id": 0}
        )
        
        if not session:
            return {
                "connected": False,
                "message": "No active WalletConnect session"
            }
        
        return {
            "connected": True,
            "session": session
        }
        
    except Exception as e:
        logger.error(f"WalletConnect status error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/swap")
async def token_swap(
    swap: TokenSwap,
    user_id: str = Depends(get_current_user)
):
    """
    Execute token swap on DEX
    
    Swaps tokens using specified DEX (Uniswap, PancakeSwap, QuickSwap)
    """
    try:
        logger.info(f"Token swap: {swap.from_token} → {swap.to_token} on {swap.dex}")
        
        # Verify user has a wallet connected
        wallet_session = await db.db['walletconnect_sessions'].find_one(
            {"user_id": user_id, "connected": True, "chain": swap.chain},
            {"_id": 0},
            sort=[("connected_at", -1)]
        )
        
        if not wallet_session:
            raise HTTPException(
                status_code=400,
                detail=f"No wallet connected for {swap.chain}. Please connect wallet first."
            )
        
        # Get swap quote
        quote = web3_service.get_swap_quote(
            swap.from_token,
            swap.to_token,
            swap.amount,
            swap.dex,
            swap.chain
        )
        
        if not quote:
            raise HTTPException(
                status_code=500,
                detail="Failed to get swap quote. Check token addresses and DEX availability."
            )
        
        # Check slippage tolerance
        if quote.get('price_impact', 0) > swap.slippage * 100:
            raise HTTPException(
                status_code=400,
                detail=f"Price impact {quote['price_impact']:.2f}% exceeds slippage tolerance {swap.slippage*100}%"
            )
        
        # Check if token approval is needed
        needs_approval = not web3_service.check_token_approval(
            swap.from_token,
            wallet_session['wallet_address'],
            web3_service._get_router_address(swap.dex, swap.chain),
            swap.amount,
            swap.chain
        )
        
        # Estimate gas
        gas_estimate = web3_service.estimate_gas_for_swap(
            swap.from_token,
            swap.to_token,
            swap.amount,
            wallet_session['wallet_address'],
            swap.dex,
            swap.chain
        )
        
        gas_price = web3_service.get_current_gas_price(swap.chain)
        
        # Store swap record
        swap_record = {
            "id": f"swap_{datetime.now(timezone.utc).timestamp()}",
            "user_id": user_id,
            "wallet_address": wallet_session['wallet_address'],
            "from_token": swap.from_token,
            "to_token": swap.to_token,
            "amount_in": swap.amount,
            "amount_out_expected": quote['amount_out'],
            "slippage": swap.slippage,
            "dex": swap.dex,
            "chain": swap.chain,
            "status": "quote_ready",
            "needs_approval": needs_approval,
            "quote": quote,
            "gas_estimate": gas_estimate,
            "gas_price": str(gas_price) if gas_price else None,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        
        await db.db['dex_swaps'].insert_one(swap_record)
        
        return {
            "success": True,
            "message": "Swap quote ready. Approve and execute via wallet.",
            "swap_id": swap_record['id'],
            "quote": {
                "amount_in": swap.amount,
                "amount_out": quote['amount_out'],
                "price_impact": quote['price_impact'],
                "dex": swap.dex,
                "chain": swap.chain
            },
            "needs_approval": needs_approval,
            "gas_estimate": gas_estimate,
            "gas_price_gwei": float(gas_price) / 1e9 if gas_price else None,
            "instructions": "This is a quote. To execute, use your connected wallet to approve and sign the transaction."
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Token swap error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/swap/{swap_id}")
async def get_swap_status(
    swap_id: str,
    user_id: str = Depends(get_current_user)
):
    """
    Get status of a token swap
    """
    try:
        swap = await db.db['dex_swaps'].find_one(
            {"id": swap_id, "user_id": user_id},
            {"_id": 0}
        )
        
        if not swap:
            raise HTTPException(status_code=404, detail="Swap not found")
        
        return {
            "success": True,
            "swap": swap
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get swap status error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/liquidity/pools")
async def get_liquidity_pools(
    chain: str = "ethereum",
    user_id: str = Depends(get_current_user)
):
    """
    Get available liquidity pools
    
    Returns list of liquidity pools for yield farming
    """
    try:
        # Get user's wallet if connected
        wallet_session = await db.db['walletconnect_sessions'].find_one(
            {"user_id": user_id, "connected": True, "chain": chain},
            {"_id": 0},
            sort=[("connected_at", -1)]
        )
        
        # Check Web3 connection
        is_connected = web3_service.is_connected(chain)
        
        if not is_connected:
            return {
                "success": False,
                "pools": [],
                "message": f"Web3 provider not connected for {chain}. Configure RPC URL in settings."
            }
        
        # For now, return popular pools as examples
        # In production, would fetch from DEX subgraphs or APIs
        popular_pools = []
        
        if chain == "ethereum":
            popular_pools = [
                {
                    "pool_address": "0x0d4a11d5EEaaC28EC3F61d100daF4d40471f1852",
                    "name": "USDT/ETH",
                    "dex": "uniswap",
                    "token0": "USDT",
                    "token1": "ETH",
                    "liquidity_usd": 150000000,  # Example
                    "apy": 12.5,  # Example
                    "volume_24h": 50000000
                },
                {
                    "pool_address": "0xB4e16d0168e52d35CaCD2c6185b44281Ec28C9Dc",
                    "name": "USDC/ETH",
                    "dex": "uniswap",
                    "token0": "USDC",
                    "token1": "ETH",
                    "liquidity_usd": 200000000,
                    "apy": 15.3,
                    "volume_24h": 75000000
                }
            ]
        elif chain == "bsc":
            popular_pools = [
                {
                    "pool_address": "0x58F876857a02D6762E0101bb5C46A8c1ED44Dc16",
                    "name": "BUSD/BNB",
                    "dex": "pancakeswap",
                    "token0": "BUSD",
                    "token1": "BNB",
                    "liquidity_usd": 100000000,
                    "apy": 18.2,
                    "volume_24h": 30000000
                }
            ]
        elif chain == "polygon":
            popular_pools = [
                {
                    "pool_address": "0x6e7a5FAFcec6BB1e78bAE2A1F0B612012BF14827",
                    "name": "USDC/MATIC",
                    "dex": "quickswap",
                    "token0": "USDC",
                    "token1": "MATIC",
                    "liquidity_usd": 50000000,
                    "apy": 22.7,
                    "volume_24h": 15000000
                }
            ]
        
        # Check user's positions if wallet connected
        user_positions = []
        if wallet_session:
            # In production, would fetch user's LP positions from blockchain
            user_positions = []
        
        return {
            "success": True,
            "chain": chain,
            "pools": popular_pools,
            "user_positions": user_positions,
            "wallet_connected": bool(wallet_session),
            "message": "Showing popular pools. Real-time data requires DEX API integration."
        }
        
    except Exception as e:
        logger.error(f"Get liquidity pools error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
