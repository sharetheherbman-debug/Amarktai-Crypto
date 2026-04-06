"""
On-Chain Whale Activity Monitor
Tracks large blockchain transactions and provides actionable trading signals
Monitors: BTC transfers (>= $100), ETH transfers (>= $1,000)
"""

import aiohttp
import asyncio
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class WhaleActivityType(Enum):
    """Types of whale activity"""
    EXCHANGE_INFLOW = "exchange_inflow"  # Bearish signal
    EXCHANGE_OUTFLOW = "exchange_outflow"  # Bullish signal
    LARGE_TRANSFER = "large_transfer"  # Neutral, needs context
    ACCUMULATION = "accumulation"  # Bullish signal
    DISTRIBUTION = "distribution"  # Bearish signal


@dataclass
class WhaleTransaction:
    """Whale transaction data"""
    timestamp: datetime
    coin: str  # BTC, ETH, etc.
    amount: float
    amount_usd: float
    from_address: str
    to_address: str
    tx_hash: str
    activity_type: WhaleActivityType
    exchange_name: Optional[str] = None


@dataclass
class WhaleSignal:
    """Trading signal from whale activity"""
    timestamp: datetime
    coin: str
    signal: str  # 'bullish', 'bearish', 'neutral'
    strength: float  # 0.0 to 1.0
    reason: str
    recent_transactions: List[WhaleTransaction]
    metrics: Dict[str, float]


class OnChainWhaleMonitor:
    """
    Monitors blockchain activity for large transactions (whale movements)
    Provides trading signals based on whale behavior
    """
    
    def __init__(
        self,
        btc_threshold_usd: float = 100.0,
        eth_threshold_count: float = 1000.0,
        lookback_hours: int = 24
    ):
        """
        Initialize whale monitor
        
        Args:
            btc_threshold_usd: BTC transaction threshold in USD (default: $100)
            eth_threshold_count: ETH transaction threshold in ETH (default: 1,000 ETH)
            lookback_hours: Hours of history to maintain (default: 24)
        """
        self.btc_threshold_usd = btc_threshold_usd
        self.eth_threshold_count = eth_threshold_count
        self.lookback_hours = lookback_hours
        
        # Transaction history per coin
        self.transactions: Dict[str, List[WhaleTransaction]] = {
            'BTC': [],
            'ETH': [],
            'USDT': [],
            'USDC': []
        }
        
        # Known exchange addresses (simplified - in production use full list)
        self.exchange_addresses = {
            'binance': ['1NDyJtNTjmwk5xPNhjgAMu4HDHigtobu1s', '0x28c6c06298d514db089934071355e5743bf21d60'],
            'coinbase': ['1FzWLkAahHooV3kzTgyx3XYC9iJ7zH3w5X', '0x71660c4005ba85c37ccec55d0c4493e66fe775d3'],
            'okx': ['1KzXE97kV7DrpxCViCN3HbGbiKhzzPM7TQ', '0x236f9f97e0e62388479bf9e5ba4889e46b0273c3']
        }
        
        # Exchange flow tracking
        self.exchange_flows: Dict[str, Dict[str, float]] = {}
        
        # Price cache for USD conversion
        self.price_cache: Dict[str, float] = {}
        self.last_price_update = None
    
    async def _get_current_prices(self) -> Dict[str, float]:
        """
        Get current crypto prices
        
        Returns:
            Dictionary of coin -> USD price
        """
        # Cache for 1 minute
        if (self.last_price_update and 
            datetime.now(timezone.utc) - self.last_price_update < timedelta(minutes=1)):
            return self.price_cache
        
        try:
            async with aiohttp.ClientSession() as session:
                # Using CoinGecko API (free tier)
                url = "https://api.coingecko.com/api/v3/simple/price"
                params = {
                    'ids': 'bitcoin,ethereum,tether,usd-coin',
                    'vs_currencies': 'usd'
                }
                
                async with session.get(url, params=params) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        self.price_cache = {
                            'BTC': data.get('bitcoin', {}).get('usd', 50000),
                            'ETH': data.get('ethereum', {}).get('usd', 3000),
                            'USDT': data.get('tether', {}).get('usd', 1),
                            'USDC': data.get('usd-coin', {}).get('usd', 1)
                        }
                        self.last_price_update = datetime.now(timezone.utc)
                        return self.price_cache
        except Exception as e:
            logger.error(f"Error fetching prices: {e}")
        
        # Return cached or default prices
        return self.price_cache or {
            'BTC': 50000,
            'ETH': 3000,
            'USDT': 1,
            'USDC': 1
        }
    
    def _classify_address(self, address: str) -> Tuple[bool, Optional[str]]:
        """
        Classify if address belongs to an exchange
        
        Args:
            address: Blockchain address
            
        Returns:
            (is_exchange, exchange_name)
        """
        for exchange_name, addresses in self.exchange_addresses.items():
            if address in addresses:
                return True, exchange_name
        
        return False, None
    
    def _determine_activity_type(
        self,
        from_address: str,
        to_address: str
    ) -> WhaleActivityType:
        """
        Determine type of whale activity
        
        Args:
            from_address: Source address
            to_address: Destination address
            
        Returns:
            WhaleActivityType
        """
        from_is_exchange, from_exchange = self._classify_address(from_address)
        to_is_exchange, to_exchange = self._classify_address(to_address)
        
        if not from_is_exchange and to_is_exchange:
            return WhaleActivityType.EXCHANGE_INFLOW
        elif from_is_exchange and not to_is_exchange:
            return WhaleActivityType.EXCHANGE_OUTFLOW
        else:
            return WhaleActivityType.LARGE_TRANSFER
    
    async def add_transaction(
        self,
        coin: str,
        amount: float,
        from_address: str,
        to_address: str,
        tx_hash: str
    ) -> Optional[WhaleTransaction]:
        """
        Add whale transaction to monitoring
        
        Args:
            coin: Cryptocurrency (BTC, ETH, etc.)
            amount: Transaction amount in native units
            from_address: Source address
            to_address: Destination address
            tx_hash: Transaction hash
            
        Returns:
            WhaleTransaction if significant, None otherwise
        """
        # Get current prices
        prices = await self._get_current_prices()
        amount_usd = amount * prices.get(coin, 0)
        
        # Check if transaction meets threshold
        if coin == 'BTC' and amount_usd < self.btc_threshold_usd:
            return None
        elif coin == 'ETH' and amount < self.eth_threshold_count:
            return None
        elif coin in ['USDT', 'USDC'] and amount < 100000:  # $100k threshold for stablecoins
            return None
        
        # Classify activity
        activity_type = self._determine_activity_type(from_address, to_address)
        
        _, exchange_name = self._classify_address(to_address)
        if exchange_name is None:
            _, exchange_name = self._classify_address(from_address)
        
        transaction = WhaleTransaction(
            timestamp=datetime.now(timezone.utc),
            coin=coin,
            amount=amount,
            amount_usd=amount_usd,
            from_address=from_address,
            to_address=to_address,
            tx_hash=tx_hash,
            activity_type=activity_type,
            exchange_name=exchange_name
        )
        
        # Store transaction
        if coin not in self.transactions:
            self.transactions[coin] = []
        
        self.transactions[coin].append(transaction)
        
        # Clean old transactions
        cutoff = datetime.now(timezone.utc) - timedelta(hours=self.lookback_hours)
        self.transactions[coin] = [
            tx for tx in self.transactions[coin]
            if tx.timestamp > cutoff
        ]
        
        logger.info(
            f"Whale transaction: {amount:.2f} {coin} (${amount_usd:,.0f}) "
            f"{activity_type.value}"
        )
        
        return transaction
    
    async def calculate_exchange_flows(self, coin: str, hours: int = 1) -> Dict[str, float]:
        """
        Calculate net exchange flows (inflows - outflows)
        
        Args:
            coin: Cryptocurrency
            hours: Time window in hours
            
        Returns:
            Dictionary of metrics
        """
        if coin not in self.transactions:
            return {'net_flow': 0, 'inflows': 0, 'outflows': 0}
        
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        
        recent_txs = [
            tx for tx in self.transactions[coin]
            if tx.timestamp > cutoff
        ]
        
        inflows = sum(
            tx.amount_usd for tx in recent_txs
            if tx.activity_type == WhaleActivityType.EXCHANGE_INFLOW
        )
        
        outflows = sum(
            tx.amount_usd for tx in recent_txs
            if tx.activity_type == WhaleActivityType.EXCHANGE_OUTFLOW
        )
        
        net_flow = inflows - outflows
        
        return {
            'net_flow': net_flow,
            'inflows': inflows,
            'outflows': outflows,
            'transaction_count': len(recent_txs)
        }
    
    async def get_whale_signal(self, coin: str) -> Optional[WhaleSignal]:
        """
        Generate trading signal from whale activity
        
        Args:
            coin: Cryptocurrency
            
        Returns:
            WhaleSignal with recommendation
        """
        if coin not in self.transactions or not self.transactions[coin]:
            return None
        
        # Get recent transactions (last hour)
        cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
        recent_txs = [
            tx for tx in self.transactions[coin]
            if tx.timestamp > cutoff
        ]
        
        if not recent_txs:
            return None
        
        # Calculate metrics
        flows = await self.calculate_exchange_flows(coin, hours=1)
        
        # Determine signal
        signal = 'neutral'
        strength = 0.0
        reason = ''
        
        # Bearish: Large inflows to exchanges (selling pressure)
        if flows['net_flow'] > 0 and flows['inflows'] > 500000:  # $500k threshold
            signal = 'bearish'
            strength = min(flows['inflows'] / 5000000, 1.0)  # Normalize to $5M max
            reason = f"Large exchange inflows: ${flows['inflows']:,.0f} (selling pressure)"
        
        # Bullish: Large outflows from exchanges (accumulation)
        elif flows['net_flow'] < 0 and flows['outflows'] > 500000:
            signal = 'bullish'
            strength = min(flows['outflows'] / 5000000, 1.0)
            reason = f"Large exchange outflows: ${flows['outflows']:,.0f} (accumulation)"
        
        # Mixed signals
        elif abs(flows['net_flow']) < 100000:
            signal = 'neutral'
            strength = 0.3
            reason = "Balanced exchange flows"
        
        whale_signal = WhaleSignal(
            timestamp=datetime.now(timezone.utc),
            coin=coin,
            signal=signal,
            strength=strength,
            reason=reason,
            recent_transactions=recent_txs[-10:],  # Last 10 transactions
            metrics=flows
        )
        
        logger.info(f"Whale signal for {coin}: {signal} (strength: {strength:.2%}) - {reason}")
        
        return whale_signal
    
    async def get_summary(self) -> Dict[str, Dict]:
        """
        Get summary of whale activity for all tracked coins
        
        Returns:
            Dictionary of coin -> activity summary
        """
        summary = {}
        
        for coin in self.transactions.keys():
            flows_1h = await self.calculate_exchange_flows(coin, hours=1)
            flows_24h = await self.calculate_exchange_flows(coin, hours=24)
            signal = await self.get_whale_signal(coin)
            
            summary[coin] = {
                'total_transactions_24h': len([
                    tx for tx in self.transactions[coin]
                    if tx.timestamp > datetime.now(timezone.utc) - timedelta(hours=24)
                ]),
                'flows_1h': flows_1h,
                'flows_24h': flows_24h,
                'signal': {
                    'type': signal.signal if signal else 'unknown',
                    'strength': signal.strength if signal else 0.0,
                    'reason': signal.reason if signal else 'No recent activity'
                } if signal else None
            }
        
        return summary
    
    async def simulate_whale_activity(self, coin: str = 'BTC', n_transactions: int = 20) -> None:
        """
        Simulate whale transactions for testing (paper/dev mode only).

        This method is intentionally disabled when ENABLE_LIVE_TRADING=true to prevent
        fabricated on-chain signals from influencing real trading decisions.

        Args:
            coin: Cryptocurrency
            n_transactions: Number of transactions to simulate
        """
        import os
        if os.getenv('ENABLE_LIVE_TRADING', 'false').lower() == 'true':
            logger.warning(
                "simulate_whale_activity() is disabled in live trading mode — "
                "skipping to prevent synthetic signals from affecting real orders."
            )
            return
        import random
        
        exchanges = list(self.exchange_addresses.keys())
        
        for i in range(n_transactions):
            # Random amount
            if coin == 'BTC':
                amount = random.uniform(10, 100)  # 10-100 BTC
            elif coin == 'ETH':
                amount = random.uniform(1000, 5000)  # 1000-5000 ETH
            else:
                amount = random.uniform(100000, 1000000)  # $100k-$1M
            
            # Random exchange
            exchange = random.choice(exchanges)
            exchange_addr = random.choice(self.exchange_addresses[exchange])
            whale_addr = f"whale_{i}_address"
            
            # Random direction (inflow or outflow)
            if random.random() > 0.5:
                # Inflow to exchange
                from_addr = whale_addr
                to_addr = exchange_addr
            else:
                # Outflow from exchange
                from_addr = exchange_addr
                to_addr = whale_addr
            
            tx_hash = f"0x{i:064x}"
            
            await self.add_transaction(
                coin=coin,
                amount=amount,
                from_address=from_addr,
                to_address=to_addr,
                tx_hash=tx_hash
            )
            
            await asyncio.sleep(0.01)


# Global instance
whale_monitor = OnChainWhaleMonitor()
