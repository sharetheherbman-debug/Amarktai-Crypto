"""
Hugging Face Integration Routes

Provides AI sentiment analysis via Hugging Face Inference API:
  GET  /api/huggingface/status          — connection / key status
  POST /api/huggingface/test-connection  — verify key validity
  POST /api/sentiment/analyze            — batch sentiment for symbols/news
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from datetime import datetime, timezone
from typing import Optional, List
import logging
import os
import httpx

from auth import get_current_user
import database as db

logger = logging.getLogger(__name__)

router = APIRouter(tags=["HuggingFace"])

HF_INFERENCE_URL = "https://api-inference.huggingface.co/models"
DEFAULT_MODEL = "cardiffnlp/twitter-roberta-base-sentiment-latest"


async def _get_hf_key(user_id: str) -> Optional[str]:
    """Retrieve user's Hugging Face token (falls back to env)."""
    doc = await db.api_keys_collection.find_one(
        {"user_id": user_id, "provider": "huggingface"},
        {"_id": 0, "api_key": 1},
    )
    if doc and doc.get("api_key"):
        return doc["api_key"]
    return os.getenv("HUGGINGFACE_API_KEY", os.getenv("HF_TOKEN", ""))


# ---------- status / test -----------------------------------------------

@router.get("/api/huggingface/status")
async def hf_status(user_id: str = Depends(get_current_user)):
    """Check whether a Hugging Face key is configured and model is reachable."""
    key = await _get_hf_key(user_id)
    configured = bool(key)
    reachable = False
    error_msg = None

    if configured:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{HF_INFERENCE_URL}/{DEFAULT_MODEL}",
                    headers={"Authorization": f"Bearer {key}"},
                    json={"inputs": "Bitcoin is rising"},
                )
                reachable = resp.status_code == 200
                if not reachable:
                    error_msg = f"HTTP {resp.status_code}"
        except Exception as exc:
            error_msg = str(exc)[:120]

    return {
        "success": True,
        "configured": configured,
        "reachable": reachable,
        "model": DEFAULT_MODEL,
        "last_error": error_msg,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/api/huggingface/test-connection")
async def hf_test_connection(user_id: str = Depends(get_current_user)):
    """Actively test the Hugging Face API connection with a sample inference."""
    key = await _get_hf_key(user_id)
    if not key:
        return {"connected": False, "message": "No Hugging Face API key configured"}

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{HF_INFERENCE_URL}/{DEFAULT_MODEL}",
                headers={"Authorization": f"Bearer {key}"},
                json={"inputs": "The crypto market is looking strong today"},
            )
            if resp.status_code == 200:
                result = resp.json()
                return {"connected": True, "message": "Hugging Face API is working", "sample": result}
            return {"connected": False, "message": f"HTTP {resp.status_code}: {resp.text[:200]}"}
    except Exception as exc:
        logger.error(f"HuggingFace test error: {exc}")
        return {"connected": False, "message": str(exc)[:200]}


# ---------- sentiment analysis -------------------------------------------

class SentimentRequest(BaseModel):
    texts: List[str] = Field(..., min_length=1, max_length=50)  # max 50 texts per batch
    model: Optional[str] = None


@router.post("/api/sentiment/analyze")
async def analyze_sentiment(
    body: SentimentRequest,
    user_id: str = Depends(get_current_user),
):
    """Run sentiment analysis on a list of texts (news headlines, tweets, etc.)."""
    key = await _get_hf_key(user_id)
    if not key:
        raise HTTPException(status_code=400, detail="Hugging Face API key not configured")

    model = body.model or DEFAULT_MODEL
    results = []

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            for text in body.texts:
                resp = await client.post(
                    f"{HF_INFERENCE_URL}/{model}",
                    headers={"Authorization": f"Bearer {key}"},
                    json={"inputs": text},
                )
                if resp.status_code == 200:
                    raw = resp.json()
                    # The model typically returns [[{label, score}, ...]]
                    labels = raw[0] if isinstance(raw, list) and raw else raw
                    results.append({
                        "text": text[:200],
                        "labels": labels,
                        "model": model,
                    })
                else:
                    results.append({
                        "text": text[:200],
                        "error": f"HTTP {resp.status_code}",
                        "model": model,
                    })
    except Exception as exc:
        logger.error(f"Sentiment analysis error: {exc}")
        raise HTTPException(status_code=502, detail=f"HuggingFace API error: {str(exc)[:200]}")

    return {
        "results": results,
        "count": len(results),
        "model": model,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
