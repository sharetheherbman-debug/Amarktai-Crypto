"""
Daily Reinvestment Service - Ledger-First Capital Allocation

This service implements the daily reinvestment job that:
1. Calculates realized profits from the ledger (single source of truth)
2. Allocates profits to top 3 performing bots (configurable)
3. Records all allocations as ledger events
4. Triggers daily email reports

Integrates with:
- Ledger Service (for realized PnL calculations)
- Performance Ranker (for identifying top performers)
- Email Service (for daily reports)
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional
import os
from engines.audit_logger import audit_logger

logger = logging.getLogger(__name__)


class DailyReinvestmentService:
    """
    Daily reinvestment service using ledger-first accounting
    
    Configuration via environment variables:
    - REINVEST_THRESHOLD: Minimum profit to trigger reinvestment (default: 500)
    - REINVEST_TOP_N: Number of top bots to allocate to (default: 3)
    - REINVEST_PERCENTAGE: Percentage of profits to reinvest (default: 80)
    - DAILY_REINVEST_TIME: Time to run reinvestment (default: "02:00")
    """
    
    def __init__(self, db):
        self.db = db
        self.bots_collection = db["bots"]
        self.users_collection = db["users"]
        
        # Configuration
        self.reinvest_threshold = float(os.getenv("REINVEST_THRESHOLD", "500"))
        self.reinvest_top_n = int(os.getenv("REINVEST_TOP_N", "3"))
        self.reinvest_percentage = float(os.getenv("REINVEST_PERCENTAGE", "80"))
        self.daily_time = os.getenv("DAILY_REINVEST_TIME", "02:00")
        
        # Scheduler state
        self.is_running = False
        self.scheduler_task = None
        self.last_run = None
    
    async def calculate_reinvestable_profit(
        self,
        user_id: str,
        ledger_service
    ) -> float:
        """
        Calculate realized profits available for reinvestment from ledger
        
        Args:
            user_id: User ID
            ledger_service: Ledger service instance
            
        Returns:
            Total realized profit available for reinvestment
        """
        try:
            # Get realized PnL from ledger (single source of truth)
            realized_pnl = await ledger_service.compute_realized_pnl(user_id)
            
            # Get total fees paid
            fees_paid = await ledger_service.compute_fees_paid(user_id)
            
            # Net profit = realized PnL - fees
            net_profit = realized_pnl - fees_paid
            
            # Only reinvest profits (not losses)
            reinvestable = max(0, net_profit)
            
            logger.info(f"User {user_id[:8]} - Realized PnL: {realized_pnl:.2f}, Fees: {fees_paid:.2f}, Reinvestable: {reinvestable:.2f}")
            
            return reinvestable
            
        except Exception as e:
            logger.error(f"Error calculating reinvestable profit for user {user_id}: {e}")
            return 0.0
    
    async def get_top_performers(
        self,
        user_id: str,
        limit: int = 3
    ) -> List[Dict]:
        """
        Get top performing bots for user
        
        Performance is based on:
        1. Total profit (primary)
        2. ROI percentage (secondary)
        3. Win rate (tertiary)
        
        Args:
            user_id: User ID
            limit: Number of top bots to return
            
        Returns:
            List of top performing bot documents
        """
        try:
            # Get all active bots
            bots = await self.bots_collection.find({
                "user_id": user_id,
                "status": {"$in": ["active", "running"]}
            }).to_list(1000)
            
            if not bots:
                return []
            
            # Calculate performance score for each bot
            for bot in bots:
                total_profit = bot.get("total_profit", 0)
                initial_capital = bot.get("initial_capital", 1000)
                current_capital = bot.get("current_capital", initial_capital)
                trades_count = bot.get("trades_count", 0)
                win_count = bot.get("win_count", 0)
                
                # ROI percentage
                roi_pct = ((current_capital - initial_capital) / initial_capital * 100) if initial_capital > 0 else 0
                
                # Win rate
                win_rate = (win_count / trades_count * 100) if trades_count > 0 else 0
                
                # Performance score: 60% profit + 30% ROI + 10% win rate
                bot["performance_score"] = (
                    (total_profit * 0.6) +
                    (roi_pct * 0.3) +
                    (win_rate * 0.1)
                )
            
            # Sort by performance score
            bots.sort(key=lambda b: b.get("performance_score", 0), reverse=True)
            
            # Return top N
            top_bots = bots[:limit]
            
            logger.info(f"Top {limit} performers for user {user_id[:8]}: {[b['name'] for b in top_bots]}")
            
            return top_bots
            
        except Exception as e:
            logger.error(f"Error getting top performers for user {user_id}: {e}")
            return []
    
    async def execute_reinvestment(
        self,
        user_id: str,
        ledger_service
    ) -> Dict:
        """
        Execute daily reinvestment for a user
        
        Steps:
        1. Calculate reinvestable profit from ledger
        2. Check if above threshold
        3. Get top N performing bots
        4. Allocate profits to top bots
        5. Record allocation events in ledger
        
        Args:
            user_id: User ID
            ledger_service: Ledger service instance
            
        Returns:
            Reinvestment result with details
        """
        try:
            # Step 1: Calculate reinvestable profit
            total_profit = await self.calculate_reinvestable_profit(user_id, ledger_service)
            
            # Step 2: Check threshold
            if total_profit < self.reinvest_threshold:
                logger.info(f"User {user_id[:8]}: Profit {total_profit:.2f} below threshold {self.reinvest_threshold}")
                return {
                    "success": False,
                    "user_id": user_id,
                    "total_profit": round(total_profit, 2),
                    "threshold": self.reinvest_threshold,
                    "message": f"Profit below reinvestment threshold ({total_profit:.2f} < {self.reinvest_threshold})",
                    "allocated_amount": 0,
                    "bots_allocated": 0
                }
            
            # Step 3: Get top performers
            top_bots = await self.get_top_performers(user_id, limit=self.reinvest_top_n)
            
            if not top_bots:
                logger.warning(f"User {user_id[:8]}: No active bots for reinvestment")
                return {
                    "success": False,
                    "user_id": user_id,
                    "total_profit": round(total_profit, 2),
                    "message": "No active bots available for reinvestment",
                    "allocated_amount": 0,
                    "bots_allocated": 0
                }
            
            # Step 4: Calculate allocation
            allocation_amount = total_profit * (self.reinvest_percentage / 100)
            allocation_per_bot = allocation_amount / len(top_bots)
            
            allocations = []
            
            # Step 5: Allocate and record
            for bot in top_bots:
                bot_id = bot["id"]
                bot_name = bot["name"]
                current_capital = bot.get("current_capital", 0)
                new_capital = current_capital + allocation_per_bot
                
                # Update bot capital
                await self.bots_collection.update_one(
                    {"id": bot_id},
                    {
                        "$set": {
                            "current_capital": new_capital,
                            "last_allocation_at": datetime.now(timezone.utc).isoformat()
                        }
                    }
                )
                
                # Record allocation event in ledger (single source of truth)
                event_id = await ledger_service.append_event(
                    user_id=user_id,
                    bot_id=bot_id,
                    event_type="allocation",
                    amount=allocation_per_bot,
                    currency="USDT",  # or get from bot config
                    timestamp=datetime.now(timezone.utc),
                    description=f"Daily reinvestment allocation to {bot_name}",
                    metadata={
                        "allocation_type": "daily_reinvestment",
                        "performance_score": bot.get("performance_score", 0),
                        "total_profit_source": total_profit,
                        "allocation_percentage": self.reinvest_percentage
                    }
                )
                
                allocations.append({
                    "bot_id": bot_id,
                    "bot_name": bot_name,
                    "allocated_amount": round(allocation_per_bot, 2),
                    "new_capital": round(new_capital, 2),
                    "event_id": event_id
                })

                await audit_logger.log_event(
                    "reinvestment_allocation",
                    user_id,
                    {
                        "bot_id": bot_id,
                        "bot_name": bot_name,
                        "amount": round(allocation_per_bot, 2),
                        "event_id": event_id,
                        "reinvest_percentage": self.reinvest_percentage
                    }
                )
                
                logger.info(f"Allocated {allocation_per_bot:.2f} to {bot_name} (event: {event_id})")
            
            # Success result
            result = {
                "success": True,
                "user_id": user_id,
                "total_profit": round(total_profit, 2),
                "allocated_amount": round(allocation_amount, 2),
                "allocation_per_bot": round(allocation_per_bot, 2),
                "bots_allocated": len(allocations),
                "allocations": allocations,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "message": f"Successfully allocated {allocation_amount:.2f} to {len(allocations)} top bots"
            }
            
            logger.info(f"✅ Reinvestment complete for user {user_id[:8]}: {allocation_amount:.2f} allocated to {len(allocations)} bots")
            
            return result
            
        except Exception as e:
            logger.error(f"Error executing reinvestment for user {user_id}: {e}")
            return {
                "success": False,
                "user_id": user_id,
                "error": str(e),
                "message": f"Reinvestment failed: {str(e)}"
            }
    
    async def run_daily_cycle(self):
        """
        Run daily reinvestment cycle for all users
        
        This is the main scheduler function that runs once per day.
        """
        try:
            logger.info("🔄 Starting daily reinvestment cycle...")
            
            # Get ledger service
            from services.ledger_service import get_ledger_service
            ledger_service = get_ledger_service(self.db)
            
            # Get all users
            users = await self.users_collection.find({}).to_list(10000)
            
            results = []
            successful = 0
            failed = 0
            
            for user in users:
                user_id = user.get("id")
                if not user_id:
                    continue
                
                try:
                    result = await self.execute_reinvestment(user_id, ledger_service)
                    results.append(result)
                    
                    if result.get("success"):
                        successful += 1
                    else:
                        failed += 1
                        
                except Exception as e:
                    logger.error(f"Reinvestment failed for user {user_id}: {e}")
                    failed += 1
            
            self.last_run = datetime.now(timezone.utc)
            
            logger.info(f"✅ Daily reinvestment cycle complete: {successful} successful, {failed} failed")
            
            # Trigger daily email reports
            await self.send_daily_reports()
            
            return {
                "total_users": len(users),
                "successful": successful,
                "failed": failed,
                "results": results,
                "timestamp": self.last_run.isoformat()
            }
            
        except Exception as e:
            logger.error(f"Daily reinvestment cycle error: {e}")
            return {
                "error": str(e),
                "message": "Daily cycle failed"
            }
    
    async def send_daily_reports(self):
        """Trigger daily email reports for all users"""
        try:
            from routes.daily_report import daily_report_service
            
            # Send reports to all users
            users = await self.users_collection.find({}).to_list(10000)
            
            for user in users:
                user_id = user.get("id")
                user_email = user.get("email")
                
                if user_id and user_email:
                    try:
                        await daily_report_service.send_daily_report(user_id)
                        logger.info(f"📧 Sent daily report to {user_email}")
                    except Exception as e:
                        logger.error(f"Failed to send report to {user_email}: {e}")
            
            logger.info("✅ Daily reports sent")
            
        except Exception as e:
            logger.error(f"Error sending daily reports: {e}")
    
    async def scheduler_loop(self):
        """Main scheduler loop - runs continuously"""
        while self.is_running:
            try:
                # Parse target time (HH:MM format)
                target_hour, target_minute = map(int, self.daily_time.split(":"))
                
                # Calculate time until next run
                now = datetime.now(timezone.utc)
                target_time = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
                
                # If target time has passed today, schedule for tomorrow
                if now >= target_time:
                    target_time += timedelta(days=1)
                
                wait_seconds = (target_time - now).total_seconds()
                
                logger.info(f"Next reinvestment cycle scheduled for {target_time.isoformat()} (in {wait_seconds/3600:.1f} hours)")
                
                # Wait until target time
                await asyncio.sleep(wait_seconds)
                
                # Run cycle
                await self.run_daily_cycle()
                
            except asyncio.CancelledError:
                logger.info("Reinvestment scheduler cancelled")
                break
            except Exception as e:
                logger.error(f"Scheduler loop error: {e}")
                # Wait 1 hour before retry on error
                await asyncio.sleep(3600)
    
    def start(self):
        """Start the daily reinvestment scheduler"""
        if self.is_running:
            logger.warning("Daily reinvestment scheduler already running")
            return
        
        self.is_running = True
        self.scheduler_task = asyncio.create_task(self.scheduler_loop())
        logger.info(f"✅ Daily reinvestment scheduler started (target time: {self.daily_time} UTC)")
    
    def stop(self):
        """Stop the daily reinvestment scheduler"""
        if not self.is_running:
            return
        
        self.is_running = False
        if self.scheduler_task:
            self.scheduler_task.cancel()
        
        logger.info("❌ Daily reinvestment scheduler stopped")
    
    async def trigger_manual_cycle(self, user_id: Optional[str] = None):
        """
        Manually trigger reinvestment cycle
        
        Args:
            user_id: Optional user ID to run for specific user only
            
        Returns:
            Cycle results
        """
        logger.info(f"🔄 Manual reinvestment trigger for user: {user_id or 'ALL'}")
        
        if user_id:
            # Single user
            from services.ledger_service import get_ledger_service
            ledger_service = get_ledger_service(self.db)
            
            result = await self.execute_reinvestment(user_id, ledger_service)
            return result
        else:
            # All users
            return await self.run_daily_cycle()


# Singleton instance
_reinvestment_service = None


def get_reinvestment_service(db):
    """Get or create reinvestment service instance"""
    global _reinvestment_service
    if _reinvestment_service is None:
        _reinvestment_service = DailyReinvestmentService(db)
    return _reinvestment_service
