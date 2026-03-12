"""
Regression test: BotValidator import and instantiation

Ensures that `validators/bot_validator.py` can always be imported successfully
and that the `class BotValidator:` declaration is present, preventing the
`NameError: name 'BotValidator' is not defined` production blocker
(POST /api/bots -> 500) from regressing.

Root cause that was fixed: the `class BotValidator:` header was accidentally
dropped from bot_validator.py, leaving the class body floating at module level.
The module-level `bot_validator = BotValidator()` then raised a NameError at
import time, causing every call to POST /api/bots to fail with a 500 error.
"""

import sys
import os
import pytest

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class TestBotValidatorImport:
    """Regression tests: BotValidator class declaration and global instance"""

    def test_bot_validator_module_imports_without_error(self):
        """bot_validator module must import without NameError or ImportError."""
        try:
            from validators.bot_validator import bot_validator, BotValidator
        except NameError as e:
            pytest.fail(
                f"NameError during bot_validator import — class declaration likely missing: {e}"
            )
        except ImportError as e:
            pytest.fail(f"ImportError during bot_validator import: {e}")

    def test_bot_validator_class_is_a_class(self):
        """BotValidator must be a class, not a stray module-level function or None."""
        from validators.bot_validator import BotValidator
        assert isinstance(BotValidator, type), (
            "BotValidator must be a class. "
            "If it is not, the 'class BotValidator:' declaration was likely dropped."
        )

    def test_bot_validator_global_instance_is_correct_type(self):
        """The module-level bot_validator singleton must be an instance of BotValidator."""
        from validators.bot_validator import bot_validator, BotValidator
        assert isinstance(bot_validator, BotValidator), (
            "bot_validator must be an instance of BotValidator. "
            "If BotValidator is undefined at module level, instantiation raises NameError."
        )

    def test_bot_validator_instance_attributes(self):
        """BotValidator instance must expose the expected configuration attributes."""
        from validators.bot_validator import bot_validator

        required_attrs = ['supported_exchanges', 'min_capital', 'max_capital', 'max_bots_total']
        for attr in required_attrs:
            assert hasattr(bot_validator, attr), \
                f"bot_validator must have attribute '{attr}'"

        assert isinstance(bot_validator.supported_exchanges, list), \
            "supported_exchanges must be a list"
        assert len(bot_validator.supported_exchanges) > 0, \
            "supported_exchanges must not be empty"
        assert bot_validator.min_capital == 100, \
            "min_capital must be 100 (R100 minimum)"
        assert bot_validator.max_capital == 100000, \
            "max_capital must be 100000 (R100,000 maximum)"
        assert bot_validator.max_bots_total > 0, \
            "max_bots_total must be a positive integer"

    def test_bot_validator_has_validate_bot_creation_method(self):
        """validate_bot_creation must be an async method on the BotValidator instance."""
        import asyncio
        from validators.bot_validator import bot_validator
        method = getattr(bot_validator, 'validate_bot_creation', None)
        assert method is not None, \
            "bot_validator must have a 'validate_bot_creation' method"
        assert callable(method), \
            "validate_bot_creation must be callable"
        assert asyncio.iscoroutinefunction(method), \
            "validate_bot_creation must be an async (coroutine) function"

    def test_all_expected_exchanges_in_supported_list(self):
        """All 7 canonical exchanges must appear in supported_exchanges."""
        from validators.bot_validator import bot_validator
        expected = {'luno', 'binance', 'kucoin', 'bybit', 'kraken', 'bitget', 'gate'}
        actual = set(bot_validator.supported_exchanges)
        assert expected == actual, (
            f"supported_exchanges mismatch. Expected: {expected}, Got: {actual}"
        )

    @pytest.mark.asyncio
    async def test_validate_bot_creation_returns_error_for_invalid_exchange(self):
        """validate_bot_creation must return (False, error_dict) for unknown exchanges."""
        from validators.bot_validator import BotValidator

        validator = BotValidator()

        bot_data = {
            'name': 'Test Bot',
            'exchange': 'not_a_real_exchange',
            'capital': 500,
            'trading_mode': 'paper',
            'risk_mode': 'safe',
        }

        is_valid, result = await validator.validate_bot_creation('user123', bot_data)

        assert is_valid is False, \
            "validate_bot_creation must return False for an invalid exchange"
        assert isinstance(result, dict), \
            "Error result must be a dict"

    @pytest.mark.asyncio
    async def test_validate_bot_creation_returns_error_for_below_minimum_capital(self):
        """validate_bot_creation must reject capital below R100 minimum."""
        from validators.bot_validator import BotValidator

        validator = BotValidator()

        bot_data = {
            'name': 'Test Bot',
            'exchange': 'luno',
            'capital': 50,  # below R100 minimum
            'trading_mode': 'paper',
            'risk_mode': 'safe',
        }

        is_valid, result = await validator.validate_bot_creation('user123', bot_data)

        assert is_valid is False, \
            "validate_bot_creation must return False when capital < R100"
        assert isinstance(result, dict), \
            "Error result must be a dict"
