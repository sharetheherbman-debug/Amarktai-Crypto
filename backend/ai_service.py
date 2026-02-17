from openai import AsyncOpenAI
import os
import logging
from typing import Dict, List, Optional
import json
from datetime import datetime, timezone
import asyncio

logger = logging.getLogger(__name__)

class AIService:
    def __init__(self):
        # Note: OpenAI client is now created per-request via resolver
        self.chats: Dict[str, List[Dict]] = {}  # user_id -> conversation history
        self.available_models = ['gpt-4o', 'gpt-4', 'gpt-3.5-turbo']
        self.default_model = 'gpt-4o'  # Using OpenAI's best available model
    
    def get_chat_history(self, user_id: str, first_name: str = "User") -> List[Dict]:
        """Get or create chat history for user with personalization"""
        if user_id not in self.chats:
            system_message = f"""You are the AI brain of Amarktai Crypto, an autonomous cryptocurrency trading system with FULL CONTROL over the entire dashboard.

You are speaking with {first_name}. Always address them by name to create a personal connection.

Your capabilities:
1. EXECUTE ALL DASHBOARD FUNCTIONS via natural language commands
2. Create, pause, resume, delete bots
3. Manage API keys and connections
4. Control autopilot (enable/disable, adjust settings)
5. Monitor all bots and provide real-time insights
6. Analyze market conditions using live data (CoinGecko, Fear & Greed Index)
7. Generate daily learning reports and strategy recommendations
8. Manage risk (stop-loss, position sizing, daily limits)
9. Calculate and display profit/loss including exchange fees
10. Activate admin panel when user says "show admin"

Trading Rules (STRICT):
- Always account for exchange fees (0.1% typical)
- Enforce stop-loss on every trade (default 15%)
- Never exceed daily loss limit (-5%)
- Paper trading mandatory for 7 days before live
- Minimum R1000 per live bot
- Maximum 30 bots total

Your SOLE PURPOSE: Make money 24/7 while protecting capital for {first_name}.

Market Intelligence Available:
- Real-time prices and market cap
- Volatility index
- Fear & Greed sentiment
- BTC/ETH dominance
- Trading signals

Be conversational, helpful, and proactive. Warn about risks immediately. Suggest optimal actions. Remember previous conversations and build on them."""
            
            self.chats[user_id] = [{"role": "system", "content": system_message}]
        
        return self.chats[user_id]
    
    async def process_command(self, user_id: str, message: str) -> Dict:
        """Process user command with AI (legacy - no context)"""
        return await self.process_command_with_context(user_id, message, "User", [])
    
    async def process_command_with_context(self, user_id: str, message: str, first_name: str, context: List[Dict]) -> Dict:
        """Process user command with AI including conversation context"""
        try:
            from services.openai_key_resolver import get_openai_client
            
            # Get OpenAI client for this user
            client, source = await get_openai_client(user_id)
            if not client:
                logger.warning(f"OpenAI key resolved source={source} - AI unavailable")
                raise Exception("OpenAI API key not configured")
            
            logger.info(f"OpenAI key resolved source={source} for AI chat")
            
            # Get conversation history
            history = self.get_chat_history(user_id, first_name)
            
            # Add user message
            history.append({"role": "user", "content": message})
            
            # Log for debugging
            logger.info(f"AI Processing for {first_name} (user {user_id}): {message[:50]}...")
            
            # Call OpenAI API
            response = await client.chat.completions.create(
                model=self.default_model,
                messages=history,
                temperature=0.7,
                max_tokens=500
            )
            
            ai_message = response.choices[0].message.content
            
            # Add assistant response to history
            history.append({"role": "assistant", "content": ai_message})
            
            # Keep history manageable (last 20 messages)
            if len(history) > 21:  # 1 system + 20 messages
                self.chats[user_id] = [history[0]] + history[-20:]
            
            logger.info(f"AI Response: {ai_message[:100]}...")
            
            # Parse command intent
            intent = self._extract_intent(message, ai_message)
            
            return {
                'response': ai_message,
                'intent': intent,
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
        except Exception as e:
            logger.error(f"AI command processing failed: {e}", exc_info=True)
            return {
                'response': f"I'm having trouble connecting to my AI brain. Please check that the OpenAI API key is configured correctly in Settings.",
                'intent': {'action': 'error'},
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
    
    def _extract_intent(self, message: str, ai_response: str) -> Dict:
        """Extract command intent from message"""
        message_lower = message.lower()
        
        # Bot management
        if 'create' in message_lower and 'bot' in message_lower:
            return {'action': 'create_bot', 'params': self._extract_bot_params(message)}
        elif 'delete' in message_lower and 'bot' in message_lower:
            return {'action': 'delete_bot'}
        elif 'pause' in message_lower and 'bot' in message_lower:
            return {'action': 'pause_bot'}
        elif 'resume' in message_lower and 'bot' in message_lower:
            return {'action': 'resume_bot'}
        
        # System mode
        elif 'autopilot' in message_lower:
            if 'start' in message_lower or 'on' in message_lower or 'enable' in message_lower:
                return {'action': 'enable_autopilot'}
            elif 'stop' in message_lower or 'off' in message_lower or 'disable' in message_lower:
                return {'action': 'disable_autopilot'}
        elif 'paper' in message_lower and 'mode' in message_lower:
            return {'action': 'set_paper_mode'}
        elif 'live' in message_lower and ('mode' in message_lower or 'trading' in message_lower):
            return {'action': 'set_live_mode'}
        elif 'emergency' in message_lower and 'stop' in message_lower:
            return {'action': 'emergency_stop'}
        
        # Analytics
        elif 'learn' in message_lower and 'yesterday' in message_lower:
            return {'action': 'get_learning_report', 'period': 'yesterday'}
        elif 'performance' in message_lower or 'profit' in message_lower:
            return {'action': 'get_performance'}
        elif 'win rate' in message_lower:
            return {'action': 'get_win_rate'}
        
        # API management
        elif 'connect' in message_lower and ('api' in message_lower or 'luno' in message_lower or 'binance' in message_lower):
            return {'action': 'connect_api'}
        elif 'test' in message_lower and ('connection' in message_lower or 'api' in message_lower):
            return {'action': 'test_api_connection'}
        
        # Default: conversation
        return {'action': 'chat'}
    
    def _extract_bot_params(self, message: str) -> Dict:
        """Extract bot creation parameters from message"""
        params = {}
        message_lower = message.lower()
        
        # Risk mode
        if 'safe' in message_lower:
            params['risk_mode'] = 'safe'
        elif 'aggressive' in message_lower:
            params['risk_mode'] = 'aggressive'
        else:
            params['risk_mode'] = 'balanced'
        
        # Exchange
        if 'luno' in message_lower:
            params['exchange'] = 'luno'
        elif 'binance' in message_lower:
            params['exchange'] = 'binance'
        elif 'kucoin' in message_lower:
            params['exchange'] = 'kucoin'
        
        return params
    
    async def generate_learning_report(self, user_id: str, trades: List[Dict], 
                                      market_data: Dict, first_name: str = "User") -> str:
        """Generate daily learning report"""
        try:
            chat = self.get_chat(user_id, first_name)
            
            prompt = f"""Analyze yesterday's trading activity and generate a concise learning report for {first_name}.

Trades Summary:
- Total trades: {len(trades)}
- Profitable trades: {sum(1 for t in trades if t.get('profit_loss', 0) > 0)}
- Loss trades: {sum(1 for t in trades if t.get('profit_loss', 0) < 0)}
- Total P&L: {sum(t.get('profit_loss', 0) for t in trades)}

Market Conditions:
{json.dumps(market_data, indent=2)}

Provide insights on:
1. What patterns led to profitable trades
2. What mistakes to avoid
3. Recommended strategy adjustments
4. Market regime analysis

Keep it under 150 words, conversational tone."""
            
            user_message = UserMessage(text=prompt)
            response = await chat.send_message(user_message)
            
            return response
        except Exception as e:
            logger.error(f"Failed to generate learning report: {e}")
            return "Unable to generate learning report at this time."
    
    async def analyze_bot_performance(self, user_id: str, bot_data: Dict) -> str:
        """Analyze bot performance and provide recommendations"""
        try:
            chat = self.get_chat(user_id)
            
            prompt = f"""Analyze this bot's performance and provide actionable recommendations.

Bot: {bot_data.get('name')}
Exchange: {bot_data.get('exchange')}
Risk Mode: {bot_data.get('risk_mode')}
Total Profit: {bot_data.get('total_profit')}
Win Rate: {bot_data.get('win_rate')}%
Max Drawdown: {bot_data.get('max_drawdown')}%
Trades: {bot_data.get('trades_count')}

Provide:
1. Performance assessment (good/concerning)
2. One specific recommendation
3. Risk level evaluation

Keep it under 100 words."""
            
            user_message = UserMessage(text=prompt)
            response = await chat.send_message(user_message)
            
            return response
        except Exception as e:
            logger.error(f"Failed to analyze bot performance: {e}")
            return "Analysis unavailable."

# Global instance
ai_service = AIService()
