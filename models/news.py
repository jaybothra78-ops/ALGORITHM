"""Data models and schemas for AI News Analyzer."""
from __future__ import annotations

from enum import Enum
from typing import Any
from pydantic import BaseModel, ConfigDict, Field


class SentimentVerdict(str, Enum):
    """Overall news sentiment classification."""
    BULLISH = "Bullish"
    BEARISH = "Bearish"
    NEUTRAL = "Neutral"


class NewsArticle(BaseModel):
    """Structured financial news article item."""
    model_config = ConfigDict(frozen=True)

    title: str = Field(..., description="Headline of the news article")
    publisher: str = Field(default="Financial News", description="News publisher source (e.g. Economic Times, Moneycontrol)")
    link: str = Field(..., description="Direct URL to the full news article")
    published_at: str = Field(..., description="Publication time or relative date")
    summary: str = Field(default="", description="Snippet or brief description of the story")


class NewsAnalysisRequest(BaseModel):
    """Request payload to analyze news for a stock."""
    model_config = ConfigDict(extra="ignore")

    symbol: str = Field(..., description="Stock ticker symbol (e.g. TVSMOTOR, RELIANCE)")
    days: int = Field(default=7, ge=1, le=30, description="Lookback window in days for news search")
    api_key: str | None = Field(default=None, description="Optional Anthropic Claude API Key")


class NewsAnalysisResponse(BaseModel):
    """Institutional AI news analysis response payload."""
    symbol: str = Field(..., description="Stock ticker analyzed")
    company_name: str = Field(..., description="Full company name")
    sentiment: str = Field(..., description="Sentiment verdict: Bullish, Bearish, or Neutral")
    sentiment_score: int = Field(..., ge=0, le=100, description="Sentiment confidence score 0-100")
    analysis_engine: str = Field(default="Claude AI Engine", description="Engine used for synthesis")
    executive_summary: str = Field(..., description="Executive summary synthesized from recent news")
    catalysts: list[str] = Field(default_factory=list, description="Key positive catalysts and growth drivers")
    risks: list[str] = Field(default_factory=list, description="Key risks, headwinds, or cautionary flags")
    technical_correlation: str = Field(..., description="Synthesis of news impact on current technical setup")
    articles: list[NewsArticle] = Field(default_factory=list, description="Recent underlying news articles")
    timestamp: float = Field(..., description="Epoch timestamp of analysis")

