"""
Trading Logic Verification Tests
Validates spawn gating, rate limiting, and reinvest logic
"""

import pytest
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.settings import settings, ExchangeLimits, FeatureFlags, SUPPORTED_EXCHANGES


class TestConfigurationValidation:
    """Test configuration validation and consistency"""
    
    def test_supported_exchanges_exactly_seven(self):
        """Verify exactly 7 exchanges are supported"""
        assert len(SUPPORTED_EXCHANGES) == 7, "Must support exactly 7 exchanges"
        expected = ['luno', 'binance', 'kucoin', 'bybit', 'kraken', 'bitget', 'gate']
        assert SUPPORTED_EXCHANGES == expected, f"Expected {expected}, got {SUPPORTED_EXCHANGES}"
    
    def test_bot_allocation_matches_capacity(self):
        """Verify bot allocation sums to total capacity"""
        total = sum(ExchangeLimits.BOT_ALLOCATION.values())
        assert total == 65, f"Bot allocation sum ({total}) should equal 65"
        assert total == settings.MAX_TOTAL_BOTS, "Bot allocation must match MAX_TOTAL_BOTS"
    
    def test_exchange_limits_consistency(self):
        """Verify each exchange has consistent limits"""
        for exchange in SUPPORTED_EXCHANGES:
            limits = ExchangeLimits.get_limits(exchange)
            bot_limit = ExchangeLimits.BOT_ALLOCATION.get(exchange)
            
            assert 'max_orders_per_day' in limits, f"{exchange} missing max_orders_per_day"
            assert 'max_orders_per_bot_per_day' in limits, f"{exchange} missing max_orders_per_bot_per_day"
            assert 'max_orders_per_minute' in limits, f"{exchange} missing max_orders_per_minute"
            assert 'max_orders_per_10_seconds' in limits, f"{exchange} missing max_orders_per_10_seconds"
            
            # Check bot limit consistency
            if 'max_bots' in limits:
                assert limits['max_bots'] == bot_limit, \
                    f"{exchange}: max_bots ({limits['max_bots']}) != allocation ({bot_limit})"


class TestSpawnGatingThresholds:
    """Test profit-gated bot spawn thresholds"""
    
    def test_spawn_threshold_r1000_per_exchange(self):
        """Verify spawn threshold is R1000 per exchange"""
        assert settings.BOT_SPAWN_PROFIT_ZAR == 1000, \
            f"Spawn threshold should be R1000, got R{settings.BOT_SPAWN_PROFIT_ZAR}"
    
    def test_new_bot_seed_capital(self):
        """Verify new bot seed capital is reasonable"""
        assert settings.NEW_BOT_SEED_CAPITAL_ZAR == 500, \
            f"New bot seed capital should be R500, got R{settings.NEW_BOT_SEED_CAPITAL_ZAR}"
        
        # Seed capital should be less than spawn threshold
        assert settings.NEW_BOT_SEED_CAPITAL_ZAR < settings.BOT_SPAWN_PROFIT_ZAR, \
            "Seed capital should be less than spawn threshold"
    
    def test_per_exchange_spawn_enabled(self):
        """Verify per-exchange spawn gating is enabled"""
        assert settings.ENABLE_PER_EXCHANGE_BOT_SPAWN == True, \
            "Per-exchange spawn gating should be enabled"
    
    def test_reinvest_threshold(self):
        """Verify reinvest threshold is configured"""
        assert settings.REINVEST_THRESHOLD_ZAR == 300, \
            f"Reinvest threshold should be R300, got R{settings.REINVEST_THRESHOLD_ZAR}"
        
        # Reinvest threshold should be less than spawn threshold
        assert settings.REINVEST_THRESHOLD_ZAR < settings.BOT_SPAWN_PROFIT_ZAR, \
            "Reinvest threshold should be less than spawn threshold"
    
    def test_top_performers_count(self):
        """Verify top performers count for reinvestment"""
        assert settings.TOP_PERFORMERS_COUNT >= 3, \
            f"Should track at least 3 top performers, got {settings.TOP_PERFORMERS_COUNT}"


class TestRateLimiting:
    """Test rate limiting configuration"""
    
    def test_rate_limits_per_exchange(self):
        """Verify rate limits are defined for all exchanges"""
        for exchange in SUPPORTED_EXCHANGES:
            limits = ExchangeLimits.get_limits(exchange)
            
            # Per-day limits
            assert limits['max_orders_per_day'] > 0, f"{exchange} missing daily limit"
            assert limits['max_orders_per_bot_per_day'] > 0, f"{exchange} missing per-bot daily limit"
            
            # Per-minute limits
            assert limits['max_orders_per_minute'] == 60, \
                f"{exchange} should have 60 orders/minute, got {limits['max_orders_per_minute']}"
            
            # Burst protection
            assert limits['max_orders_per_10_seconds'] == 10, \
                f"{exchange} should have 10 orders/10s burst limit, got {limits['max_orders_per_10_seconds']}"
    
    def test_luno_specific_limits(self):
        """Verify Luno has conservative limits"""
        luno_limits = ExchangeLimits.get_limits('luno')
        
        assert luno_limits['max_orders_per_bot_per_day'] == 400, \
            f"Luno should have 400 orders/bot/day, got {luno_limits['max_orders_per_bot_per_day']}"
        
        assert luno_limits['max_orders_per_day'] == 2000, \
            f"Luno should have 2000 total orders/day, got {luno_limits['max_orders_per_day']}"
    
    def test_burst_protection_consistent(self):
        """Verify burst protection is consistent across exchanges"""
        for exchange in SUPPORTED_EXCHANGES:
            limits = ExchangeLimits.get_limits(exchange)
            burst = limits.get('max_orders_per_10_seconds', 0)
            
            assert burst == 10, \
                f"{exchange} burst limit should be 10, got {burst}"
    
    def test_per_bot_limits_reasonable(self):
        """Verify per-bot limits are reasonable"""
        for exchange in SUPPORTED_EXCHANGES:
            limits = ExchangeLimits.get_limits(exchange)
            bot_limit = limits['max_orders_per_bot_per_day']
            total_limit = limits['max_orders_per_day']
            max_bots = ExchangeLimits.BOT_ALLOCATION.get(exchange, 0)
            
            # Per-bot limit * max_bots should not exceed total limit by too much
            theoretical_max = bot_limit * max_bots
            assert theoretical_max <= total_limit * 1.5, \
                f"{exchange}: theoretical max ({theoretical_max}) too high vs total ({total_limit})"


class TestFeatureFlags:
    """Test feature flags configuration"""
    
    def test_trading_flags(self):
        """Verify trading flags are properly configured"""
        flags = FeatureFlags.to_dict()
        
        assert 'ENABLE_TRADING' in flags, "ENABLE_TRADING flag missing"
        assert 'ENABLE_PAPER_TRADING' in flags, "ENABLE_PAPER_TRADING flag missing"
        assert 'ENABLE_LIVE_TRADING' in flags, "ENABLE_LIVE_TRADING flag missing"
        assert 'ENABLE_AUTOPILOT' in flags, "ENABLE_AUTOPILOT flag missing"
    
    def test_email_reports_flag(self):
        """Verify email reports flag exists"""
        flags = FeatureFlags.to_dict()
        assert 'ENABLE_EMAIL_REPORTS' in flags, "ENABLE_EMAIL_REPORTS flag missing"
    
    def test_default_report_times(self):
        """Verify default report times are configured"""
        report_times = FeatureFlags.REPORT_TIMES
        assert report_times == '08:00,18:00', \
            f"Report times should be '08:00,18:00', got '{report_times}'"


class TestRiskManagement:
    """Test risk management configuration"""
    
    def test_max_daily_loss_configured(self):
        """Verify max daily loss percentage is set"""
        assert settings.MAX_DAILY_LOSS_PERCENT > 0, "MAX_DAILY_LOSS_PERCENT not configured"
        assert settings.MAX_DAILY_LOSS_PERCENT <= 0.20, \
            f"MAX_DAILY_LOSS_PERCENT ({settings.MAX_DAILY_LOSS_PERCENT}) should be <= 20%"
    
    def test_max_drawdown_configured(self):
        """Verify max drawdown percentage is set"""
        assert settings.MAX_DRAWDOWN_PERCENT > 0, "MAX_DRAWDOWN_PERCENT not configured"
        assert settings.MAX_DRAWDOWN_PERCENT <= 0.30, \
            f"MAX_DRAWDOWN_PERCENT ({settings.MAX_DRAWDOWN_PERCENT}) should be <= 30%"
    
    def test_position_size_limits(self):
        """Verify position size limits are reasonable"""
        assert settings.MIN_POSITION_SIZE_PERCENT > 0, "MIN_POSITION_SIZE_PERCENT not configured"
        assert settings.MAX_POSITION_SIZE_PERCENT > settings.MIN_POSITION_SIZE_PERCENT, \
            "MAX_POSITION_SIZE_PERCENT should be greater than MIN_POSITION_SIZE_PERCENT"
        
        assert settings.MAX_POSITION_SIZE_PERCENT <= 0.10, \
            f"MAX_POSITION_SIZE_PERCENT ({settings.MAX_POSITION_SIZE_PERCENT}) should be <= 10%"


class TestEmailConfiguration:
    """Test email system configuration"""
    
    def test_smtp_configuration_exists(self):
        """Verify SMTP configuration is defined"""
        assert settings.SMTP_HOST, "SMTP_HOST not configured"
        assert settings.SMTP_PORT > 0, "SMTP_PORT not configured"
        assert settings.SMTP_PORT in [25, 465, 587, 2525], \
            f"SMTP_PORT ({settings.SMTP_PORT}) should be standard port"
    
    def test_from_email_configured(self):
        """Verify FROM_EMAIL or SMTP_USER is set"""
        from_email = settings.from_email_address
        assert from_email, "FROM_EMAIL or SMTP_USER must be configured"


def test_configuration_summary():
    """Print configuration summary for verification"""
    print("\n" + "="*60)
    print("CONFIGURATION SUMMARY")
    print("="*60)
    
    print(f"\n✓ Supported Exchanges ({len(SUPPORTED_EXCHANGES)}):")
    for exchange in SUPPORTED_EXCHANGES:
        bot_limit = ExchangeLimits.BOT_ALLOCATION.get(exchange)
        print(f"  - {exchange.upper()}: {bot_limit} bots max")
    
    print(f"\n✓ Trading Thresholds:")
    print(f"  - Spawn threshold: R{settings.BOT_SPAWN_PROFIT_ZAR} per exchange")
    print(f"  - New bot capital: R{settings.NEW_BOT_SEED_CAPITAL_ZAR}")
    print(f"  - Reinvest threshold: R{settings.REINVEST_THRESHOLD_ZAR}")
    print(f"  - Top performers tracked: {settings.TOP_PERFORMERS_COUNT}")
    
    print(f"\n✓ Rate Limiting:")
    print(f"  - Per-minute: 60 orders")
    print(f"  - Burst protection: 10 orders per 10 seconds")
    print(f"  - Luno daily limit: 2000 orders, 400 per bot")
    
    print(f"\n✓ Risk Management:")
    print(f"  - Max daily loss: {settings.MAX_DAILY_LOSS_PERCENT * 100}%")
    print(f"  - Max drawdown: {settings.MAX_DRAWDOWN_PERCENT * 100}%")
    
    print(f"\n✓ Feature Flags:")
    flags = FeatureFlags.to_dict()
    for key, value in sorted(flags.items()):
        status = "✓" if value else "✗"
        print(f"  {status} {key}: {value}")
    
    print(f"\n✓ Email Configuration:")
    print(f"  - SMTP Host: {settings.SMTP_HOST}")
    print(f"  - SMTP Port: {settings.SMTP_PORT}")
    print(f"  - Report Times: {FeatureFlags.REPORT_TIMES}")
    print(f"  - Email Reports: {FeatureFlags.ENABLE_EMAIL_REPORTS}")
    
    print("\n" + "="*60)


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v", "-s"])
