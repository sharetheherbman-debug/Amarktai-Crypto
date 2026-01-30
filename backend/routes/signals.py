"""
External Signals Integration
Ingest trading signals from external sources like TradingView and Telegram

Features:
- TradingView webhook handler
- Telegram bot integration
- Signal validation and processing
- Feed signals into ML predictor
"""

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from typing import Optional, Dict, List
import logging
from datetime import datetime, timezone

from auth import get_current_user
import database as db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/signals", tags=["External Signals"])


class TradingViewSignal(BaseModel):
    symbol: str
    action: str  # buy, sell, close
    price: Optional[float] = None
    strategy: Optional[str] = None
    timestamp: Optional[str] = None


class TelegramSignal(BaseModel):
    chat_id: str
    message: str
    symbol: Optional[str] = None
    action: Optional[str] = None


@router.post("/tradingview/webhook")
async def tradingview_webhook(signal: TradingViewSignal, request: Request):
    """
    TradingView webhook handler
    
    Receives trading signals from TradingView alerts and processes them
    """
    try:
        logger.info(f"TradingView signal received: {signal.symbol} {signal.action}")
        
        # Validate signal format
        if not signal.symbol or not signal.action:
            raise HTTPException(status_code=400, detail="Missing required fields: symbol and action")
        
        # Validate action
        valid_actions = ['buy', 'sell', 'close', 'hold']
        if signal.action.lower() not in valid_actions:
            raise HTTPException(status_code=400, detail=f"Invalid action. Must be one of: {valid_actions}")
        
        # Validate symbol format (should contain /)
        if '/' not in signal.symbol:
            # Try to add /ZAR or /USDT
            if signal.symbol.endswith('ZAR'):
                pass  # Already has ZAR
            else:
                signal.symbol = f"{signal.symbol}/ZAR"  # Default to ZAR pairs
        
        # Check if signal is from authorized source (basic IP/header check)
        # In production, should verify webhook signature
        user_agent = request.headers.get('user-agent', '')
        x_forwarded_for = request.headers.get('x-forwarded-for', '')
        
        # Store signal in database with validation status
        signal_record = {
            "id": f"signal_tv_{datetime.now(timezone.utc).timestamp()}",
            "source": "tradingview",
            "symbol": signal.symbol,
            "action": signal.action.lower(),
            "price": signal.price,
            "strategy": signal.strategy,
            "timestamp": signal.timestamp or datetime.now(timezone.utc).isoformat(),
            "processed": False,
            "validated": True,
            "validation_notes": "Format validated",
            "metadata": {
                "user_agent": user_agent[:100],  # Truncate
                "ip": x_forwarded_for or request.client.host if request.client else None
            },
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        
        await db.db['external_signals'].insert_one(signal_record)
        
        # Try to create trade recommendation using existing AI
        try:
            # Import AI router to get recommendations
            from services.ai_command_router_enhanced import ai_router
            
            # Create recommendation prompt
            prompt = f"Signal received: {signal.action.upper()} {signal.symbol}"
            if signal.price:
                prompt += f" at price {signal.price}"
            prompt += f". Strategy: {signal.strategy or 'Unknown'}. Should this signal be acted upon?"
            
            # Get AI recommendation (async)
            try:
                recommendation = await ai_router.route_command(
                    user_id="system_signals",
                    command=prompt,
                    context={"signal": signal_record}
                )
                
                # Update signal with AI recommendation
                await db.db['external_signals'].update_one(
                    {"id": signal_record['id']},
                    {"$set": {
                        "ai_recommendation": recommendation.get('response'),
                        "confidence": recommendation.get('confidence', 0.5)
                    }}
                )
                
                logger.info(f"AI recommendation generated for signal {signal_record['id']}")
            except Exception as ai_err:
                logger.warning(f"AI recommendation failed: {ai_err}")
                
        except ImportError:
            logger.debug("AI router not available for signal processing")
        except Exception as ml_err:
            logger.warning(f"ML integration error: {ml_err}")
        
        return {
            "success": True,
            "message": "Signal validated and queued for processing",
            "signal_id": signal_record['id'],
            "validated": True
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"TradingView webhook error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/telegram/webhook")
async def telegram_webhook(signal: TelegramSignal):
    """
    Telegram webhook handler
    
    Receives trading signals from Telegram bot and parses messages
    """
    try:
        import re
        
        logger.info(f"Telegram signal received: {signal.chat_id}")
        
        # Parse message for trading signal if not provided
        parsed_symbol = signal.symbol
        parsed_action = signal.action
        
        if not parsed_symbol or not parsed_action:
            # Try to parse from message
            message = signal.message.upper()
            
            # Look for action keywords
            if 'BUY' in message:
                parsed_action = 'buy'
            elif 'SELL' in message:
                parsed_action = 'sell'
            elif 'CLOSE' in message:
                parsed_action = 'close'
            
            # Look for symbol patterns (BTC, ETH, XRP, etc.)
            symbol_pattern = r'\b(BTC|ETH|XRP|LTC|ADA|DOT|LINK|UNI|DOGE|MATIC|SOL|AVAX)[/-]?(USDT|USD|ZAR|EUR)?\b'
            symbol_match = re.search(symbol_pattern, message)
            if symbol_match:
                base = symbol_match.group(1)
                quote = symbol_match.group(2) or 'ZAR'
                parsed_symbol = f"{base}/{quote}"
        
        # Validate parsed signal
        validated = bool(parsed_symbol and parsed_action)
        validation_notes = []
        
        if not parsed_symbol:
            validation_notes.append("Could not extract symbol from message")
        if not parsed_action:
            validation_notes.append("Could not extract action from message")
        
        # Store signal in database
        signal_record = {
            "id": f"signal_tg_{datetime.now(timezone.utc).timestamp()}",
            "source": "telegram",
            "chat_id": signal.chat_id,
            "message": signal.message,
            "symbol": parsed_symbol,
            "action": parsed_action,
            "processed": False,
            "validated": validated,
            "validation_notes": "; ".join(validation_notes) if validation_notes else "Successfully parsed",
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        
        await db.db['external_signals'].insert_one(signal_record)
        
        # If validated, try to get ML recommendation
        if validated:
            try:
                from services.ai_command_router_enhanced import ai_router
                
                prompt = f"Telegram trading signal: {parsed_action.upper()} {parsed_symbol}. Message: '{signal.message}'. Is this a valid trading signal?"
                
                try:
                    recommendation = await ai_router.route_command(
                        user_id="system_telegram",
                        command=prompt,
                        context={"signal": signal_record}
                    )
                    
                    await db.db['external_signals'].update_one(
                        {"id": signal_record['id']},
                        {"$set": {
                            "ai_recommendation": recommendation.get('response'),
                            "confidence": recommendation.get('confidence', 0.5)
                        }}
                    )
                except Exception as ai_err:
                    logger.warning(f"AI recommendation failed: {ai_err}")
                    
            except ImportError:
                logger.debug("AI router not available")
            except Exception as ml_err:
                logger.warning(f"ML integration error: {ml_err}")
        
        return {
            "success": True,
            "message": "Signal received and parsed",
            "signal_id": signal_record['id'],
            "validated": validated,
            "parsed": {
                "symbol": parsed_symbol,
                "action": parsed_action
            }
        }
        
    except Exception as e:
        logger.error(f"Telegram webhook error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history")
async def get_signal_history(
    user_id: str = Depends(get_current_user),
    limit: int = 50,
    source: Optional[str] = None
):
    """
    Get history of received signals
    
    Optional filtering by source (tradingview, telegram, etc.)
    """
    try:
        query = {}
        if source:
            query["source"] = source
        
        signals = await db.db['external_signals'].find(
            query,
            {"_id": 0}
        ).sort("created_at", -1).limit(limit).to_list(limit)
        
        return {
            "success": True,
            "signals": signals,
            "count": len(signals)
        }
        
    except Exception as e:
        logger.error(f"Get signal history error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/process/{signal_id}")
async def process_signal(
    signal_id: str,
    user_id: str = Depends(get_current_user)
):
    """
    Manually process a signal
    
    Feeds the signal into the ML predictor and creates trade recommendation
    """
    try:
        # Get signal
        signal = await db.db['external_signals'].find_one({"id": signal_id})
        
        if not signal:
            raise HTTPException(status_code=404, detail="Signal not found")
        
        # Check if already processed
        if signal.get('processed'):
            return {
                "success": True,
                "message": "Signal already processed",
                "signal_id": signal_id,
                "recommendation": signal.get('ai_recommendation')
            }
        
        # Validate signal has required fields
        if not signal.get('symbol') or not signal.get('action'):
            await db.db['external_signals'].update_one(
                {"id": signal_id},
                {"$set": {
                    "processed": True,
                    "processing_status": "failed",
                    "processing_error": "Missing required fields (symbol or action)"
                }}
            )
            raise HTTPException(status_code=400, detail="Signal missing required fields")
        
        # Feed into ML predictor for recommendation
        try:
            from services.ai_command_router_enhanced import ai_router
            
            prompt = f"""Analyze this trading signal and provide a recommendation:
            
            Symbol: {signal.get('symbol')}
            Action: {signal.get('action')}
            Source: {signal.get('source')}
            Price: {signal.get('price', 'Not specified')}
            Strategy: {signal.get('strategy', 'Not specified')}
            Message: {signal.get('message', 'Not specified')}
            
            Should this signal be acted upon? Consider:
            1. Signal validity and completeness
            2. Current market conditions
            3. Risk level
            4. Timing
            
            Provide a clear recommendation and confidence level."""
            
            recommendation = await ai_router.route_command(
                user_id=user_id,
                command=prompt,
                context={"signal": signal}
            )
            
            # Create trade recommendation
            trade_recommendation = {
                "signal_id": signal_id,
                "symbol": signal.get('symbol'),
                "action": signal.get('action'),
                "recommended_action": recommendation.get('action', signal.get('action')),
                "confidence": recommendation.get('confidence', 0.5),
                "reasoning": recommendation.get('response', ''),
                "risk_level": recommendation.get('risk_level', 'medium'),
                "suggested_position_size": recommendation.get('position_size', 0.02),  # 2% default
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            
            # Update signal as processed
            await db.db['external_signals'].update_one(
                {"id": signal_id},
                {
                    "$set": {
                        "processed": True,
                        "processed_at": datetime.now(timezone.utc).isoformat(),
                        "processing_status": "success",
                        "ai_recommendation": recommendation.get('response'),
                        "confidence": recommendation.get('confidence', 0.5),
                        "trade_recommendation": trade_recommendation
                    }
                }
            )
            
            logger.info(f"Signal {signal_id} processed successfully with {recommendation.get('confidence', 0)*100}% confidence")
            
            return {
                "success": True,
                "message": "Signal processed successfully",
                "signal_id": signal_id,
                "recommendation": trade_recommendation
            }
            
        except ImportError:
            # AI router not available, use basic logic
            basic_recommendation = {
                "signal_id": signal_id,
                "symbol": signal.get('symbol'),
                "action": signal.get('action'),
                "recommended_action": signal.get('action'),
                "confidence": 0.5,
                "reasoning": "Basic processing without ML (AI router not available)",
                "risk_level": "medium",
                "suggested_position_size": 0.02,
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            
            await db.db['external_signals'].update_one(
                {"id": signal_id},
                {
                    "$set": {
                        "processed": True,
                        "processed_at": datetime.now(timezone.utc).isoformat(),
                        "processing_status": "basic_processing",
                        "trade_recommendation": basic_recommendation
                    }
                }
            )
            
            return {
                "success": True,
                "message": "Signal processed with basic logic (ML not available)",
                "signal_id": signal_id,
                "recommendation": basic_recommendation
            }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Process signal error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
        
        # Update signal as processed
        await db.db['external_signals'].update_one(
            {"id": signal_id},
            {
                "$set": {
                    "processed": True,
                    "processed_at": datetime.now(timezone.utc).isoformat()
                }
            }
        )
        
        return {
            "success": True,
            "message": "Signal processed successfully",
            "signal_id": signal_id
        }
        
    except Exception as e:
        logger.error(f"Process signal error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
