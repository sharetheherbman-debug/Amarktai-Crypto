# OpenAI Key Resolution

## Overview
All AI modules in the backend now use a centralized OpenAI API key resolver that follows a consistent priority:

1. **Per-user key** (from database, encrypted)
2. **System environment variable** (`OPENAI_API_KEY`)
3. **Missing** (gracefully handled)

## Usage

```python
from services.openai_key_resolver import resolve_openai_key, get_openai_client

# Option 1: Get just the key
api_key, source = await resolve_openai_key(user_id)
if api_key:
    logger.info(f"OpenAI key resolved source={source}")
    # Use the key...
else:
    logger.warning(f"OpenAI key resolved source={source}")
    # Handle missing key...

# Option 2: Get a ready-to-use client
client, source = await get_openai_client(user_id)
if client:
    logger.info(f"OpenAI key resolved source={source}")
    response = await client.chat.completions.create(...)
```

## Key Source Logging
All AI modules now log the key source when resolving OpenAI keys:
- `OpenAI key resolved source=user` - Using per-user key from database
- `OpenAI key resolved source=system` - Using system environment variable
- `OpenAI key resolved source=missing` - No key available

## Updated Modules
The following modules have been updated to use the centralized resolver:

- `backend/ai_super_brain.py` - Daily insights generation
- `backend/ai_service.py` - AI chat service
- `backend/ai_models.py` - SystemAI, TradeAI, ReportingAI
- `backend/engines/ai_model_router.py` - AI model routing
- `backend/ai_production.py` - Production AI handler
- `backend/ai_models_router.py` - Multi-model AI router

## Benefits

1. **Consistency** - All modules follow the same key resolution logic
2. **Per-user keys** - Users can configure their own OpenAI keys
3. **System fallback** - Graceful fallback to system key
4. **Error handling** - No crashes on missing keys
5. **Observability** - All key resolutions are logged with source
6. **Security** - Per-user keys remain encrypted in database

## Testing
Run tests with:
```bash
python3 -m pytest backend/tests/test_openai_key_resolver.py -v
```

All 10 tests validate:
- User key priority
- System key fallback
- Missing key handling
- Empty/whitespace key handling
- Error recovery
- Client creation
