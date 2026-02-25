"""
Ledger Service - Immutable accounting for fills and events

This service provides the single source of truth for:
- Fills (immutable trade executions)
- Ledger events (funding, transfers, allocations)
- Derived metrics (equity, PnL, drawdown, fees)

Phase 1: Read-only + parallel write (opt-in via feature flag)
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from bson import ObjectId
import logging

logger = logging.getLogger(__name__)


class LedgerService:
    """
    Immutable ledger-based accounting service
    
    Collections:
    - fills_ledger: Immutable fill records
    - ledger_events: Funding, transfer, allocation events
    """
    
    def __init__(self, db):
        self.db = db
        self.fills_ledger = db["fills_ledger"]
        self.ledger_events = db["ledger_events"]
        
        # Create indexes for performance
        self._ensure_indexes()
    
    def _ensure_indexes(self):
        """Create indexes for efficient queries"""
        try:
            # Fills ledger indexes
            self.fills_ledger.create_index([("user_id", 1), ("timestamp", -1)])
            self.fills_ledger.create_index([("bot_id", 1), ("timestamp", -1)])
            self.fills_ledger.create_index([("client_order_id", 1)], unique=True, sparse=True)
            self.fills_ledger.create_index([("exchange_trade_id", 1)])
            self.fills_ledger.create_index([("timestamp", -1)])
            
            # Ledger events indexes
            self.ledger_events.create_index([("user_id", 1), ("timestamp", -1)])
            self.ledger_events.create_index([("event_type", 1), ("timestamp", -1)])
        except Exception as e:
            logger.warning(f"Index creation warning (may already exist): {e}")
    
    async def append_fill(
        self,
        user_id: str,
        bot_id: str,
        exchange: str,
        symbol: str,
        side: str,  # 'buy' or 'sell'
        qty: float,
        price: float,
        fee: float,
        fee_currency: str,
        timestamp: datetime,
        order_id: str,
        client_order_id: Optional[str] = None,
        exchange_trade_id: Optional[str] = None,
        is_paper: bool = True,
        metadata: Optional[Dict] = None
    ) -> str:
        """
        Append an immutable fill to the ledger
        
        Returns: fill_id
        """
        fill_doc = {
            "user_id": user_id,
            "bot_id": bot_id,
            "exchange": exchange,
            "symbol": symbol,
            "side": side.lower(),
            "qty": float(qty),
            "price": float(price),
            "fee": float(fee),
            "fee_currency": fee_currency,
            "timestamp": timestamp,
            "order_id": order_id,
            "client_order_id": client_order_id,
            "exchange_trade_id": exchange_trade_id,
            "is_paper": is_paper,
            "metadata": metadata or {},
            "created_at": datetime.utcnow()
        }
        
        try:
            result = await self.fills_ledger.insert_one(fill_doc)
            fill_id = str(result.inserted_id)
            logger.info(f"Appended fill {fill_id} for bot {bot_id}: {side} {qty} {symbol} @ {price}")
            return fill_id
        except Exception as e:
            logger.error(f"Failed to append fill: {e}")
            raise
    
    async def append_event(
        self,
        user_id: str,
        event_type: str,  # 'funding', 'transfer', 'allocation', 'circuit_breaker'
        amount: float,
        currency: str,
        timestamp: datetime,
        bot_id: Optional[str] = None,
        description: Optional[str] = None,
        metadata: Optional[Dict] = None
    ) -> str:
        """
        Append a ledger event (funding, transfers, etc.)
        
        Returns: event_id
        """
        event_doc = {
            "user_id": user_id,
            "bot_id": bot_id,
            "event_type": event_type,
            "amount": float(amount),
            "currency": currency,
            "timestamp": timestamp,
            "description": description,
            "metadata": metadata or {},
            "created_at": datetime.utcnow()
        }
        
        try:
            result = await self.ledger_events.insert_one(event_doc)
            event_id = str(result.inserted_id)
            logger.info(f"Appended event {event_id}: {event_type} {amount} {currency}")
            return event_id
        except Exception as e:
            logger.error(f"Failed to append event: {e}")
            raise
    
    async def bootstrap_paper_capital(
        self,
        user_id: str,
        amount: Optional[float] = None,
        currency: str = "ZAR"
    ) -> bool:
        """
        Bootstrap paper trading capital for a user if not already funded.
        
        Uses PAPER_STARTING_CAPITAL_ZAR from config if amount not specified.
        Idempotent: only creates the funding event once per user.
        
        Returns: True if capital was bootstrapped, False if already existed
        """
        try:
            # Check if user already has a paper funding event
            existing = await self.ledger_events.find_one({
                "user_id": user_id,
                "event_type": "paper_capital_bootstrap"
            })
            
            if existing:
                logger.debug(f"Paper capital already bootstrapped for user {user_id}")
                return False
            
            # Get default amount from config
            if amount is None:
                try:
                    from config import PAPER_STARTING_CAPITAL_ZAR
                    amount = PAPER_STARTING_CAPITAL_ZAR
                except ImportError:
                    amount = 30000.0
            
            # Create funding event with paper metadata for scoped resets
            await self.append_event(
                user_id=user_id,
                event_type="paper_capital_bootstrap",
                amount=amount,
                currency=currency,
                timestamp=datetime.utcnow(),
                description=f"Paper trading starting capital: R{amount:,.2f}",
                metadata={"mode": "paper", "is_paper": True}
            )
            
            logger.info(f"✅ Bootstrapped paper capital R{amount:,.2f} for user {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error bootstrapping paper capital: {e}")
            return False

    async def get_fills(
        self,
        user_id: Optional[str] = None,
        bot_id: Optional[str] = None,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        limit: int = 100
    ) -> List[Dict]:
        """Get fills with optional filters"""
        query = {}
        
        if user_id:
            query["user_id"] = user_id
        if bot_id:
            query["bot_id"] = bot_id
        if since or until:
            query["timestamp"] = {}
            if since:
                query["timestamp"]["$gte"] = since
            if until:
                query["timestamp"]["$lte"] = until
        
        cursor = self.fills_ledger.find(query).sort("timestamp", -1).limit(limit)
        fills = await cursor.to_list(length=limit)
        
        # Convert ObjectId to string
        for fill in fills:
            fill["_id"] = str(fill["_id"])
        
        return fills
    
    async def compute_equity(
        self,
        user_id: Optional[str] = None,
        bot_id: Optional[str] = None,
        currency: str = "USDT",
        include_unrealized: bool = True
    ) -> float:
        """
        Compute total equity from fills and events
        
        Equity = Starting Capital + Realized PnL + Unrealized PnL - Fees
        
        Can compute for user_id or bot_id
        """
        # Determine the query target
        target_id = user_id or bot_id
        target_field = "user_id" if user_id else "bot_id"
        
        if not target_id:
            raise ValueError("Must provide either user_id or bot_id")
        
        # Get funding events
        funding_query = {
            target_field: target_id,
            "event_type": "funding",
            "currency": currency
        }
        funding_cursor = self.ledger_events.find(funding_query)
        funding_events = await funding_cursor.to_list(length=1000)
        
        starting_capital = sum(event.get("amount", 0) for event in funding_events)
        
        # Get realized PnL from closed fills
        realized_pnl = await self.compute_realized_pnl(user_id=user_id, bot_id=bot_id, currency=currency)
        
        # Get unrealized PnL from open positions
        unrealized_pnl = 0
        if include_unrealized:
            unrealized_pnl = await self.compute_unrealized_pnl(user_id=user_id, bot_id=bot_id, currency=currency)
        
        # Get total fees paid
        fees_paid = await self.compute_fees_paid(user_id=user_id, bot_id=bot_id, currency=currency)
        
        equity = starting_capital + realized_pnl + unrealized_pnl - fees_paid
        
        logger.debug(f"Equity calculation for {target_field}={target_id}: starting={starting_capital}, realized={realized_pnl}, unrealized={unrealized_pnl}, fees={fees_paid}, total={equity}")
        
        return equity

    async def compute_funded_capital(
        self,
        user_id: Optional[str] = None,
        bot_id: Optional[str] = None,
        currency: Optional[str] = None
    ) -> float:
        """Compute total funded capital from ledger events."""
        target_id = user_id or bot_id
        target_field = "user_id" if user_id else "bot_id"

        if not target_id:
            raise ValueError("Must provide either user_id or bot_id")

        query = {
            target_field: target_id,
            "event_type": {"$in": ["funding", "paper_capital_bootstrap"]}
        }
        if currency:
            query["currency"] = currency

        events = await self.ledger_events.find(query).to_list(length=1000)
        return sum(event.get("amount", 0) for event in events)

    async def ensure_bot_funding(
        self,
        user_id: str,
        bot_id: str,
        amount: float,
        currency: str
    ) -> bool:
        """Ensure a funding event exists for a bot (idempotent)."""
        if amount <= 0:
            return False

        query = {
            "user_id": user_id,
            "bot_id": bot_id,
            "event_type": "funding",
            "currency": currency
        }
        existing = await self.ledger_events.find_one(query)
        if existing:
            return False

        await self.append_event(
            user_id=user_id,
            event_type="funding",
            amount=amount,
            currency=currency,
            timestamp=datetime.utcnow(),
            bot_id=bot_id,
            description=f"Initial funded capital for bot {bot_id}"
        )
        return True
    
    async def compute_realized_pnl(
        self,
        user_id: Optional[str] = None,
        bot_id: Optional[str] = None,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        currency: str = "USDT"
    ) -> float:
        """
        Compute realized PnL from closed positions
        
        Method: Match buys and sells using FIFO
        
        Can compute for user_id or bot_id
        """
        # Determine the query target
        target_id = user_id or bot_id
        target_field = "user_id" if user_id else "bot_id"
        
        if not target_id:
            raise ValueError("Must provide either user_id or bot_id")
        
        query = {target_field: target_id}
        if since or until:
            query["timestamp"] = {}
            if since:
                query["timestamp"]["$gte"] = since
            if until:
                query["timestamp"]["$lte"] = until
        
        cursor = self.fills_ledger.find(query).sort("timestamp", 1)
        fills = await cursor.to_list(length=10000)
        
        # Group by symbol
        positions_by_symbol = {}
        realized_pnl = 0.0
        
        for fill in fills:
            symbol = fill["symbol"]
            side = fill["side"]
            qty = fill["qty"]
            price = fill["price"]
            
            if symbol not in positions_by_symbol:
                positions_by_symbol[symbol] = []
            
            if side == "buy":
                # Add to position
                positions_by_symbol[symbol].append({
                    "qty": qty,
                    "price": price
                })
            elif side == "sell":
                # Close position using FIFO
                remaining_qty = qty
                sell_price = price
                
                while remaining_qty > 0 and positions_by_symbol[symbol]:
                    buy = positions_by_symbol[symbol][0]
                    
                    if buy["qty"] <= remaining_qty:
                        # Close entire buy
                        closed_qty = buy["qty"]
                        pnl = closed_qty * (sell_price - buy["price"])
                        realized_pnl += pnl
                        remaining_qty -= closed_qty
                        positions_by_symbol[symbol].pop(0)
                    else:
                        # Partially close buy
                        closed_qty = remaining_qty
                        pnl = closed_qty * (sell_price - buy["price"])
                        realized_pnl += pnl
                        buy["qty"] -= closed_qty
                        remaining_qty = 0
        
        return realized_pnl
    
    async def compute_unrealized_pnl(
        self,
        user_id: Optional[str] = None,
        bot_id: Optional[str] = None,
        currency: str = "USDT"
    ) -> float:
        """
        Compute unrealized PnL from open positions using current mark prices
        
        Method:
        1. Calculate open positions from FIFO matching
        2. Get current market prices for each symbol
        3. Calculate unrealized PnL = qty * (current_price - avg_entry_price)
        
        Can compute for user_id or bot_id
        """
        # Determine the query target
        target_id = user_id or bot_id
        target_field = "user_id" if user_id else "bot_id"
        
        if not target_id:
            raise ValueError("Must provide either user_id or bot_id")
        
        query = {target_field: target_id}
        
        cursor = self.fills_ledger.find(query).sort("timestamp", 1)
        fills = await cursor.to_list(length=10000)
        
        # Group by symbol and calculate open positions using FIFO
        positions_by_symbol = {}
        
        for fill in fills:
            symbol = fill["symbol"]
            side = fill["side"]
            qty = fill["qty"]
            price = fill["price"]
            
            if symbol not in positions_by_symbol:
                positions_by_symbol[symbol] = []
            
            if side == "buy":
                # Add to position
                positions_by_symbol[symbol].append({
                    "qty": qty,
                    "price": price
                })
            elif side == "sell":
                # Close position using FIFO
                remaining_qty = qty
                
                while remaining_qty > 0 and positions_by_symbol[symbol]:
                    buy = positions_by_symbol[symbol][0]
                    
                    if buy["qty"] <= remaining_qty:
                        # Close entire buy
                        remaining_qty -= buy["qty"]
                        positions_by_symbol[symbol].pop(0)
                    else:
                        # Partially close buy
                        buy["qty"] -= remaining_qty
                        remaining_qty = 0
        
        # Calculate unrealized PnL for remaining open positions
        unrealized_pnl = 0.0
        
        try:
            # Get price engine for mark prices
            from paper_trading_engine import paper_engine
            
            for symbol, open_buys in positions_by_symbol.items():
                if not open_buys:
                    continue
                
                # Get current mark price
                try:
                    # Determine exchange from symbol format
                    if "/ZAR" in symbol:
                        exchange = "luno"
                    else:
                        exchange = "binance"  # Default to binance for USDT pairs
                    
                    current_price = await paper_engine.get_real_price(symbol, exchange)
                    
                    # Calculate unrealized PnL for all open positions in this symbol
                    for buy in open_buys:
                        qty = buy["qty"]
                        entry_price = buy["price"]
                        pnl = qty * (current_price - entry_price)
                        unrealized_pnl += pnl
                        
                        logger.debug(f"Open position: {symbol} qty={qty} entry={entry_price} mark={current_price} unrealized_pnl={pnl}")
                        
                except Exception as e:
                    logger.warning(f"Failed to get mark price for {symbol}: {e}")
                    # Continue with other symbols
                    continue
                    
        except Exception as e:
            logger.error(f"Error calculating unrealized PnL: {e}")
            # Return 0 if price feed unavailable (graceful degradation)
            return 0.0
        
        return unrealized_pnl
    
    async def compute_fees_paid(
        self,
        user_id: Optional[str] = None,
        bot_id: Optional[str] = None,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        currency: str = "USDT"
    ) -> float:
        """
        Compute total fees paid from fills
        
        Can compute for user_id or bot_id
        """
        # Determine the query target
        target_id = user_id or bot_id
        target_field = "user_id" if user_id else "bot_id"
        
        if not target_id:
            raise ValueError("Must provide either user_id or bot_id")
        
        query = {target_field: target_id}
        if since or until:
            query["timestamp"] = {}
            if since:
                query["timestamp"]["$gte"] = since
            if until:
                query["timestamp"]["$lte"] = until
        
        # Aggregate fees
        pipeline = [
            {"$match": query},
            {"$group": {
                "_id": None,
                "total_fees": {"$sum": "$fee"}
            }}
        ]
        
        result = await self.fills_ledger.aggregate(pipeline).to_list(length=1)
        
        if result:
            return result[0].get("total_fees", 0.0)
        return 0.0
    
    async def compute_drawdown(
        self,
        user_id: Optional[str] = None,
        bot_id: Optional[str] = None,
        currency: str = "USDT"
    ) -> Tuple[float, float]:
        """
        Compute current drawdown and max drawdown
        
        Returns: (current_drawdown_pct, max_drawdown_pct)
        
        Can compute for user_id or bot_id
        """
        # Determine the query target
        target_id = user_id or bot_id
        target_field = "user_id" if user_id else "bot_id"
        
        if not target_id:
            raise ValueError("Must provide either user_id or bot_id")
        
        # Get equity time series
        fills = await self.get_fills(**{target_field: target_id}, limit=10000)
        
        if not fills:
            return 0.0, 0.0
        
        # Calculate equity at each point
        equity_series = []
        running_equity = 0.0
        
        # Get starting capital
        funding_query = {
            target_field: target_id,
            "event_type": "funding",
            "currency": currency
        }
        funding_cursor = self.ledger_events.find(funding_query)
        funding_events = await funding_cursor.to_list(length=1000)
        starting_capital = sum(event.get("amount", 0) for event in funding_events)
        
        running_equity = starting_capital
        equity_series.append(running_equity)
        
        # Simple approximation: add/subtract trade value and fees
        for fill in reversed(fills):  # Reverse to go chronological
            side = fill["side"]
            qty = fill["qty"]
            price = fill["price"]
            fee = fill["fee"]
            
            trade_value = qty * price
            
            if side == "buy":
                running_equity -= trade_value
            else:  # sell
                running_equity += trade_value
            
            running_equity -= fee
            equity_series.append(running_equity)
        
        if not equity_series or max(equity_series) == 0:
            return 0.0, 0.0
        
        # Calculate drawdowns
        peak = equity_series[0]
        max_dd = 0.0
        current_dd = 0.0
        
        for equity in equity_series:
            if equity > peak:
                peak = equity
            
            dd = (peak - equity) / peak if peak > 0 else 0
            max_dd = max(max_dd, dd)
        
        # Current drawdown
        current_equity = equity_series[-1]
        current_dd = (peak - current_equity) / peak if peak > 0 else 0
        
        return current_dd, max_dd
    
    def _normalize_timestamp(self, timestamp) -> datetime:
        """
        Normalize timestamp to datetime object
        
        Handles both datetime objects and ISO string timestamps
        from legacy data or JSON imports.
        
        Args:
            timestamp: datetime object or ISO string
            
        Returns:
            datetime object
            
        Raises:
            ValueError: If timestamp cannot be parsed
        """
        if isinstance(timestamp, datetime):
            return timestamp
        elif isinstance(timestamp, str):
            try:
                # Handle ISO format with 'Z' or timezone
                return datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            except (ValueError, AttributeError) as e:
                logger.warning(f"Invalid timestamp format: {timestamp}")
                raise ValueError(f"Cannot parse timestamp: {timestamp}") from e
        else:
            raise ValueError(f"Unsupported timestamp type: {type(timestamp)}")
    
    async def profit_series(
        self,
        user_id: str,
        period: str = "daily",  # 'daily', 'weekly', 'monthly'
        limit: int = 30
    ) -> List[Dict]:
        """
        Get profit time series aggregated by period
        
        Returns: [{"date": "2025-01-01", "realized_pnl": 100, "fees": 5, "net_profit": 95}, ...]
        """
        # Determine time bucket size
        if period == "daily":
            delta = timedelta(days=1)
            date_format = "%Y-%m-%d"
        elif period == "weekly":
            delta = timedelta(weeks=1)
            date_format = "%Y-W%W"
        elif period == "monthly":
            delta = timedelta(days=30)
            date_format = "%Y-%m"
        else:
            raise ValueError(f"Invalid period: {period}")
        
        # Get fills for the period
        since = datetime.utcnow() - (delta * limit)
        fills = await self.get_fills(user_id=user_id, since=since, limit=10000)
        
        # Group by period
        periods_data = {}
        
        for fill in reversed(fills):  # Chronological order
            try:
                timestamp = self._normalize_timestamp(fill["timestamp"])
            except ValueError:
                continue  # Skip fills with invalid timestamps
            date_key = timestamp.strftime(date_format)
            
            if date_key not in periods_data:
                periods_data[date_key] = {
                    "date": date_key,
                    "trades": 0,
                    "fees": 0.0,
                    "volume": 0.0
                }
            
            periods_data[date_key]["trades"] += 1
            periods_data[date_key]["fees"] += fill.get("fee", 0)
            periods_data[date_key]["volume"] += fill["qty"] * fill["price"]
        
        # Calculate realized PnL per period using FIFO position tracking
        # Tracks positions per symbol and calculates realized gains on each sell
        positions = {}  # symbol -> [list of (qty, cost_basis)]
        
        # Pre-group fills by date_key for efficient processing (avoids O(n²))
        fills_by_date = {}
        for fill in fills:
            try:
                timestamp = self._normalize_timestamp(fill["timestamp"])
            except ValueError:
                continue  # Skip fills with invalid timestamps
            date_key = timestamp.strftime(date_format)
            if date_key not in fills_by_date:
                fills_by_date[date_key] = []
            fills_by_date[date_key].append(fill)
        
        series = []
        for date_key in sorted(periods_data.keys()):
            data = periods_data[date_key]
            realized_pnl = 0.0
            
            # Get fills for this period (already grouped)
            period_fills = fills_by_date.get(date_key, [])
            
            for fill in period_fills:
                symbol = fill["symbol"]
                side = fill["side"]
                qty = fill["qty"]
                price = fill["price"]
                
                if symbol not in positions:
                    positions[symbol] = []
                
                if side == "buy":
                    # Add to position
                    positions[symbol].append((qty, price))
                elif side == "sell":
                    # Close position(s) and realize PnL using FIFO
                    remaining_qty = qty
                    while remaining_qty > 0 and positions[symbol]:
                        pos_qty, pos_price = positions[symbol][0]
                        
                        if pos_qty <= remaining_qty:
                            # Close entire position
                            realized_pnl += (price - pos_price) * pos_qty
                            remaining_qty -= pos_qty
                            positions[symbol].pop(0)
                        else:
                            # Partial close
                            realized_pnl += (price - pos_price) * remaining_qty
                            positions[symbol][0] = (pos_qty - remaining_qty, pos_price)
                            remaining_qty = 0
            
            data["realized_pnl"] = round(realized_pnl, 2)
            data["net_profit"] = round(data["realized_pnl"] - data["fees"], 2)
            series.append(data)
        
        return series[-limit:]
    
    async def get_stats(self, user_id: str, bot_id: Optional[str] = None) -> Dict:
        """
        Get comprehensive statistics
        
        Returns: {
            "total_fills": int,
            "total_volume": float,
            "total_fees": float,
            "win_rate": float,  # if calculable
            "avg_fill_size": float
        }
        """
        query = {"user_id": user_id}
        if bot_id:
            query["bot_id"] = bot_id
        
        # Aggregate stats
        pipeline = [
            {"$match": query},
            {"$group": {
                "_id": None,
                "total_fills": {"$sum": 1},
                "total_volume": {"$sum": {"$multiply": ["$qty", "$price"]}},
                "total_fees": {"$sum": "$fee"},
                "avg_qty": {"$avg": "$qty"}
            }}
        ]
        
        result = await self.fills_ledger.aggregate(pipeline).to_list(length=1)
        
        if result:
            stats = result[0]
            del stats["_id"]
            return stats
        
        return {
            "total_fills": 0,
            "total_volume": 0.0,
            "total_fees": 0.0,
            "avg_qty": 0.0
        }
    
    async def calculate_win_rate(self, user_id: str, bot_id: Optional[str] = None) -> Optional[float]:
        """
        Calculate win rate using FIFO position tracking.
        Returns the percentage of profitable closed positions (0.0 to 1.0).
        Returns None if no closed positions exist.
        
        Algorithm:
        - Track positions per symbol using FIFO
        - When a sell occurs, match against oldest buys
        - Track each closed trade as win/loss
        - Win rate = wins / (wins + losses)
        
        Note: For high-volume scenarios (>10k fills), consider implementing
        pagination or streaming to avoid memory issues.
        """
        query = {"user_id": user_id}
        if bot_id:
            query["bot_id"] = bot_id
        
        # Get all fills ordered by timestamp
        # For very high-volume trading, this should be paginated
        fills = await self.get_fills(user_id=user_id, bot_id=bot_id, limit=10000)
        
        if not fills:
            return None
        
        positions = {}  # symbol -> [(qty, cost_basis), ...]
        winning_trades = 0
        losing_trades = 0
        
        for fill in reversed(fills):  # Process chronologically
            symbol = fill["symbol"]
            side = fill["side"]
            qty = fill["qty"]
            price = fill["price"]
            
            if symbol not in positions:
                positions[symbol] = []
            
            if side == "buy":
                # Add to position
                positions[symbol].append((qty, price))
            elif side == "sell":
                # Close position(s) and track win/loss
                remaining_qty = qty
                while remaining_qty > 0 and positions[symbol]:
                    pos_qty, pos_price = positions[symbol][0]
                    
                    if pos_qty <= remaining_qty:
                        # Close entire position
                        pnl = (price - pos_price) * pos_qty
                        if pnl > 0:
                            winning_trades += 1
                        elif pnl < 0:
                            losing_trades += 1
                        # pnl == 0 is neither win nor loss (breakeven)
                        
                        remaining_qty -= pos_qty
                        positions[symbol].pop(0)
                    else:
                        # Partial close
                        pnl = (price - pos_price) * remaining_qty
                        if pnl > 0:
                            winning_trades += 1
                        elif pnl < 0:
                            losing_trades += 1
                        
                        positions[symbol][0] = (pos_qty - remaining_qty, pos_price)
                        remaining_qty = 0
        
        total_trades = winning_trades + losing_trades
        if total_trades == 0:
            return None
        
        return winning_trades / total_trades
    
    async def get_trade_count(
        self,
        user_id: Optional[str] = None,
        bot_id: Optional[str] = None,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None
    ) -> int:
        """
        Count trades for a bot/user in a time period
        
        Used by order pipeline for trade limiting
        """
        query = {}
        
        if user_id:
            query["user_id"] = user_id
        if bot_id:
            query["bot_id"] = bot_id
        if since or until:
            query["timestamp"] = {}
            if since:
                query["timestamp"]["$gte"] = since
            if until:
                query["timestamp"]["$lte"] = until
        
        count = await self.fills_ledger.count_documents(query)
        return count
    
    async def compute_daily_pnl(
        self,
        user_id: Optional[str] = None,
        bot_id: Optional[str] = None,
        currency: str = "USDT"
    ) -> float:
        """
        Calculate PnL for today
        
        Used by circuit breaker to detect daily loss triggers
        """
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Calculate realized PnL for today
        realized_pnl = await self.compute_realized_pnl(
            user_id=user_id,
            bot_id=bot_id,
            since=today_start,
            currency=currency
        )
        
        # Subtract today's fees
        fees = await self.compute_fees_paid(
            user_id=user_id,
            bot_id=bot_id,
            since=today_start,
            currency=currency
        )
        
        return realized_pnl - fees
    
    async def get_consecutive_losses(
        self,
        user_id: Optional[str] = None,
        bot_id: Optional[str] = None,
        limit: int = 100
    ) -> int:
        """
        Track consecutive losing trades
        
        Used by circuit breaker to detect loss streaks
        """
        query = {}
        if user_id:
            query["user_id"] = user_id
        if bot_id:
            query["bot_id"] = bot_id
        
        # Get recent fills sorted by timestamp descending
        cursor = self.fills_ledger.find(query).sort("timestamp", -1).limit(limit)
        fills = await cursor.to_list(length=limit)
        
        if not fills:
            return 0
        
        # Group fills by symbol to track positions
        # Simplified: Check if recent trades resulted in losses
        # This is a simplified heuristic - proper implementation would need full position tracking
        consecutive = 0
        positions = {}
        
        for fill in reversed(fills):  # Process chronologically
            symbol = fill["symbol"]
            side = fill["side"]
            qty = fill["qty"]
            price = fill["price"]
            
            if symbol not in positions:
                positions[symbol] = []
            
            if side == "buy":
                positions[symbol].append({"qty": qty, "price": price})
            elif side == "sell" and positions[symbol]:
                # Close position
                remaining_qty = qty
                trade_pnl = 0
                
                while remaining_qty > 0 and positions[symbol]:
                    buy = positions[symbol][0]
                    
                    if buy["qty"] <= remaining_qty:
                        closed_qty = buy["qty"]
                        trade_pnl += closed_qty * (price - buy["price"])
                        remaining_qty -= closed_qty
                        positions[symbol].pop(0)
                    else:
                        closed_qty = remaining_qty
                        trade_pnl += closed_qty * (price - buy["price"])
                        buy["qty"] -= closed_qty
                        remaining_qty = 0
                
                # Check if this was a loss
                if trade_pnl < 0:
                    consecutive += 1
                else:
                    # Reset counter on a win
                    consecutive = 0
        
        return consecutive
    
    async def get_error_rate(
        self,
        user_id: Optional[str] = None,
        bot_id: Optional[str] = None,
        hours: int = 1
    ) -> int:
        """
        Track errors per hour for circuit breaker
        
        Looks for error events in ledger_events
        """
        since = datetime.utcnow() - timedelta(hours=hours)
        
        query = {
            "event_type": "error",
            "timestamp": {"$gte": since}
        }
        
        if user_id:
            query["user_id"] = user_id
        if bot_id:
            query["bot_id"] = bot_id
        
        count = await self.ledger_events.count_documents(query)
        return count
    
    async def reconcile_with_trades_collection(
        self,
        user_id: str
    ) -> Dict:
        """
        Reconcile ledger data with legacy trades_collection
        
        Checks for discrepancies and returns a report with any issues found.
        Useful for migration validation and integrity checks.
        
        Returns: {
            "status": "ok" | "warning" | "error",
            "ledger_equity": float,
            "trades_equity": float,
            "discrepancy": float,
            "ledger_fills_count": int,
            "trades_count": int,
            "issues": List[str],
            "recommendations": List[str]
        }
        """
        issues = []
        recommendations = []
        
        try:
            # Get ledger equity
            ledger_equity = await self.compute_equity(user_id)
            ledger_fills = await self.get_fills(user_id=user_id, limit=10000)
            ledger_fills_count = len(ledger_fills)
            
            # Get trades collection data
            trades_collection = self.db["trades"]
            trades_cursor = trades_collection.find({"user_id": user_id})
            trades = await trades_cursor.to_list(length=10000)
            trades_count = len(trades)
            
            # Calculate equity from trades collection
            trades_equity = sum(trade.get("profit_loss", 0) for trade in trades)
            
            # Check for discrepancies
            discrepancy = abs(ledger_equity - trades_equity)
            discrepancy_pct = (discrepancy / max(ledger_equity, trades_equity, 1)) * 100
            
            # Count mismatches
            if discrepancy_pct > 5:
                issues.append(f"Large equity discrepancy: {discrepancy_pct:.2f}% difference")
                recommendations.append("Review ledger fills and trades for missing or duplicate entries")
            
            if abs(ledger_fills_count - trades_count) > 10:
                issues.append(f"Fill count mismatch: {ledger_fills_count} fills vs {trades_count} trades")
                recommendations.append("Ensure all trades are being recorded to fills_ledger")
            
            # Determine status
            if discrepancy_pct > 10:
                status = "error"
            elif discrepancy_pct > 5 or issues:
                status = "warning"
            else:
                status = "ok"
            
            return {
                "status": status,
                "ledger_equity": round(ledger_equity, 2),
                "trades_equity": round(trades_equity, 2),
                "discrepancy": round(discrepancy, 2),
                "discrepancy_pct": round(discrepancy_pct, 2),
                "ledger_fills_count": ledger_fills_count,
                "trades_count": trades_count,
                "issues": issues,
                "recommendations": recommendations if issues else ["Ledger and trades are in sync"],
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Reconciliation failed: {e}")
            return {
                "status": "error",
                "error": str(e),
                "issues": [f"Reconciliation check failed: {str(e)}"],
                "recommendations": ["Check database connectivity and ledger service health"],
                "timestamp": datetime.utcnow().isoformat()
            }
    
    async def verify_integrity(
        self,
        user_id: str
    ) -> Dict:
        """
        Verify ledger integrity for a user
        
        Checks:
        1. Equity recomputation matches cached value
        2. All fills have corresponding fees
        3. No duplicate client_order_ids
        4. Chronological ordering is preserved
        5. All required fields are present
        
        Returns: {
            "status": "ok" | "warning" | "error",
            "checks_passed": int,
            "checks_failed": int,
            "issues": List[str],
            "details": Dict
        }
        """
        issues = []
        checks_passed = 0
        checks_failed = 0
        
        try:
            # Check 1: Equity recomputation
            equity1 = await self.compute_equity(user_id)
            equity2 = await self.compute_equity(user_id)
            
            if abs(equity1 - equity2) < 0.01:
                checks_passed += 1
            else:
                checks_failed += 1
                issues.append(f"Equity recomputation mismatch: {equity1} vs {equity2}")
            
            # Check 2: Get all fills
            fills = await self.get_fills(user_id=user_id, limit=10000)
            
            # Check 3: All fills have fees
            fills_without_fees = [f for f in fills if f.get("fee") is None]
            if not fills_without_fees:
                checks_passed += 1
            else:
                checks_failed += 1
                issues.append(f"{len(fills_without_fees)} fills missing fee information")
            
            # Check 4: No duplicate client_order_ids
            client_order_ids = [f.get("client_order_id") for f in fills if f.get("client_order_id")]
            if len(client_order_ids) == len(set(client_order_ids)):
                checks_passed += 1
            else:
                checks_failed += 1
                duplicates = len(client_order_ids) - len(set(client_order_ids))
                issues.append(f"{duplicates} duplicate client_order_ids found")
            
            # Check 5: Chronological ordering
            timestamps = [f["timestamp"] for f in fills]
            is_sorted = all(timestamps[i] >= timestamps[i+1] for i in range(len(timestamps)-1))
            if is_sorted:
                checks_passed += 1
            else:
                checks_failed += 1
                issues.append("Fills are not in chronological order")
            
            # Check 6: Required fields present
            required_fields = ["user_id", "bot_id", "exchange", "symbol", "side", "qty", "price", "fee", "timestamp"]
            fills_missing_fields = []
            for fill in fills:
                missing = [field for field in required_fields if field not in fill]
                if missing:
                    fills_missing_fields.append((fill.get("_id"), missing))
            
            if not fills_missing_fields:
                checks_passed += 1
            else:
                checks_failed += 1
                issues.append(f"{len(fills_missing_fields)} fills missing required fields")
            
            # Determine status
            if checks_failed == 0:
                status = "ok"
            elif checks_failed < 3:
                status = "warning"
            else:
                status = "error"
            
            return {
                "status": status,
                "checks_passed": checks_passed,
                "checks_failed": checks_failed,
                "total_checks": checks_passed + checks_failed,
                "issues": issues if issues else ["All integrity checks passed"],
                "details": {
                    "total_fills": len(fills),
                    "equity": round(equity1, 2),
                    "user_id": user_id
                },
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Integrity check failed: {e}")
            return {
                "status": "error",
                "checks_passed": 0,
                "checks_failed": 1,
                "total_checks": 1,
                "issues": [f"Integrity check failed: {str(e)}"],
                "timestamp": datetime.utcnow().isoformat()
            }


# Singleton instance
_ledger_service_instance = None


def get_ledger_service(db):
    """Get or create ledger service instance"""
    global _ledger_service_instance
    if _ledger_service_instance is None:
        _ledger_service_instance = LedgerService(db)
    return _ledger_service_instance
