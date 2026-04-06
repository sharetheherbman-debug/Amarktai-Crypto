"""
Backtesting Engine
- Test strategies on historical data
- Performance simulation (SIMULATED — uses statistical random walk, not real CCXT candles)
- Strategy optimization

NOTE: The current implementation uses a Monte Carlo / random-walk simulation to
approximate historical performance.  Results are labelled ``is_simulated=True``
and must NOT be used to drive live trading decisions.  A real CCXT-based
backtester is tracked in the upgrade list (R4).
"""

import asyncio
from datetime import datetime, timezone, timedelta
from logger_config import logger
import random


class BacktestingEngine:
    def __init__(self):
        self.results_cache = {}
    
    async def backtest_strategy(self, strategy_params: dict, start_date: str, end_date: str, initial_capital: float = 1000) -> dict:
        """Backtest a trading strategy"""
        try:
            logger.info(f"Starting backtest: {start_date} to {end_date}")
            
            # Simulate historical trades
            trades = await self._simulate_trades(
                strategy_params,
                start_date,
                end_date,
                initial_capital
            )
            
            # Calculate performance metrics
            metrics = self._calculate_metrics(trades, initial_capital)
            
            result = {
                "strategy": strategy_params,
                "period": {"start": start_date, "end": end_date},
                "initial_capital": initial_capital,
                "trades": trades,
                "metrics": metrics,
                "is_simulated": True,  # Random-walk simulation — not real historical CCXT data
                "simulation_note": "Results are based on statistical simulation, not real market data.",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
            return result
            
        except Exception as e:
            logger.error(f"Backtesting failed: {e}")
            return {"error": str(e)}
    
    async def _simulate_trades(self, params: dict, start_date: str, end_date: str, capital: float) -> list:
        """Simulate trades over historical period"""
        trades = []
        current_capital = capital
        
        # Parse dates
        start = datetime.fromisoformat(start_date)
        end = datetime.fromisoformat(end_date)
        days = (end - start).days
        
        # Simulate trades (simplified - would use real historical data in production)
        risk_mode = params.get('risk_mode', 'safe')
        
        # Trade frequency based on risk
        trades_per_day = {
            'safe': 2,
            'balanced': 4,
            'risky': 6
        }.get(risk_mode, 2)
        
        total_trades = days * trades_per_day
        
        # Win rate based on risk
        win_rate = {
            'safe': 0.60,
            'balanced': 0.55,
            'risky': 0.50
        }.get(risk_mode, 0.55)
        
        for i in range(total_trades):
            # Simulate trade
            is_win = random.random() < win_rate
            
            if is_win:
                pnl = current_capital * random.uniform(0.005, 0.02)  # 0.5-2% gain
            else:
                pnl = -current_capital * random.uniform(0.003, 0.015)  # 0.3-1.5% loss
            
            current_capital += pnl
            
            trade = {
                "date": (start + timedelta(days=i/trades_per_day)).isoformat(),
                "pnl": round(pnl, 2),
                "capital_after": round(current_capital, 2),
                "side": "buy" if is_win else "sell"
            }
            
            trades.append(trade)
        
        return trades
    
    def _calculate_metrics(self, trades: list, initial_capital: float) -> dict:
        """Calculate performance metrics"""
        if not trades:
            return {}
        
        final_capital = trades[-1]['capital_after']
        total_return = ((final_capital - initial_capital) / initial_capital) * 100
        
        winning_trades = [t for t in trades if t['pnl'] > 0]
        losing_trades = [t for t in trades if t['pnl'] < 0]
        
        win_rate = (len(winning_trades) / len(trades)) * 100 if trades else 0
        
        total_profit = sum(t['pnl'] for t in winning_trades)
        total_loss = abs(sum(t['pnl'] for t in losing_trades))
        profit_factor = total_profit / total_loss if total_loss > 0 else total_profit
        
        # Calculate max drawdown
        peak = initial_capital
        max_drawdown = 0
        
        for trade in trades:
            capital = trade['capital_after']
            if capital > peak:
                peak = capital
            drawdown = ((peak - capital) / peak) * 100
            max_drawdown = max(max_drawdown, drawdown)
        
        # Sharpe ratio (simplified)
        returns = [t['pnl'] / initial_capital for t in trades]
        avg_return = sum(returns) / len(returns)
        import math
        std_dev = math.sqrt(sum((r - avg_return) ** 2 for r in returns) / len(returns))
        sharpe = (avg_return / std_dev) * math.sqrt(252) if std_dev > 0 else 0
        
        return {
            "total_trades": len(trades),
            "winning_trades": len(winning_trades),
            "losing_trades": len(losing_trades),
            "win_rate": round(win_rate, 2),
            "total_return": round(total_return, 2),
            "final_capital": round(final_capital, 2),
            "profit_factor": round(profit_factor, 2),
            "max_drawdown": round(max_drawdown, 2),
            "sharpe_ratio": round(sharpe, 2),
            "avg_trade_pnl": round(sum(t['pnl'] for t in trades) / len(trades), 2)
        }
    
    async def optimize_strategy(self, base_params: dict, start_date: str, end_date: str) -> dict:
        """Optimize strategy parameters"""
        best_result = None
        best_return = float('-inf')
        
        risk_modes = ['safe', 'balanced', 'risky']
        
        for risk_mode in risk_modes:
            params = {**base_params, 'risk_mode': risk_mode}
            result = await self.backtest_strategy(params, start_date, end_date)
            
            if 'metrics' in result:
                total_return = result['metrics'].get('total_return', 0)
                if total_return > best_return:
                    best_return = total_return
                    best_result = result
        
        return best_result or {}


# Global instance
backtesting_engine = BacktestingEngine()
