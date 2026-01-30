from fastapi import HTTPException, Depends, APIRouter
from datetime import datetime, timezone, timedelta
from typing import Optional, List
import logging

from models import User, UserLogin, Bot, BotCreate, APIKey, APIKeyCreate, Trade, SystemMode, Alert, ChatMessage, BotRiskMode
import database as db
from auth import create_access_token, get_current_user, get_password_hash, verify_password

logger = logging.getLogger(__name__)
router = APIRouter()
from ccxt_service import ccxt_service


@router.get("/api-keys")
async def get_api_keys(user_id: str = Depends(get_current_user)):
    keys = await db.api_keys_collection.find({"user_id": user_id}, {"_id": 0}).to_list(100)
    for key in keys:
        if 'secret' in key:
            key['secret'] = '***' + key['secret'][-4:] if len(key.get('secret', '')) > 4 else '***'
    return keys


