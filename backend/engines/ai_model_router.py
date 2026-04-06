"""
AI Model Router - Central OpenAI Client
- Routes requests to appropriate models (GPT-5.1, GPT-4o, GPT-4)
- Handles failover and rate limiting
- Optimizes cost vs. performance
"""

import asyncio
from typing import Dict, List, Optional
from datetime import datetime, timezone
import logging
import os

logger = logging.getLogger(__name__)

import openai

class AIModelRouter:
    def __init__(self):
        self.models = {
            'fast': 'gpt-4o',           # Fast responses, good quality
            'balanced': 'gpt-5.1',      # Best balance of speed and intelligence
            'deep': 'gpt-5.1',          # Deep reasoning (same as balanced for now)
            'fallback': 'gpt-4o'        # Fallback if primary fails
        }
        
        # Initialize clients
        self.openai_client = None
        
        # Get API keys from environment
        self.openai_key = os.environ.get('OPENAI_API_KEY')
        
        if self.openai_key:
            try:
                openai.api_key = self.openai_key
                self.openai_client = openai
                logger.info("✅ OpenAI client initialized")
            except Exception as e:
                logger.error(f"Failed to init OpenAI client: {e}")
        else:
            logger.warning(
                "⚠️  OPENAI_API_KEY is not set — AI chat, NLP, and insight features will be "
                "unavailable until the key is configured in the environment file."
            )
    
    async def chat_completion(self, messages: List[Dict], 
                             mode: str = 'balanced',
                             max_tokens: int = 1000,
                             temperature: float = 0.7) -> Dict:
        """
        Get chat completion from appropriate model
        
        Args:
            messages: List of message dicts [{"role": "user", "content": "..."}]
            mode: 'fast', 'balanced', 'deep', 'fallback'
            max_tokens: Max tokens in response
            temperature: Randomness (0-1)
        
        Returns:
            {"content": str, "model": str, "tokens": int}
        """
        try:
            model = self.models.get(mode, self.models['balanced'])
            
            if self.openai_client:
                try:
                    response = await asyncio.to_thread(
                        self.openai_client.ChatCompletion.create,
                        model=model,
                        messages=messages,
                        max_tokens=max_tokens,
                        temperature=temperature
                    )
                    
                    return {
                        "content": response.choices[0].message.content,
                        "model": model,
                        "tokens": response.usage.total_tokens,
                        "source": "openai"
                    }
                except Exception as e:
                    logger.error(f"OpenAI client failed: {e}")
                    raise
            
            # No client available
            return {
                "content": "AI service unavailable - no API keys configured",
                "model": "none",
                "tokens": 0,
                "source": "none",
                "error": "No AI client available"
            }
            
        except Exception as e:
            logger.error(f"Chat completion error: {e}")
            return {
                "content": f"Error: {str(e)}",
                "model": mode,
                "tokens": 0,
                "source": "error",
                "error": str(e)
            }
    
    async def analyze_trade_opportunity(self, market_data: Dict, bot_config: Dict) -> Dict:
        """
        Use AI to analyze if a trade opportunity is good
        Mode: fast (GPT-4o) for quick decisions
        """
        try:
            messages = [
                {
                    "role": "system",
                    "content": "You are an expert crypto trading analyst. Analyze trade opportunities and respond with clear buy/sell/hold recommendations."
                },
                {
                    "role": "user",
                    "content": f"""
Analyze this trade opportunity:

Market: {market_data.get('pair')}
Current Price: R{market_data.get('price', 0):.2f}
24h Change: {market_data.get('change_24h', 0):.2f}%
Volume: R{market_data.get('volume', 0):.2f}
RSI: {market_data.get('rsi', 50)}
MACD: {market_data.get('macd', 'neutral')}

Bot Config:
Risk Mode: {bot_config.get('risk_mode', 'safe')}
Current Capital: R{bot_config.get('current_capital', 0):.2f}
Win Rate: {bot_config.get('win_rate', 0):.1f}%

Should we trade? Respond with: BUY, SELL, or HOLD and a brief reason.
"""
                }
            ]
            
            result = await self.chat_completion(messages, mode='fast', max_tokens=200, temperature=0.4)
            
            decision = "HOLD"
            if "BUY" in result.get('content', '').upper():
                decision = "BUY"
            elif "SELL" in result.get('content', '').upper():
                decision = "SELL"
            
            return {
                "decision": decision,
                "reasoning": result.get('content', ''),
                "model": result.get('model'),
                "confidence": 0.7  # Could be extracted from response
            }
            
        except Exception as e:
            logger.error(f"Trade analysis error: {e}")
            return {
                "decision": "HOLD",
                "reasoning": f"Analysis error: {str(e)}",
                "model": "error",
                "confidence": 0.0
            }
    
    async def generate_market_insight(self, market_conditions: Dict) -> str:
        """
        Generate market insights
        Mode: balanced (GPT-5.1) for quality insights
        """
        try:
            messages = [
                {
                    "role": "system",
                    "content": "You are a crypto market analyst. Provide concise, actionable insights."
                },
                {
                    "role": "user",
                    "content": f"""
Current market conditions:
{market_conditions}

Provide a brief market insight (2-3 sentences) for traders.
"""
                }
            ]
            
            result = await self.chat_completion(messages, mode='balanced', max_tokens=300)
            return result.get('content', 'No insight available')
            
        except Exception as e:
            logger.error(f"Market insight error: {e}")
            return f"Insight generation failed: {str(e)}"
    
    async def deep_strategy_analysis(self, bot_performance: Dict, market_history: List) -> Dict:
        """
        Deep analysis of bot strategy
        Mode: deep (GPT-5.1) for complex reasoning
        """
        try:
            messages = [
                {
                    "role": "system",
                    "content": "You are an AI trading strategist. Analyze bot performance and recommend optimizations."
                },
                {
                    "role": "user",
                    "content": f"""
Bot Performance:
- Total Trades: {bot_performance.get('trades_count', 0)}
- Win Rate: {bot_performance.get('win_rate', 0):.1f}%
- Total Profit: R{bot_performance.get('total_profit', 0):.2f}
- Avg Trade Size: R{bot_performance.get('avg_trade_size', 0):.2f}
- Risk Mode: {bot_performance.get('risk_mode', 'unknown')}

Recent Market Performance:
{market_history[:10]}  # Last 10 trades

Recommendations:
1. Should we adjust risk mode?
2. Should we change trade size?
3. Any pattern in losses we should avoid?

Provide 3-5 actionable recommendations.
"""
                }
            ]
            
            result = await self.chat_completion(messages, mode='deep', max_tokens=800, temperature=0.6)
            
            return {
                "recommendations": result.get('content', ''),
                "model": result.get('model'),
                "tokens": result.get('tokens', 0)
            }
            
        except Exception as e:
            logger.error(f"Strategy analysis error: {e}")
            return {
                "recommendations": f"Analysis failed: {str(e)}",
                "model": "error",
                "tokens": 0
            }
    
    async def health_check(self) -> Dict:
        """Check if AI services are available"""
        try:
            test_messages = [
                {"role": "user", "content": "Say 'OK' if you're working"}
            ]
            
            result = await self.chat_completion(test_messages, mode='fast', max_tokens=10)
            
            return {
                "status": "healthy" if "OK" in result.get('content', '') or not result.get('error') else "degraded",
                "openai_available": self.openai_client is not None,
                "last_check": datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            logger.error(f"Health check error: {e}")
            return {
                "status": "unhealthy",
                "error": str(e),
                "last_check": datetime.now(timezone.utc).isoformat()
            }

# Global instance
ai_model_router = AIModelRouter()
