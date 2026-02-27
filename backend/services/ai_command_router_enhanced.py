"""
Production-Grade AI Command Router
Version 2.0 - Enhanced with Fuzzy Matching, Synonym Support, and Tool Registry

Features:
- Fuzzy bot name matching using rapidfuzz
- Comprehensive synonym mapping for natural language
- Multi-command parsing ("pause alpha and beta")
- Structured command output schema
- Risk-based confirmation system
- Tool Registry for AI feature access
- Health/bodyguard integration
- Full dashboard parity
"""

import re
import logging
from typing import Dict, Any, Optional, Tuple, List
from datetime import datetime, timezone
from rapidfuzz import fuzz, process

logger = logging.getLogger(__name__)


class CommandOutputSchema:
    """Standardized command output format"""
    
    @staticmethod
    def success(command: str, message: str, data: Dict[str, Any] = None, meta: Dict[str, Any] = None) -> Dict[str, Any]:
        """Create success response"""
        return {
            "ok": True,
            "command": command,
            "message": message,
            "data": data or {},
            "meta": meta or {},
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    @staticmethod
    def error(command: str, message: str, error_code: str = None, meta: Dict[str, Any] = None) -> Dict[str, Any]:
        """Create error response"""
        return {
            "ok": False,
            "command": command,
            "message": message,
            "error_code": error_code,
            "meta": meta or {},
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    @staticmethod
    def requires_confirmation(command: str, message: str, confirm_level: str, data: Dict[str, Any] = None) -> Dict[str, Any]:
        """Create confirmation required response"""
        return {
            "ok": False,
            "command": command,
            "message": message,
            "requires_confirmation": True,
            "confirmation_level": confirm_level,
            "data": data or {},
            "timestamp": datetime.now(timezone.utc).isoformat()
        }


class ConfirmationLevel:
    """Confirmation levels for risk-based system"""
    NONE = "none"  # No confirmation needed
    OPTIONAL = "optional"  # Optional confirmation (can skip)
    REQUIRED = "required"  # Must confirm
    DOUBLE = "double"  # Must type confirmation phrase
    TYPED_PHRASE = "typed_phrase"  # Must type exact phrase


class ToolRegistry:
    """Registry of tools/features AI can call"""
    
    def __init__(self, db):
        self.db = db
        self.bots_collection = db["bots"]
        self.users_collection = db["users"]
        self.system_modes_collection = db["system_modes"]
        self.trades_collection = db["trades"]
        self.tools = self._register_tools()
    
    def _register_tools(self) -> Dict[str, Dict[str, Any]]:
        """Register available tools"""
        return {
            "get_portfolio_summary": {
                "description": "Get current portfolio summary with equity, PnL, fees",
                "params": [],
                "confirmation_level": ConfirmationLevel.NONE,
                "function": self._get_portfolio_summary
            },
            "get_profit_series": {
                "description": "Get profit time series for specified period",
                "params": ["period"],
                "confirmation_level": ConfirmationLevel.NONE,
                "function": self._get_profit_series
            },
            "get_countdown_status": {
                "description": "Get countdown to R1M target with projections",
                "params": [],
                "confirmation_level": ConfirmationLevel.NONE,
                "function": self._get_countdown_status
            },
            "pause_bot": {
                "description": "Pause a trading bot",
                "params": ["bot_id", "reason"],
                "confirmation_level": ConfirmationLevel.OPTIONAL,
                "function": self._pause_bot
            },
            "resume_bot": {
                "description": "Resume a paused bot",
                "params": ["bot_id"],
                "confirmation_level": ConfirmationLevel.OPTIONAL,
                "function": self._resume_bot
            },
            "stop_bot": {
                "description": "Stop a bot permanently",
                "params": ["bot_id"],
                "confirmation_level": ConfirmationLevel.REQUIRED,
                "function": self._stop_bot
            },
            "trigger_reinvestment": {
                "description": "Trigger profit reinvestment cycle",
                "params": [],
                "confirmation_level": ConfirmationLevel.REQUIRED,
                "function": self._trigger_reinvestment
            },
            "emergency_stop": {
                "description": "EMERGENCY: Stop all trading immediately",
                "params": [],
                "confirmation_level": ConfirmationLevel.DOUBLE,
                "confirmation_phrase": "CONFIRM EMERGENCY STOP",
                "function": self._emergency_stop
            },
            "get_health_status": {
                "description": "Get system health and circuit breaker status",
                "params": [],
                "confirmation_level": ConfirmationLevel.NONE,
                "function": self._get_health_status
            },
            "get_alerts": {
                "description": "Get active system alerts and warnings",
                "params": [],
                "confirmation_level": ConfirmationLevel.NONE,
                "function": self._get_alerts
            },
            "send_test_report": {
                "description": "Send test email report (admin only)",
                "params": [],
                "confirmation_level": ConfirmationLevel.OPTIONAL,
                "admin_only": True,
                "function": self._send_test_report
            }
        }
    
    async def call_tool(self, tool_name: str, user_id: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """Call a registered tool"""
        if tool_name not in self.tools:
            return CommandOutputSchema.error(
                "unknown_tool",
                f"Tool '{tool_name}' not found in registry",
                "TOOL_NOT_FOUND"
            )
        
        tool = self.tools[tool_name]
        try:
            result = await tool["function"](user_id, **(params or {}))
            return result
        except Exception as e:
            logger.error(f"Tool execution error ({tool_name}): {e}")
            return CommandOutputSchema.error(
                tool_name,
                f"Error executing tool: {str(e)}",
                "TOOL_EXECUTION_ERROR"
            )
    
    async def _get_portfolio_summary(self, user_id: str) -> Dict[str, Any]:
        """Tool: Get portfolio summary"""
        try:
            from services.ledger_service import get_ledger_service
            ledger = get_ledger_service(self.db)
            
            equity = await ledger.compute_equity(user_id)
            realized_pnl = await ledger.compute_realized_pnl(user_id)
            fees_total = await ledger.compute_fees_paid(user_id)
            current_dd, max_dd = await ledger.compute_drawdown(user_id)
            
            bots = await self.bots_collection.find({"user_id": user_id}, {"_id": 0}).to_list(1000)
            active_count = len([b for b in bots if b.get("status") == "active"])
            
            return CommandOutputSchema.success(
                "get_portfolio_summary",
                "Portfolio summary retrieved successfully",
                data={
                    "equity": round(equity, 2),
                    "realized_pnl": round(realized_pnl, 2),
                    "fees_total": round(fees_total, 2),
                    "net_pnl": round(realized_pnl - fees_total, 2),
                    "drawdown_current": round(current_dd * 100, 2),
                    "drawdown_max": round(max_dd * 100, 2),
                    "total_bots": len(bots),
                    "active_bots": active_count
                }
            )
        except Exception as e:
            return CommandOutputSchema.error(
                "get_portfolio_summary",
                f"Error retrieving portfolio: {str(e)}",
                "PORTFOLIO_ERROR"
            )
    
    async def _get_profit_series(self, user_id: str, period: str = "daily") -> Dict[str, Any]:
        """Tool: Get profit series"""
        try:
            from services.ledger_service import get_ledger_service
            ledger = get_ledger_service(self.db)
            
            series = await ledger.profit_series(user_id, period=period, limit=30)
            
            return CommandOutputSchema.success(
                "get_profit_series",
                f"Profit series retrieved for period: {period}",
                data=series
            )
        except Exception as e:
            return CommandOutputSchema.error(
                "get_profit_series",
                f"Error retrieving profits: {str(e)}",
                "PROFIT_ERROR"
            )
    
    async def _get_countdown_status(self, user_id: str) -> Dict[str, Any]:
        """Tool: Get countdown to million status"""
        try:
            # This would call the countdown endpoint logic
            # For now, return placeholder
            return CommandOutputSchema.success(
                "get_countdown_status",
                "Countdown status retrieved",
                data={"message": "Use /api/countdown/status endpoint"}
            )
        except Exception as e:
            return CommandOutputSchema.error(
                "get_countdown_status",
                f"Error retrieving countdown: {str(e)}",
                "COUNTDOWN_ERROR"
            )
    
    async def _pause_bot(self, user_id: str, bot_id: str, reason: str = "AI command") -> Dict[str, Any]:
        """Tool: Pause bot"""
        try:
            result = await self.bots_collection.update_one(
                {"id": bot_id, "user_id": user_id},
                {"$set": {
                    "status": "paused",
                    "paused_at": datetime.now(timezone.utc).isoformat(),
                    "pause_reason": reason,
                    "paused_by_user": True
                }}
            )
            
            if result.modified_count > 0:
                bot = await self.bots_collection.find_one({"id": bot_id}, {"_id": 0})
                return CommandOutputSchema.success(
                    "pause_bot",
                    f"Bot '{bot.get('name', bot_id)}' paused successfully",
                    data={
                        "bot_id": bot_id,
                        "bot_name": bot.get("name"),
                        "status": "paused",
                        "since": datetime.now(timezone.utc).isoformat()
                    }
                )
            else:
                return CommandOutputSchema.error(
                    "pause_bot",
                    f"Bot '{bot_id}' not found or already paused",
                    "BOT_NOT_FOUND"
                )
        except Exception as e:
            return CommandOutputSchema.error(
                "pause_bot",
                f"Error pausing bot: {str(e)}",
                "PAUSE_ERROR"
            )
    
    async def _resume_bot(self, user_id: str, bot_id: str) -> Dict[str, Any]:
        """Tool: Resume bot"""
        try:
            result = await self.bots_collection.update_one(
                {"id": bot_id, "user_id": user_id, "status": "paused"},
                {"$set": {"status": "active"}, "$unset": {"paused_at": "", "pause_reason": ""}}
            )
            
            if result.modified_count > 0:
                bot = await self.bots_collection.find_one({"id": bot_id}, {"_id": 0})
                return CommandOutputSchema.success(
                    "resume_bot",
                    f"Bot '{bot.get('name', bot_id)}' resumed successfully",
                    data={
                        "bot_id": bot_id,
                        "bot_name": bot.get("name"),
                        "status": "active"
                    }
                )
            else:
                return CommandOutputSchema.error(
                    "resume_bot",
                    f"Bot '{bot_id}' not found or not paused",
                    "BOT_NOT_PAUSED"
                )
        except Exception as e:
            return CommandOutputSchema.error(
                "resume_bot",
                f"Error resuming bot: {str(e)}",
                "RESUME_ERROR"
            )
    
    async def _stop_bot(self, user_id: str, bot_id: str) -> Dict[str, Any]:
        """Tool: Stop bot permanently"""
        try:
            result = await self.bots_collection.update_one(
                {"id": bot_id, "user_id": user_id},
                {"$set": {
                    "status": "stopped",
                    "stopped_at": datetime.now(timezone.utc).isoformat()
                }}
            )
            
            if result.modified_count > 0:
                bot = await self.bots_collection.find_one({"id": bot_id}, {"_id": 0})
                return CommandOutputSchema.success(
                    "stop_bot",
                    f"Bot '{bot.get('name', bot_id)}' stopped permanently",
                    data={
                        "bot_id": bot_id,
                        "bot_name": bot.get("name"),
                        "status": "stopped"
                    }
                )
            else:
                return CommandOutputSchema.error(
                    "stop_bot",
                    f"Bot '{bot_id}' not found",
                    "BOT_NOT_FOUND"
                )
        except Exception as e:
            return CommandOutputSchema.error(
                "stop_bot",
                f"Error stopping bot: {str(e)}",
                "STOP_ERROR"
            )
    
    async def _trigger_reinvestment(self, user_id: str) -> Dict[str, Any]:
        """Tool: Trigger reinvestment"""
        try:
            from engines.capital_allocator import capital_allocator
            result = await capital_allocator.reinvest_daily_profits(user_id)
            
            return CommandOutputSchema.success(
                "trigger_reinvestment",
                "Reinvestment cycle triggered successfully",
                data=result
            )
        except Exception as e:
            return CommandOutputSchema.error(
                "trigger_reinvestment",
                f"Error triggering reinvestment: {str(e)}",
                "REINVEST_ERROR"
            )
    
    async def _emergency_stop(self, user_id: str) -> Dict[str, Any]:
        """Tool: Emergency stop"""
        try:
            # Pause all bots
            result = await self.bots_collection.update_many(
                {"user_id": user_id},
                {"$set": {
                    "status": "paused",
                    "pause_reason": "Emergency stop activated",
                    "paused_by_system": True
                }}
            )
            
            # Disable trading modes
            await self.system_modes_collection.update_one(
                {"user_id": user_id},
                {
                    "$set": {
                        "paperTrading": False,
                        "liveTrading": False,
                        "autopilot": False,
                        "emergency_stop_triggered": True,
                        "emergency_stop_at": datetime.now(timezone.utc).isoformat()
                    }
                },
                upsert=True
            )
            
            return CommandOutputSchema.success(
                "emergency_stop",
                "🚨 EMERGENCY STOP ACTIVATED - All trading halted",
                data={
                    "bots_paused": result.modified_count,
                    "trading_disabled": True,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            )
        except Exception as e:
            return CommandOutputSchema.error(
                "emergency_stop",
                f"Error executing emergency stop: {str(e)}",
                "EMERGENCY_ERROR"
            )
    
    async def _get_health_status(self, user_id: str) -> Dict[str, Any]:
        """Tool: Get health status"""
        try:
            # Get circuit breaker status
            from engines.circuit_breaker import circuit_breaker
            cb_status = circuit_breaker.get_status()
            
            # Get error rate
            # This would need to query logs/metrics
            
            return CommandOutputSchema.success(
                "get_health_status",
                "System health status retrieved",
                data={
                    "circuit_breaker": cb_status,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            )
        except Exception as e:
            return CommandOutputSchema.error(
                "get_health_status",
                f"Error retrieving health status: {str(e)}",
                "HEALTH_ERROR"
            )
    
    async def _get_alerts(self, user_id: str) -> Dict[str, Any]:
        """Tool: Get alerts"""
        try:
            # Access alerts_collection through db parameter
            alerts_collection = self.db["alerts"]
            
            alerts = await alerts_collection.find(
                {"user_id": user_id, "resolved": False},
                {"_id": 0}
            ).sort("created_at", -1).limit(20).to_list(20)
            
            return CommandOutputSchema.success(
                "get_alerts",
                f"Retrieved {len(alerts)} active alerts",
                data={"alerts": alerts}
            )
        except Exception as e:
            return CommandOutputSchema.error(
                "get_alerts",
                f"Error retrieving alerts: {str(e)}",
                "ALERTS_ERROR"
            )
    
    async def _send_test_report(self, user_id: str) -> Dict[str, Any]:
        """Tool: Send test report (admin only)"""
        try:
            from routes.daily_report import daily_report_service
            
            success = await daily_report_service.send_report_to_user(user_id)
            
            if success:
                return CommandOutputSchema.success(
                    "send_test_report",
                    "Test report sent successfully",
                    data={"sent": True}
                )
            else:
                return CommandOutputSchema.error(
                    "send_test_report",
                    "Failed to send report (SMTP not configured?)",
                    "SEND_FAILED"
                )
        except Exception as e:
            return CommandOutputSchema.error(
                "send_test_report",
                f"Error sending report: {str(e)}",
                "SEND_ERROR"
            )


class EnhancedAICommandRouter:
    """Enhanced AI Command Router with fuzzy matching and synonyms"""
    
    # Synonym mapping for natural language understanding
    SYNONYMS = {
        "pause": ["stop", "freeze", "hold", "disable", "halt", "suspend"],
        "resume": ["start", "continue", "unpause", "enable", "activate", "restart",
                   "begin", "kick off", "kick-off", "run", "go", "launch"],
        "stop": ["kill", "terminate", "delete", "remove", "destroy"],
        "show": ["display", "get", "fetch", "retrieve", "list", "check", "what is", "what are"],
        "bot": ["agent", "trader", "trading bot", "algo", "bots", "all bots"],
        "all": ["every", "all of them", "all bots", "every bot", "everyone"],
    }
    
    # Confirmation requirements
    CONFIRMATION_MAP = {
        "pause_bot": ConfirmationLevel.OPTIONAL,
        "resume_bot": ConfirmationLevel.OPTIONAL,
        "start_bot": ConfirmationLevel.OPTIONAL,
        "stop_bot": ConfirmationLevel.REQUIRED,
        "pause_all": ConfirmationLevel.OPTIONAL,
        "resume_all": ConfirmationLevel.OPTIONAL,
        "reinvest": ConfirmationLevel.REQUIRED,
        "emergency_stop": ConfirmationLevel.DOUBLE,
        "enable_live_trading": ConfirmationLevel.TYPED_PHRASE,
        # Info commands require no confirmation
        "portfolio_summary": ConfirmationLevel.NONE,
        "profits": ConfirmationLevel.NONE,
        "bot_status": ConfirmationLevel.NONE,
        "show_health": ConfirmationLevel.NONE,
        "show_alerts": ConfirmationLevel.NONE,
    }
    
    def __init__(self, db):
        self.db = db
        self.bots_collection = db["bots"]
        self.users_collection = db["users"]
        self.tool_registry = ToolRegistry(db)
        
        # Command patterns with enhanced regex
        self.command_patterns = {
            # Bot lifecycle - now supports fuzzy bot names
            "pause_bot": r"(pause|stop|freeze|hold|disable)\s+(?:bot\s+)?(.+)",
            "resume_bot": r"(resume|start|continue|unpause|enable|activate|restart)\s+(?:bot\s+)?(.+)",
            "stop_bot": r"(kill|terminate|delete|remove|destroy)\s+(?:bot\s+)?(.+)",
            "start_bot": r"(?:start|activate)\s+(?:bot\s+)?(.+)",
            
            # Multi-bot operations
            "pause_multiple": r"(?:pause|stop)\s+(?:bots?\s+)?(.+?)\s+(?:and|,)\s+(.+)",
            "pause_all": r"(?:pause|stop)\s+(?:all|every)(?:\s+bots?)?",
            "resume_all": r"(?:resume|start|begin|launch|go|run)\s+(?:all|every)(?:\s+bots?)?|(?:start|resume)\s+all\s+bots?",
            
            # Emergency
            "emergency_stop": r"emergency\s+stop|halt\s+all|stop\s+everything",
            
            # Status/Info commands
            "bot_status": r"(?:status|info)\s+(?:of\s+)?(?:bot\s+)?(.+)",
            "portfolio_summary": r"(?:show|display|get)\s+(?:portfolio|summary|balance)",
            "profits": r"(?:show|display|get)\s+profit",
            "show_health": r"(?:show|display|get)\s+(?:health|system\s+health)",
            "show_alerts": r"(?:show|display|get)\s+(?:alerts|warnings)",
            "show_error_rate": r"(?:show|display|get)\s+(?:error\s+rate|errors)",
            "why_circuit_breaker": r"why\s+(?:did\s+)?(?:circuit\s+breaker|cb)\s+trip",
            
            # Reinvest
            "reinvest": r"reinvest|trigger\s+reinvest|run\s+reinvest",
            
            # Admin
            "send_test_report": r"send\s+test\s+report|test\s+email|test\s+report",
        }
    
    def normalize_text(self, text: str) -> str:
        """Normalize text by expanding synonyms"""
        text_lower = text.lower()
        
        # Expand synonyms
        for key, synonyms in self.SYNONYMS.items():
            for synonym in synonyms:
                pattern = r'\b' + re.escape(synonym) + r'\b'
                text_lower = re.sub(pattern, key, text_lower)
        
        return text_lower
    
    async def find_bot_fuzzy(self, user_id: str, bot_identifier: str, threshold: int = 80) -> Optional[Dict]:
        """Find bot using fuzzy matching"""
        # Get all user's bots
        bots = await self.bots_collection.find({"user_id": user_id}, {"_id": 0}).to_list(1000)
        
        if not bots:
            return None
        
        # Try exact ID match first
        for bot in bots:
            if bot.get("id") == bot_identifier:
                return bot
        
        # Try fuzzy name matching
        bot_names = {bot.get("name"): bot for bot in bots}
        
        # Use rapidfuzz to find best match - WRatio for better handling of different length strings
        match = process.extractOne(
            bot_identifier,
            bot_names.keys(),
            scorer=fuzz.WRatio,  # WRatio better for strings of different lengths
            score_cutoff=threshold
        )
        
        if match:
            matched_name, score, _ = match
            logger.info(f"Fuzzy matched '{bot_identifier}' to '{matched_name}' (score: {score})")
            return bot_names[matched_name]
        
        return None
    
    async def parse_multi_command(self, message: str) -> List[Tuple[str, List[str]]]:
        """Parse multi-command input like 'pause alpha and beta'"""
        # Check for multi-bot pattern
        pattern = r"(?:pause|stop|resume|start)\s+(?:bots?\s+)?(.+?)\s+(?:and|,)\s+(.+)"
        match = re.search(pattern, message.lower())
        
        if match:
            action = re.search(r"(pause|stop|resume|start)", message.lower()).group(1)
            bot1 = match.group(1).strip()
            bot2 = match.group(2).strip()
            
            command_map = {
                "pause": "pause_bot",
                "stop": "stop_bot",
                "resume": "resume_bot",
                "start": "start_bot"
            }
            
            return [
                (command_map.get(action, "pause_bot"), [bot1]),
                (command_map.get(action, "pause_bot"), [bot2])
            ]
        
        return []
    
    async def parse_and_execute(
        self,
        user_id: str,
        message: str,
        confirmed: bool = False,
        confirmation_phrase: str = None,
        is_admin: bool = False
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Parse message and execute command with enhanced features
        
        Returns:
            (is_command, result_dict)
        """
        # Normalize message (expand synonyms)
        normalized_message = self.normalize_text(message)
        
        # Check for multi-command
        multi_commands = await self.parse_multi_command(normalized_message)
        if multi_commands:
            results = []
            for cmd_name, bot_identifiers in multi_commands:
                for bot_id in bot_identifiers:
                    result = await self._execute_single_command(
                        user_id, cmd_name, (bot_id,), confirmed, confirmation_phrase, is_admin
                    )
                    results.append(result)
            
            return True, {
                "multi_command": True,
                "results": results,
                "message": f"Executed {len(results)} commands"
            }
        
        # Try to match command patterns
        for command_name, pattern in self.command_patterns.items():
            match = re.search(pattern, normalized_message)
            if match:
                result = await self._execute_single_command(
                    user_id, command_name, match.groups(), confirmed, confirmation_phrase, is_admin
                )
                return True, result
        
        # Not a command
        return False, {}
    
    async def _execute_single_command(
        self,
        user_id: str,
        command: str,
        match_groups: tuple,
        confirmed: bool,
        confirmation_phrase: str,
        is_admin: bool
    ) -> Dict[str, Any]:
        """Execute a single parsed command with confirmation handling"""
        try:
            # Check admin permission
            if command == "send_test_report" and not is_admin:
                return CommandOutputSchema.error(
                    command,
                    "This command requires admin privileges",
                    "PERMISSION_DENIED"
                )
            
            # Get confirmation level
            confirmation_level = self.CONFIRMATION_MAP.get(command, ConfirmationLevel.NONE)
            
            # Handle confirmation requirements
            if confirmation_level != ConfirmationLevel.NONE and not confirmed:
                if confirmation_level == ConfirmationLevel.DOUBLE:
                    required_phrase = "CONFIRM EMERGENCY STOP"
                    if confirmation_phrase != required_phrase:
                        return CommandOutputSchema.requires_confirmation(
                            command,
                            f"⚠️ This is a CRITICAL action. Type exactly: '{required_phrase}' to confirm.",
                            confirmation_level
                        )
                elif confirmation_level == ConfirmationLevel.TYPED_PHRASE:
                    required_phrase = "I UNDERSTAND THE RISKS"
                    if confirmation_phrase != required_phrase:
                        return CommandOutputSchema.requires_confirmation(
                            command,
                            f"⚠️ This action requires typing: '{required_phrase}' to confirm.",
                            confirmation_level
                        )
                elif confirmation_level in [ConfirmationLevel.REQUIRED, ConfirmationLevel.OPTIONAL]:
                    return CommandOutputSchema.requires_confirmation(
                        command,
                        "⚠️ This action requires confirmation. Confirm to proceed.",
                        confirmation_level
                    )
            
            # Execute command
            return await self._execute_command_logic(user_id, command, match_groups, is_admin)
        
        except Exception as e:
            logger.error(f"Command execution error: {e}")
            return CommandOutputSchema.error(
                command,
                f"Error executing command: {str(e)}",
                "EXECUTION_ERROR"
            )
    
    async def _execute_command_logic(
        self,
        user_id: str,
        command: str,
        match_groups: tuple,
        is_admin: bool
    ) -> Dict[str, Any]:
        """Execute the actual command logic"""
        
        # Bot lifecycle commands
        if command in ["pause_bot", "resume_bot", "stop_bot", "start_bot"]:
            bot_identifier = match_groups[-1] if match_groups else None
            if not bot_identifier:
                return CommandOutputSchema.error(command, "Bot identifier required", "MISSING_BOT")
            
            bot = await self.find_bot_fuzzy(user_id, bot_identifier)
            if not bot:
                return CommandOutputSchema.error(
                    command,
                    f"Bot '{bot_identifier}' not found. Use fuzzy matching or check bot name.",
                    "BOT_NOT_FOUND"
                )
            
            # Use tool registry for bot lifecycle commands
            tool_map = {
                "pause_bot": "pause_bot",
                "resume_bot": "resume_bot",
                "stop_bot": "stop_bot",
                "start_bot": "resume_bot"  # Note: Start uses resume tool (activates inactive bot)
            }
            
            return await self.tool_registry.call_tool(
                tool_map[command],
                user_id,
                {"bot_id": bot["id"]}
            )
        
        # Bulk operations
        elif command == "pause_all":
            result = await self.bots_collection.update_many(
                {"user_id": user_id, "status": "active"},
                {"$set": {"status": "paused"}}
            )
            return CommandOutputSchema.success(
                "pause_all",
                f"Paused {result.modified_count} bot(s)",
                data={"count": result.modified_count}
            )
        
        elif command == "resume_all":
            result = await self.bots_collection.update_many(
                {"user_id": user_id, "status": "paused"},
                {"$set": {"status": "active"}}
            )
            return CommandOutputSchema.success(
                "resume_all",
                f"Resumed {result.modified_count} bot(s)",
                data={"count": result.modified_count}
            )
        
        # Emergency stop
        elif command == "emergency_stop":
            return await self.tool_registry.call_tool("emergency_stop", user_id)
        
        # Status/Info commands
        elif command == "portfolio_summary":
            return await self.tool_registry.call_tool("get_portfolio_summary", user_id)
        
        elif command == "profits":
            return await self.tool_registry.call_tool("get_profit_series", user_id)
        
        elif command == "bot_status":
            bot_identifier = match_groups[-1] if match_groups else None
            bot = await self.find_bot_fuzzy(user_id, bot_identifier)
            if not bot:
                return CommandOutputSchema.error(command, f"Bot '{bot_identifier}' not found", "BOT_NOT_FOUND")
            
            return CommandOutputSchema.success(
                "bot_status",
                f"Status for bot '{bot.get('name')}'",
                data={
                    "name": bot.get("name"),
                    "status": bot.get("status"),
                    "current_capital": round(bot.get("current_capital", 0), 2),
                    "total_profit": round(bot.get("total_profit", 0), 2),
                    "trades_count": bot.get("trades_count", 0),
                    "win_rate": round(bot.get("win_rate", 0), 2)
                }
            )
        
        elif command == "show_health":
            return await self.tool_registry.call_tool("get_health_status", user_id)
        
        elif command == "show_alerts":
            return await self.tool_registry.call_tool("get_alerts", user_id)
        
        # Reinvest
        elif command == "reinvest":
            return await self.tool_registry.call_tool("trigger_reinvestment", user_id)
        
        # Admin
        elif command == "send_test_report":
            return await self.tool_registry.call_tool("send_test_report", user_id)
        
        else:
            return CommandOutputSchema.error(
                command,
                "Unknown command",
                "UNKNOWN_COMMAND"
            )


def get_enhanced_ai_command_router(db):
    """Factory function to get enhanced command router"""
    return EnhancedAICommandRouter(db)
