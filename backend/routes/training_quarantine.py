"""
Training & Quarantine API - Unified Section for Bot Rehabilitation
Combines training jobs and quarantine management into one cohesive interface
"""

from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timezone
from typing import Optional, List, Dict
import logging

from auth import get_current_user
import database as db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/training-quarantine", tags=["Training & Quarantine"])

# Training and diagnostics thresholds
LOW_WIN_RATE_THRESHOLD = 40.0  # Consider bot struggling if below 40%
CRITICAL_WIN_RATE_THRESHOLD = 45.0  # Below 45% needs immediate action
MAX_CONSECUTIVE_LOSSES = 5  # Alert on 5+ consecutive losses
HIGH_DRAWDOWN_PCT = 10.0  # Significant drawdown threshold
MIN_CAPITAL_THRESHOLD = 500.0  # Minimum capital for effective trading
CRITICAL_ISSUE_COUNT = 3  # 3+ issues means bot should stay in quarantine
MAX_ACCEPTABLE_LOSS_WITH_GOOD_WIN_RATE = 50.0  # Max loss acceptable with >50% win rate


@router.get("/bots")
async def get_training_quarantine_bots(user_id: str = Depends(get_current_user)):
    """Get all bots in training or quarantine with their status
    
    Returns unified view of:
    - Quarantined bots with countdown
    - Training bots with progress
    - Recently graduated bots
    """
    try:
        # Get quarantined bots
        quarantined_bots = await db.bots_collection.find(
            {
                "user_id": user_id,
                "status": "quarantined"
            },
            {"_id": 0}
        ).to_list(100)
        
        # Get training bots (bots with active training jobs)
        training_bots = await db.bots_collection.find(
            {
                "user_id": user_id,
                "status": {"$in": ["training", "quarantined"]}
            },
            {"_id": 0}
        ).to_list(100)
        
        # Get training jobs for these bots
        bot_ids = [bot['id'] for bot in training_bots]
        training_jobs = await db.training_jobs_collection.find(
            {
                "bot_id": {"$in": bot_ids},
                "status": {"$in": ["pending", "in_progress"]}
            },
            {"_id": 0}
        ).to_list(100)
        
        # Map training jobs to bots
        training_jobs_map = {job['bot_id']: job for job in training_jobs}
        
        # Enrich bot data with training info
        enriched_bots = []
        for bot in training_bots:
            bot_id = bot['id']
            training_job = training_jobs_map.get(bot_id)
            
            # Calculate quarantine countdown if applicable
            quarantine_remaining = None
            retraining_until = bot.get('retraining_until')
            if retraining_until:
                try:
                    until_dt = datetime.fromisoformat(retraining_until.replace('Z', '+00:00'))
                    now = datetime.now(timezone.utc)
                    if until_dt > now:
                        quarantine_remaining = int((until_dt - now).total_seconds())
                except (ValueError, AttributeError) as e:
                    logger.warning(f"Failed to parse retraining_until: {e}")
                    pass
            
            enriched_bots.append({
                "bot_id": bot['id'],
                "name": bot.get('name'),
                "exchange": bot.get('exchange'),
                "status": bot.get('status'),
                "quarantine_count": bot.get('quarantine_count', 0),
                "quarantine_reason": bot.get('quarantine_reason'),
                "quarantined_at": bot.get('quarantined_at'),
                "retraining_until": retraining_until,
                "quarantine_remaining_seconds": quarantine_remaining,
                "training_job": training_job,
                "current_capital": bot.get('current_capital', 0),
                "total_profit": bot.get('total_profit', 0),
                "win_rate": bot.get('win_rate', 0),
                "trades_count": bot.get('trades_count', 0)
            })
        
        return {
            "bots": enriched_bots,
            "summary": {
                "total_quarantined": len([b for b in enriched_bots if b['status'] == 'quarantined']),
                "total_training": len([b for b in enriched_bots if b.get('training_job')]),
                "pending_redeployment": len([b for b in enriched_bots if b['quarantine_remaining_seconds'] and b['quarantine_remaining_seconds'] < 3600])
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Get training/quarantine bots error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/reports")
async def get_training_reports(user_id: str = Depends(get_current_user)):
    """Get training reports for all user bots
    
    Returns:
    - Completed training reports
    - Training diagnostics
    - Recommended adjustments
    """
    try:
        # Get all training jobs for user's bots
        user_bots = await db.bots_collection.find(
            {"user_id": user_id},
            {"_id": 0, "id": 1, "name": 1}
        ).to_list(1000)
        
        bot_ids = [bot['id'] for bot in user_bots]
        bot_names = {bot['id']: bot.get('name') for bot in user_bots}
        
        # Get training jobs
        training_jobs = await db.training_jobs_collection.find(
            {"bot_id": {"$in": bot_ids}},
            {"_id": 0}
        ).sort("created_at", -1).to_list(100)
        
        # Enrich with bot names
        for job in training_jobs:
            job['bot_name'] = bot_names.get(job['bot_id'], 'Unknown')
        
        # Separate completed vs in-progress
        completed_reports = [j for j in training_jobs if j.get('status') == 'completed']
        in_progress = [j for j in training_jobs if j.get('status') in ['pending', 'in_progress']]
        
        return {
            "completed_reports": completed_reports,
            "in_progress": in_progress,
            "total_reports": len(training_jobs),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Get training reports error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/report/{bot_id}")
async def get_bot_training_report(bot_id: str, user_id: str = Depends(get_current_user)):
    """Get detailed training report for a specific bot
    
    Returns:
    - Last N trades snapshot
    - Detected issues
    - Recommended risk adjustments
    - Training progress
    """
    try:
        # Verify bot belongs to user
        bot = await db.bots_collection.find_one({"id": bot_id, "user_id": user_id}, {"_id": 0})
        if not bot:
            raise HTTPException(status_code=404, detail="Bot not found")
        
        # Get latest training job
        training_job = await db.training_jobs_collection.find_one(
            {"bot_id": bot_id},
            {"_id": 0}
        )
        
        if not training_job:
            # Generate report on the fly if no training job exists
            training_job = await _generate_training_report(bot_id, bot)
        
        # Get last 20 trades for analysis
        recent_trades = await db.trades_collection.find(
            {"bot_id": bot_id, "status": "closed"},
            {"_id": 0}
        ).sort("timestamp", -1).limit(20).to_list(20)
        
        # Analyze trades for issues
        issues = await _analyze_bot_issues(bot, recent_trades)
        recommendations = await _generate_recommendations(bot, recent_trades, issues)
        
        return {
            "bot_id": bot_id,
            "bot_name": bot.get('name'),
            "training_job": training_job,
            "recent_trades_count": len(recent_trades),
            "recent_trades_summary": {
                "total_pnl": sum(t.get('net_pnl', t.get('profit_loss', 0)) for t in recent_trades),
                "avg_pnl": sum(t.get('net_pnl', t.get('profit_loss', 0)) for t in recent_trades) / len(recent_trades) if recent_trades else 0,
                "wins": len([t for t in recent_trades if t.get('net_pnl', t.get('profit_loss', 0)) > 0]),
                "losses": len([t for t in recent_trades if t.get('net_pnl', t.get('profit_loss', 0)) < 0]),
            },
            "detected_issues": issues,
            "recommendations": recommendations,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get bot training report error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def _generate_training_report(bot_id: str, bot: Dict) -> Dict:
    """Generate a training report for a bot"""
    return {
        "id": f"report_{bot_id}",
        "bot_id": bot_id,
        "status": "generated_on_demand",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "trigger": "manual_request",
        "report": "On-demand report generated"
    }


async def _analyze_bot_issues(bot: Dict, recent_trades: List[Dict]) -> List[str]:
    """Analyze bot performance and identify issues"""
    issues = []
    
    # Check win rate
    if recent_trades:
        wins = len([t for t in recent_trades if t.get('net_pnl', t.get('profit_loss', 0)) > 0])
        win_rate = (wins / len(recent_trades)) * 100
        
        if win_rate < LOW_WIN_RATE_THRESHOLD:
            issues.append(f"Low win rate: {win_rate:.1f}% (target: 50%+)")
    
    # Check for consecutive losses
    consecutive_losses = 0
    max_consecutive_losses = 0
    for trade in sorted(recent_trades, key=lambda t: t.get('timestamp', '')):
        if trade.get('net_pnl', trade.get('profit_loss', 0)) < 0:
            consecutive_losses += 1
            max_consecutive_losses = max(max_consecutive_losses, consecutive_losses)
        else:
            consecutive_losses = 0
    
    if max_consecutive_losses >= MAX_CONSECUTIVE_LOSSES:
        issues.append(f"Long losing streak detected: {max_consecutive_losses} consecutive losses")
    
    # Check drawdown
    current_drawdown = bot.get('current_drawdown_pct', 0)
    if current_drawdown > HIGH_DRAWDOWN_PCT:
        issues.append(f"High drawdown: {current_drawdown:.1f}%")
    
    # Check capital erosion
    initial_capital = bot.get('initial_capital', 0)
    current_capital = bot.get('current_capital', 0)
    if initial_capital > 0:
        capital_change_pct = ((current_capital - initial_capital) / initial_capital) * 100
        if capital_change_pct < -HIGH_DRAWDOWN_PCT:
            issues.append(f"Significant capital loss: {capital_change_pct:.1f}%")
    
    return issues


async def _generate_recommendations(bot: Dict, recent_trades: List[Dict], issues: List[str]) -> List[str]:
    """Generate recommendations based on bot performance"""
    recommendations = []
    
    # Recommend risk mode change if needed
    risk_mode = bot.get('risk_mode', 'balanced')
    if "Low win rate" in str(issues) and risk_mode != 'safe':
        recommendations.append("Consider switching to 'safe' risk mode to reduce position sizes")
    
    # Recommend pause if severe issues
    if len(issues) >= CRITICAL_ISSUE_COUNT:
        recommendations.append("Multiple issues detected - bot should remain in quarantine")
    
    # Recommend capital injection if capital is low
    current_capital = bot.get('current_capital', 0)
    if current_capital < MIN_CAPITAL_THRESHOLD:
        recommendations.append(f"Low capital (R{current_capital:.2f}) - consider injecting more funds or reducing trade frequency")
    
    # Recommend win rate improvement strategies
    if recent_trades:
        wins = len([t for t in recent_trades if t.get('net_pnl', t.get('profit_loss', 0)) > 0])
        win_rate = (wins / len(recent_trades)) * 100 if recent_trades else 0
        
        if win_rate < CRITICAL_WIN_RATE_THRESHOLD:
            recommendations.append("Win rate below target - AI models may need recalibration")
    
    if not recommendations:
        recommendations.append("Bot performance is acceptable - ready for redeployment after quarantine period")
    
    return recommendations
