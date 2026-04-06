"""
AI Model Assignments

SystemAI: gpt-4o - Daily strategy & risk decisions
TradeAI: gpt-4o - Trade execution decisions
ReportingAI: gpt-4 - Email reports & summaries
ChatOpsAI: gpt-4o - WebSocket chat
"""

from openai import AsyncOpenAI
from logger_config import logger
import os


class AIModels:
    def __init__(self):
        # Note: OpenAI client is now created per-request via resolver
        pass
    
    async def system_ai(self, message: str, context: str = "", user_id: str = None) -> str:
        """SystemAI - gpt-4o for daily strategy decisions"""
        try:
            from services.openai_key_resolver import get_openai_client
            
            client, source = await get_openai_client(user_id)
            if not client:
                logger.warning(f"OpenAI key resolved source={source} - AI unavailable")
                return "OpenAI API key not configured"
            
            logger.info(f"OpenAI key resolved source={source} for SystemAI")
                
            system_message = f"""You are SystemAI, the global risk and strategy controller for Amarktai trading system.

{context}

Your role:
- Make daily risk mode decisions
- Review trades and tune strategies
- Decide when to enable/disable live trading
- Make big-picture system decisions

Be concise and data-driven."""
            
            response = await client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": message}
                ],
                temperature=0.7
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"SystemAI error: {e}")
            return "System AI temporarily unavailable"
    
    async def trade_ai(self, features: dict, user_id: str = None) -> dict:
        """TradeAI - gpt-4o for trade execution"""
        try:
            from services.openai_key_resolver import get_openai_client
            
            client, source = await get_openai_client(user_id)
            if not client:
                logger.warning(f"OpenAI key resolved source={source} - AI unavailable")
                return {"decision": "SKIP", "confidence": 0, "reasoning": "API key not configured"}
            
            logger.info(f"OpenAI key resolved source={source} for TradeAI")
                
            message = f"""Analyze this trade opportunity:

Pair: {features.get('pair')}
Price: {features.get('price')}
Trend: {features.get('trend')}
AI Signals:
- Regime: {features.get('regime')}
- ML Prediction: {features.get('ml_prediction')}
- Fetch.ai: {features.get('fetchai_signal')}

Decide: LONG, SHORT, or SKIP
Provide confidence (0-1)"""
            
            response = await client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are TradeAI. Analyze signals and make LONG/SHORT/SKIP decisions with confidence scores."},
                    {"role": "user", "content": message}
                ],
                temperature=0.7
            )
            text = response.choices[0].message.content
            
            # Parse response
            decision = "SKIP"
            confidence = 0.5
            
            if "LONG" in text.upper():
                decision = "LONG"
            elif "SHORT" in text.upper():
                decision = "SHORT"
            
            # Extract confidence
            if "confidence" in text.lower():
                try:
                    conf_text = text.lower().split("confidence")[1].split()[0]
                    confidence = float(conf_text.replace(":", "").replace(",", ""))
                except:
                    confidence = 0.7
            
            return {"decision": decision, "confidence": confidence, "reasoning": text}
        except Exception as e:
            logger.error(f"TradeAI error: {e}")
            return {"decision": "SKIP", "confidence": 0, "reasoning": "AI unavailable"}
    
    async def reporting_ai(self, data: dict, user_id: str = None) -> str:
        """ReportingAI - gpt-4 for email reports"""
        try:
            from services.openai_key_resolver import get_openai_client
            
            client, source = await get_openai_client(user_id)
            if not client:
                logger.warning(f"OpenAI key resolved source={source} - using fallback report")
                return f"Daily Report\n\n{data}"
            
            logger.info(f"OpenAI key resolved source={source} for ReportingAI")
                
            message = f"""Generate a professional daily trading report email:

Data:
{data}

Create a clear, concise summary with:
1. Performance highlights
2. Key metrics
3. Notable events
4. Recommendations"""
            
            response = await client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "You are ReportingAI. Generate professional, human-readable trading reports."},
                    {"role": "user", "content": message}
                ],
                temperature=0.7
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"ReportingAI error: {e}")
            return f"Daily Report\n\n{data}"


ai_models = AIModels()
