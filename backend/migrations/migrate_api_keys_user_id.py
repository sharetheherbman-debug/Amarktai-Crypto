#!/usr/bin/env python3
"""
Database Migration Script: Convert api_keys.user_id from ObjectId to String

This migration ensures all user_id fields in the api_keys collection are stored as strings
for consistency across the application.

Usage:
    python backend/migrations/migrate_api_keys_user_id.py

Requirements:
    - MONGO_URL and DB_NAME environment variables must be set
    - Or modify the script to use your connection string directly
"""

import asyncio
import os
import sys
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
from datetime import datetime

# Add parent directory to path to import database module
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


async def migrate_api_keys_user_id():
    """
    Convert all api_keys.user_id fields from ObjectId to string
    Safe to run multiple times (idempotent)
    """
    # Get MongoDB connection details
    mongo_url = os.getenv('MONGO_URL', 'mongodb://localhost:27017')
    db_name = os.getenv('DB_NAME', 'amarktai')
    
    print(f"🔌 Connecting to MongoDB at {mongo_url}")
    print(f"📊 Database: {db_name}")
    
    try:
        # Connect to MongoDB
        client = AsyncIOMotorClient(mongo_url)
        db = client[db_name]
        api_keys_collection = db.api_keys
        
        # Test connection
        await client.admin.command('ping')
        print("✅ MongoDB connection successful")
        
        # Find all documents with ObjectId user_id
        objectid_docs = []
        cursor = api_keys_collection.find({})
        
        async for doc in cursor:
            user_id = doc.get('user_id')
            if isinstance(user_id, ObjectId):
                objectid_docs.append(doc)
        
        total_objectid = len(objectid_docs)
        print(f"\n📝 Found {total_objectid} documents with ObjectId user_id")
        
        if total_objectid == 0:
            print("✅ No migration needed - all user_id fields are already strings")
            return
        
        # Confirm migration
        print("\n⚠️  This will convert ObjectId user_id fields to strings")
        response = input("Continue? (yes/no): ").strip().lower()
        
        if response != 'yes':
            print("❌ Migration cancelled")
            return
        
        # Perform migration
        migrated_count = 0
        failed_count = 0
        
        print("\n🔄 Starting migration...")
        
        for doc in objectid_docs:
            try:
                old_user_id = doc['user_id']
                new_user_id = str(old_user_id)
                provider = doc.get('provider', 'unknown')
                
                # Update the document
                result = await api_keys_collection.update_one(
                    {"_id": doc["_id"]},
                    {
                        "$set": {
                            "user_id": new_user_id,
                            "migrated_at": datetime.utcnow().isoformat(),
                            "migration_note": f"Converted from ObjectId({old_user_id})"
                        }
                    }
                )
                
                if result.modified_count > 0:
                    migrated_count += 1
                    print(f"  ✅ Migrated: {provider} for user {new_user_id[:8]}...")
                else:
                    print(f"  ⚠️  No update needed: {provider} for user {new_user_id[:8]}...")
                    
            except Exception as e:
                failed_count += 1
                print(f"  ❌ Failed to migrate document {doc.get('_id')}: {e}")
        
        # Summary
        print("\n" + "="*60)
        print("Migration Summary:")
        print(f"  Total documents found: {total_objectid}")
        print(f"  Successfully migrated: {migrated_count}")
        print(f"  Failed: {failed_count}")
        print("="*60)
        
        if failed_count == 0:
            print("\n✅ Migration completed successfully!")
        else:
            print(f"\n⚠️  Migration completed with {failed_count} failures")
        
        # Close connection
        client.close()
        
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        raise


if __name__ == "__main__":
    print("="*60)
    print("API Keys User ID Migration")
    print("="*60)
    print()
    
    asyncio.run(migrate_api_keys_user_id())
