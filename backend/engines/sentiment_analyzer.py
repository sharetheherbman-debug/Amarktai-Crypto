"""
Sentiment Analysis Module
Uses HuggingFace (FinBERT/distilbert) for sentiment analysis with keyword fallback.
Combines HuggingFace Inference API with keyword scoring for robust results.
"""

import asyncio
import os
import aiohttp
from functools import lru_cache
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class SentimentType(Enum):
    """Sentiment classification"""
    VERY_BULLISH = "very_bullish"
    BULLISH = "bullish"
    NEUTRAL = "neutral"
    BEARISH = "bearish"
    VERY_BEARISH = "very_bearish"


@dataclass
class NewsArticle:
    """News article data"""
    timestamp: datetime
    title: str
    content: str
    source: str
    url: str
    coins_mentioned: List[str]


@dataclass
class SentimentScore:
    """Sentiment analysis result"""
    timestamp: datetime
    text: str
    sentiment: SentimentType
    score: float  # -1.0 (very bearish) to 1.0 (very bullish)
    confidence: float
    keywords: List[str]
    source: str


@dataclass
class AggregatedSentiment:
    """Aggregated sentiment signal"""
    timestamp: datetime
    coin: str
    sentiment: SentimentType
    score: float
    confidence: float
    article_count: int
    key_topics: List[str]
    recommendation: str  # 'buy', 'sell', 'hold'


class SentimentAnalyzer:
    """
    Analyzes market sentiment from news and social media.
    Primary: HuggingFace InferenceClient (FinBERT / distilbert-sst2)
    Fallback: keyword-based scoring
    """

    # HuggingFace model for financial sentiment (FinBERT)
    HF_SENTIMENT_MODEL = "ProsusAI/finbert"
    # Lightweight fallback model
    HF_FALLBACK_MODEL = "distilbert-base-uncased-finetuned-sst-2-english"

    def __init__(self):
        # Store analyzed content
        self.sentiment_history: Dict[str, List[SentimentScore]] = {}

        # News and sentiment caches
        self._news_cache: Dict[str, tuple] = {}  # coin -> (fetched_at, articles, status)
        self._news_cache_ttl = int(os.getenv("NEWS_CACHE_TTL_SECONDS", "300"))
        self._last_news_error: Optional[str] = None
        self._news_source: str = "none"
        self._sentiment_cache: Dict[str, tuple] = {}  # coin -> (cached_at, AggregatedSentiment)
        self._sentiment_cache_ttl = int(os.getenv("SENTIMENT_CACHE_TTL_SECONDS", "300"))

        # Sentiment keywords for rule-based fallback
        self.bullish_keywords = [
            'bullish', 'surge', 'rally', 'breakout', 'moon', 'pump',
            'adoption', 'institutional', 'breakthrough', 'all-time high',
            'ATH', 'bull run', 'accumulation', 'upgrade', 'partnership'
        ]

        self.bearish_keywords = [
            'bearish', 'crash', 'dump', 'collapse', 'regulation',
            'ban', 'hack', 'scandal', 'investigation', 'fraud',
            'lawsuit', 'bankruptcy', 'bear market', 'correction'
        ]

    @property
    def news_status(self) -> dict:
        """Return current news source configuration status."""
        key = os.getenv("CRYPTONEWS_API_KEY", "").strip()
        return {
            "configured": bool(key),
            "source": "cryptocompare" if key else "none",
            "cache_ttl_seconds": self._news_cache_ttl,
        }

    async def _call_huggingface(self, text: str, user_id: Optional[str] = None) -> Optional[float]:
        """
        Call HuggingFace Inference API for financial sentiment.
        Uses FinBERT (ProsusAI/finbert) which returns positive/negative/neutral labels.

        Returns:
            Score in [-1.0, 1.0] or None if unavailable
        """
        try:
            from services.huggingface_key_resolver import get_huggingface_client

            # Try FinBERT first, fall back to distilbert-sst2
            for model in (self.HF_SENTIMENT_MODEL, self.HF_FALLBACK_MODEL):
                client, source = await get_huggingface_client(user_id, model=model)
                if not client:
                    logger.debug(f"HuggingFace key source={source} — skipping sentiment model {model}")
                    return None

                try:
                    results = client.text_classification(text[:512])
                    if not results:
                        continue

                    label = results[0].get("label", "").upper()
                    # score is the model's confidence in [0.0, 1.0]
                    confidence = float(results[0].get("score", 0.5))
                    # Clamp to [0, 1] to be safe
                    confidence = max(0.0, min(1.0, confidence))

                    # FinBERT labels: positive / negative / neutral
                    # SST-2 labels: POSITIVE / NEGATIVE
                    # Transform to [-1.0, 1.0]: confidence maps to signal strength.
                    # Clamp to 0 so a 3-class model (FinBERT) with confidence < 0.5
                    # on the winning class never inverts the sign.
                    if label == "POSITIVE":
                        return round(max(0.0, (confidence - 0.5) * 2.0), 3)
                    elif label == "NEGATIVE":
                        return round(min(0.0, -((confidence - 0.5) * 2.0)), 3)
                    else:
                        # NEUTRAL or unknown label
                        return 0.0
                except Exception as model_err:
                    logger.warning(f"HuggingFace model {model} failed: {model_err}")
                    continue

        except Exception as e:
            logger.error(f"HuggingFace sentiment call failed: {e}")

        return None
    
    def _keyword_based_sentiment(self, text: str) -> Tuple[float, List[str]]:
        """
        Calculate sentiment using keyword matching
        
        Args:
            text: Text to analyze
            
        Returns:
            (sentiment_score, matched_keywords)
        """
        text_lower = text.lower()
        
        # Count keyword matches
        bullish_matches = [kw for kw in self.bullish_keywords if kw in text_lower]
        bearish_matches = [kw for kw in self.bearish_keywords if kw in text_lower]
        
        # Calculate score
        bullish_count = len(bullish_matches)
        bearish_count = len(bearish_matches)
        
        total = bullish_count + bearish_count
        if total == 0:
            return 0.0, []
        
        score = (bullish_count - bearish_count) / total
        keywords = bullish_matches + bearish_matches
        
        return score, keywords
    
    async def analyze_text(
        self,
        text: str,
        source: str = "unknown",
        use_ai: bool = True,
        user_id: Optional[str] = None,
    ) -> SentimentScore:
        """
        Analyze sentiment of text.
        Primary: HuggingFace FinBERT via InferenceClient
        Fallback: keyword-based scoring

        Args:
            text: Text to analyze
            source: Source of text
            use_ai: Whether to attempt AI-based analysis
            user_id: Optional user ID for key resolution

        Returns:
            SentimentScore
        """
        # Keyword-based analysis (always computed as fallback)
        keyword_score, keywords = self._keyword_based_sentiment(text)

        # HuggingFace-based analysis (primary)
        hf_score = None
        if use_ai:
            hf_score = await self._call_huggingface(text, user_id=user_id)

        # Use HuggingFace score if available, otherwise keyword score
        final_score = hf_score if hf_score is not None else keyword_score

        # Classify sentiment
        if final_score >= 0.6:
            sentiment = SentimentType.VERY_BULLISH
        elif final_score >= 0.2:
            sentiment = SentimentType.BULLISH
        elif final_score <= -0.6:
            sentiment = SentimentType.VERY_BEARISH
        elif final_score <= -0.2:
            sentiment = SentimentType.BEARISH
        else:
            sentiment = SentimentType.NEUTRAL

        # Confidence: higher when HuggingFace and keywords agree
        if hf_score is not None:
            agreement = 1.0 - abs(hf_score - keyword_score) / 2.0
            confidence = min(0.92, max(0.5, agreement))
        else:
            confidence = 0.45  # Lower confidence without AI

        return SentimentScore(
            timestamp=datetime.now(timezone.utc),
            text=text[:200],
            sentiment=sentiment,
            score=final_score,
            confidence=confidence,
            keywords=keywords,
            source=source,
        )
    
    async def fetch_news(self, coin: str = "BTC", limit: int = 10) -> List[NewsArticle]:
        """
        Fetch recent news articles from CryptoCompare (if CRYPTONEWS_API_KEY set)
        or return an empty list with a clear status (never fake data).

        Caches results for NEWS_CACHE_TTL_SECONDS (default 300).
        """
        now = datetime.now(timezone.utc)
        cache_key = coin.upper()
        cached = self._news_cache.get(cache_key)
        if cached:
            fetched_at, articles, _ = cached
            age = (now - fetched_at).total_seconds()
            if age < self._news_cache_ttl:
                return articles[:limit]

        api_key = os.getenv("CRYPTONEWS_API_KEY", "").strip()
        if not api_key:
            self._last_news_error = "CRYPTONEWS_API_KEY not configured"
            self._news_source = "none"
            self._news_cache[cache_key] = (now, [], "news_source_unconfigured")
            return []

        url = "https://min-api.cryptocompare.com/data/v2/news/"
        params = {"lang": "EN", "categories": coin}
        headers = {"authorization": f"Apikey {api_key}"}
        articles: List[NewsArticle] = []
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, params=params, headers=headers) as resp:
                    if resp.status == 429:
                        self._last_news_error = "CryptoCompare rate-limited (429)"
                        logger.warning("CryptoCompare news API rate-limited")
                        # Return stale cache if available
                        if cached:
                            return cached[1][:limit]
                        return []
                    if resp.status != 200:
                        self._last_news_error = f"CryptoCompare HTTP {resp.status}"
                        logger.warning(f"CryptoCompare news API error: {resp.status}")
                        return []
                    data = await resp.json()
                    raw_articles = data.get("Data", [])
                    for item in raw_articles[:limit]:
                        published_on = item.get("published_on", 0)
                        ts = datetime.fromtimestamp(published_on, tz=timezone.utc) if published_on else now
                        article = NewsArticle(
                            timestamp=ts,
                            title=item.get("title", ""),
                            content=item.get("body", item.get("title", ""))[:1000],
                            source=item.get("source", "CryptoCompare"),
                            url=item.get("url", ""),
                            coins_mentioned=[t.strip() for t in item.get("categories", coin).split("|") if t.strip()],
                        )
                        articles.append(article)
            self._last_news_error = None
            self._news_source = "cryptocompare"
            self._news_cache[cache_key] = (now, articles, "ok")
            logger.info(f"Fetched {len(articles)} real news articles for {coin} from CryptoCompare")
        except asyncio.TimeoutError:
            self._last_news_error = "CryptoCompare request timed out"
            logger.warning("CryptoCompare news API timed out")
        except Exception as e:
            self._last_news_error = str(e)
            logger.error(f"CryptoCompare news fetch failed: {e}")

        return articles

    async def get_news_diagnostics(self) -> dict:
        """Return news fetch status for the diagnostics endpoint."""
        key = os.getenv("CRYPTONEWS_API_KEY", "").strip()
        # Get the most recently cached entry across all coins
        last_fetch_ts = None
        total_articles = 0
        for coin_key, (fetched_at, articles, _) in self._news_cache.items():
            total_articles += len(articles)
            if last_fetch_ts is None or fetched_at > last_fetch_ts:
                last_fetch_ts = fetched_at
        return {
            "configured": bool(key),
            "source": "cryptocompare" if key else "none",
            "articles_count": total_articles,
            "last_fetch_ts": last_fetch_ts.isoformat() if last_fetch_ts else None,
            "last_error": self._last_news_error,
            "cache_ttl_seconds": self._news_cache_ttl,
        }


    async def analyze_coin_sentiment(
        self,
        coin: str,
        hours: int = 24
    ) -> Optional[AggregatedSentiment]:
        """
        Analyze aggregated sentiment for a coin
        
        Args:
            coin: Cryptocurrency
            hours: Time window in hours
            
        Returns:
            AggregatedSentiment
        """
        now_ts = datetime.now(timezone.utc)
        cached_entry = self._sentiment_cache.get(coin.upper())
        if cached_entry:
            cached_at, cached_result = cached_entry
            if (now_ts - cached_at).total_seconds() < self._sentiment_cache_ttl:
                logger.debug(f"Sentiment cache hit for {coin}")
                return cached_result

        # Fetch recent news
        articles = await self.fetch_news(coin, limit=20)
        
        if not articles:
            return None
        
        # Analyze each article
        sentiments = []
        for article in articles:
            text = f"{article.title}. {article.content}"
            sentiment = await self.analyze_text(text, source=article.source)
            sentiments.append(sentiment)
        
        # Store in history
        if coin not in self.sentiment_history:
            self.sentiment_history[coin] = []
        
        self.sentiment_history[coin].extend(sentiments)
        
        # Clean old history
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        self.sentiment_history[coin] = [
            s for s in self.sentiment_history[coin]
            if s.timestamp > cutoff
        ]
        
        # Aggregate sentiment
        recent = self.sentiment_history[coin]
        
        if not recent:
            return None
        
        avg_score = sum(s.score for s in recent) / len(recent)
        avg_confidence = sum(s.confidence for s in recent) / len(recent)
        
        # Classify aggregated sentiment
        if avg_score >= 0.5:
            agg_sentiment = SentimentType.VERY_BULLISH
            recommendation = 'buy'
        elif avg_score >= 0.2:
            agg_sentiment = SentimentType.BULLISH
            recommendation = 'buy'
        elif avg_score <= -0.5:
            agg_sentiment = SentimentType.VERY_BEARISH
            recommendation = 'sell'
        elif avg_score <= -0.2:
            agg_sentiment = SentimentType.BEARISH
            recommendation = 'sell'
        else:
            agg_sentiment = SentimentType.NEUTRAL
            recommendation = 'hold'
        
        # Extract key topics
        all_keywords = []
        for s in recent:
            all_keywords.extend(s.keywords)
        
        # Count keyword frequency
        keyword_counts = {}
        for kw in all_keywords:
            keyword_counts[kw] = keyword_counts.get(kw, 0) + 1
        
        # Top 5 keywords
        key_topics = sorted(
            keyword_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )[:5]
        key_topics = [kw for kw, _ in key_topics]
        
        result = AggregatedSentiment(
            timestamp=datetime.now(timezone.utc),
            coin=coin,
            sentiment=agg_sentiment,
            score=avg_score,
            confidence=avg_confidence,
            article_count=len(recent),
            key_topics=key_topics,
            recommendation=recommendation
        )
        
        logger.info(
            f"Sentiment for {coin}: {agg_sentiment.value} "
            f"(score: {avg_score:.2f}, confidence: {avg_confidence:.2%}) "
            f"-> {recommendation}"
        )
        
        self._sentiment_cache[coin.upper()] = (datetime.now(timezone.utc), result)
        return result
    
    async def get_sentiment_summary(self) -> Dict[str, Dict]:
        """
        Get sentiment summary for all tracked coins
        
        Returns:
            Dictionary of coin -> sentiment summary
        """
        summary = {}
        
        for coin in ['BTC', 'ETH', 'USDT']:
            sentiment = await self.analyze_coin_sentiment(coin, hours=24)
            
            if sentiment:
                summary[coin] = {
                    'sentiment': sentiment.sentiment.value,
                    'score': sentiment.score,
                    'confidence': sentiment.confidence,
                    'article_count': sentiment.article_count,
                    'key_topics': sentiment.key_topics,
                    'recommendation': sentiment.recommendation,
                    'timestamp': sentiment.timestamp.isoformat()
                }

        return summary

    async def get_overall_sentiment(self) -> Optional[Dict]:
        """
        Get aggregated overall market sentiment across tracked coins.
        Called by compatibility_endpoints.py.

        Returns:
            Dict with keys: sentiment, score, recommendation, sources_analyzed, timestamp
            or None if no data available
        """
        summary = await self.get_sentiment_summary()

        if not summary:
            return None

        # Aggregate across all coins
        scores = [v['score'] for v in summary.values()]
        avg_score = sum(scores) / len(scores)
        sources_analyzed = sum(v['article_count'] for v in summary.values())

        # Determine overall sentiment label
        if avg_score >= 0.5:
            sentiment = SentimentType.VERY_BULLISH.value
            recommendation = 'buy'
        elif avg_score >= 0.2:
            sentiment = SentimentType.BULLISH.value
            recommendation = 'buy'
        elif avg_score <= -0.5:
            sentiment = SentimentType.VERY_BEARISH.value
            recommendation = 'sell'
        elif avg_score <= -0.2:
            sentiment = SentimentType.BEARISH.value
            recommendation = 'sell'
        else:
            sentiment = SentimentType.NEUTRAL.value
            recommendation = 'hold'

        return {
            'sentiment': sentiment,
            'score': round(avg_score, 3),
            'recommendation': recommendation,
            'sources_analyzed': sources_analyzed,
            'coins': list(summary.keys()),
            'timestamp': datetime.now(timezone.utc).isoformat(),
        }


# Global instance
sentiment_analyzer = SentimentAnalyzer()
