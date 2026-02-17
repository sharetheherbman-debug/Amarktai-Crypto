"""
HuggingFace Integration Routes
Provides endpoints for HuggingFace API key management and model access.
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, List
import logging

from auth import get_current_user
from services.huggingface_key_resolver import (
    resolve_huggingface_key,
    test_huggingface_connection,
    get_huggingface_client
)

logger = logging.getLogger(__name__)
router = APIRouter()


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
    """
    try:
        result = await test_huggingface_connection(user_id)
        
        if result["status"] == "error":
            raise HTTPException(status_code=400, detail=result)
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Test connection error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
