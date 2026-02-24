"""
HuggingFace Integration Routes
Provides endpoints for HuggingFace API key management and model access.
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
    get_huggingface_client
)

logger = logging.getLogger(__name__)
router = APIRouter()

# In-memory last-success tracking (per process, resets on restart)
_hf_last_success: Optional[str] = None
_hf_last_error: Optional[str] = None
_hf_last_latency_ms: Optional[float] = None

# Lightweight probe input used by the health check
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
    
    Args:
        task: Filter by task (e.g., "text-classification", "sentiment-analysis", "summarization")
        limit: Maximum number of models to return (default: 20, max: 100)
        
    Returns:
        List of available models with metadata
    """
    try:
        # Validate limit
        if limit < 1 or limit > 100:
            raise HTTPException(status_code=400, detail="Limit must be between 1 and 100")
        
        api_key, source = await resolve_huggingface_key(user_id)
        
        if not api_key:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "No HuggingFace API key configured",
                    "source": source
                }
            )
        
        # Fetch models from HuggingFace Hub
        try:
            from huggingface_hub import HfApi
            
            api = HfApi(token=api_key)
            
            # Get models, optionally filtered by task
            models = api.list_models(
                filter=task,
                sort="downloads",
                direction=-1,
                limit=limit
            )
            
            # Convert to list and extract relevant info
            model_list = []
            for model in models:
                model_info = {
                    "modelId": model.modelId,
                    "author": model.author if hasattr(model, "author") else "unknown",
                    "pipeline_tag": model.pipeline_tag if hasattr(model, "pipeline_tag") else None,
                    "tags": model.tags if hasattr(model, "tags") else [],
                    "downloads": model.downloads if hasattr(model, "downloads") else 0,
                    "likes": model.likes if hasattr(model, "likes") else 0
                }
                model_list.append(model_info)
            
            return {
                "success": True,
                "models": model_list,
                "count": len(model_list),
                "source": source,
                "task_filter": task
            }
            
        except Exception as e:
            logger.error(f"Failed to fetch models from HuggingFace: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to fetch models: {str(e)}"
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get models error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
    
    Args:
        text: Text to analyze
        model: Optional model to use (defaults to popular sentiment model)
        
    Returns:
        Sentiment analysis results
    """
    try:
        text = data.get("text")
        if not text:
            raise HTTPException(status_code=400, detail="Text is required")
        
        model = data.get("model", "distilbert-base-uncased-finetuned-sst-2-english")
        
        client, source = await get_huggingface_client(user_id, model=model)
        
        if not client:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "No HuggingFace API key configured",
                    "source": source
                }
            )
        
        # Perform sentiment analysis
        try:
            result = client.text_classification(text)
            
            return {
                "success": True,
                "text": text,
                "model": model,
                "sentiment": result[0]["label"] if result else "neutral",
                "confidence": result[0]["score"] if result else 0.0,
                "source": source,
                "raw_result": result
            }
            
        except Exception as e:
            logger.error(f"Sentiment analysis failed: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Sentiment analysis failed: {str(e)}"
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Analyze sentiment error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/huggingface/summarize")
async def summarize_text(
    data: dict,
    user_id: str = Depends(get_current_user)
):
    """
    Summarize text using HuggingFace models.
    
    Args:
        text: Text to summarize
        max_length: Maximum length of summary
        model: Optional model to use
        
    Returns:
        Summarized text
    """
    try:
        text = data.get("text")
        if not text:
            raise HTTPException(status_code=400, detail="Text is required")
        
        max_length = data.get("max_length", 150)
        model = data.get("model", "facebook/bart-large-cnn")
        
        client, source = await get_huggingface_client(user_id, model=model)
        
        if not client:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "No HuggingFace API key configured",
                    "source": source
                }
            )
        
        # Perform summarization
        try:
            result = client.summarization(
                text,
                parameters={"max_length": max_length}
            )
            
            summary = result[0]["summary_text"] if result else ""
            
            return {
                "success": True,
                "original_text": text,
                "summary": summary,
                "model": model,
                "source": source,
                "original_length": len(text),
                "summary_length": len(summary)
            }
            
        except Exception as e:
            logger.error(f"Summarization failed: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Summarization failed: {str(e)}"
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Summarize error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/huggingface/classify")
async def classify_text(
    data: dict,
    user_id: str = Depends(get_current_user)
):
    """
    Perform zero-shot classification on text using HuggingFace.
    
    Allows classifying text into custom categories without training.
    Uses facebook/bart-large-mnli or similar zero-shot models.
    
    Args:
        data: Dictionary containing:
            - text (str): Text to classify
            - labels (list): List of classification labels
            - model (str, optional): Model to use (default: facebook/bart-large-mnli)
            
    Returns:
        Classification results with labels and scores
    """
    try:
        text = data.get("text")
        labels = data.get("labels", [])
        
        if not text:
            raise HTTPException(status_code=400, detail="Text is required")
        
        if not labels or len(labels) == 0:
            raise HTTPException(status_code=400, detail="At least one label is required")
        
        model = data.get("model", "facebook/bart-large-mnli")
        
        client, source = await get_huggingface_client(user_id, model=model)
        
        if not client:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "No HuggingFace API key configured",
                    "source": source
                }
            )
        
        # Perform zero-shot classification
        try:
            result = client.zero_shot_classification(
                text,
                labels,
                multi_label=False
            )
            
            return {
                "success": True,
                "text": text,
                "labels": result.get("labels", []),
                "scores": result.get("scores", []),
                "model": model,
                "source": source
            }
            
        except Exception as e:
            logger.error(f"Classification failed: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Classification failed: {str(e)}"
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Classify error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/huggingface/embeddings")
async def generate_embeddings(
    data: dict,
    user_id: str = Depends(get_current_user)
):
    """
    Generate text embeddings using HuggingFace sentence transformers.
    
    Useful for semantic similarity, clustering, and RL feature extraction.
    Uses sentence-transformers/all-MiniLM-L6-v2 or similar models.
    
    Args:
        data: Dictionary containing:
            - text (str): Text to generate embeddings for
            - model (str, optional): Model to use (default: sentence-transformers/all-MiniLM-L6-v2)
            
    Returns:
        Embedding vector as a list of floats
    """
    try:
        text = data.get("text")
        
        if not text:
            raise HTTPException(status_code=400, detail="Text is required")
        
        model = data.get("model", "sentence-transformers/all-MiniLM-L6-v2")
        
        client, source = await get_huggingface_client(user_id, model=model)
        
        if not client:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "No HuggingFace API key configured",
                    "source": source
                }
            )
        
        # Generate embeddings
        try:
            result = client.feature_extraction(text)
            
            # HuggingFace returns nested lists, flatten to 1D vector
            if isinstance(result, list) and len(result) > 0:
                if isinstance(result[0], list):
                    # Take mean pooling if multiple token embeddings
                    import numpy as np
                    embeddings = np.mean(result, axis=0).tolist()
                else:
                    embeddings = result
            else:
                embeddings = []
            
            return {
                "success": True,
                "text": text,
                "embeddings": embeddings,
                "dimensions": len(embeddings),
                "model": model,
                "source": source
            }
            
        except Exception as e:
            logger.error(f"Embeddings generation failed: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Embeddings generation failed: {str(e)}"
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Embeddings error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
            # Run a lightweight health probe on first call
            t0 = time.monotonic()
            try:
                client, _ = await get_huggingface_client(user_id, model=model_id)
                if client:
                    _ = client.text_classification(HF_HEALTH_PROBE_TEXT)
                    _hf_last_latency_ms = round((time.monotonic() - t0) * 1000, 1)
                    _hf_last_success = datetime.now(timezone.utc).isoformat()
                    _hf_last_error = None
            except Exception as probe_err:
                err_msg = str(probe_err)
                # Rate-limit error logging: only store the message, avoid log spam
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
