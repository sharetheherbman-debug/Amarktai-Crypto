"""
Email Alert Triggers
Integrates email notifications with bodyguard, trade limiter, and other events
"""
import logging
from typing import Dict, Optional
from datetime import datetime, timezone
import asyncio

from services.email_service import EmailService
import database as db

logger = logging.getLogger(__name__)

# Initialize email service
email_service = EmailService()


class EmailAlerts:
    """Manages email notifications for various trading events"""
    
    async def send_trade_limit_warning(self, user_id: str, bot_id: str, current_trades: int, limit: int):
        """Send email when bot reaches 80% of trade limit
        
        Args:
            user_id: User ID
            bot_id: Bot ID
            current_trades: Current trade count
            limit: Trade limit
        """
        try:
            # Get user email
            user = await db.users.find_one({"id": user_id}, {"_id": 0})
            if not user:
                logger.warning(f"User not found: {user_id}")
                return
            
            if not user.get('email'):
                logger.warning(f"No email configured for user {user_id}")
                return
            
            # Get bot info
            bot = await db.bots_collection.find_one({"id": bot_id}, {"_id": 0})
            if not bot:
                return
            
            bot_name = bot.get('name', 'Unknown')
            percentage = int((current_trades / limit) * 100)
            
            subject = f"⚠️ Trade Limit Warning: {bot_name}"
            
            body = f"""
Hello,

Your bot "{bot_name}" has reached {percentage}% of its daily trade limit.

Current Status:
- Trades today: {current_trades}
- Daily limit: {limit}
- Remaining: {limit - current_trades}

The bot will be paused automatically when it reaches 100% of the limit.

Best regards,
Amarktai Crypto (part of Amarktai Network)
            """.strip()
            
            html_body = f"""
<html>
<body style="font-family: Arial, sans-serif; line-height: 1.6;">
    <h2 style="color: #ff9800;">⚠️ Trade Limit Warning</h2>
    
    <p>Hello,</p>
    
    <p>Your bot <strong>{bot_name}</strong> has reached <strong>{percentage}%</strong> of its daily trade limit.</p>
    
    <h3>Current Status:</h3>
    <ul>
        <li>Trades today: <strong>{current_trades}</strong></li>
        <li>Daily limit: <strong>{limit}</strong></li>
        <li>Remaining: <strong>{limit - current_trades}</strong></li>
    </ul>
    
    <p style="color: #666;">The bot will be paused automatically when it reaches 100% of the limit.</p>
    
    <hr style="border: 1px solid #eee;">
    <p style="color: #888; font-size: 12px;">
        Best regards,<br>
        <strong>Amarktai Crypto (part of Amarktai Network)</strong>
    </p>
</body>
</html>
            """.strip()
            
            await email_service.send_email(
                to_email=user['email'],
                subject=subject,
                body=body,
                html_body=html_body
            )
            
            logger.info(f"Sent trade limit warning email to {user['email']}")
            
        except Exception as e:
            logger.error(f"Failed to send trade limit warning email: {e}")
    
    async def send_trade_limit_reached(self, user_id: str, bot_id: str, trades: int, limit: int):
        """Send email when bot reaches trade limit and is paused
        
        Args:
            user_id: User ID
            bot_id: Bot ID
            trades: Trade count
            limit: Trade limit
        """
        try:
            user = await db.users.find_one({"id": user_id}, {"_id": 0})
            if not user or not user.get('email'):
                return
            
            bot = await db.bots_collection.find_one({"id": bot_id}, {"_id": 0})
            if not bot:
                return
            
            bot_name = bot.get('name', 'Unknown')
            
            subject = f"🛑 Bot Paused: {bot_name} - Trade Limit Reached"
            
            body = f"""
Hello,

Your bot "{bot_name}" has reached its daily trade limit and has been PAUSED.

Details:
- Trades executed today: {trades}
- Daily limit: {limit}
- Status: PAUSED

The bot will automatically resume trading tomorrow when the daily counter resets.

Best regards,
Amarktai Crypto (part of Amarktai Network)
            """.strip()
            
            html_body = f"""
<html>
<body style="font-family: Arial, sans-serif; line-height: 1.6;">
    <h2 style="color: #f44336;">🛑 Bot Paused - Trade Limit Reached</h2>
    
    <p>Hello,</p>
    
    <p>Your bot <strong>{bot_name}</strong> has reached its daily trade limit and has been <strong style="color: #f44336;">PAUSED</strong>.</p>
    
    <h3>Details:</h3>
    <ul>
        <li>Trades executed today: <strong>{trades}</strong></li>
        <li>Daily limit: <strong>{limit}</strong></li>
        <li>Status: <strong style="color: #f44336;">PAUSED</strong></li>
    </ul>
    
    <p style="color: #666;">The bot will automatically resume trading tomorrow when the daily counter resets.</p>
    
    <hr style="border: 1px solid #eee;">
    <p style="color: #888; font-size: 12px;">
        Best regards,<br>
        <strong>Amarktai Crypto (part of Amarktai Network)</strong>
    </p>
</body>
</html>
            """.strip()
            
            await email_service.send_email(
                to_email=user['email'],
                subject=subject,
                body=body,
                html_body=html_body
            )
            
            logger.info(f"Sent trade limit reached email to {user['email']}")
            
        except Exception as e:
            logger.error(f"Failed to send trade limit reached email: {e}")
    
    async def send_bodyguard_alert(self, user_id: str, bot_id: str, drawdown_pct: float, threshold: float):
        """Send email when bodyguard pauses a bot due to drawdown
        
        Args:
            user_id: User ID
            bot_id: Bot ID
            drawdown_pct: Current drawdown percentage
            threshold: Drawdown threshold
        """
        try:
            user = await db.users.find_one({"id": user_id}, {"_id": 0})
            if not user or not user.get('email'):
                return
            
            bot = await db.bots_collection.find_one({"id": bot_id}, {"_id": 0})
            if not bot:
                return
            
            bot_name = bot.get('name', 'Unknown')
            risk_mode = bot.get('risk_mode', 'balanced')
            
            subject = f"🛡️ Bodyguard Alert: {bot_name} Paused Due to Drawdown"
            
            body = f"""
Hello,

The Bodyguard has paused your bot "{bot_name}" due to excessive drawdown.

Details:
- Bot: {bot_name}
- Risk Mode: {risk_mode}
- Current Drawdown: {drawdown_pct:.1f}%
- Threshold: {threshold}%
- Status: PAUSED

The bot will resume automatically when drawdown improves to {threshold - 2}% or better.

This is a protective measure to prevent further losses.

Best regards,
Amarktai Crypto (part of Amarktai Network)
            """.strip()
            
            html_body = f"""
<html>
<body style="font-family: Arial, sans-serif; line-height: 1.6;">
    <h2 style="color: #ff5722;">🛡️ Bodyguard Alert - Bot Paused</h2>
    
    <p>Hello,</p>
    
    <p>The <strong>Bodyguard</strong> has paused your bot <strong>{bot_name}</strong> due to excessive drawdown.</p>
    
    <h3>Details:</h3>
    <ul>
        <li>Bot: <strong>{bot_name}</strong></li>
        <li>Risk Mode: <strong>{risk_mode}</strong></li>
        <li>Current Drawdown: <strong style="color: #f44336;">{drawdown_pct:.1f}%</strong></li>
        <li>Threshold: <strong>{threshold}%</strong></li>
        <li>Status: <strong style="color: #f44336;">PAUSED</strong></li>
    </ul>
    
    <p style="color: #666;">The bot will resume automatically when drawdown improves to <strong>{threshold - 2}%</strong> or better.</p>
    
    <p style="background-color: #fff3cd; padding: 10px; border-left: 4px solid #ff9800;">
        ℹ️ This is a protective measure to prevent further losses.
    </p>
    
    <hr style="border: 1px solid #eee;">
    <p style="color: #888; font-size: 12px;">
        Best regards,<br>
        <strong>Amarktai Crypto (part of Amarktai Network)</strong>
    </p>
</body>
</html>
            """.strip()
            
            await email_service.send_email(
                to_email=user['email'],
                subject=subject,
                body=body,
                html_body=html_body
            )
            
            logger.info(f"Sent bodyguard alert email to {user['email']}")
            
        except Exception as e:
            logger.error(f"Failed to send bodyguard alert email: {e}")
    
    async def send_stop_loss_alert(self, user_id: str, bot_id: str, trade_id: str, loss_amount: float):
        """Send email when stop-loss is triggered
        
        Args:
            user_id: User ID
            bot_id: Bot ID
            trade_id: Trade ID
            loss_amount: Loss amount
        """
        try:
            user = await db.users.find_one({"id": user_id}, {"_id": 0})
            if not user or not user.get('email'):
                return
            
            bot = await db.bots_collection.find_one({"id": bot_id}, {"_id": 0})
            if not bot:
                return
            
            bot_name = bot.get('name', 'Unknown')
            
            subject = f"⚠️ Stop-Loss Triggered: {bot_name}"
            
            body = f"""
Hello,

A stop-loss has been triggered for bot "{bot_name}".

Details:
- Bot: {bot_name}
- Trade ID: {trade_id}
- Loss: R{abs(loss_amount):.2f}
- Cooldown: 60 minutes

The bot is now in a cooldown period and will not trade for the next hour.

Best regards,
Amarktai Crypto (part of Amarktai Network)
            """.strip()
            
            html_body = f"""
<html>
<body style="font-family: Arial, sans-serif; line-height: 1.6;">
    <h2 style="color: #ff9800;">⚠️ Stop-Loss Triggered</h2>
    
    <p>Hello,</p>
    
    <p>A stop-loss has been triggered for bot <strong>{bot_name}</strong>.</p>
    
    <h3>Details:</h3>
    <ul>
        <li>Bot: <strong>{bot_name}</strong></li>
        <li>Trade ID: <code>{trade_id}</code></li>
        <li>Loss: <strong style="color: #f44336;">R{abs(loss_amount):.2f}</strong></li>
        <li>Cooldown: <strong>60 minutes</strong></li>
    </ul>
    
    <p style="color: #666;">The bot is now in a cooldown period and will not trade for the next hour.</p>
    
    <hr style="border: 1px solid #eee;">
    <p style="color: #888; font-size: 12px;">
        Best regards,<br>
        <strong>Amarktai Crypto (part of Amarktai Network)</strong>
    </p>
</body>
</html>
            """.strip()
            
            await email_service.send_email(
                to_email=user['email'],
                subject=subject,
                body=body,
                html_body=html_body
            )
            
            logger.info(f"Sent stop-loss alert email to {user['email']}")
            
        except Exception as e:
            logger.error(f"Failed to send stop-loss alert email: {e}")


# Global singleton instance
email_alerts = EmailAlerts()
