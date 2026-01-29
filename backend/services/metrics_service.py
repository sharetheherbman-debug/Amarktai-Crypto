"""
Metrics Service - Single Source of Truth for Overview and Profits
All dashboard metrics MUST be computed through this service
Uses accounting_service for consistent profit/trade calculations
Provides consistent, accurate counts and calculations
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, List
import database as db
from services.accounting import accounting_service

logger = logging.getLogger(__name__)


class MetricsService:
    """Centralized metrics computation service"""
    
    async def get_overview_metrics(self, user_id: str) -> Dict:
        """Get comprehensive overview metrics for dashboard
        
        Uses accounting_service for profit calculations to ensure consistency
        across Overview, Profits, and Live Trades pages.
        
        Computes:
        - Total profit (from accounting service - net realised PnL)
        - 24h change and percentage
        - Bot counts (total, active, paper, live)
        - Exposure and risk level
        - AI sentiment
        - Last update timestamp
        
        Args:
            user_id: User ID to compute metrics for
            
        Returns:
            Dict of metrics with all overview data
        """
        try:
            # Get unified accounting metrics (SINGLE SOURCE OF TRUTH)
            accounting_metrics = await accounting_service.get_unified_metrics(
                user_id=user_id,
                trading_mode=None,  # All modes
                include_unrealised=True
            )
            
            # Get profit from accounting service
            total_profit = accounting_metrics["net_realised_pnl_zar"]
            executed_trades_count = accounting_metrics["executed_trades_count"]
            
            # Get all user's bots (excluding deleted)
            bots_cursor = db.bots_collection.find(
                {"user_id": user_id, "status": {"$ne": "deleted"}},
                {"_id": 0}
            )
            all_bots = await bots_cursor.to_list(1000)
            
            # Count bots by status and mode
            total_bots = len(all_bots)
            active_bots = [b for b in all_bots if b.get('status') == 'active']
            active_count = len(active_bots)
            
            # Count by trading mode (only active bots)
            paper_bots = len([b for b in active_bots if b.get('trading_mode') == 'paper'])
            live_bots = len([b for b in active_bots if b.get('trading_mode') == 'live'])
            
            # Calculate total capital
            total_current = sum(bot.get('current_capital', 0) for bot in active_bots)
            total_initial = sum(bot.get('initial_capital', 0) for bot in active_bots)
            
            # Calculate 24h change from accounting service
            # Get trades from last 24h
            twenty_four_hours_ago = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
            recent_trades_cursor = db.trades_collection.find(
                {
                    "user_id": user_id,
                    "status": "closed",
                    "timestamp": {"$gte": twenty_four_hours_ago}
                },
                {"_id": 0, "net_pnl": 1, "profit_loss": 1}
            )
            recent_trades = await recent_trades_cursor.to_list(10000)
            
            # Use net_pnl if available, fallback to profit_loss (consistent with accounting service)
            change_24h = sum(
                t.get('net_pnl', t.get('profit_loss', 0)) 
                for t in recent_trades
            )
            change_24h_pct = (change_24h / total_initial * 100) if total_initial > 0 else 0
            
            # Calculate exposure
            total_capital = sum(bot.get('current_capital', 0) for bot in active_bots)
            # Exposure as percentage of total capital at risk
            exposure = (total_capital / (total_capital + 1000)) * 100 if total_capital > 0 else 0
            
            # Determine risk level based on exposure
            if exposure < 50:
                risk_level = "Low"
            elif exposure < 75:
                risk_level = "Medium"
            else:
                risk_level = "High"
            
            # AI sentiment based on 24h performance
            if change_24h_pct > 0:
                ai_sentiment = "Bullish"
            elif change_24h_pct < 0:
                ai_sentiment = "Bearish"
            else:
                ai_sentiment = "Neutral"
            
            # Build bot display string
            if live_bots > 0:
                bot_display = f"{active_count} active / {total_bots} ({live_bots} live, {paper_bots} paper)"
            else:
                bot_display = f"{active_count} active / {total_bots} (paper)"
            
            # Get system mode for trading status
            modes = await db.system_modes_collection.find_one({"user_id": user_id}, {"_id": 0})
            if modes and modes.get('liveTrading'):
                trading_status = "Live Trading"
            elif modes and modes.get('paperTrading'):
                trading_status = "Paper Trading"
            else:
                trading_status = "Inactive"
            
            # Check for integrity issues
            integrity_status = await self._check_integrity(user_id, all_bots)
            
            return {
                # Profit metrics from accounting service (SINGLE SOURCE OF TRUTH)
                "total_profit": total_profit,
                "totalProfit": total_profit,  # Backward compatibility
                "net_realised_pnl_zar": accounting_metrics["net_realised_pnl_zar"],
                "unrealised_pnl_zar": accounting_metrics["unrealised_pnl_zar"],
                "executed_trades_count": executed_trades_count,
                "total_fees_zar": accounting_metrics["total_fees_zar"],
                "change_24h": round(change_24h, 2),
                "change_24h_pct": round(change_24h_pct, 2),
                
                # Bot counts
                "total_bots": total_bots,
                "active_bots": active_count,
                "paper_bots": paper_bots,
                "live_bots": live_bots,
                "activeBots": bot_display,  # Backward compatibility
                
                # Risk metrics
                "exposure": round(exposure, 2),
                "risk_level": risk_level,
                "riskLevel": risk_level,  # Backward compatibility
                
                # Sentiment
                "ai_sentiment": ai_sentiment,
                "aiSentiment": ai_sentiment,  # Backward compatibility
                
                # Status
                "trading_status": trading_status,
                "tradingStatus": trading_status,  # Backward compatibility
                "last_update": datetime.now(timezone.utc).isoformat(),
                "lastUpdate": datetime.now(timezone.utc).isoformat(),  # Backward compatibility
                "integrity_status": integrity_status,
                
                # Metadata
                "data_source": "accounting_service",
                "accounting_timestamp": accounting_metrics["last_calculated_at"]
            }
            
        except Exception as e:
            logger.error(f"Overview metrics error: {e}", exc_info=True)
            # Return safe defaults on error
            return {
                "total_profit": 0.0,
                "totalProfit": 0.0,
                "change_24h": 0.0,
                "change_24h_pct": 0.0,
                "total_bots": 0,
                "active_bots": 0,
                "paper_bots": 0,
                "live_bots": 0,
                "activeBots": "0 / 0",
                "exposure": 0.0,
                "risk_level": "Unknown",
                "riskLevel": "Unknown",
                "ai_sentiment": "Neutral",
                "aiSentiment": "Neutral",
                "trading_status": "Unknown",
                "tradingStatus": "Unknown",
                "last_update": datetime.now(timezone.utc).isoformat(),
                "lastUpdate": datetime.now(timezone.utc).isoformat(),
                "integrity_status": {"status": "error", "message": str(e)}
            }
    
    async def get_profit_history(
        self, 
        user_id: str, 
        time_range: str = "7d",
        interval: str = "1h"
    ) -> Dict:
        """Get profit history over time
        
        Args:
            user_id: User ID
            time_range: Time range (1d, 7d, 30d, 90d, 1y, all)
            interval: Data point interval (5m, 15m, 1h, 4h, 1d)
            
        Returns:
            Dict with timeseries data and summary
        """
        try:
            # Calculate time range
            now = datetime.now(timezone.utc)
            
            range_map = {
                "1d": timedelta(days=1),
                "7d": timedelta(days=7),
                "30d": timedelta(days=30),
                "90d": timedelta(days=90),
                "1y": timedelta(days=365),
                "all": timedelta(days=3650)  # 10 years
            }
            
            start_time = now - range_map.get(time_range, timedelta(days=7))
            
            # Get all trades in range
            trades_cursor = db.trades_collection.find(
                {
                    "user_id": user_id,
                    "status": "closed",
                    "timestamp": {"$gte": start_time.isoformat()}
                },
                {"_id": 0, "timestamp": 1, "profit_loss": 1}
            ).sort("timestamp", 1)
            
            trades = await trades_cursor.to_list(10000)
            
            if not trades:
                return {
                    "range": time_range,
                    "interval": interval,
                    "datapoints": [],
                    "summary": {
                        "total_pnl": 0,
                        "trade_count": 0,
                        "start_time": start_time.isoformat(),
                        "end_time": now.isoformat()
                    }
                }
            
            # Group trades by interval
            interval_map = {
                "5m": timedelta(minutes=5),
                "15m": timedelta(minutes=15),
                "1h": timedelta(hours=1),
                "4h": timedelta(hours=4),
                "1d": timedelta(days=1)
            }
            
            interval_delta = interval_map.get(interval, timedelta(hours=1))
            
            # Create time buckets
            datapoints = []
            cumulative_pnl = 0
            current_bucket_start = start_time
            bucket_trades = []
            
            for trade in trades:
                trade_time = datetime.fromisoformat(trade['timestamp'].replace('Z', '+00:00'))
                
                # Close buckets that are complete
                while trade_time >= current_bucket_start + interval_delta:
                    if bucket_trades:
                        bucket_pnl = sum(t.get('profit_loss', 0) for t in bucket_trades)
                        cumulative_pnl += bucket_pnl
                        
                        datapoints.append({
                            "timestamp": current_bucket_start.isoformat(),
                            "profit_loss": round(bucket_pnl, 2),
                            "cumulative_pnl": round(cumulative_pnl, 2),
                            "trade_count": len(bucket_trades)
                        })
                        
                        bucket_trades = []
                    
                    current_bucket_start += interval_delta
                
                # Add trade to current bucket
                bucket_trades.append(trade)
            
            # Close final bucket
            if bucket_trades:
                bucket_pnl = sum(t.get('profit_loss', 0) for t in bucket_trades)
                cumulative_pnl += bucket_pnl
                
                datapoints.append({
                    "timestamp": current_bucket_start.isoformat(),
                    "profit_loss": round(bucket_pnl, 2),
                    "cumulative_pnl": round(cumulative_pnl, 2),
                    "trade_count": len(bucket_trades)
                })
            
            return {
                "range": time_range,
                "interval": interval,
                "datapoints": datapoints,
                "summary": {
                    "total_pnl": round(cumulative_pnl, 2),
                    "trade_count": len(trades),
                    "start_time": start_time.isoformat(),
                    "end_time": now.isoformat()
                }
            }
            
        except Exception as e:
            logger.error(f"Profit history error: {e}", exc_info=True)
            return {
                "range": time_range,
                "interval": interval,
                "datapoints": [],
                "summary": {
                    "total_pnl": 0,
                    "trade_count": 0,
                    "error": str(e)
                }
            }
    
    async def _check_integrity(self, user_id: str, bots: List[Dict]) -> Dict:
        """Check for integrity issues in metrics
        
        Args:
            user_id: User ID
            bots: List of user's bots
            
        Returns:
            Dict with integrity status
        """
        try:
            issues = []
            
            # Check if bot profits match trade rollups
            for bot in bots[:10]:  # Check first 10 bots to avoid slow queries
                bot_id = bot.get('id')
                if not bot_id:
                    continue
                
                # Get trade profit sum
                trades_cursor = db.trades_collection.find(
                    {"bot_id": bot_id, "status": "closed"},
                    {"_id": 0, "profit_loss": 1}
                )
                trades = await trades_cursor.to_list(1000)
                trade_profit = sum(t.get('profit_loss', 0) for t in trades)
                
                # Compare with bot's recorded profit
                bot_profit = bot.get('total_profit', 0)
                
                if abs(trade_profit - bot_profit) > 0.01:  # Allow small rounding errors
                    issues.append(f"Bot {bot.get('name')} profit mismatch: {bot_profit} vs {trade_profit}")
            
            if issues:
                return {
                    "status": "warning",
                    "message": "Some mismatches detected",
                    "issues": issues[:5]  # Limit to first 5
                }
            else:
                return {
                    "status": "ok",
                    "message": "All metrics consistent"
                }
                
        except Exception as e:
            logger.error(f"Integrity check error: {e}")
            return {
                "status": "error",
                "message": f"Could not verify integrity: {str(e)}"
            }


# Global singleton instance
metrics_service = MetricsService()
