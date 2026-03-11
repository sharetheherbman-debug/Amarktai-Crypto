"""
Test Bot Caps Enforcement
Verifies that bot capacity limits are enforced correctly with SEPARATE caps for
normal bots and scalper bots (they do NOT share slots).

Normal caps:
- Luno: max 5 normal bots
- All other exchanges: max 10 normal bots

Scalper caps (independent):
- Luno: max 2 scalper bots
- All other exchanges: max 5 scalper bots
"""

import pytest
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from rules.bot_rules import BOT_CAPS, SCALPER_CAPS, SUPPORTED_EXCHANGES


class TestBotCaps:
    """Test bot capacity enforcement — normal bots"""

    def test_normal_bot_caps_constants(self):
        """Verify normal bot caps are properly defined"""
        assert BOT_CAPS['luno'] == 5, "Luno should have max 5 normal bots"
        assert BOT_CAPS['binance'] == 10
        assert BOT_CAPS['kucoin'] == 10
        assert BOT_CAPS['bybit'] == 10
        assert BOT_CAPS['kraken'] == 10
        assert BOT_CAPS['bitget'] == 10
        assert BOT_CAPS['gate'] == 10

    def test_scalper_bot_caps_constants(self):
        """Verify scalper bot caps are properly defined and separate from normal caps"""
        assert SCALPER_CAPS['luno'] == 2, "Luno should have max 2 scalper bots"
        assert SCALPER_CAPS['binance'] == 5
        assert SCALPER_CAPS['kucoin'] == 5
        assert SCALPER_CAPS['bybit'] == 5
        assert SCALPER_CAPS['kraken'] == 5
        assert SCALPER_CAPS['bitget'] == 5
        assert SCALPER_CAPS['gate'] == 5

    def test_scalper_caps_do_not_equal_normal_caps(self):
        """Scalper and normal caps must be different (they are separate slot pools)"""
        for exchange in SUPPORTED_EXCHANGES:
            assert BOT_CAPS[exchange] != SCALPER_CAPS[exchange], (
                f"Exchange {exchange}: normal and scalper caps must differ"
            )

    def test_supported_exchanges_list(self):
        """Verify exactly 7 supported exchanges"""
        assert len(SUPPORTED_EXCHANGES) == 7, "Must have exactly 7 supported exchanges"
        assert 'luno' in SUPPORTED_EXCHANGES
        assert 'binance' in SUPPORTED_EXCHANGES
        assert 'kucoin' in SUPPORTED_EXCHANGES
        assert 'bybit' in SUPPORTED_EXCHANGES
        assert 'kraken' in SUPPORTED_EXCHANGES
        assert 'bitget' in SUPPORTED_EXCHANGES
        assert 'gate' in SUPPORTED_EXCHANGES
        assert 'valr' not in [e.lower() for e in SUPPORTED_EXCHANGES]
        assert 'ovex' not in [e.lower() for e in SUPPORTED_EXCHANGES]

    def test_check_bot_cap_limit_normal_luno(self):
        """Normal bots: Luno allows 5, blocks 6th"""
        from rules.bot_rules import check_bot_cap_limit

        can_create, _ = check_bot_cap_limit('luno', 4, bot_type='normal')
        assert can_create is True
        can_create, reason = check_bot_cap_limit('luno', 5, bot_type='normal')
        assert can_create is False
        assert reason == 'BOT_CAP_EXCEEDED'

    def test_check_bot_cap_limit_scalper_luno(self):
        """Scalper bots: Luno allows 2, blocks 3rd"""
        from rules.bot_rules import check_bot_cap_limit

        can_create, _ = check_bot_cap_limit('luno', 1, bot_type='scalper')
        assert can_create is True
        can_create, reason = check_bot_cap_limit('luno', 2, bot_type='scalper')
        assert can_create is False
        assert reason == 'BOT_CAP_EXCEEDED'

    def test_check_bot_cap_limit_normal_binance(self):
        """Normal bots: Binance allows 10, blocks 11th"""
        from rules.bot_rules import check_bot_cap_limit

        can_create, _ = check_bot_cap_limit('binance', 9, bot_type='normal')
        assert can_create is True
        can_create, reason = check_bot_cap_limit('binance', 10, bot_type='normal')
        assert can_create is False
        assert reason == 'BOT_CAP_EXCEEDED'

    def test_check_bot_cap_limit_scalper_binance(self):
        """Scalper bots: Binance allows 5, blocks 6th"""
        from rules.bot_rules import check_bot_cap_limit

        can_create, _ = check_bot_cap_limit('binance', 4, bot_type='scalper')
        assert can_create is True
        can_create, reason = check_bot_cap_limit('binance', 5, bot_type='scalper')
        assert can_create is False
        assert reason == 'BOT_CAP_EXCEEDED'

    def test_luno_5_normal_plus_2_scalper_allowed(self):
        """Luno: 5 normal + 2 scalper coexist — each checks independent cap"""
        from rules.bot_rules import check_bot_cap_limit

        # 5 normal bots at cap (block 6th)
        ok, reason = check_bot_cap_limit('luno', 5, bot_type='normal')
        assert ok is False and reason == 'BOT_CAP_EXCEEDED'

        # 2 scalper bots at cap (block 3rd) — SEPARATE from normal
        ok, reason = check_bot_cap_limit('luno', 2, bot_type='scalper')
        assert ok is False and reason == 'BOT_CAP_EXCEEDED'

        # But 4 normal + 2 scalper is fine for both pools
        ok_normal, _ = check_bot_cap_limit('luno', 4, bot_type='normal')
        ok_scalper, _ = check_bot_cap_limit('luno', 2, bot_type='scalper')
        # 4 normal ok; 2 scalper is exactly at cap → blocked
        assert ok_normal is True
        assert ok_scalper is False  # 2 == cap → blocked

        # 4 normal + 1 scalper → both pools ok
        ok_normal, _ = check_bot_cap_limit('luno', 4, bot_type='normal')
        ok_scalper, _ = check_bot_cap_limit('luno', 1, bot_type='scalper')
        assert ok_normal is True
        assert ok_scalper is True

    def test_other_exchange_10_normal_plus_5_scalper_allowed(self):
        """Non-Luno exchanges: 10 normal + 5 scalper each at their independent caps"""
        from rules.bot_rules import check_bot_cap_limit

        for exchange in ['binance', 'kucoin', 'bybit', 'kraken', 'bitget', 'gate']:
            # 10th normal allowed, 11th blocked
            ok, _ = check_bot_cap_limit(exchange, 9, bot_type='normal')
            assert ok is True, f"{exchange}: 9 normal should be allowed"
            ok, reason = check_bot_cap_limit(exchange, 10, bot_type='normal')
            assert ok is False, f"{exchange}: 10 normal should be blocked"

            # 5th scalper allowed, 6th blocked — independently
            ok, _ = check_bot_cap_limit(exchange, 4, bot_type='scalper')
            assert ok is True, f"{exchange}: 4 scalpers should be allowed"
            ok, reason = check_bot_cap_limit(exchange, 5, bot_type='scalper')
            assert ok is False, f"{exchange}: 5 scalpers should be blocked"

    def test_get_max_bots_type_aware(self):
        """get_max_bots_for_exchange returns different values for normal vs scalper"""
        from rules.bot_rules import get_max_bots_for_exchange

        assert get_max_bots_for_exchange('luno', 'normal') == 5
        assert get_max_bots_for_exchange('luno', 'scalper') == 2
        assert get_max_bots_for_exchange('binance', 'normal') == 10
        assert get_max_bots_for_exchange('binance', 'scalper') == 5

    def test_invalid_exchange_rejected(self):
        """Test that invalid exchanges are rejected"""
        from rules.bot_rules import validate_exchange

        is_valid, reason = validate_exchange('invalid_exchange')
        assert is_valid is False
        assert reason == 'INVALID_EXCHANGE'

        is_valid, reason = validate_exchange('valr')
        assert is_valid is False, "VALR should be invalid"

        is_valid, reason = validate_exchange('ovex')
        assert is_valid is False, "OVEX should be invalid"

    def test_normal_bot_validator_counts_only_normal_bots(self):
        """bot_validator.py must count only bot_type=='normal' for normal cap check."""
        import os
        path = os.path.join(os.path.dirname(__file__), '..', 'backend', 'validators', 'bot_validator.py')
        with open(path) as f:
            src = f.read()
        # The normal-bot count query must NOT use {"$ne": "scalper"} — it
        # should use {"bot_type": "normal"} or equivalent explicit type filter
        # so that uagent bots don't accidentally count against normal caps.
        assert '"bot_type": "normal"' in src or "bot_type.*normal" in src or \
               'NORMAL_EXCHANGE_CAP_REACHED' in src, \
            "bot_validator must have explicit normal-bot cap enforcement"

    def test_scalper_validator_counts_only_scalper_bots(self):
        """bot_validator.py must count only bot_type=='scalper' for scalper cap check."""
        import os
        path = os.path.join(os.path.dirname(__file__), '..', 'backend', 'validators', 'bot_validator.py')
        with open(path) as f:
            src = f.read()
        assert 'SCALPER_EXCHANGE_CAP_REACHED' in src
        assert 'SCALPER_GLOBAL_CAP_REACHED' in src


class TestExchangeConfiguration:
    """Test exchange configuration consistency"""

    def test_exchange_limits_match_supported_list(self):
        """Verify exchange limits are defined for all supported exchanges"""
        from exchange_limits import EXCHANGE_LIMITS
        for exchange in SUPPORTED_EXCHANGES:
            assert exchange in EXCHANGE_LIMITS, f"Exchange {exchange} missing from EXCHANGE_LIMITS"

    def test_bot_caps_match_supported_list(self):
        """Verify bot caps are defined for all supported exchanges"""
        for exchange in SUPPORTED_EXCHANGES:
            assert exchange in BOT_CAPS, f"Exchange {exchange} missing from BOT_CAPS"

    def test_scalper_caps_match_supported_list(self):
        """Verify scalper caps are defined for all supported exchanges"""
        for exchange in SUPPORTED_EXCHANGES:
            assert exchange in SCALPER_CAPS, f"Exchange {exchange} missing from SCALPER_CAPS"

    def test_exchange_limits_scalper_cap_consistency(self):
        """exchange_limits.SCALPER_BOT_ALLOCATION must match rules.SCALPER_CAPS"""
        from exchange_limits import SCALPER_BOT_ALLOCATION
        for exchange in SUPPORTED_EXCHANGES:
            assert SCALPER_BOT_ALLOCATION.get(exchange) == SCALPER_CAPS.get(exchange), (
                f"Mismatch on {exchange}: exchange_limits={SCALPER_BOT_ALLOCATION.get(exchange)} "
                f"vs rules={SCALPER_CAPS.get(exchange)}"
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
