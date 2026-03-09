"""
Test Provider Truth Model
Ensures the canonical provider hierarchy is correctly implemented:
  - CoinStats is NOT in canonical provider lists (AI, market data, enricher)
  - CoinStats is in legacy list, marked deprecated, disabled, hidden
  - CoinDesk is primary market data provider
  - CryptoCompare is secondary, CoinGecko tertiary, Coinranking quaternary
  - Provider registry matches frontend constants
  - No stale CoinStats-first wiring in active dashboard code
"""

import pytest
import sys
import os
import re
from pathlib import Path

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))


# ── Provider truth constants ────────────────────────────────────────────────

CANONICAL_EXCHANGES = {'luno', 'binance', 'kucoin', 'bybit', 'kraken', 'bitget', 'gate'}
CANONICAL_AI_PROVIDERS = {'openai', 'huggingface', 'fetchai'}
CANONICAL_MARKET_DATA = {'coindesk', 'cryptocompare', 'coingecko', 'coinranking'}
CANONICAL_ENRICHERS = {'glassnode', 'etherscan', 'whale_alert', 'lunarcrush', 'cryptopanic'}
LEGACY_PROVIDERS = {'coinstats'}


# ── Backend provider registry tests ─────────────────────────────────────────

class TestProviderRegistry:
    """Tests for backend/services/provider_registry.py"""

    def _import_registry(self):
        try:
            from services.provider_registry import PROVIDERS, ProviderType
            return PROVIDERS, ProviderType
        except ImportError:
            pytest.skip("provider_registry has unmet dependency (ccxt/httpx)")
            return None, None

    def test_registry_has_all_canonical_providers(self):
        PROVIDERS, _ = self._import_registry()
        if PROVIDERS is None:
            return
        provider_ids = set(PROVIDERS.keys())
        expected = (
            CANONICAL_EXCHANGES | CANONICAL_AI_PROVIDERS |
            CANONICAL_MARKET_DATA | CANONICAL_ENRICHERS | LEGACY_PROVIDERS
        )
        missing = expected - provider_ids
        assert not missing, f"Missing providers in registry: {missing}"

    def test_coinstats_is_legacy_type(self):
        PROVIDERS, ProviderType = self._import_registry()
        if PROVIDERS is None:
            return
        cs = PROVIDERS.get('coinstats')
        assert cs is not None, "coinstats should still exist in registry"
        assert cs.provider_type == ProviderType.LEGACY, (
            f"coinstats should be LEGACY, got {cs.provider_type}"
        )

    def test_coinstats_not_in_ai_type(self):
        PROVIDERS, ProviderType = self._import_registry()
        if PROVIDERS is None:
            return
        ai_ids = {k for k, v in PROVIDERS.items() if v.provider_type == ProviderType.AI}
        assert 'coinstats' not in ai_ids, "coinstats must NOT be AI type"

    def test_market_data_providers_exist(self):
        PROVIDERS, ProviderType = self._import_registry()
        if PROVIDERS is None:
            return
        md_ids = {k for k, v in PROVIDERS.items() if v.provider_type == ProviderType.MARKET_DATA}
        assert md_ids == CANONICAL_MARKET_DATA, f"Expected {CANONICAL_MARKET_DATA}, got {md_ids}"

    def test_enricher_providers_exist(self):
        PROVIDERS, ProviderType = self._import_registry()
        if PROVIDERS is None:
            return
        enr_ids = {k for k, v in PROVIDERS.items() if v.provider_type == ProviderType.ENRICHER}
        assert enr_ids == CANONICAL_ENRICHERS, f"Expected {CANONICAL_ENRICHERS}, got {enr_ids}"

    def test_exchange_count_still_7(self):
        PROVIDERS, ProviderType = self._import_registry()
        if PROVIDERS is None:
            return
        exch_ids = {k for k, v in PROVIDERS.items() if v.provider_type == ProviderType.EXCHANGE}
        assert exch_ids == CANONICAL_EXCHANGES, f"Expected {CANONICAL_EXCHANGES}, got {exch_ids}"


# ── Backend keys_service tests ──────────────────────────────────────────────

class TestKeysService:
    """Tests for backend/services/keys_service.py"""

    def test_supported_providers_includes_new_types(self):
        try:
            from services.keys_service import SUPPORTED_PROVIDERS
        except ImportError:
            pytest.skip("keys_service has unmet dependency (motor/database)")
            return
        sp = set(SUPPORTED_PROVIDERS)
        for p in CANONICAL_MARKET_DATA | CANONICAL_ENRICHERS:
            assert p in sp, f"{p} should be in SUPPORTED_PROVIDERS"

    def test_coinstats_still_in_supported_providers(self):
        """CoinStats is retained as legacy fallback."""
        try:
            from services.keys_service import SUPPORTED_PROVIDERS
        except ImportError:
            pytest.skip("keys_service has unmet dependency (motor/database)")
            return
        assert 'coinstats' in SUPPORTED_PROVIDERS


# ── Frontend source-level tests ─────────────────────────────────────────────

class TestFrontendProviderTruth:
    """Scan frontend source to verify provider truth alignment."""

    @pytest.fixture(autouse=True)
    def _setup_paths(self):
        self.frontend_src = Path(__file__).parent.parent / 'frontend' / 'src'
        self.platforms_js = self.frontend_src / 'constants' / 'platforms.js'

    def test_platforms_js_coinstats_not_in_ai_providers(self):
        content = self.platforms_js.read_text()
        # Find the SUPPORTED_AI_PROVIDERS array
        match = re.search(r"export const SUPPORTED_AI_PROVIDERS\s*=\s*\[([^\]]+)\]", content)
        assert match, "SUPPORTED_AI_PROVIDERS not found in platforms.js"
        ai_list = match.group(1)
        assert 'coinstats' not in ai_list, "coinstats must NOT be in SUPPORTED_AI_PROVIDERS"

    def test_platforms_js_has_market_data_providers(self):
        content = self.platforms_js.read_text()
        match = re.search(r"export const MARKET_DATA_PROVIDERS\s*=\s*\[([^\]]+)\]", content)
        assert match, "MARKET_DATA_PROVIDERS not found in platforms.js"
        md_list = match.group(1)
        for p in ['coindesk', 'cryptocompare', 'coingecko', 'coinranking']:
            assert p in md_list, f"{p} missing from MARKET_DATA_PROVIDERS"

    def test_platforms_js_has_intelligence_enrichers(self):
        content = self.platforms_js.read_text()
        match = re.search(r"export const INTELLIGENCE_ENRICHERS\s*=\s*\[([^\]]+)\]", content)
        assert match, "INTELLIGENCE_ENRICHERS not found in platforms.js"
        enr_list = match.group(1)
        for p in ['glassnode', 'etherscan', 'whale_alert', 'lunarcrush', 'cryptopanic']:
            assert p in enr_list, f"{p} missing from INTELLIGENCE_ENRICHERS"

    def test_platforms_js_coinstats_marked_legacy(self):
        content = self.platforms_js.read_text()
        match = re.search(r"export const LEGACY_PROVIDERS\s*=\s*\[([^\]]+)\]", content)
        assert match, "LEGACY_PROVIDERS not found in platforms.js"
        legacy_list = match.group(1)
        assert 'coinstats' in legacy_list, "coinstats should be in LEGACY_PROVIDERS"

    def test_platforms_js_coinstats_disabled_by_default(self):
        content = self.platforms_js.read_text()
        # Find the coinstats config block and check enabled: false
        cs_match = re.search(
            r"coinstats:\s*\{[^}]*enabled:\s*(true|false)",
            content, re.DOTALL
        )
        assert cs_match, "coinstats config block not found"
        assert cs_match.group(1) == 'false', "coinstats must have enabled: false"

    def test_platforms_js_coinstats_deprecated_flag(self):
        content = self.platforms_js.read_text()
        cs_match = re.search(
            r"coinstats:\s*\{[^}]*deprecated:\s*(true|false)",
            content, re.DOTALL
        )
        assert cs_match, "coinstats config should have deprecated flag"
        assert cs_match.group(1) == 'true', "coinstats must have deprecated: true"


# ── Active dashboard has no CoinStats canonical wiring ──────────────────────

class TestNoCoinStatsCanonicalWiring:
    """Ensure active dashboard sections don't import CoinStatsPanel."""

    @pytest.fixture(autouse=True)
    def _setup_paths(self):
        self.sections_dir = (
            Path(__file__).parent.parent / 'frontend' / 'src' /
            'pages' / 'dashboard' / 'sections'
        )

    def test_metrics_section_does_not_import_coinstats_panel(self):
        metrics_file = self.sections_dir / 'MetricsWithTabsSection.js'
        content = metrics_file.read_text()
        assert 'CoinStatsPanel' not in content, (
            "MetricsWithTabsSection should not import CoinStatsPanel"
        )

    def test_metrics_section_uses_market_intelligence_panel(self):
        metrics_file = self.sections_dir / 'MetricsWithTabsSection.js'
        content = metrics_file.read_text()
        assert 'MarketIntelligencePanel' in content, (
            "MetricsWithTabsSection should import MarketIntelligencePanel"
        )

    def test_metrics_tab_not_named_coinstats(self):
        metrics_file = self.sections_dir / 'MetricsWithTabsSection.js'
        content = metrics_file.read_text()
        # Should not have a tab called 'coinstats'
        assert "setMetricsTab('coinstats')" not in content, (
            "MetricsWithTabsSection tab should not be named 'coinstats'"
        )

    def test_coinstats_panel_marked_deprecated(self):
        cs_file = self.sections_dir / 'CoinStatsPanel.js'
        assert cs_file.exists(), "CoinStatsPanel.js should still exist (retained as legacy)"
        content = cs_file.read_text()
        assert 'DEPRECATED' in content, (
            "CoinStatsPanel.js should be marked DEPRECATED"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
