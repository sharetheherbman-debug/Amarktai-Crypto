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
        self.api_key = os.environ.get('OPENAI_API_KEY')
        self.client = AsyncOpenAI(api_key=self.api_key) if self.api_key else None
    
    async def system_ai(self, message: str, context: str = "") -> str:
        """SystemAI - gpt-4o for daily strategy decisions"""
        try:
            if not self.client:
                return "OpenAI API key not configured"
                
            system_message = f"""You are SystemAI, the global risk and strategy controller for Amarktai trading system.

{context}

Your role:
- Make daily risk mode decisions
- Review trades and tune strategies
- Decide when to enable/disable live trading
- Make big-picture system decisions

Be concise and data-driven."""
            
            response = await self.client.chat.completions.create(
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
    
    async def trade_ai(self, features: dict) -> dict:
        """TradeAI - gpt-4o for trade execution"""
        try:
            if not self.client:
                return {"decision": "SKIP", "confidence": 0, "reasoning": "API key not configured"}
                
            message = f"""Analyze this trade opportunity:

Pair: {features.get('pair')}
Price: {features.get('price')}
Trend: {features.get('trend')}
AI Signals:
- Regime: {features.get('regime')}
- ML Prediction: {features.get('ml_prediction')}
- CoinStats Signal: {features.get('coinstats_signal')}
- Fetch.ai: {features.get('fetchai_signal')}

Decide: LONG, SHORT, or SKIP
Provide confidence (0-1)"""
            
            response = await self.client.chat.completions.create(
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
    
    async def reporting_ai(self, data: dict) -> str:
        """ReportingAI - gpt-4 for email reports"""
        try:
            if not self.client:
                return f"Daily Report\n\n{data}"
                
            message = f"""Generate a professional daily trading report email:

Data:
{data}

Create a clear, concise summary with:
1. Performance highlights
2. Key metrics
3. Notable events
4. Recommendations"""
            
            response = await self.client.chat.completions.create(
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
