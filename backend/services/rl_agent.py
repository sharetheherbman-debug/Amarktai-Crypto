"""
Reinforcement Learning Agent Service
Implements a policy-gradient RL agent that adjusts bot parameters based on reward signals.
"""

import numpy as np
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timezone
import logging
import json

logger = logging.getLogger(__name__)


class RLAgent:
    """
    Policy-Gradient Reinforcement Learning Agent for Trading Bot Optimization
    
    Adjusts bot parameters (stop loss, take profit, position size, etc.) based on:
    - Profit/Loss rewards
    - Sharpe ratio
    - Maximum drawdown
    - Win rate
    """
    
    def __init__(self, learning_rate: float = 0.01, gamma: float = 0.99):
        """
        Initialize RL agent with hyperparameters.
        
        Args:
            learning_rate: Learning rate for policy updates
            gamma: Discount factor for future rewards
        """
        self.learning_rate = learning_rate
        self.gamma = gamma
        
        # Policy parameters (weights for parameter adjustments)
        self.policy_weights = {
            'stop_loss_pct': 0.0,
            'take_profit_pct': 0.0,
            'position_size_multiplier': 0.0,
            'risk_per_trade_pct': 0.0,
            'cooldown_minutes': 0.0
        }
        
        # Training history
        self.episodes = 0
        self.total_reward = 0.0
        self.policy_updates = 0
        self.reward_history = []
        
        logger.info("RL Agent initialized")
    
    def calculate_reward(
        self,
        profit: float,
        sharpe_ratio: Optional[float] = None,
        max_drawdown: Optional[float] = None,
        win_rate: Optional[float] = None,
        trades_count: int = 0
    ) -> float:
        """
        Calculate reward signal from bot performance metrics.
        
        Args:
            profit: Total profit/loss in ZAR
            sharpe_ratio: Risk-adjusted return metric
            max_drawdown: Maximum drawdown percentage
            win_rate: Percentage of winning trades
            trades_count: Number of trades executed
            
        Returns:
            Reward signal (higher is better)
        """
        # Base reward from profit
        reward = profit / 100.0  # Normalize by dividing by 100
        
        # Bonus for good Sharpe ratio
        if sharpe_ratio is not None and sharpe_ratio > 0:
            reward += sharpe_ratio * 0.5
        
        # Penalty for high drawdown
        if max_drawdown is not None and max_drawdown > 0:
            reward -= (max_drawdown / 100.0) * 2.0
        
        # Bonus for high win rate
        if win_rate is not None and win_rate > 50:
            reward += (win_rate - 50) / 100.0
        
        # Small penalty if too few trades (encourage activity)
        if trades_count < 10:
            reward -= 0.1
        
        return reward
    
    def select_action(self, state: Dict) -> Dict:
        """
        Select parameter adjustments based on current policy.
        
        Args:
            state: Current bot state with performance metrics
            
        Returns:
            Dictionary of parameter adjustments
        """
        # Add exploration noise (epsilon-greedy with decay)
        epsilon = max(0.1, 1.0 - (self.episodes / 1000.0))
        
        adjustments = {}
        
        for param, weight in self.policy_weights.items():
            if np.random.random() < epsilon:
                # Explore: random adjustment
                adjustment = np.random.uniform(-0.1, 0.1)
            else:
                # Exploit: use policy weight
                adjustment = weight + np.random.normal(0, 0.02)  # Small noise
            
            adjustments[param] = adjustment
        
        return adjustments
    
    def update_policy(
        self,
        state: Dict,
        action: Dict,
        reward: float,
        next_state: Dict
    ):
        """
        Update policy weights based on experience using policy gradient.
        
        Args:
            state: Previous state
            action: Action taken (parameter adjustments)
            reward: Reward received
            next_state: Resulting state
        """
        # Simple policy gradient update
        for param, adjustment in action.items():
            if param in self.policy_weights:
                # Update weight in direction of reward
                gradient = reward * adjustment
                self.policy_weights[param] += self.learning_rate * gradient
                
                # Clip weights to reasonable range
                self.policy_weights[param] = np.clip(
                    self.policy_weights[param],
                    -1.0,
                    1.0
                )
        
        self.policy_updates += 1
        self.total_reward += reward
        self.reward_history.append(reward)
        
        # Keep only last 100 rewards
        if len(self.reward_history) > 100:
            self.reward_history = self.reward_history[-100:]
    
    def generate_recommendations(
        self,
        current_params: Dict,
        performance_metrics: Dict
    ) -> List[Dict]:
        """
        Generate parameter adjustment recommendations for a bot.
        
        Args:
            current_params: Current bot parameters
            performance_metrics: Recent performance metrics
            
        Returns:
            List of recommended parameter changes with reasoning
        """
        recommendations = []
        
        # Calculate current reward
        reward = self.calculate_reward(
            profit=performance_metrics.get('total_profit', 0),
            sharpe_ratio=performance_metrics.get('sharpe_ratio'),
            max_drawdown=performance_metrics.get('max_drawdown'),
            win_rate=performance_metrics.get('win_rate'),
            trades_count=performance_metrics.get('trades_count', 0)
        )
        
        # Get policy-based adjustments
        state = {
            'profit': performance_metrics.get('total_profit', 0),
            'win_rate': performance_metrics.get('win_rate', 50),
            'sharpe': performance_metrics.get('sharpe_ratio', 0)
        }
        
        adjustments = self.select_action(state)
        
        # Stop Loss adjustment
        if 'stop_loss_pct' in current_params:
            current_sl = current_params['stop_loss_pct']
            adjustment = adjustments.get('stop_loss_pct', 0)
            new_sl = current_sl * (1 + adjustment)
            new_sl = np.clip(new_sl, 1.0, 10.0)  # Keep between 1% and 10%
            
            if abs(new_sl - current_sl) > 0.1:
                reason = "Adjust stop loss based on drawdown pattern"
                if performance_metrics.get('max_drawdown', 0) > 15:
                    reason = "Tighten stop loss due to high drawdown"
                
                recommendations.append({
                    'parameter': 'stop_loss_pct',
                    'current_value': current_sl,
                    'suggested_value': round(new_sl, 2),
                    'reason': reason,
                    'confidence': abs(reward) / 10.0
                })
        
        # Take Profit adjustment
        if 'take_profit_pct' in current_params:
            current_tp = current_params['take_profit_pct']
            adjustment = adjustments.get('take_profit_pct', 0)
            new_tp = current_tp * (1 + adjustment)
            new_tp = np.clip(new_tp, 2.0, 20.0)  # Keep between 2% and 20%
            
            if abs(new_tp - current_tp) > 0.2:
                reason = "Optimize take profit based on profit distribution"
                recommendations.append({
                    'parameter': 'take_profit_pct',
                    'current_value': current_tp,
                    'suggested_value': round(new_tp, 2),
                    'reason': reason,
                    'confidence': abs(reward) / 10.0
                })
        
        # Position Size adjustment
        if 'position_size_multiplier' in current_params:
            current_size = current_params['position_size_multiplier']
            adjustment = adjustments.get('position_size_multiplier', 0)
            new_size = current_size * (1 + adjustment)
            new_size = np.clip(new_size, 0.5, 2.0)  # Keep between 0.5x and 2x
            
            if abs(new_size - current_size) > 0.1:
                reason = "Adjust position sizing based on win rate"
                if performance_metrics.get('win_rate', 50) > 60:
                    reason = "Increase size due to high win rate"
                elif performance_metrics.get('win_rate', 50) < 40:
                    reason = "Decrease size due to low win rate"
                
                recommendations.append({
                    'parameter': 'position_size_multiplier',
                    'current_value': current_size,
                    'suggested_value': round(new_size, 2),
                    'reason': reason,
                    'confidence': abs(reward) / 10.0
                })
        
        return recommendations
    
    def get_status(self) -> Dict:
        """
        Get current RL agent status and metrics.
        
        Returns:
            Dictionary with agent statistics
        """
        avg_reward = (
            sum(self.reward_history) / len(self.reward_history)
            if self.reward_history
            else 0.0
        )
        
        return {
            'episodes': self.episodes,
            'policy_updates': self.policy_updates,
            'total_reward': round(self.total_reward, 2),
            'avg_reward': round(avg_reward, 2),
            'policy_weights': {
                k: round(v, 4) for k, v in self.policy_weights.items()
            },
            'recent_rewards': [round(r, 2) for r in self.reward_history[-10:]],
            'learning_rate': self.learning_rate,
            'gamma': self.gamma
        }
    
    def save_state(self) -> Dict:
        """Save agent state for persistence."""
        return {
            'policy_weights': self.policy_weights,
            'episodes': self.episodes,
            'total_reward': self.total_reward,
            'policy_updates': self.policy_updates,
            'reward_history': self.reward_history,
            'learning_rate': self.learning_rate,
            'gamma': self.gamma,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
    
    def load_state(self, state: Dict):
        """Load agent state from persistence."""
        self.policy_weights = state.get('policy_weights', self.policy_weights)
        self.episodes = state.get('episodes', 0)
        self.total_reward = state.get('total_reward', 0.0)
        self.policy_updates = state.get('policy_updates', 0)
        self.reward_history = state.get('reward_history', [])
        self.learning_rate = state.get('learning_rate', self.learning_rate)
        self.gamma = state.get('gamma', self.gamma)
        
        logger.info(f"RL Agent state loaded: {self.episodes} episodes, {self.policy_updates} updates")


# Global RL agent instance
rl_agent = RLAgent()


def get_rl_agent() -> RLAgent:
    """Get the global RL agent instance."""
    return rl_agent


async def initialize_rl_agent():
    """
    Initialize RL agent by loading state from database.
    Should be called on server startup.
    """
    try:
        import database as db
        
        if db.db is None:
            logger.warning("Database not connected, RL agent starting with default state")
            return
        
        # Load state from database
        state_doc = await db.db.rl_agent_state.find_one({"_id": "global"})
        
        if state_doc:
            # Remove MongoDB _id field
            state_doc.pop('_id', None)
            rl_agent.load_state(state_doc)
            logger.info(f"✅ RL Agent initialized from database: {rl_agent.episodes} episodes")
        else:
            logger.info("ℹ️ RL Agent starting fresh (no saved state found)")
    except Exception as e:
        logger.error(f"Failed to initialize RL agent from database: {e}")
        logger.info("RL Agent starting with default state")
