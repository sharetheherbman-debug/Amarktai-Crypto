"""
Sentiment Analysis Module
Uses HuggingFace (FinBERT/distilbert) for sentiment analysis with keyword fallback.
Combines HuggingFace Inference API with keyword scoring for robust results.
"""

import asyncio
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
                    # Transform to [-1.0, 1.0]: confidence maps to signal strength
                    if label == "POSITIVE":
                        # Map [0.5, 1.0] confidence to [0.0, 1.0] sentiment score
                        return round((confidence - 0.5) * 2.0, 3)
                    elif label == "NEGATIVE":
                        return round(-((confidence - 0.5) * 2.0), 3)
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
        Fetch recent news articles (simulated for now)
        
        Args:
            coin: Cryptocurrency to fetch news for
            limit: Maximum number of articles
            
        Returns:
            List of NewsArticle
        """
        # In production, integrate with actual news APIs like:
        # - CryptoCompare News API
        # - NewsAPI
        # - CoinGecko News
        # - Twitter API for social sentiment
        
        # Simulated news for demonstration
        articles = []
        
        sample_news = [
            {
                'title': f'{coin} Price Surges on Institutional Adoption',
                'content': f'{coin} has seen significant institutional investment this week, with major funds announcing positions.',
                'source': 'CryptoNews'
            },
            {
                'title': f'Regulatory Concerns Impact {coin} Market',
                'content': f'New regulatory proposals have created uncertainty in the {coin} market, leading to volatility.',
                'source': 'CoinTelegraph'
            },
            {
                'title': f'{coin} Network Upgrade Completed Successfully',
                'content': f'The latest {coin} network upgrade has been implemented, improving scalability and efficiency.',
                'source': 'Decrypt'
            }
        ]
        
        for i, news in enumerate(sample_news[:limit]):
            article = NewsArticle(
                timestamp=datetime.now(timezone.utc) - timedelta(hours=i),
                title=news['title'],
                content=news['content'],
                source=news['source'],
                url=f"https://example.com/article-{i}",
                coins_mentioned=[coin]
            )
            articles.append(article)
        
        return articles
    
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
