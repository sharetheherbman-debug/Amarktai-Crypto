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
    
    async def start(self):
        """Start self-healing monitor"""
        if self.is_running:
            return
        
        self.is_running = True
        logger.info("🏥 Self-healing system started")
        
        asyncio.create_task(self._monitor_health())
    
    async def stop(self):
        """Stop self-healing monitor"""
        self.is_running = False
        logger.info("Self-healing system stopped")

    def get_status(self):
        """Return current self-healing system status dict.

        The shape must match what ``routes.autonomy_control`` unpacks
        (keys: state, enabled, monitored_systems, last_action,
        last_result, last_reason_code, last_check, last_error).
        """
        return {
            "state": "running" if self.is_running else "stopped",
            "enabled": True,
            "monitored_systems": ["database", "memory", "disk"],
            "last_action": None,
            "last_result": None,
            "last_reason_code": None,
            "last_check": (
                datetime.now(timezone.utc).isoformat()
                if self.is_running
                else None
            ),
            "last_error": None,
        }
    
    async def _monitor_health(self):
        """Monitor system health every 30 seconds"""
        while self.is_running:
            try:
                await self._check_database_connection()
                await self._check_memory_usage()
                await self._check_disk_space()
                try:
                    from services.autonomy_heartbeat import heartbeat_registry
                    heartbeat_registry.mark_ok("self_heal")
                except Exception:
                    pass
                
            except Exception as e:
                logger.error(f"Health monitoring error: {e}")
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
            await db.client.admin.command('ping')
            
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
        logger.info(f"Attempting recovery for {service_name} (attempt {self.recovery_attempts[service_name]})")
        
        success = await recovery_func()
        
        if success:
            self.recovery_attempts[service_name] = 0
        
        return success


# Global instance
self_healing = SelfHealingSystem()
