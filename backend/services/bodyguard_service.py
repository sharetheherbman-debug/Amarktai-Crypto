"""
Bodyguard Service - AI Drawdown Protection with Win-Aware Logic
Monitors bot equity and enforces risk-adjusted thresholds
Implements recovery-aware reset and cooldown with hysteresis
NEVER pauses winning/profitable bots - only intervenes on persistent losses
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, Tuple
import database as db
from realtime_events import rt_events
from websocket_manager import manager

logger = logging.getLogger(__name__)


# Risk-based drawdown thresholds
DRAWDOWN_THRESHOLDS = {
    'safe': 15.0,       # Safe mode: pause at 15% drawdown
    'balanced': 20.0,   # Balanced mode: pause at 20% drawdown
    'aggressive': 25.0  # Aggressive mode: pause at 25% drawdown
}

# Hysteresis buffer for resume (2%)
RESUME_HYSTERESIS = 2.0

# Cooldown period after pause (minutes)
PAUSE_COOLDOWN_MINUTES = 30

# Win-aware thresholds
MIN_TRADES_FOR_WIN_CHECK = 10  # Need at least 10 trades to assess profitability
PROFITABLE_WIN_RATE_THRESHOLD = 50.0  # 50%+ win rate considered profitable
PROFITABLE_NET_PNL_THRESHOLD = 0.0  # Positive net PnL
MAX_ACCEPTABLE_LOSS_WITH_GOOD_WIN_RATE = 50.0  # Max loss (in currency) acceptable with >50% win rate


class BodyguardService:
    """Enhanced bodyguard service with win-aware logic and quarantine integration"""
    
    async def is_bot_profitable(self, bot_id: str) -> Tuple[bool, str]:
        """Check if a bot is currently profitable (win-aware check)
        
        Args:
            bot_id: Bot ID to check
            
        Returns:
            Tuple of (is_profitable, reason_description)
        """
        try:
            # Get bot data
            bot = await db.bots_collection.find_one({"id": bot_id}, {"_id": 0})
            if not bot:
                return False, "Bot not found"
            
            # Check trade count
            trades_count = bot.get('trades_count', 0)
            if trades_count < MIN_TRADES_FOR_WIN_CHECK:
                return False, f"Insufficient trades ({trades_count} < {MIN_TRADES_FOR_WIN_CHECK})"
            
            # Check net PnL (most important indicator)
            total_profit = bot.get('total_profit', 0)
            if total_profit > PROFITABLE_NET_PNL_THRESHOLD:
                return True, f"Net profitable (R{total_profit:.2f})"
            
            # Check win rate
            win_rate = bot.get('win_rate', 0)
            if win_rate >= PROFITABLE_WIN_RATE_THRESHOLD:
                # Even if slightly down, good win rate means bot has potential
                if total_profit > -MAX_ACCEPTABLE_LOSS_WITH_GOOD_WIN_RATE:
                    return True, f"High win rate ({win_rate:.1f}%) with acceptable loss"
            
            # Check rolling window profitability (last 20 trades)
            recent_profit = await self._get_recent_pnl(bot_id, num_trades=20)
            if recent_profit > 0:
                return True, f"Recent profit positive (R{recent_profit:.2f})"
            
            return False, f"Not profitable (total: R{total_profit:.2f}, win rate: {win_rate:.1f}%)"
            
        except Exception as e:
            logger.error(f"Error checking bot profitability: {e}")
            return False, f"Error: {str(e)}"
    
    async def _get_recent_pnl(self, bot_id: str, num_trades: int = 20) -> float:
        """Get net PnL from recent trades
        
        Args:
            bot_id: Bot ID
            num_trades: Number of recent trades to check
            
        Returns:
            Net PnL from recent trades
        """
        try:
            trades = await db.trades_collection.find(
                {"bot_id": bot_id, "status": "closed"},
                {"_id": 0, "net_pnl": 1, "profit_loss": 1}
            ).sort("timestamp", -1).limit(num_trades).to_list(num_trades)
            
            # Use net_pnl if available, fallback to profit_loss
            total = sum(t.get("net_pnl", t.get("profit_loss", 0)) for t in trades)
            return total
            
        except Exception as e:
            logger.error(f"Error getting recent PnL: {e}")
            return 0.0
    
    async def check_bot_drawdown(self, user_id: str, bot_id: str) -> Tuple[bool, Optional[str]]:
        """Check if bot should be paused or resumed based on drawdown
        
        WIN-AWARE: Never pauses profitable bots even if temporary drawdown.
        Only pauses persistently losing bots.
        
        Args:
            user_id: User ID
            bot_id: Bot ID to check
            
        Returns:
            Tuple of (action_taken, action_description)
            action_taken: True if bot was paused or resumed
            action_description: Description of action taken, or None
        """
        try:
            # Get bot data
            bot = await db.bots_collection.find_one({"id": bot_id, "user_id": user_id}, {"_id": 0})
            if not bot:
                return False, None
            
            # Get risk mode and threshold
            risk_mode = bot.get('risk_mode', 'balanced')
            threshold = DRAWDOWN_THRESHOLDS.get(risk_mode, 20.0)
            
            # Calculate current drawdown
            equity_peak = bot.get('equity_peak', bot.get('initial_capital', 1000))
            current_capital = bot.get('current_capital', bot.get('initial_capital', 1000))
            
            # If no equity peak set, initialize it
            if not bot.get('equity_peak'):
                await db.bots_collection.update_one(
                    {"id": bot_id},
                    {"$set": {"equity_peak": current_capital}}
                )
                equity_peak = current_capital
            
            # Calculate drawdown percentage
            if equity_peak > 0:
                current_drawdown_pct = ((equity_peak - current_capital) / equity_peak) * 100
            else:
                current_drawdown_pct = 0
            
            # Update bot's current drawdown
            await db.bots_collection.update_one(
                {"id": bot_id},
                {"$set": {"current_drawdown_pct": round(current_drawdown_pct, 2)}}
            )
            
            bot_status = bot.get('status', 'active')
            paused_by_bodyguard = bot.get('paused_by_bodyguard', False)
            
            # Check if we hit new equity peak (recovery)
            if current_capital >= equity_peak:
                # New peak! Reset drawdown tracking
                await self._reset_drawdown_tracking(bot_id, current_capital)
                
                # If bot was paused by bodyguard, resume it
                if bot_status == 'paused' and paused_by_bodyguard:
                    return await self._resume_bot(user_id, bot_id, bot, "Recovered to new equity peak")
                
                return False, None
            
            # WIN-AWARE CHECK: Don't pause profitable bots
            is_profitable, profit_reason = await self.is_bot_profitable(bot_id)
            
            # Check if currently active and drawdown exceeds threshold
            if bot_status == 'active' and current_drawdown_pct >= threshold:
                # If bot is profitable, don't pause it
                if is_profitable:
                    logger.info(f"🛡️ Bodyguard: Not pausing profitable bot {bot.get('name')} despite {current_drawdown_pct:.1f}% drawdown - {profit_reason}")
                    return False, None
                
                # Bot is not profitable and exceeds drawdown - pause it
                return await self._pause_bot(user_id, bot_id, bot, current_drawdown_pct, threshold)
            
            # Check if paused by bodyguard and drawdown improved enough to resume
            if bot_status == 'paused' and paused_by_bodyguard:
                resume_threshold = threshold - RESUME_HYSTERESIS
                if current_drawdown_pct < resume_threshold:
                    return await self._resume_bot(user_id, bot_id, bot, f"Drawdown improved to {current_drawdown_pct:.1f}%")
            
            return False, None
            
        except Exception as e:
            logger.error(f"Bodyguard drawdown check error for bot {bot_id}: {e}", exc_info=True)
            return False, None
    
    async def _pause_bot(
        self, 
        user_id: str, 
        bot_id: str, 
        bot: Dict, 
        current_drawdown_pct: float, 
        threshold: float
    ) -> Tuple[bool, str]:
        """Pause bot due to drawdown threshold breach and place in quarantine
        
        Args:
            user_id: User ID
            bot_id: Bot ID
            bot: Bot data dict
            current_drawdown_pct: Current drawdown percentage
            threshold: Threshold that was breached
            
        Returns:
            Tuple of (True, description)
        """
        try:
            bot_name = bot.get('name', 'Unknown')
            risk_mode = bot.get('risk_mode', 'balanced')
            trading_mode = bot.get('trading_mode', 'paper')
            
            # Determine action based on mode
            if trading_mode == 'paper':
                # Paper mode: Quarantine the bot (don't stop scheduler)
                action = "quarantined"
                action_description = "quarantined for retraining"
            else:
                # Live mode: Pause only (be more cautious)
                action = "paused"
                action_description = "paused"
            
            # Update bot status
            await db.bots_collection.update_one(
                {"id": bot_id},
                {
                    "$set": {
                        "status": action,
                        "paused_at": datetime.now(timezone.utc).isoformat(),
                        "paused_by_bodyguard": True,
                        "paused_by_system": True,
                        "pause_reason": f"Drawdown threshold breach: {current_drawdown_pct:.1f}% >= {threshold}%",
                        "bodyguard_pause_threshold": threshold,
                        "bodyguard_pause_drawdown": round(current_drawdown_pct, 2)
                    }
                }
            )
            
            # If paper mode, quarantine the bot
            if trading_mode == 'paper':
                try:
                    from services.bot_quarantine import quarantine_service
                    quarantine_result = await quarantine_service.quarantine_bot(
                        bot_id,
                        f"Bodyguard: {current_drawdown_pct:.1f}% drawdown >= {threshold}%"
                    )
                    
                    # Create training job stub
                    training_job_id = await self._create_training_job(bot_id, user_id, {
                        "trigger": "bodyguard_quarantine",
                        "reason": f"Drawdown {current_drawdown_pct:.1f}%",
                        "quarantine_count": quarantine_result.get('quarantine_count', 1)
                    })
                    
                    logger.info(f"🔒 Quarantined bot {bot_name} - training job {training_job_id} created")
                    
                except Exception as e:
                    logger.error(f"Failed to quarantine bot: {e}")
            
            # Get updated bot data
            updated_bot = await db.bots_collection.find_one({"id": bot_id}, {"_id": 0})
            
            # Broadcast realtime update
            if action == "quarantined":
                await rt_events.bot_quarantined(user_id, bot_id, f"Drawdown {current_drawdown_pct:.1f}%")
            else:
                await rt_events.bot_paused(user_id, updated_bot)
            
            # Send additional overview update
            await manager.send_message(user_id, {
                "type": "overview_updated",
                "message": f"Bot {action_description} by bodyguard due to drawdown"
            })
            
            description = (
                f"🛡️ Bodyguard {action_description} '{bot_name}': Drawdown {current_drawdown_pct:.1f}% "
                f"reached {risk_mode} threshold ({threshold}%)"
            )
            
            logger.warning(description)
            return True, description
            
        except Exception as e:
            logger.error(f"Error pausing bot {bot_id}: {e}", exc_info=True)
            return False, None
    
    async def _create_training_job(self, bot_id: str, user_id: str, metadata: Dict) -> str:
        """Create a training job for a quarantined bot
        
        Args:
            bot_id: Bot ID
            user_id: User ID
            metadata: Additional metadata about why training was triggered
            
        Returns:
            Training job ID
        """
        try:
            import uuid
            training_job_id = str(uuid.uuid4())
            
            # Create training job stub
            training_job = {
                "id": training_job_id,
                "bot_id": bot_id,
                "user_id": user_id,
                "status": "pending",
                "trigger": metadata.get("trigger", "bodyguard"),
                "trigger_reason": metadata.get("reason", "Bodyguard quarantine"),
                "quarantine_count": metadata.get("quarantine_count", 1),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "training_started_at": None,
                "training_completed_at": None,
                "report": None
            }
            
            # Save to database
            await db.training_jobs_collection.insert_one(training_job)
            
            # Broadcast training job created event
            await rt_events.training_started(user_id, bot_id, training_job)
            
            return training_job_id
            
        except Exception as e:
            logger.error(f"Failed to create training job: {e}")
            return "error"
    
    async def _resume_bot(
        self, 
        user_id: str, 
        bot_id: str, 
        bot: Dict, 
        reason: str
    ) -> Tuple[bool, str]:
        """Resume bot after recovery from drawdown
        
        Args:
            user_id: User ID
            bot_id: Bot ID
            bot: Bot data dict
            reason: Reason for resume
            
        Returns:
            Tuple of (True, description)
        """
        try:
            bot_name = bot.get('name', 'Unknown')
            
            # Update bot status
            await db.bots_collection.update_one(
                {"id": bot_id},
                {
                    "$set": {
                        "status": "active",
                        "resumed_at": datetime.now(timezone.utc).isoformat(),
                        "paused_by_bodyguard": False,
                    },
                    "$unset": {
                        "pause_reason": "",
                        "bodyguard_pause_threshold": "",
                        "bodyguard_pause_drawdown": ""
                    }
                }
            )
            
            # Get updated bot data
            updated_bot = await db.bots_collection.find_one({"id": bot_id}, {"_id": 0})
            
            # Broadcast realtime update
            await rt_events.bot_resumed(user_id, updated_bot)
            
            # Send additional overview update
            await manager.send_message(user_id, {
                "type": "overview_updated",
                "message": "Bot resumed after recovery"
            })
            
            description = f"🛡️ Bodyguard resumed '{bot_name}': {reason}"
            
            logger.info(description)
            return True, description
            
        except Exception as e:
            logger.error(f"Error resuming bot {bot_id}: {e}", exc_info=True)
            return False, None
    
    async def _reset_drawdown_tracking(self, bot_id: str, new_peak: float):
        """Reset drawdown tracking when bot reaches new equity peak
        
        Args:
            bot_id: Bot ID
            new_peak: New equity peak value
        """
        try:
            await db.bots_collection.update_one(
                {"id": bot_id},
                {
                    "$set": {
                        "equity_peak": new_peak,
                        "current_drawdown_pct": 0,
                        "last_peak_update": datetime.now(timezone.utc).isoformat()
                    }
                }
            )
            
            logger.info(f"Bot {bot_id}: New equity peak set to {new_peak:.2f}")
            
        except Exception as e:
            logger.error(f"Error resetting drawdown tracking for bot {bot_id}: {e}")
    
    async def get_bot_drawdown_status(self, bot_id: str) -> Optional[Dict]:
        """Get detailed drawdown status for a bot
        
        Args:
            bot_id: Bot ID
            
        Returns:
            Dict with drawdown status or None
        """
        try:
            bot = await db.bots_collection.find_one({"id": bot_id}, {"_id": 0})
            if not bot:
                return None
            
            risk_mode = bot.get('risk_mode', 'balanced')
            threshold = DRAWDOWN_THRESHOLDS.get(risk_mode, 20.0)
            
            equity_peak = bot.get('equity_peak', bot.get('initial_capital', 0))
            current_capital = bot.get('current_capital', 0)
            current_drawdown_pct = bot.get('current_drawdown_pct', 0)
            
            paused_by_bodyguard = bot.get('paused_by_bodyguard', False)
            
            # Calculate resume threshold if paused
            resume_threshold = threshold - RESUME_HYSTERESIS if paused_by_bodyguard else None
            
            return {
                "bot_id": bot_id,
                "bot_name": bot.get('name'),
                "risk_mode": risk_mode,
                "threshold": threshold,
                "equity_peak": round(equity_peak, 2),
                "current_capital": round(current_capital, 2),
                "current_drawdown_pct": round(current_drawdown_pct, 2),
                "paused_by_bodyguard": paused_by_bodyguard,
                "resume_threshold": resume_threshold,
                "can_resume": paused_by_bodyguard and current_drawdown_pct < resume_threshold if resume_threshold else False,
                "status": bot.get('status'),
                "pause_reason": bot.get('pause_reason')
            }
            
        except Exception as e:
            logger.error(f"Error getting drawdown status for bot {bot_id}: {e}")
            return None
    
    async def check_all_user_bots(self, user_id: str) -> Dict:
        """Check all bots for a user and take appropriate actions
        
        Args:
            user_id: User ID
            
        Returns:
            Dict with summary of actions taken
        """
        try:
            # Get all active or paused bots
            bots_cursor = db.bots_collection.find(
                {
                    "user_id": user_id,
                    "status": {"$in": ["active", "paused"]}
                },
                {"_id": 0, "id": 1}
            )
            bots = await bots_cursor.to_list(100)
            
            paused_count = 0
            resumed_count = 0
            checked_count = 0
            
            for bot in bots:
                bot_id = bot.get('id')
                if bot_id:
                    action_taken, description = await self.check_bot_drawdown(user_id, bot_id)
                    checked_count += 1
                    
                    if action_taken and description:
                        if 'paused' in description.lower():
                            paused_count += 1
                        elif 'resumed' in description.lower():
                            resumed_count += 1
            
            return {
                "checked": checked_count,
                "paused": paused_count,
                "resumed": resumed_count,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error checking all bots for user {user_id}: {e}")
            return {
                "checked": 0,
                "paused": 0,
                "resumed": 0,
                "error": str(e)
            }


# Global singleton instance
bodyguard_service = BodyguardService()
