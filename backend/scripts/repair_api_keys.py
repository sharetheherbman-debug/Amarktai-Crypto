#!/usr/bin/env python3
"""
API Keys Repair Script
Fixes missing or null id fields in api_keys collection
Can be run manually or on startup
"""

import asyncio
import logging
import sys
import os
from uuid import uuid4
from datetime import datetime, timezone

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import database as db

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)


async def repair_api_keys():
    """
    Repair API keys collection:
    1. Add missing 'id' fields
    2. Ensure all documents have user_id as string
    3. Add missing timestamps
    4. Initialize status fields if missing
    
    Returns:
        Dict with repair statistics
    """
    stats = {
        "total_keys": 0,
        "missing_id": 0,
        "fixed_id": 0,
        "fixed_user_id": 0,
        "fixed_timestamps": 0,
        "fixed_status": 0,
        "errors": 0
    }
    
    try:
        # Count total keys
        stats["total_keys"] = await db.api_keys_collection.count_documents({})
        logger.info(f"Found {stats['total_keys']} API keys to check")
        
        if stats["total_keys"] == 0:
            logger.info("No API keys to repair")
            return stats
        
        # Find keys missing id field
        cursor = db.api_keys_collection.find({})
        
        async for doc in cursor:
            doc_id = doc.get("_id")
            needs_update = False
            update_fields = {}
            
            # Check 1: Missing or null id field
            if not doc.get("id"):
                stats["missing_id"] += 1
                new_id = str(uuid4())
                update_fields["id"] = new_id
                needs_update = True
                logger.info(f"Adding id={new_id} to key for user={doc.get('user_id')} provider={doc.get('provider')}")
            
            # Check 2: Ensure user_id is string
            user_id = doc.get("user_id")
            if user_id and not isinstance(user_id, str):
                # Convert ObjectId to string
                update_fields["user_id"] = str(user_id)
                needs_update = True
                stats["fixed_user_id"] += 1
            
            # Check 3: Add created_at if missing
            if not doc.get("created_at"):
                update_fields["created_at"] = datetime.now(timezone.utc)
                needs_update = True
                stats["fixed_timestamps"] += 1
            
            # Check 4: Add updated_at if missing
            if not doc.get("updated_at"):
                update_fields["updated_at"] = datetime.now(timezone.utc)
                needs_update = True
            
            # Check 5: Initialize status fields if missing
            if not doc.get("status"):
                # If last_test_ok exists, derive status from it
                if doc.get("last_test_ok") is True:
                    update_fields["status"] = "test_ok"
                elif doc.get("last_test_ok") is False:
                    update_fields["status"] = "test_failed"
                else:
                    update_fields["status"] = "saved_untested"
                needs_update = True
                stats["fixed_status"] += 1
            
            # Apply updates if needed
            if needs_update:
                try:
                    await db.api_keys_collection.update_one(
                        {"_id": doc_id},
                        {"$set": update_fields}
                    )
                    stats["fixed_id"] += 1
                except Exception as e:
                    logger.error(f"Error updating key {doc_id}: {e}")
                    stats["errors"] += 1
        
        logger.info("="*60)
        logger.info("API Keys Repair Complete")
        logger.info(f"Total keys checked: {stats['total_keys']}")
        logger.info(f"Keys missing id: {stats['missing_id']}")
        logger.info(f"Keys fixed (id added): {stats['fixed_id']}")
        logger.info(f"Keys with user_id fixed: {stats['fixed_user_id']}")
        logger.info(f"Keys with timestamps fixed: {stats['fixed_timestamps']}")
        logger.info(f"Keys with status fixed: {stats['fixed_status']}")
        logger.info(f"Errors: {stats['errors']}")
        logger.info("="*60)
        
        return stats
        
    except Exception as e:
        logger.error(f"Fatal error during API keys repair: {e}", exc_info=True)
        stats["errors"] += 1
        return stats


async def main():
    """Main entry point for manual execution"""
    logger.info("Starting API Keys Repair Script")
    
    try:
        # Connect to database
        await db.connect()
        logger.info("Connected to database")
        
        # Run repair
        stats = await repair_api_keys()
        
        # Exit with appropriate code
        if stats["errors"] > 0:
            logger.error("Repair completed with errors")
            sys.exit(1)
        else:
            logger.info("Repair completed successfully")
            sys.exit(0)
            
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
