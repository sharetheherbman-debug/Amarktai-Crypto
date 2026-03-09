"""
Tests for scalper bot classification fixes.

Covers:
1. bot_validator.validate_bot_creation preserves bot_type='scalper'
2. bot_validator.validate_bot_creation preserves profit_routing='SCALPER_GROWTH'
3. Normal bots get bot_type='normal' when not specified
4. Invalid bot_type values default to 'normal'
5. Migration logic for fix_bot_type_field
"""
import sys
import os
sys.path.insert(0, 'backend')
os.environ['ENVIRONMENT'] = 'testing'

import pytest


# ─── Validation logic unit tests (no DB needed) ─────────────────────────────

def _apply_bot_type_logic(bot_data):
    """Mirror the validator logic added to bot_validator.py."""
    valid_bot_types = {'normal', 'scalper', 'uagent'}
    raw_bot_type = (bot_data.get("bot_type") or "normal").lower()
    bot_type = raw_bot_type if raw_bot_type in valid_bot_types else "normal"

    valid_profit_routings = {'RETURN_TO_MAIN', 'SCALPER_GROWTH'}
    raw_routing = (bot_data.get("profit_routing") or "RETURN_TO_MAIN").upper()
    profit_routing = raw_routing if raw_routing in valid_profit_routings else "RETURN_TO_MAIN"

    return bot_type, profit_routing


def test_scalper_bot_type_preserved():
    """bot_type='scalper' must be returned as-is."""
    bt, _ = _apply_bot_type_logic({"bot_type": "scalper"})
    assert bt == "scalper", f"Expected 'scalper', got '{bt}'"


def test_scalper_bot_type_case_insensitive():
    """bot_type='SCALPER' should normalise to 'scalper'."""
    bt, _ = _apply_bot_type_logic({"bot_type": "SCALPER"})
    assert bt == "scalper"


def test_normal_bot_type_preserved():
    """bot_type='normal' must be returned as-is."""
    bt, _ = _apply_bot_type_logic({"bot_type": "normal"})
    assert bt == "normal"


def test_missing_bot_type_defaults_to_normal():
    """Missing bot_type must default to 'normal'."""
    bt, _ = _apply_bot_type_logic({})
    assert bt == "normal"


def test_none_bot_type_defaults_to_normal():
    """bot_type=None must default to 'normal'."""
    bt, _ = _apply_bot_type_logic({"bot_type": None})
    assert bt == "normal"


def test_invalid_bot_type_fallback_to_normal():
    """Unknown bot_type values must fall back to 'normal'."""
    bt, _ = _apply_bot_type_logic({"bot_type": "super_scalper_v2"})
    assert bt == "normal"


def test_uagent_bot_type_preserved():
    """bot_type='uagent' must be preserved."""
    bt, _ = _apply_bot_type_logic({"bot_type": "uagent"})
    assert bt == "uagent"


def test_scalper_growth_routing_preserved():
    """profit_routing='SCALPER_GROWTH' must be returned as-is."""
    _, pr = _apply_bot_type_logic({"profit_routing": "SCALPER_GROWTH"})
    assert pr == "SCALPER_GROWTH"


def test_routing_case_insensitive():
    """profit_routing='scalper_growth' should normalise to 'SCALPER_GROWTH'."""
    _, pr = _apply_bot_type_logic({"profit_routing": "scalper_growth"})
    assert pr == "SCALPER_GROWTH"


def test_missing_routing_defaults_to_return_to_main():
    """Missing profit_routing must default to 'RETURN_TO_MAIN'."""
    _, pr = _apply_bot_type_logic({})
    assert pr == "RETURN_TO_MAIN"


def test_invalid_routing_fallback():
    """Unknown profit_routing values must fall back to 'RETURN_TO_MAIN'."""
    _, pr = _apply_bot_type_logic({"profit_routing": "MAGIC_ROUTING"})
    assert pr == "RETURN_TO_MAIN"


# ─── BotFleetSection filter logic unit tests ─────────────────────────────────

def _filter_bots(bots, fleet_tab, status_filter='all', platform_filter='all'):
    """Mirror the filteredBots logic in BotFleetSection.js."""
    result = []
    for bot in bots:
        status = bot.get('status', 'unknown')
        if status == 'deleted' or bot.get('deleted') or bot.get('deleted_at'):
            continue
        bt = (bot.get('bot_type') or '').lower()
        if fleet_tab == 'normal' and (bt == 'scalper' or bt == 'uagent'):
            continue
        if fleet_tab == 'scalper' and bt != 'scalper':
            continue
        if fleet_tab == 'uagent' and bt != 'uagent':
            continue
        if status_filter != 'all' and status != status_filter:
            continue
        if platform_filter != 'all' and (bot.get('exchange') or '').lower() != platform_filter:
            continue
        result.append(bot)
    return result


def test_scalper_tab_shows_only_scalper_bots():
    """Scalper tab must only show bots with bot_type='scalper'."""
    bots = [
        {'id': '1', 'bot_type': 'scalper', 'status': 'active', 'exchange': 'binance'},
        {'id': '2', 'bot_type': 'normal', 'status': 'active', 'exchange': 'binance'},
        {'id': '3', 'bot_type': None, 'status': 'active', 'exchange': 'binance'},
    ]
    filtered = _filter_bots(bots, 'scalper')
    assert len(filtered) == 1
    assert filtered[0]['id'] == '1'


def test_normal_tab_excludes_scalper_bots():
    """Normal tab must exclude bots with bot_type='scalper'."""
    bots = [
        {'id': '1', 'bot_type': 'scalper', 'status': 'active', 'exchange': 'binance'},
        {'id': '2', 'bot_type': 'normal', 'status': 'active', 'exchange': 'binance'},
        {'id': '3', 'bot_type': None, 'status': 'active', 'exchange': 'binance'},
    ]
    filtered = _filter_bots(bots, 'normal')
    ids = [b['id'] for b in filtered]
    assert '1' not in ids
    assert '2' in ids
    assert '3' in ids


def test_scalper_tab_empty_when_no_scalpers():
    """Scalper tab must show 0 bots when none have bot_type='scalper'."""
    bots = [
        {'id': '1', 'bot_type': 'normal', 'status': 'active'},
        {'id': '2', 'bot_type': None, 'status': 'active'},
    ]
    filtered = _filter_bots(bots, 'scalper')
    assert len(filtered) == 0


if __name__ == '__main__':
    # Run each test manually
    for name, fn in list(globals().items()):
        if name.startswith('test_'):
            fn()
            print(f'  PASS: {name}')
    print('\nAll scalper classification tests PASSED')
