# Advanced Trading System Documentation

## Overview

This document describes the state-of-the-art machine-driven trading system with regime-adaptive intelligence, multi-modal alpha fusion, enhanced infrastructure, and **multi-agent architecture**.

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Regime-Adaptive Intelligence](#regime-adaptive-intelligence)
3. [Order Flow Imbalance (OFI)](#order-flow-imbalance-ofi)
4. [Multi-Modal Alpha Fusion](#multi-modal-alpha-fusion)
5. [Infrastructure Enhancements](#infrastructure-enhancements)
6. [Multi-Agent System](#multi-agent-system)
7. [FLock.io Integration](#flockio-integration)
8. [Fractional Kelly Position Sizing](#fractional-kelly-position-sizing)
9. [Chandelier Exits](#chandelier-exits)
10. [Prometheus Metrics](#prometheus-metrics)
11. [Reflexion Loop](#reflexion-loop)
12. [Configuration](#configuration)
13. [API Endpoints](#api-endpoints)
14. [Production Deployment](#production-deployment)

---

## Architecture Overview

The advanced trading system now includes **autonomous multi-agent capabilities** using Fetch.ai uAgents:

```
┌─────────────────────────────────────────────────────────────────┐
│                    Fetch.ai uAgents Bureau                      │
│         (Decentralized Agent Coordination)                      │
└─────────────────────────────────────────────────────────────────┘
          │           │           │           │           │
          ▼           ▼           ▼           ▼           ▼
┌──────────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
│   Regime     │ │   OFI    │ │  Whale   │ │  Alpha   │ │Self-Heal │
│   Agent      │ │  Agent   │ │  Agent   │ │  Fusion  │ │  Agent   │
│  (HMM/GMM)   │ │(Orderbook│ │(On-chain)│ │  Agent   │ │(Reflexion│
└──────────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘
          │           │           │           │           │
          └───────────┴───────────┴───────────┴───────────┘
                              │
                              ▼
                   ┌────────────────────┐
                   │  FLock.io Trading  │
                   │    Specialist      │
                   │  (Vertical LLM)    │
                   └────────────────────┘
                              │
                              ▼
                   ┌────────────────────┐
                   │  Fractional Kelly  │
                   │  + Chandelier      │
                   │  (Risk Management) │
                   └────────────────────┘
                              │
                              ▼
                   ┌────────────────────┐
                   │  Prometheus        │
                   │  Metrics           │
                   └────────────────────┘
```

### Key Components

1. **Regime Detector**: Hidden Markov Models (HMM) and Gaussian Mixture Models (GMM)
2. **OFI Calculator**: Order Flow Imbalance for micro-scale entry timing
3. **Whale Monitor**: Large blockchain transaction tracking
4. **Sentiment Analyzer**: News and social media with LLMs
5. **Macro Monitor**: Macroeconomic events (CPI, Fed rates, etc.)
6. **Alpha Fusion Engine**: Multi-modal signal combination
7. **Self-Healing AI**: Autonomous error detection and recovery
8. **FLock.io Client**: Vertical-specific trading intelligence
9. **Fractional Kelly**: Optimal position sizing
10. **Chandelier Exits**: ATR-based dynamic stops
11. **Prometheus Metrics**: Observability (Latency, Traffic, Errors, Saturation)
12. **Reflexion Loop**: Responder-Critic-Revisor pattern with Episodic Memory

---

## Multi-Agent System

### Overview

The system can operate as a **decentralized multi-agent system** using Fetch.ai uAgents framework. Each engine becomes an autonomous agent that:

- Registers on the Fetch.ai Almanac
- Communicates via inter-agent messages
- Makes sovereign decisions
- Self-heals autonomously

### Agent Types

#### 1. Regime Agent
- **Port**: 8001
- **Function**: Market state detection
- **Update Frequency**: Every 60 seconds
- **Output**: Regime classifications (Bullish/Calm, Bearish/Volatile, Squeeze)

#### 2. OFI Agent
- **Port**: 8002
- **Function**: Order flow imbalance calculation
- **Update Frequency**: Every 1 second
- **Output**: Buy/sell signals with strength

#### 3. Whale Agent
- **Port**: 8003
- **Function**: On-chain transaction monitoring
- **Update Frequency**: Every 5 minutes
- **Output**: Institutional flow signals

#### 4. Alpha Fusion Agent
- **Port**: 8004
- **Function**: Multi-modal signal fusion
- **Update Frequency**: Every 30 seconds
- **Output**: Unified trading recommendations

#### 5. Self-Healing Agent
- **Port**: 8005
- **Function**: System health monitoring and auto-recovery
- **Update Frequency**: Every 60 seconds
- **Output**: Health reports and healing actions

### Starting the Agent System

```python
from engines.uagents_framework import start_agent_system

# Start all agents in bureau
start_agent_system()
```

### Agent Communication

Agents communicate via structured messages:

```python
# Market Data Message
class MarketDataMessage(Model):
    symbol: str
    price: float
    volume: float
    timestamp: str

# Signal Message
class SignalMessage(Model):
    symbol: str
    signal_type: str
    recommendation: str
    confidence: float
    reasoning: str
    timestamp: str
```

---

## FLock.io Integration

### Overview

FLock.io replaces generic GPT calls with **vertical-specific trading intelligence** using the `flock-trading-specialist-v1` model.

### API Configuration

```python
from engines.flock_ai_client import flock_client

# Initialize with API key
flock_client = FlockAIClient(api_key="your_flock_api_key")

# Get trading decision
decision = await flock_client.get_trading_decision(
    market_data={'symbol': 'BTC/USDT', 'price': 50000, 'volume_24h': 1000000000},
    regime_state={'regime': 'bullish_calm', 'confidence': 0.85},
    ofi_signal={'recommendation': 'buy', 'signal_strength': 0.65},
    whale_signal={'signal': 'bullish', 'reason': 'Large outflows'},
    sentiment={'sentiment': 'bullish', 'confidence': 0.75}
)

# Returns:
# {
#   'decision': 'buy',
#   'reasoning': 'Strong bullish signals across all indicators...',
#   'confidence': 0.75,
#   'source': 'flock-trading-specialist-v1'
# }
```

### Advantages Over Generic LLMs

- **Domain-Specific**: Trained on trading data
- **Vertical Optimization**: Better understanding of financial terms
- **Higher Accuracy**: 20-30% better than generic models
- **Lower Latency**: Optimized inference

---

## Fractional Kelly Position Sizing

### Formula

The Kelly Criterion determines optimal position size:

```
f* = (bp - q) / b

where:
- b = reward/risk ratio
- p = win probability
- q = loss probability = 1 - p
- f* = fraction of capital to risk
```

### Fractional Kelly

Uses **25% of full Kelly** for stability:

```
position_size = capital × (0.25 × f*)
```

### Usage

```python
from engines.fractional_kelly import kelly_calculator

position_size, metrics = kelly_calculator.calculate_position_size(
    capital=10000,        # Available capital
    win_rate=0.55,        # 55% win rate
    reward_risk_ratio=2.0, # 2:1 reward/risk
    confidence=0.8        # 80% signal confidence
)

# Returns:
# position_size = $1375 (13.75% of capital)
# metrics = {
#   'full_kelly': 0.55,
#   'fractional_kelly': 0.1375,
#   'position_fraction': 0.1375,
#   'recommendation': 'trade'
# }
```

### Safeguards

- **Minimum Position**: 1% of capital
- **Maximum Position**: 25% of capital
- **Negative Edge Detection**: Prevents trading when Kelly < 0
- **Confidence Adjustment**: Scales position by signal confidence
- **Market Conditions**: Adjusts for volatility and stress

---

## Chandelier Exits

### Formula

Dynamic stops based on Average True Range (ATR):

```
StopLoss_Long  = HighestHigh_period - (ATR × multiplier)
StopLoss_Short = LowestLow_period  + (ATR × multiplier)
```

### Parameters

- **ATR Period**: 14 (default)
- **ATR Multiplier**: 3.0 (default)
- **Lookback Period**: 20 (default)

### Usage

```python
from engines.chandelier_exits import chandelier_exits

# Add price data
chandelier_exits.add_price_data(
    symbol='BTC/USDT',
    high=50500,
    low=49500,
    close=50000
)

# Calculate stop loss
stop_data = await chandelier_exits.calculate_stop_loss(
    symbol='BTC/USDT',
    side='long',
    entry_price=50000
)

# Returns:
# {
#   'stop_loss': 48500,
#   'stop_distance': 1500,
#   'stop_distance_pct': 3.0,
#   'atr': 500
# }
```

### Trailing Stops

```python
# Calculate trailing stop
trailing_data = await chandelier_exits.calculate_trailing_stop(
    symbol='BTC/USDT',
    side='long',
    entry_price=50000,
    current_price=51000,
    previous_stop=48500
)

# Returns:
# {
#   'trailing_stop': 49000,  # Stop moved up
#   'stop_moved': True,
#   'stop_hit': False,
#   'unrealized_pnl': 1000
# }
```

---

## Prometheus Metrics

### Golden Signals

Tracks the four Golden Signals for observability:

1. **Latency**: Tick-to-trade timing
2. **Traffic**: Trades, API requests, signals
3. **Errors**: Component failures, healing attempts
4. **Saturation**: Capital utilization, rate limits

### Metrics Endpoint

```bash
curl http://localhost:8000/api/metrics

# Returns Prometheus format:
# amarktai_trade_latency_seconds_bucket{le="0.1"} 42
# amarktai_trades_total{exchange="binance",symbol="BTCUSDT",side="buy"} 150
# amarktai_errors_total{component="trading_engine",error_type="timeout"} 3
# amarktai_capital_utilization_ratio 0.65
```

### Grafana Dashboard

Import the metrics into Grafana:

1. **Data Source**: http://localhost:8000/api/metrics
2. **Scrape Interval**: 15s
3. **Dashboards**: Trading performance, system health, signal quality

### Usage in Code

```python
from engines.prometheus_metrics import prometheus_metrics, TradeLatencyTimer

# Record trade
with TradeLatencyTimer(prometheus_metrics):
    # Execute trade
    pass

# Record manually
prometheus_metrics.record_trade('binance', 'BTC/USDT', 'buy', 'live')
prometheus_metrics.update_win_rate('bot_123', 0.58)
prometheus_metrics.update_drawdown('bot_123', 5.2)
```

---

## Reflexion Loop

### Overview

Implements the **Responder-Critic-Revisor** pattern for autonomous self-healing:

1. **Responder**: Detects system state and issues
2. **Critic**: Analyzes root causes
3. **Revisor**: Applies fixes automatically

### Episodic Memory

Uses **LangChain + Chroma** to learn from successful trades:

```python
from engines.reflexion_loop import reflexion_loop

# Store success episode
await reflexion_loop.store_success_episode(
    trade_data={'symbol': 'BTC/USDT', 'side': 'long', 'entry_price': 50000},
    reasoning="Bullish regime with strong OFI signal",
    regime='bullish_calm',
    volatility=0.02,
    outcome={'exit_price': 51000, 'pnl': 1000, 'pnl_pct': 2.0}
)

# Retrieve similar episodes
episodes = await reflexion_loop.retrieve_similar_episodes(
    current_situation="Bullish regime with strong buying pressure",
    regime='bullish_calm',
    k=3  # Top 3 similar
)
```

### Running Reflexion Loop

```python
# Manual cycle
cycle = await reflexion_loop.run_reflexion_cycle()

# Continuous loop
await reflexion_loop.start()

# Stop
await reflexion_loop.stop()
```

---

## Configuration

See updated `.env.example` for all configuration options.

### Critical Settings

```bash
# FLock.io
FLOCK_API_KEY=your_api_key_here
FLOCK_ENABLED=true

# Kelly
KELLY_FRACTION=0.25  # Conservative
KELLY_MAX_POSITION_SIZE=0.25  # 25% max

# Chandelier
CHANDELIER_ATR_MULTIPLIER=3.0  # Standard

# Prometheus
PROMETHEUS_ENABLED=true

# Reflexion
REFLEXION_ENABLED=true
EPISODIC_MEMORY_ENABLED=true

# uAgents (Experimental)
UAGENTS_ENABLED=false  # Set true for multi-agent mode
```

---

## Production Deployment

### Updated Checklist

- [ ] Configure FLock.io API key
- [ ] Set Kelly fraction (0.25 recommended)
- [ ] Tune Chandelier ATR multiplier
- [ ] Enable Prometheus metrics
- [ ] Setup Grafana dashboards
- [ ] Enable Reflexion loop
- [ ] Test Episodic Memory
- [ ] (Optional) Enable uAgents framework
- [ ] Monitor all metrics
- [ ] Review healing success rate

### Performance Monitoring

Monitor these key metrics:

1. **Trade Latency**: < 100ms target
2. **Healing Success Rate**: > 80% target
3. **Kelly Edge**: Always positive
4. **Chandelier Stop Distance**: 2-4% typical
5. **Capital Utilization**: 50-70% optimal

---

## Summary of New Features

| Feature | Purpose | File | Status |
|---------|---------|------|--------|
| FLock.io | Vertical trading LLM | `flock_ai_client.py` | ✅ Complete |
| Fractional Kelly | Position sizing | `fractional_kelly.py` | ✅ Complete |
| Chandelier Exits | Dynamic stops | `chandelier_exits.py` | ✅ Complete |
| Prometheus | Observability | `prometheus_metrics.py` | ✅ Complete |
| Reflexion Loop | Self-healing | `reflexion_loop.py` | ✅ Complete |
| uAgents | Multi-agent | `uagents_framework.py` | ✅ Complete |

**Total New Code**: 1,890+ lines across 6 modules

---

**Version**: 3.0.0 (Multi-Agent Edition)  
**Last Updated**: December 2025  
**Author**: Amarktai Network Development Team

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Regime-Adaptive Intelligence](#regime-adaptive-intelligence)
3. [Order Flow Imbalance (OFI)](#order-flow-imbalance-ofi)
4. [Multi-Modal Alpha Fusion](#multi-modal-alpha-fusion)
5. [Infrastructure Enhancements](#infrastructure-enhancements)
6. [Configuration](#configuration)
7. [API Endpoints](#api-endpoints)
8. [Production Deployment](#production-deployment)
9. [Troubleshooting](#troubleshooting)

---

## Architecture Overview

The advanced trading system consists of six interconnected modules:

```
┌─────────────────────────────────────────────────────────────────┐
│                    Alpha Fusion Engine                          │
│              (Multi-Modal Signal Combination)                    │
└─────────────────────────────────────────────────────────────────┘
          │           │           │           │           │
          ▼           ▼           ▼           ▼           ▼
┌──────────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
│   Regime     │ │   OFI    │ │  Whale   │ │Sentiment │ │  Macro   │
│  Detector    │ │Calculator│ │ Monitor  │ │ Analyzer │ │ Monitor  │
│  (HMM/GMM)   │ │(Orderbook│ │(On-chain)│ │(News/LLM)│ │(Economic)│
└──────────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘
          │           │           │           │           │
          └───────────┴───────────┴───────────┴───────────┘
                              │
                              ▼
                   ┌────────────────────┐
                   │  Trading Engine    │
                   │   (Execution)      │
                   └────────────────────┘
                              │
                              ▼
                   ┌────────────────────┐
                   │  Self-Healing AI   │
                   │ (Error Recovery)   │
                   └────────────────────┘
```

### Key Components

1. **Regime Detector**: Uses Hidden Markov Models (HMM) and Gaussian Mixture Models (GMM) to identify market states
2. **OFI Calculator**: Calculates Order Flow Imbalance for micro-scale entry timing
3. **Whale Monitor**: Tracks large blockchain transactions for institutional flow insights
4. **Sentiment Analyzer**: Analyzes news and social media using LLMs
5. **Macro Monitor**: Tracks macroeconomic events (CPI, Fed rates, etc.)
6. **Alpha Fusion Engine**: Combines all signals with configurable weights
7. **Self-Healing AI**: Autonomous error detection and recovery

---

## Regime-Adaptive Intelligence

### Market Regimes

The system detects three primary market regimes:

1. **Bullish/Calm** 🟢
   - Positive returns with low volatility
   - Ideal for trend-following strategies
   - Increased position sizing (1.2x multiplier)
   - Wider stop losses (2%), higher take profits (5%)

2. **Bearish/Volatile** 🔴
   - Negative returns with high volatility
   - Defensive positioning required
   - Reduced position sizing (0.5x multiplier)
   - Tighter stops (3%), conservative targets (3%)

3. **Squeeze** 🟡
   - Low volatility with unclear direction
   - Breakout preparation mode
   - Moderate position sizing (0.7x multiplier)
   - Tight stops (1.5%), quick targets (2.5%)

### Statistical Models

#### Hidden Markov Model (HMM)

The HMM learns transition probabilities between market states:

```python
# Model structure
n_states = 3
covariance_type = "full"
n_iterations = 100

# Features extracted
- Log returns
- Rolling volatility (20-period)
- Momentum (rate of change)
- Price z-scores
```

#### Gaussian Mixture Model (GMM)

GMM provides validation and confidence scoring:

```python
# Model configuration
n_components = 3
covariance_type = "full"

# Clustering approach
- Fits feature distributions
- Identifies regime clusters
- Provides probability estimates
```

### Feature Engineering

The system extracts four key features from price data:

1. **Log Returns**: `ln(P_t / P_{t-1})`
2. **Volatility**: Rolling standard deviation of returns
3. **Momentum**: Rate of change over window
4. **Z-Score**: Standardized price deviation

### Usage Example

```python
from engines.regime_detector import regime_detector

# Update price data
await regime_detector.update_price_data(
    symbol="BTC/USDT",
    price=50000.0,
    volume=100.0
)

# Detect regime
regime_state = await regime_detector.detect_regime("BTC/USDT")

print(f"Regime: {regime_state.regime.value}")
print(f"Confidence: {regime_state.confidence:.2%}")
print(f"Volatility: {regime_state.volatility:.4f}")

# Get adaptive parameters
params = regime_detector.get_trading_parameters(regime_state)
print(f"Position size multiplier: {params['position_size_multiplier']}")
print(f"Stop loss: {params['stop_loss_pct']}%")
```

---

## Order Flow Imbalance (OFI)

### Mathematical Formula

OFI measures order book pressure using the formula:

```
e_n = I{P^b_n ≥ P^b_{n-1}}q^b_n - I{P^b_n ≤ P^b_{n-1}}q^b_{n-1}
      - I{P^a_n ≤ P^a_{n-1}}q^a_n + I{P^a_n ≥ P^a_{n-1}}q^a_{n-1}
```

Where:
- `P^b_n`: Bid price at time n
- `P^a_n`: Ask price at time n
- `q^b_n`: Bid quantity at time n
- `q^a_n`: Ask quantity at time n
- `I{condition}`: Indicator function (1 if true, 0 if false)

### Signal Interpretation

- **Positive OFI**: Buying pressure dominates → Bullish signal
- **Negative OFI**: Selling pressure dominates → Bearish signal
- **Near-zero OFI**: Balanced order flow → Neutral signal

### Aggregation

OFI values are aggregated over 1-second intervals (configurable) to reduce noise:

```python
aggregated_ofi = Σ(e_n) for n in [t-1s, t]
```

### Usage Example

```python
from engines.order_flow_imbalance import ofi_calculator

# Add order book snapshot
await ofi_calculator.add_snapshot(
    symbol="BTC/USDT",
    bid_price=50000.0,
    bid_qty=1.5,
    ask_price=50050.0,
    ask_qty=1.2
)

# Get signal
signal = await ofi_calculator.get_signal("BTC/USDT")

if signal:
    print(f"Recommendation: {signal.recommendation}")
    print(f"Signal strength: {signal.signal_strength:.2f}")
    print(f"Aggregated OFI: {signal.aggregated_ofi:.3f}")
    
# Get predictive features
features = await ofi_calculator.get_predictive_features("BTC/USDT")
print(f"OFI trend: {features['ofi_trend']:.3f}")
print(f"Buy pressure ratio: {features['buy_pressure_ratio']:.2%}")
```

---

## Multi-Modal Alpha Fusion

### Signal Sources

The alpha fusion engine combines five independent signal sources:

| Source | Weight | Description | Update Frequency |
|--------|--------|-------------|------------------|
| Regime Detection | 25% | Market state (HMM/GMM) | Per price update |
| OFI | 20% | Order book imbalance | Per snapshot (1s) |
| Whale Activity | 20% | Large transactions | Real-time blockchain |
| Sentiment | 20% | News/social media | Hourly |
| Macro Events | 15% | Economic indicators | Event-driven |

### Fusion Process

1. **Normalization**: Convert each signal to [-1, 1] scale
2. **Weighting**: Apply configurable weights to each signal
3. **Confidence Adjustment**: Scale by individual signal confidence
4. **Aggregation**: Weighted average of all signals
5. **Classification**: Map score to signal strength

```python
# Fusion formula
weighted_score = Σ(signal_i × weight_i × confidence_i)

# Classification thresholds
if weighted_score ≥ 0.5:  signal = STRONG_BUY
elif weighted_score ≥ 0.2:  signal = BUY
elif weighted_score ≤ -0.5: signal = STRONG_SELL
elif weighted_score ≤ -0.2: signal = SELL
else:                       signal = NEUTRAL
```

### On-Chain Whale Monitoring

Tracks transactions above thresholds:
- **BTC**: $100 USD minimum
- **ETH**: 1,000 ETH minimum
- **Stablecoins**: $100,000 minimum

#### Signal Logic

- **Exchange Inflow** (Bearish): Whales moving coins to exchanges → Selling pressure
- **Exchange Outflow** (Bullish): Whales moving coins off exchanges → Accumulation
- **Net Flow > $500k**: Generate strong signal

### Sentiment Analysis

Uses multiple approaches:

1. **Keyword Matching**: Fast baseline sentiment
   - Bullish keywords: surge, rally, breakthrough, ATH, moon
   - Bearish keywords: crash, dump, regulation, ban, hack

2. **LLM Analysis** (Optional): Advanced sentiment with OpenAI/DeepSeek
   - Contextual understanding
   - Nuanced interpretation
   - Higher confidence scores

3. **Aggregation**: Combine multiple news sources
   - Weight by source credibility
   - Time-decay for older articles
   - Consensus scoring

### Macro News Integration

Monitors key economic events:

| Event Type | Impact | Risk Adjustment |
|------------|--------|-----------------|
| Fed Rate Cut | Risk On | +0.2 |
| Fed Rate Hike | Risk Off | -0.3 |
| CPI Below Expected | Risk On | +0.15 |
| CPI Above Expected | Risk Off | -0.2 |
| Low Unemployment | Risk On | +0.1 |
| High Unemployment | Risk Off | -0.15 |
| Rising Treasury Yields | Risk Off | -0.25 |
| Geopolitical Tension | Risk Off | -0.3 |

### Usage Example

```python
from engines.alpha_fusion_engine import alpha_fusion

# Generate fused signal
fused_signal = await alpha_fusion.fuse_signals("BTC/USDT")

print(f"Signal: {fused_signal.signal.value}")
print(f"Confidence: {fused_signal.confidence:.0%}")
print(f"Score: {fused_signal.score:+.2f}")
print(f"Position multiplier: {fused_signal.position_size_multiplier:.2f}x")
print(f"Stop loss: {fused_signal.stop_loss_pct:.1f}%")
print(f"Take profit: {fused_signal.take_profit_pct:.1f}%")

print("\nReasoning:")
for reason in fused_signal.reasoning:
    print(f"  - {reason}")

print("\nComponent Scores:")
for component, score in fused_signal.component_scores.items():
    print(f"  {component}: {score:+.2f}")
```

---

## Infrastructure Enhancements

### WebSocket Real-Time Streaming

Enhanced WebSocket implementation for low-latency data feeds:

```python
# Configuration
WEBSOCKET_ENABLED=true
WEBSOCKET_HEARTBEAT_INTERVAL=30  # seconds
WEBSOCKET_MAX_CONNECTIONS=1000
```

**Features:**
- Bi-directional communication
- Automatic reconnection
- Message queuing during disconnects
- Heartbeat monitoring

### Geographic Latency Optimization

Recommended AWS regions for optimal exchange connectivity:

| Exchange | Recommended Region | Latency |
|----------|-------------------|---------|
| Binance | Tokyo (ap-northeast-1) | ~5ms |
| OKX | Singapore (ap-southeast-1) | ~8ms |
| Kraken | Frankfurt (eu-central-1) | ~12ms |
| Coinbase | N. Virginia (us-east-1) | ~15ms |

Configure in `.env`:
```bash
GEOGRAPHIC_REGION=ap-northeast-1  # Tokyo for Binance
```

### Enhanced Circuit Breaker

ATR-based circuit breaker for dynamic risk management:

```python
# Trigger condition
if unrealized_pnl < -(3 × ATR):
    trigger_circuit_breaker()
```

**Configuration:**
```bash
CIRCUIT_BREAKER_ATR_ENABLED=true
CIRCUIT_BREAKER_ATR_MULTIPLIER=3.0
MAX_DRAWDOWN_PERCENT=0.20
MAX_DAILY_LOSS_PERCENT=0.10
MAX_CONSECUTIVE_LOSSES=5
```

### Self-Healing AI

Autonomous error detection and recovery system:

**Error Classification:**
- Connection timeouts → Retry + Reset connection
- API rate limits → Adjust parameters
- Database errors → Reset connection + Restart
- Insufficient balance → Pause bot + Adjust
- Authentication failures → Manual intervention required

**Healing Actions:**
1. **Retry**: Simple retry with exponential backoff
2. **Reset Connection**: Clear and re-establish connections
3. **Clear Cache**: Flush cached data
4. **Adjust Parameters**: Modify rate limits, timeouts
5. **Pause Bot**: Temporary suspension
6. **Restart Service**: Full service restart (manual)
7. **Manual Intervention**: Alert human operator

**Usage:**
```python
from engines.self_healing_ai import self_healing_ai

# Report error
try:
    # Your code
    pass
except Exception as e:
    error_event = await self_healing_ai.report_error(
        error=e,
        component='trading_engine',
        context={'bot_id': bot_id}
    )
    
    # Automatic healing
    healing_attempt = await self_healing_ai.heal_error(error_event)
    
    if healing_attempt.success:
        # Retry operation
        pass
```

---

## Configuration

### Environment Variables

Add to `.env` file:

```bash
# ============================================================================
# ADVANCED TRADING SYSTEM
# ============================================================================

# Regime Detection
REGIME_DETECTION_ENABLED=true
REGIME_LOOKBACK_PERIODS=100
REGIME_N_STATES=3

# Order Flow Imbalance
OFI_ENABLED=true
OFI_AGGREGATION_WINDOW=1
OFI_LOOKBACK_SECONDS=60
OFI_THRESHOLD=0.1

# Whale Monitoring
WHALE_MONITORING_ENABLED=true
WHALE_BTC_THRESHOLD_USD=100
WHALE_ETH_THRESHOLD_COUNT=1000
WHALE_LOOKBACK_HOURS=24

# Sentiment Analysis
SENTIMENT_ANALYSIS_ENABLED=true
SENTIMENT_USE_AI=true
SENTIMENT_NEWS_LIMIT=20

# Macro Monitoring
MACRO_MONITORING_ENABLED=true
MACRO_LOOKBACK_DAYS=30

# Alpha Fusion Weights (must sum to 1.0)
ALPHA_REGIME_WEIGHT=0.25
ALPHA_OFI_WEIGHT=0.20
ALPHA_WHALE_WEIGHT=0.20
ALPHA_SENTIMENT_WEIGHT=0.20
ALPHA_MACRO_WEIGHT=0.15

# Self-Healing AI
SELF_HEALING_ENABLED=true
SELF_HEALING_MAX_ERROR_RATE=10
SELF_HEALING_ERROR_WINDOW_MINUTES=60
SELF_HEALING_MAX_RETRIES=3

# Infrastructure
WEBSOCKET_ENABLED=true
GEOGRAPHIC_REGION=us-east-1
CIRCUIT_BREAKER_ATR_ENABLED=true
CIRCUIT_BREAKER_ATR_MULTIPLIER=3.0
```

---

## API Endpoints

### Regime Detection

```bash
# Get current regime for symbol
GET /api/advanced/regime/{symbol}

# Get all tracked regimes
GET /api/advanced/regime/summary

# Response
{
  "symbol": "BTC/USDT",
  "regime": "bullish_calm",
  "confidence": 0.85,
  "volatility": 0.012,
  "trend_strength": 0.67,
  "trading_params": {
    "position_size_multiplier": 1.2,
    "stop_loss_pct": 2.0,
    "take_profit_pct": 5.0
  }
}
```

### Order Flow Imbalance

```bash
# Get OFI signal for symbol
GET /api/advanced/ofi/{symbol}

# Get OFI statistics
GET /api/advanced/ofi/stats/{symbol}

# Response
{
  "symbol": "BTC/USDT",
  "recommendation": "buy",
  "signal_strength": 0.65,
  "aggregated_ofi": 15.3,
  "current_ofi": 12.1
}
```

### Whale Activity

```bash
# Get whale signal for coin
GET /api/advanced/whale/{coin}

# Get whale activity summary
GET /api/advanced/whale/summary

# Response
{
  "coin": "BTC",
  "signal": "bullish",
  "strength": 0.72,
  "reason": "Large exchange outflows: $2,500,000 (accumulation)",
  "metrics": {
    "net_flow": -2500000,
    "inflows": 800000,
    "outflows": 3300000
  }
}
```

### Sentiment Analysis

```bash
# Get sentiment for coin
GET /api/advanced/sentiment/{coin}

# Get sentiment summary
GET /api/advanced/sentiment/summary

# Response
{
  "coin": "BTC",
  "sentiment": "bullish",
  "score": 0.45,
  "confidence": 0.78,
  "article_count": 15,
  "key_topics": ["adoption", "institutional", "breakout"],
  "recommendation": "buy"
}
```

### Macro Events

```bash
# Get macro signal
GET /api/advanced/macro/signal

# Get macro summary
GET /api/advanced/macro/summary

# Response
{
  "signal": "increase_risk",
  "risk_multiplier": 1.15,
  "reason": "Favorable macro environment (3 positive events)",
  "recent_events": [...]
}
```

### Alpha Fusion

```bash
# Get fused signal for symbol
GET /api/advanced/fusion/{symbol}

# Get portfolio signals
POST /api/advanced/fusion/portfolio
{
  "symbols": ["BTC/USDT", "ETH/USDT"]
}

# Response
{
  "symbol": "BTC/USDT",
  "signal": "buy",
  "confidence": 0.82,
  "score": 0.45,
  "position_size_multiplier": 1.15,
  "stop_loss_pct": 2.2,
  "take_profit_pct": 4.5,
  "reasoning": [
    "Market regime: bullish_calm (confidence: 85%)",
    "Order flow: buy (strength: 65%)",
    "Whale activity: bullish - Large exchange outflows",
    "Sentiment: bullish (15 articles)"
  ],
  "component_scores": {
    "regime": 0.7,
    "ofi": 0.65,
    "whale": 0.6,
    "sentiment": 0.45,
    "macro": 0.3
  }
}
```

### Self-Healing

```bash
# Get health report
GET /api/advanced/self-healing/health

# Response
{
  "overall_status": "healthy",
  "metrics": {
    "recent_errors": 3,
    "recent_healings": 2,
    "healing_success_rate": 0.85
  },
  "component_health": {...},
  "recent_healing_attempts": [...]
}
```

---

## Production Deployment

### Pre-Deployment Checklist

- [ ] Configure all environment variables in `.env`
- [ ] Set `OPENAI_API_KEY` for sentiment analysis
- [ ] Choose appropriate `GEOGRAPHIC_REGION` for exchange proximity
- [ ] Adjust alpha fusion weights based on backtesting
- [ ] Enable self-healing AI monitoring
- [ ] Configure circuit breaker thresholds
- [ ] Test WebSocket connections
- [ ] Verify all dependencies installed

### Installation

```bash
# 1. Install dependencies
cd backend
pip install -r requirements.txt

# 2. Verify ML libraries
python -c "import sklearn, hmmlearn, statsmodels; print('OK')"

# 3. Run tests
pytest tests/test_advanced_trading_system.py -v

# 4. Start system
python server.py
```

### Monitoring

Monitor system health:

```bash
# Check self-healing status
curl http://localhost:8000/api/advanced/self-healing/health

# Monitor regime detection
curl http://localhost:8000/api/advanced/regime/summary

# View fusion signals
curl http://localhost:8000/api/advanced/fusion/BTC/USDT
```

### Performance Optimization

1. **Regime Detection**: Increase `REGIME_LOOKBACK_PERIODS` for more stable regimes
2. **OFI**: Decrease `OFI_AGGREGATION_WINDOW` for faster signals (higher noise)
3. **Whale Monitoring**: Lower thresholds to catch more transactions
4. **Sentiment**: Enable `SENTIMENT_USE_AI` for better accuracy (higher API costs)
5. **Alpha Fusion**: Adjust weights based on historical performance

### Scaling Recommendations

- **High-Frequency Trading**: Optimize OFI with sub-second aggregation
- **Multiple Exchanges**: Deploy in multiple regions with colocation
- **Large Volume**: Increase whale monitoring thresholds
- **News-Heavy Markets**: Increase `SENTIMENT_NEWS_LIMIT`

---

## Troubleshooting

### Common Issues

#### 1. Regime Detection Not Working

**Symptoms**: Always returns "unknown" regime

**Solutions**:
- Ensure sufficient price history (>20 data points)
- Check if `REGIME_DETECTION_ENABLED=true`
- Verify numpy, scipy, sklearn installed
- Increase `REGIME_LOOKBACK_PERIODS`

#### 2. OFI Signals Always Neutral

**Symptoms**: No buy/sell recommendations

**Solutions**:
- Lower `OFI_THRESHOLD` value
- Ensure order book snapshots being added
- Check if exchange provides order book data
- Verify timestamps are recent

#### 3. No Whale Signals

**Symptoms**: Whale monitor shows no activity

**Solutions**:
- Lower `WHALE_BTC_THRESHOLD_USD` or `WHALE_ETH_THRESHOLD_COUNT`
- Check blockchain data source connectivity
- Verify exchange addresses configured
- Increase `WHALE_LOOKBACK_HOURS`

#### 4. Sentiment Analysis Fails

**Symptoms**: Sentiment always neutral or errors

**Solutions**:
- Check `OPENAI_API_KEY` is set (if using AI)
- Verify news API connectivity
- Disable AI: `SENTIMENT_USE_AI=false`
- Check rate limits on news sources

#### 5. Self-Healing Not Working

**Symptoms**: Errors not being healed

**Solutions**:
- Ensure `SELF_HEALING_ENABLED=true`
- Check error rate within window limits
- Verify healing actions have permissions
- Review logs for healing attempts

### Performance Issues

#### High CPU Usage

- Reduce `REGIME_LOOKBACK_PERIODS`
- Increase `OFI_AGGREGATION_WINDOW`
- Disable unused features
- Optimize feature calculation intervals

#### High Memory Usage

- Lower `WHALE_LOOKBACK_HOURS`
- Reduce `OFI_LOOKBACK_SECONDS`
- Clear old history periodically
- Limit concurrent symbol tracking

#### API Rate Limits

- Increase `OFI_AGGREGATION_WINDOW`
- Reduce `SENTIMENT_NEWS_LIMIT`
- Cache API responses
- Implement request queuing

---

## Recommendations for Production

### Before Going Live

1. **Backtesting**: Test alpha fusion on historical data for at least 3 months
2. **Paper Trading**: Run in paper mode for 2-4 weeks
3. **A/B Testing**: Compare with baseline strategy
4. **Risk Management**: Set conservative circuit breaker thresholds
5. **Monitoring**: Set up alerts for system health

### Optimization Strategy

1. **Week 1-2**: Run with default weights, monitor performance
2. **Week 3-4**: Adjust weights based on which signals perform best
3. **Month 2**: Fine-tune thresholds (OFI, whale, sentiment)
4. **Month 3**: Optimize for specific market conditions
5. **Ongoing**: Regular backtesting and parameter updates

### Risk Mitigation

- Start with small position sizes (0.5x multiplier)
- Enable all circuit breakers
- Monitor self-healing success rate
- Review fusion reasoning for each trade
- Keep manual override capability
- Regular health reports review

### Cost Optimization

- Use keyword-based sentiment (free) before enabling AI
- Cache whale data to reduce API calls
- Aggregate macro events weekly instead of daily
- Use simulated data for testing

---

## Support

For issues or questions:
1. Check logs: `journalctl -u amarktai-api -f`
2. Review health report: `GET /api/advanced/self-healing/health`
3. Test individual components in isolation
4. Consult test suite for usage examples

---

**Version**: 1.0.0  
**Last Updated**: December 2025  
**Author**: Amarktai Network Development Team
