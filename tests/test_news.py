"""Unit and integration tests for AI News Analyzer."""
from fastapi.testclient import TestClient
from main import app
from models.news import NewsAnalysisRequest, NewsArticle
from services.news_service import NewsService


def test_fetch_news_format():
    articles = NewsService.fetch_news("RELIANCE", limit=5)
    assert isinstance(articles, list)
    if articles:
        a = articles[0]
        assert hasattr(a, "title")
        assert hasattr(a, "publisher")
        assert hasattr(a, "link")


def test_analyze_news_nlp_synthesis():
    dummy_articles = [
        NewsArticle(
            title="Reliance Industries Q1 net profit surges 25% on strong retail growth",
            publisher="The Economic Times",
            link="https://economictimes.indiatimes.com",
            published_at="Mon, 31 Aug 2026 10:00:00 GMT",
            summary="Reliance reported revenue expansion and higher EBITDA margins.",
        ),
        NewsArticle(
            title="Brokerages raise target price on Reliance citing digital expansion",
            publisher="Moneycontrol",
            link="https://moneycontrol.com",
            published_at="Tue, 01 Sep 2026 08:00:00 GMT",
            summary="Analysts maintain a buy rating with an upside target.",
        ),
    ]

    res = NewsService._analyze_with_nlp_engine("RELIANCE", dummy_articles)
    assert res.symbol == "RELIANCE"
    assert res.sentiment in ("Bullish", "Neutral", "Bearish")
    assert res.sentiment_score >= 0 and res.sentiment_score <= 100
    assert len(res.catalysts) > 0
    assert len(res.articles) == 2


def test_news_analyze_api_endpoint():
    with TestClient(app) as c:
        payload = {"symbol": "TVSMOTOR", "days": 7}
        resp = c.post("/news/analyze", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert "symbol" in data
        assert data["symbol"] == "TVSMOTOR"
        assert "sentiment" in data
        assert "sentiment_score" in data
        assert "executive_summary" in data
        assert "catalysts" in data
        assert "articles" in data

    # Test GET endpoint
    with TestClient(app) as c:
        resp_get = c.get("/news/analyze?symbol=TVSMOTOR&days=7")
        assert resp_get.status_code == 200
        data_get = resp_get.json()
        assert data_get["symbol"] == "TVSMOTOR"
        assert "sentiment" in data_get

