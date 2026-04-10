"""
Centralized Lifecycle Manager
Manages startup and shutdown of all subsystems with correct async/sync handling
"""
import asyncio
import inspect
from typing import List, Callable, Optional, Any
from logger_config import logger
from utils.env_utils import env_bool


class SubsystemDefinition:
    """Definition of a subsystem with its start/stop callables"""
    def __init__(
        self,
        name: str,
        module_path: str,
        instance_name: str,
        start_method: str = "start",
        stop_method: str = "stop",
        enabled_flag: Optional[str] = None,
        create_task: bool = False
    ):
        self.name = name
        self.module_path = module_path
        self.instance_name = instance_name
        self.start_method = start_method
        self.stop_method = stop_method
        self.enabled_flag = enabled_flag
        self.create_task = create_task
        self.instance = None
        self.task = None


class LifecycleManager:
    """Manages startup and shutdown of all subsystems"""
    
    def __init__(self):
        self.subsystems: List[SubsystemDefinition] = []
        self.background_tasks: List[asyncio.Task] = []
        self.feature_flags = {}
        
    def _load_feature_flags(self):
        """Load all feature flags from environment"""
        self.feature_flags = {
            'enable_trading': env_bool('ENABLE_TRADING', False),
            'enable_autopilot': env_bool('ENABLE_AUTOPILOT', False),
            'enable_ccxt': env_bool('ENABLE_CCXT', True),
            'enable_schedulers': env_bool('ENABLE_SCHEDULERS', False),
            'disable_ai_bodyguard': env_bool('DISABLE_AI_BODYGUARD', False),
            'enable_realtime': env_bool('ENABLE_REALTIME', True),
            'enable_learning_loop': env_bool('ENABLE_LEARNING_LOOP', False),
            'enable_daily_reports': env_bool('ENABLE_DAILY_REPORTS', False),
            'enable_nightly_learning': env_bool('ENABLE_NIGHTLY_LEARNING', False),
        }
        logger.info(f"🎚️ Feature flags: {self.feature_flags}")

        # Warn loudly if the trading scheduler will NOT start — this is the most
        # common silent failure: bots appear active but no trades execute.
        if not self.feature_flags['enable_trading']:
            logger.critical(
                "⚠️  ENABLE_TRADING is NOT set (or is 0/false). "
                "The TradingScheduler will NOT start — bots will NEVER cycle. "
                "Set ENABLE_TRADING=1 in your environment to enable trading."
            )
        if not self.feature_flags['enable_schedulers']:
            logger.warning(
                "⚠️  ENABLE_SCHEDULERS is NOT set. "
                "Autonomous subsystems (self-healing, AI scheduler, etc.) are disabled."
            )
        
    def _register_subsystems(self):
        """Register all subsystems in startup order"""
        self.subsystems = [
            # Autopilot Engine
            SubsystemDefinition(
                name="Autopilot Engine",
                module_path="autopilot_engine",
                instance_name="autopilot",
                enabled_flag="enable_autopilot"
            ),
            # AI Bodyguard
            SubsystemDefinition(
                name="AI Bodyguard",
                module_path="ai_bodyguard",
                instance_name="bodyguard",
                enabled_flag="disable_ai_bodyguard",  # Note: inverted logic
                create_task=True
            ),
            # Self-Learning System
            SubsystemDefinition(
                name="Self-Learning System",
                module_path="self_learning",
                instance_name="learning_system",
                start_method="init_db"
            ),
            # Autonomous Scheduler
            SubsystemDefinition(
                name="Autonomous Scheduler",
                module_path="autonomous_scheduler",
                instance_name="autonomous_scheduler",
                enabled_flag="enable_schedulers"
            ),
            # Self-Healing System
            SubsystemDefinition(
                name="Self-Healing System",
                module_path="engines.self_healing",
                instance_name="self_healing",
                enabled_flag="enable_schedulers"
            ),
            # Advanced Orders
            SubsystemDefinition(
                name="Advanced Orders",
                module_path="advanced_orders",
                instance_name="advanced_orders",
                enabled_flag="enable_schedulers"
            ),
            # AI Scheduler
            SubsystemDefinition(
                name="AI Backend Scheduler",
                module_path="ai_scheduler",
                instance_name="ai_scheduler",
                enabled_flag="enable_schedulers"
            ),
            # AI Memory Manager
            SubsystemDefinition(
                name="AI Memory Manager",
                module_path="ai_memory_manager",
                instance_name="memory_manager",
                start_method="run_maintenance",
                enabled_flag="enable_schedulers",
                create_task=True
            ),
            # Realtime Broadcaster
            SubsystemDefinition(
                name="Realtime Broadcaster",
                module_path="services.realtime_broadcaster",
                instance_name="realtime_broadcaster",
                enabled_flag="enable_realtime",
                create_task=True
            ),
            # Learning Loop Scheduler
            SubsystemDefinition(
                name="Learning Loop Scheduler",
                module_path="services.learning_loop",
                instance_name="learning_loop",
                enabled_flag="enable_learning_loop",
                create_task=True
            ),
            # Nightly Learning Scheduler (APScheduler-based, runs at 2 AM)
            SubsystemDefinition(
                name="Nightly Learning Scheduler",
                module_path="services.nightly_learning_scheduler",
                instance_name="nightly_learning_scheduler",
                enabled_flag="enable_nightly_learning",
                start_method="start",
            ),
            # Daily Admin Reports
            SubsystemDefinition(
                name="Daily Admin Reports",
                module_path="services.daily_admin_report",
                instance_name="daily_admin_reporter",
                enabled_flag="enable_daily_reports",
                create_task=True
            ),
            # Trading Scheduler
            SubsystemDefinition(
                name="Trading Scheduler",
                module_path="trading_scheduler",
                instance_name="trading_scheduler",
                enabled_flag="enable_trading"  # Requires both trading and schedulers
            ),
            # NOTE: TradingEngineProduction loop intentionally NOT started here.
            # trading_scheduler (above) is the sole authoritative scheduler — it handles
            # both paper and live bots at a 10-second staggered cadence with full gate/risk
            # checks. Starting trading_engine_production alongside it caused duplicate
            # paper-trade execution on every tick. Shutdown still calls trading_engine.stop()
            # via server.py for safety; that is a no-op if the loop was never started.
            # NOTE: Production Autopilot removed - using unified autopilot_engine.py instead
            # Risk Management
            SubsystemDefinition(
                name="Risk Management",
                module_path="engines.risk_management",
                instance_name="risk_management",
                enabled_flag="enable_trading"
            ),
            # Wallet Balance Monitor
            SubsystemDefinition(
                name="Wallet Balance Monitor",
                module_path="jobs.wallet_balance_monitor",
                instance_name="wallet_balance_monitor"
            ),
        ]
        
    async def start_all(self) -> List[asyncio.Task]:
        """Start all enabled subsystems"""
        self._load_feature_flags()
        self._register_subsystems()
        
        for subsystem in self.subsystems:
            await self._start_subsystem(subsystem)
            
        return self.background_tasks
        
    async def _start_subsystem(self, subsystem: SubsystemDefinition):
        """Start a single subsystem with correct async/sync handling"""
        try:
            # Check if enabled
            if subsystem.enabled_flag:
                flag_name = subsystem.enabled_flag
                
                # Handle inverted logic for disable_ai_bodyguard
                if flag_name == "disable_ai_bodyguard":
                    if self.feature_flags.get(flag_name, False):
                        logger.info(f"🛡️ {subsystem.name} disabled (DISABLE_AI_BODYGUARD=1)")
                        return
                elif flag_name == "enable_trading":
                    # Trading scheduler needs both trading and schedulers enabled
                    if subsystem.name == "Trading Scheduler":
                        if not (self.feature_flags.get('enable_trading', False) and 
                                self.feature_flags.get('enable_schedulers', False)):
                            logger.info(f"💹 {subsystem.name} disabled (requires ENABLE_TRADING=1 and ENABLE_SCHEDULERS=1)")
                            return
                    elif not self.feature_flags.get(flag_name, False):
                        logger.info(f"💹 {subsystem.name} disabled ({flag_name.upper()}=0)")
                        return
                else:
                    if not self.feature_flags.get(flag_name, False):
                        logger.info(f"🤖 {subsystem.name} disabled ({flag_name.upper()}=0)")
                        return
            
            # Import the module
            module = __import__(subsystem.module_path, fromlist=[subsystem.instance_name])
            subsystem.instance = getattr(module, subsystem.instance_name)
            
            # Get the start method
            start_callable = getattr(subsystem.instance, subsystem.start_method)
            
            # Determine if method is async or sync
            is_async = inspect.iscoroutinefunction(start_callable)
            
            # Call start method
            if subsystem.create_task and is_async:
                # Create a background task
                task = asyncio.create_task(start_callable())
                self.background_tasks.append(task)
                logger.info(f"✅ {subsystem.name} started (task created)")
            elif is_async:
                # Await the async method
                await start_callable()
                logger.info(f"✅ {subsystem.name} started")
            else:
                # Call sync method directly (NO await)
                start_callable()
                logger.info(f"✅ {subsystem.name} started")
                
        except Exception as e:
            logger.error(f"Failed to start {subsystem.name}: {e}")
            
    async def stop_all(self):
        """Stop all subsystems and cancel background tasks"""
        logger.info("🔴 Shutting down all subsystems...")
        
        # Cancel background tasks first
        if self.background_tasks:
            logger.info(f"📋 Cancelling {len(self.background_tasks)} background tasks...")
            for task in self.background_tasks:
                if not task.done():
                    task.cancel()
            
            try:
                # Properly await the gather with timeout
                await asyncio.wait_for(
                    asyncio.gather(*self.background_tasks, return_exceptions=True),
                    timeout=5.0
                )
                logger.info("✅ Background tasks cancelled")
            except asyncio.TimeoutError:
                logger.warning("⚠️ Background task cancellation timed out after 5s")
            except Exception as e:
                logger.error(f"Error cancelling background tasks: {e}")
        
        # Stop subsystems in reverse order
        for subsystem in reversed(self.subsystems):
            await self._stop_subsystem(subsystem)
            
    async def _stop_subsystem(self, subsystem: SubsystemDefinition):
        """Stop a single subsystem with correct async/sync handling"""
        if subsystem.instance is None:
            return
            
        try:
            # Get the stop method
            stop_callable = getattr(subsystem.instance, subsystem.stop_method, None)
            if stop_callable is None:
                return
            
            # Determine if method is async or sync
            is_async = inspect.iscoroutinefunction(stop_callable)
            
            # Call stop method
            if is_async:
                await stop_callable()
            else:
                # Call sync method directly (NO await)
                stop_callable()
                
            logger.info(f"✅ {subsystem.name} stopped")
            
        except Exception as e:
            logger.error(f"Error stopping {subsystem.name}: {e}")


# Global singleton instance
lifecycle_manager = LifecycleManager()
