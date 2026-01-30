# Amarktai Network - Production Upgrade Summary

**Date**: 2026-01-30  
**Version**: Production Upgrade v2.0  
**Status**: ✅ Complete

## Overview

This upgrade transforms the Amarktai Network into a production-ready trading platform with enhanced genetic evolution, risk management, real-time wallet transfers, and extensible feature frameworks.

## Key Improvements

### 1. Enhanced Genetic Evolution System

**Mutation Rate**: Increased from 15% to 25% for faster adaptation
- Configurable via `EVOLUTION_MUTATION_RATE` environment variable
- Default: 0.25 (25% mutation probability)

**Performance Weighting**: Recent trades weighted more heavily
- Last 24 hours: 40% weight
- Last 48 hours: 30% weight  
- All-time: 30% weight
- Regime-aware bonus scoring

**Diversity Requirements**: 
- Parent selection favors different exchanges (70% probability)
- Prevents over-concentration on single exchange/pair
- Maintains genetic diversity across population

**Evolution Frequency**: Changed from daily to hourly
- Runs every hour when autopilot enabled
- Requires minimum 10 bots for evolution
- Evolves bottom 30% using top 30% as parents

### 2. Autopilot Improvements

**Reinvestment**: Changed from daily to hourly
- New threshold: R300 (down from R500)
- More frequent capital redeployment
- Faster bot spawning capability

**Bot Spawning**:
- New capital requirement: R500 (down from R1000)
- Total bot limit: 45 (configurable via MAX_TOTAL_BOTS)
- Distribution: 5+10+10+10+10 across exchanges

**Configuration**: 
```bash
MAX_TOTAL_BOTS=45
REINVEST_THRESHOLD_ZAR=300
NEW_BOT_CAPITAL=500
EVOLUTION_MUTATION_RATE=0.25
QUARANTINE_THRESHOLD=-0.05
```

### 3. Enhanced Risk Management

**Increased Tolerance**:
- Daily loss limit: 15% (up from 10%)
- Maximum drawdown: 25% (up from 20%)
- Error budget: 20 errors/hour (up from 10)

**Position Sizing**:
- Minimum per-trade: 2% of capital
- Maximum per-trade: 5% of capital

**New Bot Features**:
- `trailing_stop_percent`: Dynamic stop loss that follows price
- `take_profit_percent`: Configurable profit targets

**Configuration**:
```bash
MAX_DAILY_LOSS_PERCENT=0.15
MAX_DRAWDOWN_PERCENT=0.25
MAX_ERRORS_PER_HOUR=20
```

### 4. Exchange Trade Limits

Updated to reflect production safety caps:

| Exchange | Daily Trades | Notes |
|----------|-------------|-------|
| Binance  | 500         | Highest volume |
| KuCoin   | 1000        | Most permissive |
| Luno     | 400         | Conservative |
| VALR     | 1500        | South African |
| OVEX     | 500         | Moderate |

### 5. Real-Time Wallet Transfers

**New Service**: `services/wallet_transfers_service.py`

**Features**:
- Queue-based transfer management
- Whitelisted address security
- Rate limiting (5 second delay between transfers)
- Real-time status tracking via SSE
- Support for withdrawal and deposit coordination

**Endpoints**:
- `POST /api/wallet/transfer` - Initiate transfer
- `GET /api/wallet/transfer/{id}` - Check status
- `GET /api/wallet/transfers` - List history
- `POST /api/wallet/whitelist` - Add trusted address
- `GET /api/wallet/whitelist` - List whitelisted addresses

**Configuration**:
```bash
ENABLE_REALTIME_TRANSFERS=false  # Off by default for safety
```

### 6. New Feature Routes (Stubs)

#### External Signals (`routes/signals.py`)
- TradingView webhook integration
- Telegram bot signal ingestion
- Signal validation and queuing
- ML predictor integration points

#### DeFi Trading (`routes/defi_trading.py`)
- WalletConnect session management
- DEX token swaps (Uniswap, PancakeSwap)
- Liquidity pool integration
- Yield farming framework

#### Strategy Marketplace (`routes/marketplace.py`)
- Strategy publishing and discovery
- Rating and review system
- Strategy cloning
- Leaderboards

#### Advanced Backtesting (`routes/backtesting.py`)
- Standard backtesting
- Walk-forward analysis
- Monte Carlo simulation
- Parameter optimization

### 7. Deployment Enhancements

**install.sh Fixes**:
- Fixed undefined `PROJECT_ROOT` variable
- Added `/var/log/amarktai` directory creation
- Proper `.env.example` copying logic
- Improved error handling

**Directory Structure**:
```
/var/amarktai/
  ├── app/              # Repository root
  │   ├── backend/      # FastAPI application
  │   ├── frontend/     # React application
  │   └── docs/         # All documentation (NEW)
  └── /var/log/amarktai/  # Log files (NEW)
```

### 8. Documentation Reorganization

**All Markdown Files Moved to `/docs/`**:
- 43 markdown files consolidated
- README.md updated with correct paths
- Cleaner repository root
- Better organization

**Key Documents**:
- `/docs/DEPLOYMENT_GUIDE.md` - Production deployment
- `/docs/QUICK_START.md` - Getting started
- `/docs/COMPLETE_FEATURE_LIST.md` - All features
- `/docs/PRODUCTION_FEATURES_IMPLEMENTATION.md` - Implementation details

## Configuration Reference

### Environment Variables (New/Updated)

```bash
# Autopilot
MAX_TOTAL_BOTS=45
REINVEST_THRESHOLD_ZAR=300
NEW_BOT_CAPITAL=500
EVOLUTION_MUTATION_RATE=0.25
QUARANTINE_THRESHOLD=-0.05

# Risk Management
MAX_DAILY_LOSS_PERCENT=0.15
MAX_DRAWDOWN_PERCENT=0.25
MAX_ERRORS_PER_HOUR=20

# Features
ENABLE_REALTIME_TRANSFERS=false
ENABLE_SCHEDULERS=true

# Security
ENCRYPTION_KEY=  # Required for API key encryption
```

## Database Schema Updates

### Bot Model Additions
```python
trailing_stop_percent: Optional[float]  # Dynamic stop loss
take_profit_percent: Optional[float]    # Profit targets
```

### New Collections
- `wallet_transfers` - Transfer history
- `whitelisted_addresses` - Trusted withdrawal addresses
- `external_signals` - TradingView/Telegram signals
- `marketplace_strategies` - Published strategies
- `strategy_ratings` - User ratings and reviews
- `backtests` - Backtest results
- `walkforward_tests` - Walk-forward analysis
- `montecarlo_tests` - Monte Carlo simulations

## Migration Guide

### For Existing Deployments

1. **Update Configuration**:
```bash
cd /var/amarktai/app
git pull origin main
cp .env.example backend/.env  # Merge changes
```

2. **Add New Variables to `.env`**:
```bash
# Add to backend/.env
EVOLUTION_MUTATION_RATE=0.25
QUARANTINE_THRESHOLD=-0.05
MAX_DAILY_LOSS_PERCENT=0.15
MAX_DRAWDOWN_PERCENT=0.25
MAX_ERRORS_PER_HOUR=20
ENABLE_REALTIME_TRANSFERS=false
```

3. **Restart Services**:
```bash
sudo systemctl restart amarktai-api.service
```

4. **Verify**:
```bash
curl http://localhost:8000/api/health/ping
```

### For New Deployments

Follow the standard deployment guide in `/docs/DEPLOYMENT_GUIDE.md`. All new features are included by default.

## Testing & Verification

### Code Quality
- ✅ Code review: 0 issues found
- ✅ Security scan: 0 alerts (CodeQL)
- ✅ Configuration: All variables verified
- ✅ Imports: All modules load correctly

### Backward Compatibility
- ✅ Existing bots continue to function
- ✅ API endpoints unchanged (additions only)
- ✅ Database schema backward compatible
- ✅ Configuration fallbacks to safe defaults

## Performance Impact

### Expected Improvements
- **Evolution Speed**: 24x faster (hourly vs daily)
- **Capital Efficiency**: 40% lower barriers (R300/R500 vs R500/R1000)
- **Adaptation Rate**: 67% higher mutation (25% vs 15%)
- **Risk Tolerance**: 50% more drawdown room (25% vs 20%)

### Resource Requirements
- **Memory**: Unchanged (~2GB)
- **CPU**: Slight increase (+10-15%) from hourly cycles
- **Database**: New collections add minimal overhead
- **Network**: Unchanged for existing features

## Future Enhancements

### Planned Features (Stubs Ready)
1. **TradingView Integration** - Full implementation
2. **DeFi Trading** - WalletConnect integration
3. **Marketplace** - Strategy sharing platform
4. **Advanced Backtesting** - Walk-forward & Monte Carlo
5. **Futures Trading** - Leverage support
6. **RL Agents** - Reinforcement learning hybrid

### Extension Points
- `routes/signals.py` - Signal processing logic
- `routes/defi_trading.py` - Web3 integration
- `routes/marketplace.py` - Rating algorithms
- `routes/backtesting.py` - Simulation engine

## Security Considerations

### New Security Features
1. **Whitelisted Addresses** - Transfer restrictions
2. **Queue Management** - Rate limiting for transfers
3. **Enhanced Encryption** - ENCRYPTION_KEY requirement
4. **Error Budgets** - Self-healing with MAX_ERRORS_PER_HOUR

### Best Practices
- Keep `ENABLE_REALTIME_TRANSFERS=false` until thoroughly tested
- Whitelist addresses before enabling transfers
- Monitor error rates with self-healing
- Review quarantine candidates regularly

## Support & Troubleshooting

### Common Issues

**Issue**: Config variables not loading
- **Solution**: Restart service, clear Python cache (`rm -rf backend/__pycache__`)

**Issue**: Evolution not running
- **Solution**: Check `ENABLE_SCHEDULERS=true` and `AUTOPILOT_ENABLED=1`

**Issue**: Wallet transfers disabled
- **Solution**: Set `ENABLE_REALTIME_TRANSFERS=true` (after whitelisting addresses)

### Logs
```bash
# Service logs
sudo journalctl -u amarktai-api.service -f

# Application logs
tail -f /var/log/amarktai/*.log
```

## Changelog

### v2.0.0 (2026-01-30) - Production Upgrade

**Added**:
- Hourly genetic evolution with 25% mutation rate
- Recent-performance weighting (24-48h emphasis)
- Regime-aware fitness scoring
- Real-time wallet transfers service
- External signal integration (TradingView/Telegram)
- DeFi trading framework
- Strategy marketplace stubs
- Advanced backtesting stubs
- Trailing stops and take profit to bot model

**Changed**:
- Reinvestment frequency: daily → hourly
- Reinvest threshold: R500 → R300
- New bot capital: R1000 → R500
- Max daily loss: 10% → 15%
- Max drawdown: 20% → 25%
- Error budget: 10/hr → 20/hr
- Exchange limits updated to production values

**Fixed**:
- Undefined PROJECT_ROOT in install.sh
- Missing /var/log/amarktai directory
- Config package compatibility

**Removed**:
- None (backward compatible)

## Contributors

This upgrade was implemented as a comprehensive production readiness initiative, addressing all requirements from the upgrade guide while maintaining backward compatibility.

## License

See LICENSE file in repository root.
