"""
AI Memory Management System
- Short-term: Last 30 days in MongoDB
- Archive: Zip conversations older than 30 days
- Cleanup: Delete archives older than 6 months
"""

import asyncio
from datetime import datetime, timezone, timedelta
import database as db
from logger_config import logger
import zipfile
import json
import os
from pathlib import Path


class AIMemoryManager:
    def __init__(self):
        # BLOCKER FIX: Make AI memory path configurable via env var
        # Default to writable location in production, not /app
        memory_base = os.getenv("AI_MEMORY_PATH", "/var/amarktai/data/ai_memory")
        self.archive_path = Path(memory_base) / "chat_archives"
        self.archive_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"AI Memory Manager initialized with path: {self.archive_path}")
        
    async def get_conversation_history(self, user_id: str, days: int = 30) -> list:
        """Get conversation history for the last N days"""
        try:
            cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
            
            messages = await db.chat_messages_collection.find(
                {
                    "user_id": user_id,
                    "timestamp": {"$gte": cutoff_date}
                },
                {"_id": 0}
            ).sort("timestamp", 1).to_list(None)
            
            return messages
            
        except Exception as e:
            logger.error(f"Error fetching conversation history: {e}")
            return []
    
    async def archive_old_conversations(self):
        """Archive conversations older than 30 days for all users"""
        try:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=30)
            cutoff_iso = cutoff_date.isoformat()
            
            # Find all messages older than 30 days
            old_messages = await db.chat_messages_collection.find(
                {"timestamp": {"$lt": cutoff_iso}},
                {"_id": 0}
            ).to_list(None)
            
            if not old_messages:
                logger.info("No messages to archive")
                return
            
            # Group by user
            by_user = {}
            for msg in old_messages:
                user_id = msg.get('user_id')
                if user_id not in by_user:
                    by_user[user_id] = []
                by_user[user_id].append(msg)
            
            # Create archive for each user
            archive_date = cutoff_date.strftime("%Y%m%d")
            
            for user_id, messages in by_user.items():
                archive_file = self.archive_path / f"chat_{user_id}_{archive_date}.zip"
                
                with zipfile.ZipFile(archive_file, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    json_content = json.dumps(messages, indent=2, default=str)
                    zipf.writestr(f"conversations_{archive_date}.json", json_content)
                
                logger.info(f"Archived {len(messages)} messages for user {user_id} to {archive_file}")
            
            # Delete archived messages from database
            delete_result = await db.chat_messages_collection.delete_many(
                {"timestamp": {"$lt": cutoff_iso}}
            )
            
            logger.info(f"Deleted {delete_result.deleted_count} archived messages from database")
            
        except Exception as e:
            logger.error(f"Archive error: {e}")
    
    async def cleanup_old_archives(self):
        """Delete archive files older than 6 months"""
        try:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=180)  # 6 months
            
            deleted_count = 0
            for archive_file in self.archive_path.glob("chat_*.zip"):
                file_mtime = datetime.fromtimestamp(archive_file.stat().st_mtime, tz=timezone.utc)
                
                if file_mtime < cutoff_date:
                    archive_file.unlink()
                    deleted_count += 1
                    logger.info(f"Deleted old archive: {archive_file}")
            
            logger.info(f"Cleanup complete: deleted {deleted_count} old archives")
            
        except Exception as e:
            logger.error(f"Cleanup error: {e}")
    
    async def run_maintenance(self):
        """Run daily maintenance: archive old conversations and cleanup old archives"""
        while True:
            try:
                # Run at 3 AM UTC
                now = datetime.now(timezone.utc)
                next_run = now.replace(hour=3, minute=0, second=0, microsecond=0)
                
                if next_run < now:
                    next_run += timedelta(days=1)
                
                wait_seconds = (next_run - now).total_seconds()
                logger.info(f"Next memory maintenance in {wait_seconds/3600:.1f} hours")
                
                await asyncio.sleep(wait_seconds)
                
                # Run maintenance
                logger.info("Starting memory maintenance...")
                await self.archive_old_conversations()
                await self.cleanup_old_archives()
                logger.info("Memory maintenance complete")
                
            except Exception as e:
                logger.error(f"Maintenance error: {e}")
                await asyncio.sleep(3600)  # Retry in 1 hour


# Global instance
memory_manager = AIMemoryManager()
