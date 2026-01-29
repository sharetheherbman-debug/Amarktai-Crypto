"""
AI Chat Enhancement - Clear on refresh, daily summary on login

Improves chat UX with:
- Clear UI on refresh/logout
- Daily summary since last login
- Server-side conversation storage
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import Optional, List
from pydantic import BaseModel
import logging
from datetime import datetime, timezone, timedelta

from auth import get_current_user
import database as db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/chat", tags=["AI Chat Enhanced"])


class ChatClearRequest(BaseModel):
    clear_server_side: bool = False


@router.post("/clear")
async def clear_chat_history(
    request: ChatClearRequest,
    user_id: str = Depends(get_current_user)
):
    """
    Clear chat history
    
    By default, only clears UI state (returns empty).
    If clear_server_side=True, also clears server-side storage.
    """
    try:
        if request.clear_server_side:
            # Clear server-side messages
            result = await db.chat_messages_collection.delete_many({
                "user_id": user_id
            })
            logger.info(f"Cleared {result.deleted_count} chat messages for user {user_id}")
        
        return {
            "success": True,
            "messages": [],
            "message": "Chat cleared" if request.clear_server_side else "UI cleared"
        }
        
    except Exception as e:
        logger.error(f"Clear chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/daily-summary")
async def get_daily_summary(user_id: str = Depends(get_current_user)):
    """
    Get daily summary since last login
    
    Includes:
    - Trades executed
    - Profit/fees
    - Quarantines
    - Alerts
    - Wallet events
    """
    try:
        # Get user's last login time
        user = await db.users_collection.find_one(
            {"id": user_id},
            {"_id": 0, "last_login_at": 1}
        )
        
        # Default to last 24 hours if no last_login_at
        last_login = user.get("last_login_at") if user else None
        if not last_login:
            last_login = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        
        # Get trades since last login
        trades_cursor = db.trades_collection.find({
            "user_id": user_id,
            "timestamp": {"$gte": last_login}
        })
        trades = await trades_cursor.to_list(10000)
        
        # Calculate totals
        total_trades = len(trades)
        total_gross = sum(t.get("gross_pnl", 0) for t in trades)
        total_fees = sum(t.get("fee_amount", 0) for t in trades)
        total_net = sum(t.get("net_pnl", 0) for t in trades)
        
        # Get quarantines since last login
        quarantines_count = await db.bots_collection.count_documents({
            "user_id": user_id,
            "status": "quarantined",
            "quarantined_at": {"$gte": last_login}
        })
        
        # Get alerts since last login
        alerts_cursor = db.alerts_collection.find({
            "user_id": user_id,
            "timestamp": {"$gte": last_login},
            "dismissed": False
        })
        alerts = await alerts_cursor.to_list(100)
        
        # Get wallet events since last login
        wallet_events_cursor = db.wallet_transfers_collection.find({
            "user_id": user_id,
            "timestamp": {"$gte": last_login}
        })
        wallet_events = await wallet_events_cursor.to_list(100)
        
        # Build summary message
        summary_parts = []
        summary_parts.append(f"📊 **Activity Since Your Last Login**")
        summary_parts.append(f"")
        
        if total_trades > 0:
            summary_parts.append(f"✅ **{total_trades} trades** executed")
            summary_parts.append(f"   - Gross Profit: R{total_gross:.2f}")
            summary_parts.append(f"   - Fees Paid: R{total_fees:.2f}")
            summary_parts.append(f"   - Net Profit: R{total_net:.2f}")
        else:
            summary_parts.append(f"📉 No trades executed since last login")
        
        if quarantines_count > 0:
            summary_parts.append(f"")
            summary_parts.append(f"⚠️ **{quarantines_count} bot(s)** quarantined")
        
        if len(alerts) > 0:
            summary_parts.append(f"")
            summary_parts.append(f"🔔 **{len(alerts)} new alert(s)**")
        
        if len(wallet_events) > 0:
            summary_parts.append(f"")
            summary_parts.append(f"💰 **{len(wallet_events)} wallet transaction(s)**")
        
        summary_text = "\n".join(summary_parts)
        
        return {
            "user_id": user_id,
            "since": last_login,
            "summary": summary_text,
            "details": {
                "trades_count": total_trades,
                "gross_profit": round(total_gross, 2),
                "fees": round(total_fees, 2),
                "net_profit": round(total_net, 2),
                "quarantines_count": quarantines_count,
                "alerts_count": len(alerts),
                "wallet_events_count": len(wallet_events)
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Get daily summary error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/welcome")
async def get_welcome_message(user_id: str = Depends(get_current_user)):
    """
    Get welcome message for chat initialization
    
    Returns welcome + daily summary combined.
    """
    try:
        # Get user details
        user = await db.users_collection.find_one(
            {"id": user_id},
            {"_id": 0, "first_name": 1}
        )
        
        username = user.get("first_name", "User") if user else "User"
        
        # Get daily summary
        summary_response = await get_daily_summary(user_id)
        
        # Combine welcome + summary
        welcome_text = f"👋 **Welcome back, {username}!**\n\n{summary_response['summary']}"
        
        return {
            "user_id": user_id,
            "message": welcome_text,
            "details": summary_response["details"],
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Get welcome message error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/session/end")
async def end_chat_session(user_id: str = Depends(get_current_user)):
    """
    End chat session (called on logout/refresh)
    
    Updates last_login_at for next daily summary calculation.
    """
    try:
        # Update last_login_at to now
        await db.users_collection.update_one(
            {"id": user_id},
            {
                "$set": {
                    "last_login_at": datetime.now(timezone.utc).isoformat(),
                    "last_chat_session_end": datetime.now(timezone.utc).isoformat()
                }
            }
        )
        
        logger.info(f"Chat session ended for user {user_id}")
        
        return {
            "success": True,
            "message": "Session ended"
        }
        
    except Exception as e:
        logger.error(f"End chat session error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
