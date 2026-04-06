"""
Nightly Learning Scheduler

Runs learning jobs at scheduled times (default: 2 AM).
Gated by environment variables for safety.
"""

import asyncio
import logging
from datetime import datetime, time, timezone
from typing import Optional
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from utils.env_utils import env_bool
from services.learning_loop import learning_loop

logger = logging.getLogger(__name__)


class NightlyLearningScheduler:
    """Schedules nightly learning jobs with proper gating"""
    
    def __init__(self):
        self.scheduler: Optional[AsyncIOScheduler] = None
        self.is_running = False
        self.last_run: Optional[datetime] = None
        self.last_run_status: Optional[str] = None
        self.last_run_error: Optional[str] = None
        
    def _is_enabled(self) -> tuple[bool, str]:
        """Check if nightly learning is enabled with reason"""
        # Must have self-learning enabled
        if not env_bool('ENABLE_SELF_LEARNING', True):
            return False, "ENABLE_SELF_LEARNING is false"
        
        # Must explicitly enable nightly learning
        if not env_bool('ENABLE_NIGHTLY_LEARNING', False):
            return False, "ENABLE_NIGHTLY_LEARNING is false (default disabled)"
        
        return True, "enabled"
    
    async def _run_learning_job(self):
        """Execute nightly learning job with error handling"""
        self.last_run = datetime.now(timezone.utc)
        self.last_run_status = "running"
        self.last_run_error = None
        
        # Check if live learning is enabled
        enable_live = env_bool('ENABLE_LIVE_LEARNING', False)
        
        try:
            logger.info("🧠 Starting nightly learning job...")
            logger.info(f"   Live learning: {'enabled' if enable_live else 'disabled (paper only)'}")
            
            # Run learning loop
            # Note: learning_loop.run_nightly_learning handles paper/live gating internally
            result = await learning_loop.run_nightly_learning(dry_run=False)
            
            self.last_run_status = "completed"
            logger.info(f"✅ Nightly learning completed: {result.get('summary', 'No summary')}")
            
        except Exception as e:
            self.last_run_status = "error"
            self.last_run_error = str(e)
            logger.error(f"❌ Nightly learning failed: {e}", exc_info=True)
    
    def start(self):
        """Start the nightly learning scheduler"""
        enabled, reason = self._is_enabled()
        
        if not enabled:
            logger.info(f"🧠 Nightly learning scheduler: {reason}")
            return
        
        if self.is_running:
            logger.warning("Nightly learning scheduler already running")
            return
        
        # Get schedule hour (default: 2 AM)
        import os
        schedule_hour = int(os.getenv('NIGHTLY_LEARNING_HOUR', '2'))
        
        # Create scheduler
        self.scheduler = AsyncIOScheduler()
        
        # Add job - runs daily at specified hour
        self.scheduler.add_job(
            self._run_learning_job,
            CronTrigger(hour=schedule_hour, minute=0),
            id='nightly_learning',
            name='Nightly Learning Job',
            max_instances=1,  # Only one instance at a time
            coalesce=True,    # If missed, run once (not multiple times)
            misfire_grace_time=3600  # 1 hour grace period
        )
        
        self.scheduler.start()
        self.is_running = True
        
        logger.info(f"✅ Nightly learning scheduler started (runs at {schedule_hour}:00 UTC)")
        logger.info(f"   Paper-only mode: {not env_bool('ENABLE_LIVE_LEARNING', False)}")
    
    def stop(self):
        """Stop the nightly learning scheduler"""
        if self.scheduler and self.is_running:
            self.scheduler.shutdown()
            self.is_running = False
            logger.info("🔴 Nightly learning scheduler stopped")
    
    def get_status(self) -> dict:
        """Get scheduler status for diagnostics"""
        enabled, reason = self._is_enabled()
        
        return {
            "enabled": enabled,
            "reason": reason,
            "running": self.is_running,
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "last_run_status": self.last_run_status,
            "last_run_error": self.last_run_error,
            "schedule_hour": int(os.getenv('NIGHTLY_LEARNING_HOUR', '2')),
            "live_learning_enabled": env_bool('ENABLE_LIVE_LEARNING', False)
        }


# Global instance
nightly_learning_scheduler = NightlyLearningScheduler()
