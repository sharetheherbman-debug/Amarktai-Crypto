"""
Tests for ml_predictor.py – verifying deterministic behavior.

These tests mock CCXT so no network calls are made.
"""

import asyncio
import sys
import os
import pytest
import importlib
from unittest.mock import AsyncMock, MagicMock, patch

# Ensure backend is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))


def _candles(closes):
    """Build minimal OHLCV list: [ts, open, high, low, close, volume]."""
    return [[i * 3600000, c, c, c, c, 0] for i, c in enumerate(closes)]


# ──────────────────────────────────────────────────────────────────────────────
# Unit tests for the internal _compute_momentum helper
# ──────────────────────────────────────────────────────────────────────────────

class TestComputeMomentum:
    def _get_func(self):
        import importlib
        import ml_predictor as m
        importlib.reload(m)
        return m._compute_momentum

    def test_uptrend_detected(self):
        compute = self._get_func()
        # Steadily rising prices – short EMA should be above long EMA
        closes = [100.0 + i * 2 for i in range(30)]
        direction, confidence, pct = compute(closes)
        assert direction == "up", f"Expected 'up', got '{direction}'"
        assert 0.4 <= confidence <= 0.9

    def test_downtrend_detected(self):
        compute = self._get_func()
        # Steadily falling prices
        closes = [200.0 - i * 2 for i in range(30)]
        direction, confidence, pct = compute(closes)
        assert direction == "down", f"Expected 'down', got '{direction}'"
        assert 0.4 <= confidence <= 0.9

    def test_flat_market_neutral(self):
        compute = self._get_func()
        # Perfectly flat prices – no momentum
        closes = [100.0] * 30
        direction, confidence, pct = compute(closes)
        assert direction == "neutral"

    def test_deterministic_same_input_same_output(self):
        compute = self._get_func()
        closes = [100.0 + i * 0.5 for i in range(30)]
        r1 = compute(closes)
        r2 = compute(closes)
        assert r1 == r2, "Same input must produce same output (deterministic)"

    def test_insufficient_data_returns_neutral(self):
        compute = self._get_func()
        closes = [100.0] * 10  # fewer than 20 required
        direction, confidence, pct = compute(closes)
        assert direction == "neutral"
        assert confidence == 0.3


# ──────────────────────────────────────────────────────────────────────────────
# Integration-style tests for MLPredictor.predict_price (CCXT mocked)
# ──────────────────────────────────────────────────────────────────────────────

class TestMLPredictorPredict:

    def test_deterministic_given_compute_momentum(self):
        """
        Verify predict_price produces deterministic output for the same candle data
        by calling _compute_momentum directly with fixed inputs.
        """
        import ml_predictor as m
        importlib.reload(m)

        closes_up = [100.0 + i * 1.5 for i in range(30)]
        closes_down = [200.0 - i * 1.5 for i in range(30)]

        r1 = m._compute_momentum(closes_up)
        r2 = m._compute_momentum(closes_up)
        assert r1 == r2, "compute_momentum must be deterministic for same input"
        assert r1[0] == "up"

        r3 = m._compute_momentum(closes_down)
        assert r3[0] == "down"
        assert r1 != r3, "Up and down trends must produce different predictions"

    def test_returns_simulated_when_ccxt_unavailable(self):
        """When CCXT cannot return enough candle data, predict_price must return is_simulated=True."""
        import ml_predictor as m
        importlib.reload(m)

        mock_exchange = MagicMock()
        mock_exchange.fetch_ohlcv = AsyncMock(side_effect=Exception("connection refused"))
        mock_exchange.close = AsyncMock()
        mock_exchange_cls = MagicMock(return_value=mock_exchange)

        import ccxt.async_support as real_ccxt_async
        with patch.object(real_ccxt_async, 'binance', mock_exchange_cls, create=True), \
             patch.object(real_ccxt_async, 'kucoin', mock_exchange_cls, create=True), \
             patch.object(real_ccxt_async, 'bybit', mock_exchange_cls, create=True):
            predictor = m.MLPredictor()
            result = asyncio.get_event_loop().run_until_complete(
                predictor.predict_price("BTC_USDT")
            )

        assert result.get("is_simulated") is True

    def test_returns_simulated_when_insufficient_candles(self):
        """When exchange returns fewer than 20 candles, result must be is_simulated=True."""
        import ml_predictor as m
        importlib.reload(m)

        ohlcv = _candles([100.0] * 5)

        mock_exchange = MagicMock()
        mock_exchange.fetch_ohlcv = AsyncMock(return_value=ohlcv)
        mock_exchange.close = AsyncMock()
        mock_exchange_cls = MagicMock(return_value=mock_exchange)

        import ccxt.async_support as real_ccxt_async
        with patch.object(real_ccxt_async, 'binance', mock_exchange_cls, create=True), \
             patch.object(real_ccxt_async, 'kucoin', mock_exchange_cls, create=True), \
             patch.object(real_ccxt_async, 'bybit', mock_exchange_cls, create=True):
            predictor = m.MLPredictor()
            result = asyncio.get_event_loop().run_until_complete(
                predictor.predict_price("BTC_USDT")
            )

        assert result.get("is_simulated") is True

    def test_returns_real_prediction_with_sufficient_candles(self):
        """When exchange returns >= 20 candles, predict_price must return is_simulated=False."""
        import ml_predictor as m
        importlib.reload(m)

        closes = [100.0 + i * 1.5 for i in range(30)]
        ohlcv = _candles(closes)

        mock_exchange = MagicMock()
        mock_exchange.fetch_ohlcv = AsyncMock(return_value=ohlcv)
        mock_exchange.close = AsyncMock()
        mock_exchange_cls = MagicMock(return_value=mock_exchange)

        import ccxt.async_support as real_ccxt_async
        with patch.object(real_ccxt_async, 'binance', mock_exchange_cls, create=True):
            predictor = m.MLPredictor()
            result = asyncio.get_event_loop().run_until_complete(
                predictor.predict_price("BTC_USDT")
            )

        assert result.get("is_simulated") is False
        assert result.get("direction") in ("up", "down", "neutral")
        assert 0.0 <= result.get("confidence", -1) <= 1.0
        assert result.get("error") is None
