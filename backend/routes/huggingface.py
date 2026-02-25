"""
HuggingFace Integration Routes
Provides endpoints for HuggingFace API key management and model access.

All endpoints ALWAYS return structured JSON { success, result|error, model_used, source }.
Never raises unhandled 500 to clients — errors are returned as JSON with success=False.
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, List
import logging
import time
from datetime import datetime, timezone

from auth import get_current_user
from services.huggingface_key_resolver import (
    resolve_huggingface_key,
    test_huggingface_connection,
    get_huggingface_client,
    HF_DEFAULT_MODELS,
)

logger = logging.getLogger(__name__)
router = APIRouter()

# In-memory last-success tracking (per process, resets on restart)
_hf_last_success: Optional[str] = None
_hf_last_error: Optional[str] = None
_hf_last_latency_ms: Optional[float] = None

HF_HEALTH_PROBE_TEXT = "Bitcoin price is rising today."

class HuggingFaceModelInfo(BaseModel):
    """HuggingFace model information"""
    modelId: str
    author: str
    pipeline_tag: Optional[str] = None
    tags: List[str] = []
    downloads: int = 0
    likes: int = 0


@router.get("/api/huggingface/test-connection")
async def test_connection(user_id: str = Depends(get_current_user)):
    """
    Test HuggingFace API connection with user's key.
    
    Returns:
        Status of connection test with user info if successful
        Returns 200 with not_configured status if no key is configured
    """
    try:
        result = await test_huggingface_connection(user_id)
        
        # If error is due to missing key, return not_configured status (200 OK)
        if result["status"] == "error" and "No HuggingFace API key configured" in result.get("message", ""):
            return {
                "status": "not_configured",
                "message": "No HuggingFace API key configured",
                "source": result.get("source", "missing"),
                "configured": False
            }
        
        # If other error, still return it but don't raise HTTP exception
        if result["status"] == "error":
            return {
                "status": "error",
                "message": result.get("message", "Connection test failed"),
                "source": result.get("source", "unknown"),
                "configured": True
            }
        
        # Success - ensure configured flag is present
        if result.get("status") == "success":
            result["configured"] = True
        return result
        
    except Exception as e:
        logger.error(f"Test connection error: {e}")
        # Return graceful error response instead of 500
        return {
            "status": "error",
            "message": str(e),
            "source": "unknown",
            "configured": False
        }


@router.get("/api/huggingface/models")
async def get_models(
    user_id: str = Depends(get_current_user),
    task: Optional[str] = None,
    limit: int = 20
):
    """
    Get list of available HuggingFace models.
    Always returns 200 JSON { success, models, count, source }.
    Falls back to default model list when API key is missing or Hub is unreachable.
    """
    limit = max(1, min(limit, 100))
    api_key, source = await resolve_huggingface_key(user_id)

    # Default curated model list (returned when key is missing or Hub unreachable)
    _defaults = [
        {"modelId": HF_DEFAULT_MODELS["sentiment"], "pipeline_tag": "text-classification"},
        {"modelId": HF_DEFAULT_MODELS["summarize"], "pipeline_tag": "summarization"},
        {"modelId": HF_DEFAULT_MODELS["embeddings"], "pipeline_tag": "feature-extraction"},
        {"modelId": HF_DEFAULT_MODELS["classify"], "pipeline_tag": "zero-shot-classification"},
    ]

    if not api_key:
        return {
            "success": True,
            "models": _defaults,
            "count": len(_defaults),
            "source": source,
            "task_filter": task,
            "note": "No API key configured — showing default model list",
        }

    try:
        from huggingface_hub import HfApi
        api = HfApi(token=api_key)
        models = api.list_models(filter=task, sort="downloads", direction=-1, limit=limit)
        model_list = []
        for m in models:
            model_list.append({
                "modelId": m.modelId,
                "author": getattr(m, "author", "unknown"),
                "pipeline_tag": getattr(m, "pipeline_tag", None),
                "tags": getattr(m, "tags", []),
                "downloads": getattr(m, "downloads", 0),
                "likes": getattr(m, "likes", 0),
            })
        return {
            "success": True,
            "models": model_list,
            "count": len(model_list),
            "source": source,
            "task_filter": task,
        }
    except Exception as e:
        logger.error(f"HF list_models error: {e}")
        return {
            "success": True,
            "models": _defaults,
            "count": len(_defaults),
            "source": source,
            "task_filter": task,
            "note": f"Hub unreachable, showing defaults: {str(e)[:100]}",
        }


@router.get("/api/huggingface/tasks")
async def get_available_tasks(user_id: str = Depends(get_current_user)):
    """
    Get list of available HuggingFace tasks/pipelines.
    
    Returns:
        List of available task types with descriptions
    """
    # Common HuggingFace tasks for crypto trading
    tasks = [
        {
            "id": "text-classification",
            "name": "Text Classification",
            "description": "Classify text into categories (e.g., bullish/bearish sentiment)",
            "use_case": "Sentiment analysis of news and social media"
        },
        {
            "id": "summarization",
            "name": "Summarization",
            "description": "Summarize long documents into shorter versions",
            "use_case": "Condense long analyst reports or news articles"
        },
        {
            "id": "translation",
            "name": "Translation",
            "description": "Translate text between languages",
            "use_case": "Process non-English crypto news and reports"
        },
        {
            "id": "text-generation",
            "name": "Text Generation",
            "description": "Generate text based on prompts",
            "use_case": "Generate trading insights and reports"
        },
        {
            "id": "question-answering",
            "name": "Question Answering",
            "description": "Answer questions based on context",
            "use_case": "Extract specific information from documents"
        },
        {
            "id": "zero-shot-classification",
            "name": "Zero-Shot Classification",
            "description": "Classify text without training data",
            "use_case": "Classify news into custom categories"
        },
        {
            "id": "feature-extraction",
            "name": "Feature Extraction",
            "description": "Extract embeddings from text",
            "use_case": "Text similarity and clustering analysis"
        }
    ]
    
    return {
        "success": True,
        "tasks": tasks,
        "count": len(tasks)
    }


@router.post("/api/huggingface/analyze-sentiment")
async def analyze_sentiment(
    data: dict,
    user_id: str = Depends(get_current_user)
):
    """
    Analyze sentiment of text using HuggingFace models.
    Always returns structured JSON { success, result, model_used, latency_ms, source }.
    """
    t0 = time.monotonic()
    text = (data.get("text") or "").strip()
    if not text:
        return {"success": False, "error": "text is required", "model_used": None, "result": None, "source": "none"}

    model = data.get("model") or HF_DEFAULT_MODELS["sentiment"]

    try:
        client, source = await get_huggingface_client(user_id, model=model)

        if not client:
            return {
                "success": False,
                "error": "No HuggingFace API key configured. Add your key in API Setup.",
                "model_used": model,
                "result": None,
                "source": source,
            }

        try:
            raw = client.text_classification(text)
            item = raw[0] if raw else {}
            latency_ms = round((time.monotonic() - t0) * 1000, 1)
            return {
                "success": True,
                "result": {"label": item.get("label"), "score": item.get("score")},
                "model_used": model,
                "latency_ms": latency_ms,
                "source": source,
            }
        except Exception as infer_err:
            logger.error(f"HF sentiment inference error: {infer_err}")
            return {
                "success": False,
                "error": str(infer_err),
                "model_used": model,
                "result": None,
                "source": source,
            }

    except Exception as e:
        logger.error(f"Analyze sentiment outer error: {e}")
        return {"success": False, "error": str(e), "model_used": model, "result": None, "source": "error"}


@router.post("/api/huggingface/summarize")
async def summarize_text(
    data: dict,
    user_id: str = Depends(get_current_user)
):
    """
    Summarize text using HuggingFace models.
    Always returns structured JSON { success, result, model_used, latency_ms, source }.
    """
    t0 = time.monotonic()
    text = (data.get("text") or "").strip()
    if not text:
        return {"success": False, "error": "text is required", "model_used": None, "result": None, "source": "none"}

    max_length = data.get("max_length", 150)
    model = data.get("model") or HF_DEFAULT_MODELS["summarize"]

    try:
        client, source = await get_huggingface_client(user_id, model=model)

        if not client:
            return {
                "success": False,
                "error": "No HuggingFace API key configured. Add your key in API Setup.",
                "model_used": model,
                "result": None,
                "source": source,
            }

        try:
            raw = client.summarization(text, parameters={"max_length": max_length})
            summary = raw[0].get("summary_text", "") if raw else ""
            latency_ms = round((time.monotonic() - t0) * 1000, 1)
            return {
                "success": True,
                "result": {"summary": summary},
                "model_used": model,
                "latency_ms": latency_ms,
                "source": source,
            }
        except Exception as infer_err:
            logger.error(f"HF summarize error: {infer_err}")
            return {
                "success": False,
                "error": str(infer_err),
                "model_used": model,
                "result": None,
                "source": source,
            }

    except Exception as e:
        logger.error(f"Summarize outer error: {e}")
        return {"success": False, "error": str(e), "model_used": model, "result": None, "source": "error"}


@router.post("/api/huggingface/classify")
async def classify_text(
    data: dict,
    user_id: str = Depends(get_current_user)
):
    """
    Zero-shot classification using HuggingFace.
    Always returns structured JSON { success, result, model_used, latency_ms, source }.
    """
    t0 = time.monotonic()
    text = (data.get("text") or "").strip()
    labels = data.get("labels", [])

    if not text:
        return {"success": False, "error": "text is required", "model_used": None, "result": None, "source": "none"}
    if not labels:
        return {"success": False, "error": "labels required for classify", "model_used": None, "result": None, "source": "none"}

    model = data.get("model") or HF_DEFAULT_MODELS["classify"]

    try:
        client, source = await get_huggingface_client(user_id, model=model)

        if not client:
            return {
                "success": False,
                "error": "No HuggingFace API key configured. Add your key in API Setup.",
                "model_used": model,
                "result": None,
                "source": source,
            }

        try:
            raw = client.zero_shot_classification(text, labels, multi_label=False)
            latency_ms = round((time.monotonic() - t0) * 1000, 1)
            return {
                "success": True,
                "result": {"labels": raw.get("labels", []), "scores": raw.get("scores", [])},
                "model_used": model,
                "latency_ms": latency_ms,
                "source": source,
            }
        except Exception as infer_err:
            logger.error(f"HF classify error: {infer_err}")
            return {
                "success": False,
                "error": str(infer_err),
                "model_used": model,
                "result": None,
                "source": source,
            }

    except Exception as e:
        logger.error(f"Classify outer error: {e}")
        return {"success": False, "error": str(e), "model_used": model, "result": None, "source": "error"}


@router.post("/api/huggingface/embeddings")
async def generate_embeddings(
    data: dict,
    user_id: str = Depends(get_current_user)
):
    """
    Generate text embeddings using HuggingFace sentence transformers.
    Always returns structured JSON { success, result, model_used, latency_ms, source }.
    """
    t0 = time.monotonic()
    text = (data.get("text") or "").strip()
    if not text:
        return {"success": False, "error": "text is required", "model_used": None, "result": None, "source": "none"}

    model = data.get("model") or HF_DEFAULT_MODELS["embeddings"]

    try:
        client, source = await get_huggingface_client(user_id, model=model)

        if not client:
            return {
                "success": False,
                "error": "No HuggingFace API key configured. Add your key in API Setup.",
                "model_used": model,
                "result": None,
                "source": source,
            }

        try:
            raw = client.feature_extraction(text)
            # HuggingFace returns nested lists — take mean pooling
            if isinstance(raw, list) and len(raw) > 0:
                if isinstance(raw[0], list):
                    import numpy as np
                    embeddings = list(map(float, np.mean(raw, axis=0)))
                else:
                    embeddings = [float(v) for v in raw]
            else:
                embeddings = []
            latency_ms = round((time.monotonic() - t0) * 1000, 1)
            return {
                "success": True,
                "result": {"embeddings": embeddings, "dimensions": len(embeddings)},
                "model_used": model,
                "latency_ms": latency_ms,
                "source": source,
            }
        except Exception as infer_err:
            logger.error(f"HF embeddings error: {infer_err}")
            return {
                "success": False,
                "error": str(infer_err),
                "model_used": model,
                "result": None,
                "source": source,
            }

    except Exception as e:
        logger.error(f"Embeddings outer error: {e}")
        return {"success": False, "error": str(e), "model_used": model, "result": None, "source": "error"}


# ============================================================================
# HuggingFace Status + Minimal Infer Endpoints  (F1)
# ============================================================================

@router.get("/api/hf/status")
async def get_hf_status(user_id: str = Depends(get_current_user)):
    """
    Get HuggingFace integration health/status.

    Returns:
        status: "connected" | "disabled" | "error"
        enabled: bool  – whether a HF key is configured
        model: str     – model used for last health probe
        last_success_at: ISO timestamp or null
        last_error: last error message or null
        latency_ms: latency of last successful inference or null
    """
    global _hf_last_success, _hf_last_error, _hf_last_latency_ms
    try:
        api_key, source = await resolve_huggingface_key(user_id)
        enabled = bool(api_key)
        model_id = "distilbert-base-uncased-finetuned-sst-2-english"

        if not enabled:
            return {
                "status": "disabled",
                "enabled": False,
                "model": model_id,
                "source": source,
                "last_success_at": None,
                "last_error": "No HuggingFace API key configured",
                "latency_ms": None,
            }

        if _hf_last_success is None:
            # Run a lightweight health probe on first call using whoami (no inference needed)
            t0 = time.monotonic()
            try:
                from huggingface_hub import HfApi
                api = HfApi(token=api_key)
                api.whoami()  # Validates token without hitting inference endpoint
                _hf_last_latency_ms = round((time.monotonic() - t0) * 1000, 1)
                _hf_last_success = datetime.now(timezone.utc).isoformat()
                _hf_last_error = None
            except Exception as probe_err:
                err_msg = str(probe_err)
                _hf_last_error = err_msg
                logger.warning("HF health probe failed (will not retry until restart): %s", err_msg[:200])

        # Determine status field
        if _hf_last_success is not None:
            hf_status = "connected"
        elif _hf_last_error:
            hf_status = "error"
        else:
            hf_status = "disabled"

        return {
            "status": hf_status,
            "enabled": enabled,
            "model": model_id,
            "source": source,
            "last_success_at": _hf_last_success,
            "last_error": _hf_last_error,
            "latency_ms": _hf_last_latency_ms,
        }
    except Exception as e:
        logger.error(f"HF status error: {e}")
        return {"status": "error", "enabled": False, "model": None, "last_success_at": None,
                "last_error": str(e), "latency_ms": None}


@router.post("/api/hf/infer")
async def hf_infer(data: dict, user_id: str = Depends(get_current_user)):
    """
    Minimal safe HuggingFace inference endpoint.

    Accepts:
        text: str – input text (max 512 chars for safety)
        task: str – "sentiment" | "summarize" | "classify" (default: sentiment)
        labels: list[str] – required for task=classify
        model: str – optional model override

    Returns sanitised inference output.  Errors are returned as JSON (never 500).
    """
    global _hf_last_success, _hf_last_error, _hf_last_latency_ms

    text = (data.get("text") or "").strip()[:512]
    if not text:
        raise HTTPException(status_code=400, detail="text is required (max 512 chars)")

    task = data.get("task", "sentiment").lower()
    labels = data.get("labels") or []
    model_override = data.get("model")

    try:
        DEFAULT_MODELS = {
            "sentiment": "distilbert-base-uncased-finetuned-sst-2-english",
            "summarize": "facebook/bart-large-cnn",
            "classify": "facebook/bart-large-mnli",
        }
        model_id = model_override or DEFAULT_MODELS.get(task, DEFAULT_MODELS["sentiment"])
        client, source = await get_huggingface_client(user_id, model=model_id)
        if not client:
            raise HTTPException(
                status_code=400,
                detail={"error": "No HuggingFace API key configured. Add your key in API Setup.",
                        "action": "Add HF token"}
            )

        t0 = time.monotonic()
        try:
            if task == "summarize":
                raw = client.summarization(text, parameters={"max_length": 150})
                result = {"summary": raw[0].get("summary_text", "") if raw else ""}
            elif task == "classify":
                if not labels:
                    raise HTTPException(status_code=400, detail="labels required for task=classify")
                raw = client.zero_shot_classification(text, labels, multi_label=False)
                result = {"labels": raw.get("labels", []), "scores": raw.get("scores", [])}
            else:  # default: sentiment
                raw = client.text_classification(text)
                item = raw[0] if raw else {}
                result = {"label": item.get("label"), "score": item.get("score")}

            latency = round((time.monotonic() - t0) * 1000, 1)
            _hf_last_latency_ms = latency
            _hf_last_success = datetime.now(timezone.utc).isoformat()
            _hf_last_error = None

            return {"success": True, "task": task, "model": model_id,
                    "source": source, "latency_ms": latency, "result": result}

        except HTTPException:
            raise
        except Exception as infer_err:
            _hf_last_error = str(infer_err)
            logger.error(f"HF infer task={task} error: {infer_err}")
            return {"success": False, "task": task, "model": model_id,
                    "error": str(infer_err), "result": None}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"HF infer outer error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
