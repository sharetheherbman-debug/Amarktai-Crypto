"""
Backtesting API Routes
Provides endpoints for backtesting trading strategies
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional, Dict
from datetime import datetime, timezone, timedelta
import logging

from auth import get_current_user
from backtesting_engine import BacktestingEngine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/backtest", tags=["Backtesting"])

# Initialize backtesting engine
backtest_engine = BacktestingEngine()


class BacktestRequest(BaseModel):
    """Request to run a backtest"""
    strategy_params: Dict = Field(..., description="Strategy parameters")
    start_date: str = Field(..., description="Start date (ISO format)")
    end_date: str = Field(..., description="End date (ISO format)")
    initial_capital: float = Field(1000, description="Initial capital", gt=0)
    pair: Optional[str] = Field("BTC/ZAR", description="Trading pair")
    exchange: Optional[str] = Field("binance", description="Exchange")


class BacktestOptimizeRequest(BaseModel):
    """Request to optimize strategy parameters"""
    parameter_ranges: Dict = Field(..., description="Parameter ranges to test")
    start_date: str = Field(..., description="Start date (ISO format)")
    end_date: str = Field(..., description="End date (ISO format)")
    initial_capital: float = Field(1000, description="Initial capital", gt=0)
    optimization_metric: str = Field("sharpe_ratio", description="Metric to optimize")


@router.post("/run")
async def run_backtest(
    request: BacktestRequest,
    user_id: str = Depends(get_current_user)
):
    """Run a backtest for a trading strategy
    
    Args:
        request: Backtest configuration
        user_id: Current user ID
        
    Returns:
        Backtest results with performance metrics
    """
    try:
        logger.info(f"Running backtest for user {user_id[:8]}: {request.start_date} to {request.end_date}")
        
        # Validate dates
        try:
            start = datetime.fromisoformat(request.start_date.replace('Z', '+00:00'))
            end = datetime.fromisoformat(request.end_date.replace('Z', '+00:00'))
            
            if start >= end:
                raise HTTPException(
                    status_code=400,
                    detail="Start date must be before end date"
                )
            
            # Check date range (max 1 year)
            max_days = 365
            if (end - start).days > max_days:
                raise HTTPException(
                    status_code=400,
                    detail=f"Date range too large (max {max_days} days)"
                )
                
        except ValueError as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid date format: {str(e)}"
            )
        
        # Run backtest
        result = await backtest_engine.backtest_strategy(
            strategy_params=request.strategy_params,
            start_date=request.start_date,
            end_date=request.end_date,
            initial_capital=request.initial_capital
        )
        
        if "error" in result:
            raise HTTPException(status_code=500, detail=result["error"])
        
        # Add metadata
        result["user_id"] = user_id
        result["pair"] = request.pair
        result["exchange"] = request.exchange
        
        return {
            "success": True,
            "backtest": result
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Backtest error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/optimize")
async def optimize_strategy(
    request: BacktestOptimizeRequest,
    user_id: str = Depends(get_current_user)
):
    """Optimize strategy parameters using grid search
    
    Args:
        request: Optimization configuration
        user_id: Current user ID
        
    Returns:
        Best parameters and performance comparison
    """
    try:
        logger.info(f"Optimizing strategy for user {user_id[:8]}")

        # Validate dates
        try:
            start = datetime.fromisoformat(request.start_date.replace('Z', '+00:00'))
            end = datetime.fromisoformat(request.end_date.replace('Z', '+00:00'))
            if start >= end:
                raise HTTPException(status_code=400, detail="Start date must be before end date")
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid date format: {str(e)}")

        # Small bounded parameter grid (max 27 combinations)
        # risk_mode × stop_loss × take_profit
        from itertools import product as iterproduct

        risk_modes = request.parameter_ranges.get("risk_mode", ["safe", "balanced", "risky"])
        stop_losses = request.parameter_ranges.get("stop_loss", [0.03, 0.05, 0.08])
        take_profits = request.parameter_ranges.get("take_profit", [0.06, 0.10, 0.15])

        # Clamp to max 30 combos
        all_combos = list(iterproduct(risk_modes[:3], stop_losses[:3], take_profits[:3]))
        MAX_COMBOS = 30
        combos = all_combos[:MAX_COMBOS]

        metric = request.optimization_metric  # e.g. "sharpe_ratio", "total_return", "win_rate"

        best_result = None
        best_score = float('-inf')
        all_results = []

        timeout_per_run = 5.0  # seconds per backtest run
        import asyncio as _asyncio

        for risk_mode, stop_loss, take_profit in combos:
            params = {
                "risk_mode": risk_mode,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "position_size": 0.15,
            }
            try:
                result = await _asyncio.wait_for(
                    backtest_engine.backtest_strategy(
                        strategy_params=params,
                        start_date=request.start_date,
                        end_date=request.end_date,
                        initial_capital=request.initial_capital,
                    ),
                    timeout=timeout_per_run,
                )
                metrics = result.get("metrics", {})
                raw = metrics.get(metric)
                if raw is None:
                    raw = metrics.get("total_return")
                score = raw if raw is not None else 0.0
                all_results.append({
                    "parameters": params,
                    "score": score,
                    "metric": metric,
                    "metrics": metrics,
                    "is_simulated": result.get("is_simulated", True),
                })
                if score > best_score:
                    best_score = score
                    best_result = result
                    best_result["_params"] = params
            except _asyncio.TimeoutError:
                logger.warning(f"Backtest combo {params} timed out")
                continue
            except Exception as combo_err:
                logger.warning(f"Backtest combo {params} failed: {combo_err}")
                continue

        if not all_results:
            raise HTTPException(status_code=500, detail="All parameter combinations failed or timed out.")

        all_results.sort(key=lambda x: x["score"], reverse=True)

        return {
            "success": True,
            "best_parameters": best_result.get("_params") if best_result else all_results[0]["parameters"],
            "best_score": best_score,
            "optimization_metric": metric,
            "grid_search": True,
            "tested_combinations": len(all_results),
            "max_combinations": MAX_COMBOS,
            "all_results": all_results,
            "is_simulated": True,
            "simulation_note": "Results are based on statistical simulation, not real historical CCXT data.",
            "best_backtest_result": best_result,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Optimization error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history")
async def get_backtest_history(
    limit: int = 10,
    user_id: str = Depends(get_current_user)
):
    """Get backtest history for current user
    
    Args:
        limit: Maximum number of results
        user_id: Current user ID
        
    Returns:
        List of previous backtests
    """
    try:
        # In production, would query database for saved backtests
        # For now, return empty list
        return {
            "success": True,
            "backtests": [],
            "total": 0,
            "message": "No backtest history yet. Run /api/backtest/run to create one."
        }
        
    except Exception as e:
        logger.error(f"Get backtest history error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
