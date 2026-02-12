"""
Audit Logger - Production-grade audit trail
- Logs all critical actions
- Tracks user actions, bot actions, system events
- Generates compliance reports
- Supports forensic analysis
"""

import asyncio
import time
from typing import Dict, List, Optional
from datetime import datetime, timezone, timedelta
import logging

import database as db

logger = logging.getLogger(__name__)

_AUDIT_COLLECTION_WARNING_INTERVAL = 300
_last_missing_audit_collection_warning = 0.0


def _get_audit_logs_collection():
    """Return audit log collection with backward-compatible fallback."""
    if db.audit_logs_collection is not None:
        return db.audit_logs_collection
    return db.audit_logs


def _warn_missing_audit_collection():
    global _last_missing_audit_collection_warning
    now = time.monotonic()
    if now - _last_missing_audit_collection_warning >= _AUDIT_COLLECTION_WARNING_INTERVAL:
        logger.warning("Audit logging skipped: audit_logs_collection is not initialized")
        _last_missing_audit_collection_warning = now

class AuditLogger:
    def __init__(self):
        self.log_retention_days = 90  # Keep logs for 90 days
        self.critical_events = [
            'bot_created',
            'bot_deleted',
            'bot_promoted_to_live',
            'emergency_stop_triggered',
            'capital_rebalance',
            'live_trade_executed',
            'api_key_added',
            'api_key_deleted',
            'system_mode_changed'
        ]
    
    async def log_event(self, event_type: str, user_id: str, details: Dict, 
                       severity: str = 'info') -> bool:
        """
        Log an audit event
        
        Args:
            event_type: Type of event (e.g., 'bot_created', 'trade_executed')
            user_id: User who triggered the event
            details: Dict with event-specific details
            severity: 'info', 'warning', 'critical'
        """
        try:
            audit_entry = {
                "event_type": event_type,
                "user_id": user_id,
                "severity": severity,
                "details": details,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "ip_address": details.get('ip_address', 'unknown'),
                "user_agent": details.get('user_agent', 'unknown')
            }
            
            # Add criticality flag
            audit_entry['is_critical'] = event_type in self.critical_events
            
            # Insert into audit log (best-effort)
            collection = _get_audit_logs_collection()
            if collection is None:
                _warn_missing_audit_collection()
                return True
            await collection.insert_one(audit_entry)
            
            # Log critical events to system logger too
            if audit_entry['is_critical']:
                logger.warning(f"🔒 AUDIT: {event_type} by user {user_id[:8]} - {details}")
            
            return True
            
        except Exception as e:
            logger.error(f"Audit log error: {e}")
            return False
    
    async def log_bot_action(self, action: str, user_id: str, bot_id: str, 
                            bot_name: str, details: Dict = None) -> bool:
        """Log bot-related actions"""
        return await self.log_event(
            event_type=f"bot_{action}",
            user_id=user_id,
            details={
                "bot_id": bot_id,
                "bot_name": bot_name,
                **(details or {})
            },
            severity='info' if action in ['paused', 'resumed'] else 'warning'
        )
    
    async def log_trade(self, user_id: str, bot_id: str, trade_data: Dict) -> bool:
        """Log trade execution"""
        return await self.log_event(
            event_type='live_trade_executed' if not trade_data.get('is_paper') else 'paper_trade_executed',
            user_id=user_id,
            details={
                "bot_id": bot_id,
                "trade_id": trade_data.get('id'),
                "pair": trade_data.get('pair'),
                "side": trade_data.get('side'),
                "amount": trade_data.get('amount'),
                "entry_price": trade_data.get('entry_price'),
                "profit_loss": trade_data.get('profit_loss', 0),
                "is_paper": trade_data.get('is_paper', True)
            },
            severity='info' if trade_data.get('is_paper') else 'warning'
        )
    
    async def log_capital_change(self, user_id: str, bot_id: str, 
                                 old_capital: float, new_capital: float, 
                                 reason: str) -> bool:
        """Log capital changes"""
        return await self.log_event(
            event_type='capital_changed',
            user_id=user_id,
            details={
                "bot_id": bot_id,
                "old_capital": old_capital,
                "new_capital": new_capital,
                "change": new_capital - old_capital,
                "change_pct": ((new_capital - old_capital) / old_capital * 100) if old_capital > 0 else 0,
                "reason": reason
            },
            severity='warning' if abs(new_capital - old_capital) > 1000 else 'info'
        )
    
    async def log_api_key_action(self, user_id: str, exchange: str, action: str) -> bool:
        """Log API key management actions"""
        return await self.log_event(
            event_type=f'api_key_{action}',
            user_id=user_id,
            details={
                "exchange": exchange,
                "action": action
            },
            severity='critical'
        )
    
    async def log_system_mode_change(self, user_id: str, mode: str, 
                                    value: bool, reason: str = None) -> bool:
        """Log system mode changes (emergency stop, live trading, etc.)"""
        return await self.log_event(
            event_type='system_mode_changed',
            user_id=user_id,
            details={
                "mode": mode,
                "value": value,
                "reason": reason or "User action"
            },
            severity='critical'
        )
    
    async def log_ai_action(self, user_id: str, command: str, result: Dict) -> bool:
        """Log AI command execution"""
        return await self.log_event(
            event_type='ai_command_executed',
            user_id=user_id,
            details={
                "command": command,
                "success": result.get('success', False),
                "result": str(result)[:500]  # Truncate long results
            },
            severity='info'
        )
    
    async def get_user_audit_trail(self, user_id: str, 
                                   days: int = 7,
                                   event_types: List[str] = None) -> List[Dict]:
        """Get audit trail for a user"""
        try:
            since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
            
            query = {
                "user_id": user_id,
                "timestamp": {"$gte": since}
            }
            
            if event_types:
                query["event_type"] = {"$in": event_types}
            
            logs = await audit_logs_collection.find(
                query,
                {"_id": 0}
            ).sort("timestamp", -1).limit(1000).to_list(1000)
            
            return logs
            
        except Exception as e:
            logger.error(f"Get audit trail error: {e}")
            return []
    
    async def get_critical_events(self, user_id: str, days: int = 30) -> List[Dict]:
        """Get all critical events for a user"""
        try:
            since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
            
            critical_logs = await audit_logs_collection.find(
                {
                    "user_id": user_id,
                    "is_critical": True,
                    "timestamp": {"$gte": since}
                },
                {"_id": 0}
            ).sort("timestamp", -1).to_list(1000)
            
            return critical_logs
            
        except Exception as e:
            logger.error(f"Get critical events error: {e}")
            return []
    
    async def generate_compliance_report(self, user_id: str, 
                                        start_date: str, 
                                        end_date: str) -> Dict:
        """Generate compliance report for a date range"""
        try:
            logs = await audit_logs_collection.find(
                {
                    "user_id": user_id,
                    "timestamp": {
                        "$gte": start_date,
                        "$lte": end_date
                    }
                },
                {"_id": 0}
            ).to_list(10000)
            
            # Categorize events
            by_type = {}
            by_severity = {"info": 0, "warning": 0, "critical": 0}
            
            for log in logs:
                event_type = log.get('event_type', 'unknown')
                severity = log.get('severity', 'info')
                
                if event_type not in by_type:
                    by_type[event_type] = 0
                by_type[event_type] += 1
                
                by_severity[severity] += 1
            
            # Get critical events
            critical = [log for log in logs if log.get('is_critical')]
            
            return {
                "user_id": user_id,
                "period": {
                    "start": start_date,
                    "end": end_date
                },
                "total_events": len(logs),
                "by_type": by_type,
                "by_severity": by_severity,
                "critical_events": critical,
                "generated_at": datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            logger.error(f"Compliance report error: {e}")
            return {"error": str(e)}
    
    async def cleanup_old_logs(self, days: int = None) -> Dict:
        """Clean up audit logs older than retention period"""
        try:
            retention = days or self.log_retention_days
            cutoff = (datetime.now(timezone.utc) - timedelta(days=retention)).isoformat()
            
            result = await audit_logs_collection.delete_many({
                "timestamp": {"$lt": cutoff}
            })
            
            logger.info(f"🧹 Cleaned up {result.deleted_count} old audit logs")
            
            return {
                "success": True,
                "deleted_count": result.deleted_count,
                "cutoff_date": cutoff
            }
            
        except Exception as e:
            logger.error(f"Cleanup logs error: {e}")
            return {"success": False, "error": str(e)}
    
    async def get_statistics(self, user_id: str, days: int = 30) -> Dict:
        """Get audit log statistics"""
        try:
            since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
            
            logs = await audit_logs_collection.find(
                {
                    "user_id": user_id,
                    "timestamp": {"$gte": since}
                },
                {"_id": 0}
            ).to_list(10000)
            
            return {
                "user_id": user_id,
                "period_days": days,
                "total_events": len(logs),
                "critical_events": len([l for l in logs if l.get('is_critical')]),
                "most_common_event": max(set([l.get('event_type') for l in logs]), 
                                        key=[l.get('event_type') for l in logs].count) if logs else None,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            logger.error(f"Get statistics error: {e}")
            return {"error": str(e)}

# Global instance
audit_logger = AuditLogger()
