"""
JSON Serialization Utilities
Handles MongoDB ObjectId and other non-JSON-serializable types,
plus safe numeric coercion and decision-payload sanitization.
"""

from bson import ObjectId
from datetime import datetime
from typing import Any, Dict, List, Union
import logging

logger = logging.getLogger(__name__)


def serialize_doc(doc: Any) -> Any:
    """
    Recursively serialize MongoDB documents to JSON-safe format
    
    Handles:
    - ObjectId -> str
    - datetime -> ISO string
    - Nested dicts and lists
    - None values
    
    Args:
        doc: Document to serialize (dict, list, or primitive)
        
    Returns:
        JSON-serializable version of doc
    """
    if doc is None:
        return None
    
    if isinstance(doc, ObjectId):
        return str(doc)
    
    if isinstance(doc, datetime):
        return doc.isoformat()
    
    if isinstance(doc, dict):
        return {key: serialize_doc(value) for key, value in doc.items()}
    
    if isinstance(doc, list):
        return [serialize_doc(item) for item in doc]
    
    if isinstance(doc, tuple):
        return tuple(serialize_doc(item) for item in doc)
    
    # Primitive types (str, int, float, bool) pass through
    return doc


def serialize_mongo_doc(doc: Dict[str, Any], exclude_fields: List[str] = None) -> Dict[str, Any]:
    """
    Serialize a MongoDB document and optionally exclude sensitive fields
    
    Args:
        doc: MongoDB document
        exclude_fields: List of field names to exclude (e.g., ['password_hash', '_id'])
        
    Returns:
        Serialized dict with excluded fields removed
    """
    if doc is None:
        return {}
    
    if exclude_fields is None:
        exclude_fields = []
    
    # Remove excluded fields
    filtered_doc = {k: v for k, v in doc.items() if k not in exclude_fields}
    
    # Serialize to JSON-safe format
    return serialize_doc(filtered_doc)


def serialize_list(docs: List[Dict[str, Any]], exclude_fields: List[str] = None) -> List[Dict[str, Any]]:
    """
    Serialize a list of MongoDB documents
    
    Args:
        docs: List of MongoDB documents
        exclude_fields: Fields to exclude from each document
        
    Returns:
        List of serialized documents
    """
    if not docs:
        return []
    
    return [serialize_mongo_doc(doc, exclude_fields) for doc in docs]


# Re-export numeric utilities for backwards compatibility.
# These live in utils/numeric_utils.py to avoid a circular import with bson.
from utils.numeric_utils import safe_numeric, sanitize_numeric_dict  # noqa: E402,F401
