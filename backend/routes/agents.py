"""
Agent Management Routes
Provides endpoints for creating and monitoring Fetch.ai trading agents.
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone
import logging

from auth import get_current_user, is_admin
import database as db

logger = logging.getLogger(__name__)
router = APIRouter()


class AgentCreateRequest(BaseModel):
    """Request model for creating a new agent"""
    name: str
    type: str  # 'fetchai'
    strategy: str  # 'adaptive', 'trend', 'mean_reversion', 'momentum'
    capital: float
    risk_tier: str  # 'safe', 'balanced', 'risky'
    exchange: Optional[str] = 'luno'
    pair: Optional[str] = 'BTC/ZAR'


@router.post("/api/agents/create")
async def create_agent(
    request: AgentCreateRequest,
    user_id: str = Depends(get_current_user)
):
    """
    Create a new Fetch.ai trading agent.
    
    Args:
        request: Agent configuration including type, strategy, capital, and risk tier
        
    Returns:
        Created agent details with ID and status
    """
    try:
        # Validate agent type
        if request.type not in ['fetchai']:
            raise HTTPException(
                status_code=400,
                detail="Agent type must be 'fetchai'"
            )
        
        # Validate strategy
        valid_strategies = ['adaptive', 'trend', 'mean_reversion', 'momentum']
        if request.strategy not in valid_strategies:
            raise HTTPException(
                status_code=400,
                detail=f"Strategy must be one of: {', '.join(valid_strategies)}"
            )
        
        # Validate risk tier
        valid_risk_tiers = ['safe', 'balanced', 'risky']
        if request.risk_tier not in valid_risk_tiers:
            raise HTTPException(
                status_code=400,
                detail=f"Risk tier must be one of: {', '.join(valid_risk_tiers)}"
            )
        
        # Validate capital
        if request.capital < 100:
            raise HTTPException(
                status_code=400,
                detail="Minimum capital is R 100"
            )
        
        # Check database connection
        if db.db is None:
            raise HTTPException(status_code=503, detail="Database not connected")
        
        # Get user to verify they exist
        user = await db.users_collection.find_one({"id": user_id})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Check for duplicate agent names
        existing_agent = await db.db.agents.find_one({
            "user_id": user_id,
            "name": request.name,
            "status": {"$ne": "deleted"}
        })
        
        if existing_agent:
            raise HTTPException(
                status_code=400,
                detail=f"Agent with name '{request.name}' already exists"
            )
        
        # Create agent document
        agent_doc = {
            "user_id": user_id,
            "name": request.name,
            "type": request.type,
            "strategy": request.strategy,
            "capital": request.capital,
            "risk_tier": request.risk_tier,
            "exchange": request.exchange,
            "pair": request.pair,
            "status": "active",
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            "trades_count": 0,
            "total_profit": 0.0,
            "last_action": None,
            "metadata": {
                "framework": "fetch.ai",
                "version": "1.0.0"
            }
        }
        
        # Insert into database
        result = await db.db.agents.insert_one(agent_doc)
        agent_id = str(result.inserted_id)
        
        logger.info(f"Created {request.type} agent '{request.name}' for user {user_id[:8]}")
        
        # Return created agent
        return {
            "success": True,
            "agent": {
                "id": agent_id,
                "name": request.name,
                "type": request.type,
                "strategy": request.strategy,
                "capital": request.capital,
                "risk_tier": request.risk_tier,
                "exchange": request.exchange,
                "pair": request.pair,
                "status": "active",
                "created_at": agent_doc["created_at"].isoformat()
            },
            "message": f"{request.type.capitalize()} agent created successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Agent creation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/agents/status")
async def get_agents_status(user_id: str = Depends(get_current_user)):
    """
    Get status of all agents for the current user.
    
    Returns:
        List of agents with their current status, performance, and metadata
    """
    try:
        if db.db is None:
            raise HTTPException(status_code=503, detail="Database not connected")
        
        # Fetch all active agents for user
        agents_cursor = db.db.agents.find({
            "user_id": user_id,
            "status": {"$ne": "deleted"}
        }).sort("created_at", -1)
        
        agents = await agents_cursor.to_list(length=100)
        
        # Format agent data
        agent_list = []
        for agent in agents:
            agent_list.append({
                "id": str(agent["_id"]),
                "name": agent.get("name", "Unknown"),
                "type": agent.get("type", "unknown"),
                "strategy": agent.get("strategy", "unknown"),
                "capital": agent.get("capital", 0.0),
                "risk_tier": agent.get("risk_tier", "balanced"),
                "exchange": agent.get("exchange", "unknown"),
                "pair": agent.get("pair", "unknown"),
                "status": agent.get("status", "unknown"),
                "created_at": agent.get("created_at").isoformat() if agent.get("created_at") else None,
                "trades_count": agent.get("trades_count", 0),
                "total_profit": agent.get("total_profit", 0.0),
                "last_action": agent.get("last_action"),
                "metadata": agent.get("metadata", {})
            })
        
        return {
            "success": True,
            "agents": agent_list,
            "count": len(agent_list),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get agents status error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/api/agents/{agent_id}")
async def delete_agent(
    agent_id: str,
    user_id: str = Depends(get_current_user)
):
    """
    Delete (soft delete) an agent.
    
    Args:
        agent_id: ID of the agent to delete
        
    Returns:
        Confirmation of deletion
    """
    try:
        if db.db is None:
            raise HTTPException(status_code=503, detail="Database not connected")
        
        # Find agent
        from bson import ObjectId
        
        try:
            agent_oid = ObjectId(agent_id)
        except:
            raise HTTPException(status_code=400, detail="Invalid agent ID")
        
        agent = await db.db.agents.find_one({
            "_id": agent_oid,
            "user_id": user_id
        })
        
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        
        # Soft delete
        await db.db.agents.update_one(
            {"_id": agent_oid},
            {
                "$set": {
                    "status": "deleted",
                    "updated_at": datetime.now(timezone.utc),
                    "deleted_at": datetime.now(timezone.utc)
                }
            }
        )
        
        logger.info(f"Deleted agent {agent_id} for user {user_id[:8]}")
        
        return {
            "success": True,
            "message": "Agent deleted successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete agent error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/agents/{agent_id}/pause")
async def pause_agent(
    agent_id: str,
    user_id: str = Depends(get_current_user)
):
    """
    Pause an active agent.
    
    Args:
        agent_id: ID of the agent to pause
        
    Returns:
        Updated agent status
    """
    try:
        if db.db is None:
            raise HTTPException(status_code=503, detail="Database not connected")
        
        from bson import ObjectId
        
        try:
            agent_oid = ObjectId(agent_id)
        except:
            raise HTTPException(status_code=400, detail="Invalid agent ID")
        
        agent = await db.db.agents.find_one({
            "_id": agent_oid,
            "user_id": user_id
        })
        
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        
        if agent.get("status") != "active":
            raise HTTPException(
                status_code=400,
                detail=f"Agent is {agent.get('status')}, cannot pause"
            )
        
        # Update status
        await db.db.agents.update_one(
            {"_id": agent_oid},
            {
                "$set": {
                    "status": "paused",
                    "updated_at": datetime.now(timezone.utc)
                }
            }
        )
        
        logger.info(f"Paused agent {agent_id} for user {user_id[:8]}")
        
        return {
            "success": True,
            "status": "paused",
            "message": "Agent paused successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Pause agent error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/agents/{agent_id}/resume")
async def resume_agent(
    agent_id: str,
    user_id: str = Depends(get_current_user)
):
    """
    Resume a paused agent.
    
    Args:
        agent_id: ID of the agent to resume
        
    Returns:
        Updated agent status
    """
    try:
        if db.db is None:
            raise HTTPException(status_code=503, detail="Database not connected")
        
        from bson import ObjectId
        
        try:
            agent_oid = ObjectId(agent_id)
        except:
            raise HTTPException(status_code=400, detail="Invalid agent ID")
        
        agent = await db.db.agents.find_one({
            "_id": agent_oid,
            "user_id": user_id
        })
        
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        
        if agent.get("status") != "paused":
            raise HTTPException(
                status_code=400,
                detail=f"Agent is {agent.get('status')}, cannot resume"
            )
        
        # Update status
        await db.db.agents.update_one(
            {"_id": agent_oid},
            {
                "$set": {
                    "status": "active",
                    "updated_at": datetime.now(timezone.utc)
                }
            }
        )
        
        logger.info(f"Resumed agent {agent_id} for user {user_id[:8]}")
        
        return {
            "success": True,
            "status": "active",
            "message": "Agent resumed successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Resume agent error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
