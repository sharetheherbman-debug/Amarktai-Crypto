"""
Multi-Model AI Router
Routes different tasks to appropriate AI models (gpt-4o, gpt-4, gpt-3.5-turbo)
"""
from openai import AsyncOpenAI
from logger_config import logger
from config import AI_MODELS
import os


class AIModelsRouter:
    def __init__(self):
        # Note: OpenAI client is now created per-request via resolver
        self.models = {
            'system_brain': AI_MODELS.get('system_brain', 'gpt-4o'),
            'trade_decision': AI_MODELS.get('trade_decision', 'gpt-4o'),
            'reporting': AI_MODELS.get('reporting', 'gpt-4o-mini'),
            'chatops': AI_MODELS.get('chatops', 'gpt-4o')
        }
    
    async def get_client_for_user(self, user_id: str = None):
        """Get OpenAI client for user - prefers per-user key, falls back to system key
        
        Args:
            user_id: User ID (optional). If not provided, uses system key
            
        Returns:
            Tuple of (AsyncOpenAI client or None, source string)
        """
        try:
            from services.openai_key_resolver import get_openai_client
            
            # Use the resolver
            client, source = await get_openai_client(user_id)
            logger.info(f"AI Router: OpenAI key resolved source={source} for user {user_id[:8] if user_id else 'system'}")
            
            return client, source
                
        except Exception as e:
            logger.error(f"AI Router: Error getting client for user {user_id[:8] if user_id else 'unknown'}: {e}")
            return None, 'missing'
    
    async def system_brain_decision(self, prompt: str, context: dict, user_id: str = None) -> str:
        """
        GPT-4o - System Brain
        For: Autopilot decisions, risk management, strategic planning
        """
        try:
            client, source = await self.get_client_for_user(user_id)
            if not client:
                return "OpenAI API key not configured. Please configure your OpenAI key in API Settings."
                
            system_message = f"""You are the Amarktai System Brain - the highest-level AI controller.

Your role: Make strategic decisions about autopilot, capital allocation, risk management.

Current system state:
{context}

Think strategically. Consider long-term growth, risk mitigation, and optimal capital deployment."""

            response = await client.chat.completions.create(
                model=self.models['system_brain'],
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7
            )
            return response.choices[0].message.content
        
        except Exception as e:
            logger.error(f"System brain error: {e}")
            # Fallback to trade decision
            return await self.trade_decision(prompt, context, user_id)
    
    async def trade_decision(self, prompt: str, context: dict, user_id: str = None) -> str:
        """
        GPT-4o - Trade Execution Brain
        For: Individual bot trading decisions, technical analysis
        """
        try:
            client, source = await self.get_client_for_user(user_id)
            if not client:
                return "OpenAI API key not configured. Please configure your OpenAI key in API Settings."
                
            system_message = f"""You are the Amarktai Trade Execution Brain.

Your role: Make fast, accurate trading decisions for individual bots.

Context:
{context}

Focus on: Technical patterns, entry/exit timing, position sizing."""

            response = await client.chat.completions.create(
                model=self.models['trade_decision'],
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7
            )
            return response.choices[0].message.content
        
        except Exception as e:
            logger.error(f"Trade decision error: {e}")
            return f"Trade decision unavailable: {str(e)}"
    
    async def generate_report(self, prompt: str, data: dict, user_id: str = None) -> str:
        """
        GPT-4 - Reporting Brain
        For: Daily summaries, performance reports, email content
        """
        try:
            client, source = await self.get_client_for_user(user_id)
            if not client:
                return "OpenAI API key not configured. Please configure your OpenAI key in API Settings."
                
            system_message = f"""You are the Amarktai Reporting Brain.

Your role: Generate clear, concise reports and summaries.

Data to summarize:
{data}

Focus on: Key metrics, insights, actionable recommendations."""

            response = await client.chat.completions.create(
                model=self.models['reporting'],
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7
            )
            return response.choices[0].message.content
        
        except Exception as e:
            logger.error(f"Report generation error: {e}")
            return f"Report generation unavailable: {str(e)}"
    
    async def chatops_response(self, prompt: str, context: dict, user_id: str) -> str:
        """
        GPT-4o - ChatOps Brain
        For: Dashboard chat, real-time commands, user interaction
        """
        try:
            client, source = await self.get_client_for_user(user_id)
            if not client:
                return "OpenAI API key not configured. Please configure your OpenAI key in API Settings."
                
            system_message = f"""You are the Amarktai ChatOps Brain - real-time assistant.

Your role: Respond quickly to user queries and execute commands.

System context:
{context}

Be: Fast, accurate, helpful. Execute commands when requested."""

            response = await client.chat.completions.create(
                model=self.models['chatops'],
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=500
            )
            return response.choices[0].message.content
        
        except Exception as e:
            logger.error(f"ChatOps error: {e}")
            return f"ChatOps unavailable: {str(e)}"
    
    def route_to_best_model(self, task_type: str) -> str:
        """Determine which model to use for a task"""
        routing_map = {
            "autopilot": "system_brain",
            "risk_assessment": "system_brain",
            "capital_allocation": "system_brain",
            "strategic_planning": "system_brain",
            "trade_execution": "trade_decision",
            "technical_analysis": "trade_decision",
            "bot_decision": "trade_decision",
            "daily_report": "reporting",
            "summary": "reporting",
            "email": "reporting",
            "chat": "chatops",
            "command": "chatops",
            "question": "chatops"
        }
        
        model_type = routing_map.get(task_type, "chatops")
        return self.models[model_type]


ai_models_router = AIModelsRouter()
