"""
Self-Healing System
- Auto-recovery from crashes
- Database connection recovery
- Service health monitoring
"""

import asyncio
from datetime import datetime, timezone
from logger_config import logger
import psutil
import database as db


class SelfHealingSystem:
    def __init__(self):
        self.is_running = False
        self.health_checks = []
        self.recovery_attempts = {}
        self.max_recovery_attempts = 3
        self.last_check = None
        self.last_action = "initialized"
        self.last_result = "idle"
        self.last_reason_code = "INIT"
        self.last_error = None
        self.monitored_systems = ["database", "memory", "disk"]
    
    async def start(self):
        """Start self-healing monitor"""
        if self.is_running:
            return
        
        self.is_running = True
        self.last_action = "start_monitor"
        self.last_result = "started"
        self.last_reason_code = "START_REQUESTED"
        logger.info("🏥 Self-healing system started")
        
        asyncio.create_task(self._monitor_health())
    
    async def stop(self):
        """Stop self-healing monitor"""
        self.is_running = False
        self.last_action = "stop_monitor"
        self.last_result = "stopped"
        self.last_reason_code = "STOP_REQUESTED"
        logger.info("Self-healing system stopped")
    
    async def _monitor_health(self):
        """Monitor system health every 30 seconds"""
        while self.is_running:
            try:
                self.last_check = datetime.now(timezone.utc)
                await self._check_database_connection()
                await self._check_memory_usage()
                await self._check_disk_space()
                self.last_action = "health_scan"
                self.last_result = "ok"
                self.last_reason_code = "HEALTHY"
                self.last_error = None
                try:
                    from services.autonomy_heartbeat import heartbeat_registry
                    heartbeat_registry.mark_ok("self_heal")
                except Exception:
                    pass
                
            except Exception as e:
                logger.error(f"Health monitoring error: {e}")
                self.last_action = "health_scan"
                self.last_result = "error"
                self.last_reason_code = "SCAN_ERROR"
                self.last_error = str(e)
                try:
                    from services.autonomy_heartbeat import heartbeat_registry
                    heartbeat_registry.mark_error("self_heal", str(e))
                except Exception:
                    pass
            
            await asyncio.sleep(30)
    
    async def _check_database_connection(self):
        """Check and recover database connection"""
        try:
            # Test connection
            await db.command('ping')
            
            # Reset recovery counter on success
            if 'db_connection' in self.recovery_attempts:
                self.recovery_attempts['db_connection'] = 0
                
        except Exception as e:
            logger.error(f"Database connection check failed: {e}")
            await self._attempt_recovery('db_connection', self._recover_database)
    
    async def _recover_database(self):
        """Attempt to recover database connection"""
        try:
            await db.init_db()
            logger.info("✅ Database connection recovered")
            return True
        except Exception as e:
            logger.error(f"Database recovery failed: {e}")
            return False
    
    async def _check_memory_usage(self):
        """Check memory usage and alert if high"""
        try:
            memory = psutil.virtual_memory()
            
            if memory.percent > 90:
                logger.error(f"🚨 Critical memory usage: {memory.percent}%")
                await self._attempt_recovery('memory', self._free_memory)
            elif memory.percent > 80:
                logger.warning(f"⚠️ High memory usage: {memory.percent}%")
                
        except Exception as e:
            logger.error(f"Memory check failed: {e}")
    
    async def _free_memory(self):
        """Attempt to free memory"""
        try:
            import gc
            gc.collect()
            logger.info("Garbage collection triggered")
            return True
        except Exception as e:
            logger.error(f"Memory cleanup failed: {e}")
            return False
    
    async def _check_disk_space(self):
        """Check disk space and alert if low"""
        try:
            disk = psutil.disk_usage('/')
            
            if disk.percent > 90:
                logger.error(f"🚨 Critical disk usage: {disk.percent}%")
            elif disk.percent > 80:
                logger.warning(f"⚠️ High disk usage: {disk.percent}%")
                
        except Exception as e:
            logger.error(f"Disk check failed: {e}")
    
    async def _attempt_recovery(self, service_name: str, recovery_func):
        """Attempt recovery with retry limit"""
        if service_name not in self.recovery_attempts:
            self.recovery_attempts[service_name] = 0
        
        if self.recovery_attempts[service_name] >= self.max_recovery_attempts:
            logger.error(f"Max recovery attempts reached for {service_name}")
            # Send alert to admin
            from email_alerts import email_alerts
            await email_alerts.alert_system_error(
                'admin@amarktai.com',
                f"Failed to recover {service_name} after {self.max_recovery_attempts} attempts"
            )
            return False
        
        self.recovery_attempts[service_name] += 1
        self.last_action = f"recover_{service_name}"
        self.last_reason_code = "RECOVERY_ATTEMPT"
        logger.info(f"Attempting recovery for {service_name} (attempt {self.recovery_attempts[service_name]})")
        
        success = await recovery_func()
        
        if success:
            self.recovery_attempts[service_name] = 0
            self.last_result = "recovered"
            self.last_reason_code = "RECOVERY_SUCCESS"
            self.last_error = None
        else:
            self.last_result = "recovery_failed"
            self.last_reason_code = "RECOVERY_FAILED"
        
        return success


# Global instance
self_healing = SelfHealingSystem()
