"""AI Financial News Scraper and Sentiment Analysis Service."""
from __future__ import annotations

import os
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
import html

from core.logging import logger
from models.news import NewsAnalysisRequest, NewsAnalysisResponse, NewsArticle


class NewsService:
    """Service to fetch real-time financial news and perform AI sentiment synthesis."""

    @classmethod
    def fetch_news(cls, symbol: str, limit: int = 10) -> list[NewsArticle]:
        """Fetch live financial news articles for a given stock ticker."""
        clean_sym = symbol.strip().upper()
        articles: list[NewsArticle] = []

        # 1. Fetch from Google News RSS for Indian Stock Market
        try:
            query = f"{clean_sym} share price NSE stock India"
            encoded_query = urllib.parse.quote_plus(query)
            rss_url = f"https://news.google.com/rss/search?q={encoded_query}&hl=en-IN&gl=IN&ceid=IN:en"

            req = urllib.request.Request(
                rss_url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                xml_content = resp.read()

            root = ET.fromstring(xml_content)
            for item in root.findall("./channel/item")[:limit]:
                title = item.findtext("title", "").strip()
                link = item.findtext("link", "").strip()
                pub_date = item.findtext("pubDate", "").strip()
                desc = item.findtext("description", "").strip()

                # Clean publisher from title (usually formatted as "Title - Publisher Name")
                publisher = "Financial News"
                if " - " in title:
                    parts = title.rsplit(" - ", 1)
                    title = parts[0].strip()
                    publisher = parts[1].strip()

                # Clean HTML tags from description snippet
                clean_desc = re.sub(r"<[^>]+>", "", html.unescape(desc)).strip()
                if clean_desc.startswith(title):
                    clean_desc = clean_desc[len(title):].strip()

                if title and link:
                    articles.append(NewsArticle(
                        title=title,
                        publisher=publisher,
                        link=link,
                        published_at=pub_date,
                        summary=clean_desc[:240] if clean_desc else "Latest corporate and financial developments.",
                    ))
        except Exception as exc:
            logger.warning(f"Google News RSS fetch failed for {clean_sym}: {exc}")

        # 2. Fallback to Yahoo Finance News RSS if needed
        if not articles:
            try:
                yf_ticker = f"{clean_sym}.NS"
                yf_rss = f"https://finance.yahoo.com/rss/headline?s={yf_ticker}"
                req = urllib.request.Request(yf_rss, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    xml_content = resp.read()
                root = ET.fromstring(xml_content)
                for item in root.findall("./channel/item")[:limit]:
                    title = item.findtext("title", "").strip()
                    link = item.findtext("link", "").strip()
                    pub_date = item.findtext("pubDate", "").strip()
                    desc = item.findtext("description", "").strip()
                    clean_desc = re.sub(r"<[^>]+>", "", html.unescape(desc)).strip()
                    if title and link:
                        articles.append(NewsArticle(
                            title=title,
                            publisher="Yahoo Finance",
                            link=link,
                            published_at=pub_date,
                            summary=clean_desc[:240],
                        ))
            except Exception as exc:
                logger.warning(f"Yahoo Finance RSS fetch failed for {clean_sym}: {exc}")

        return articles

    @classmethod
    def analyze_news(cls, request: NewsAnalysisRequest) -> NewsAnalysisResponse:
        """Perform comprehensive AI news analysis and sentiment synthesis."""
        clean_sym = request.symbol.strip().upper()
        articles = cls.fetch_news(clean_sym, limit=12)

        # Check for Anthropic Claude API Key (from request payload or environment)
        anthropic_key = (request.api_key or os.getenv("ANTHROPIC_API_KEY", "")).strip()
        if anthropic_key and articles:
            try:
                return cls._analyze_with_claude(clean_sym, articles, anthropic_key)
            except Exception as exc:
                logger.warning(f"Claude API analysis failed, falling back to deep NLP engine: {exc}")

        # Default institutional financial NLP analysis engine
        return cls._analyze_with_nlp_engine(clean_sym, articles)

    @classmethod
    def _analyze_with_nlp_engine(cls, symbol: str, articles: list[NewsArticle]) -> NewsAnalysisResponse:
        """Rule-based institutional NLP analyzer for financial headlines and snippets."""
        bullish_keywords = {
            "surge", "jump", "growth", "profit", "gain", "rally", "upgrade", "buy", "target", "record",
            "order", "contract", "expansion", "dividend", "revenue", "outperform", "bullish", "acquisition",
            "high", "soar", "deal", "positive", "strong", "beats", "guidance", "boost", "inflows", "q4", "q3", "ebitda"
        }
        bearish_keywords = {
            "fall", "drop", "loss", "decline", "slump", "downgrade", "sell", "plunge", "cut", "weak",
            "probe", "penalty", "fine", "lawsuit", "debt", "default", "underperform", "bearish", "crash",
            "low", "negative", "cautious", "slowdown", "headwind", "margin pressure", "concerns", "investigation"
        }

        bull_count = 0
        bear_count = 0
        extracted_catalysts: list[str] = []
        extracted_risks: list[str] = []

        if not articles:
            return NewsAnalysisResponse(
                symbol=symbol,
                company_name=f"{symbol} Equity",
                sentiment="Neutral",
                sentiment_score=50,
                analysis_engine="Institutional Financial NLP Engine",
                executive_summary=f"No major breaking news headlines detected for {symbol} in the selected window. The stock is currently trading based on standard technical momentum and market-wide sentiment.",
                catalysts=[
                    f"Consolidation pattern forming on {symbol} chart.",
                    "Institutional order flow remaining stable.",
                    "Macro sector stability supporting base valuations."
                ],
                risks=[
                    "Lack of immediate high-impact fundamental catalysts.",
                    "Broader index volatility may influence short-term swings."
                ],
                technical_correlation=f"{symbol} technical indicators (RSI & Moving Averages) should be monitored for key breakout confirmations given the quiet news backdrop.",
                articles=[],
                timestamp=time.time(),
            )

        for art in articles:
            text = f"{art.title} {art.summary}".lower()
            b_matches = sum(1 for kw in bullish_keywords if re.search(r'\b' + re.escape(kw) + r'\b', text))
            r_matches = sum(1 for kw in bearish_keywords if re.search(r'\b' + re.escape(kw) + r'\b', text))

            bull_count += b_matches
            bear_count += r_matches

            if b_matches > r_matches and len(extracted_catalysts) < 4:
                clean_title = art.title.replace("  ", " ").strip()
                extracted_catalysts.append(clean_title)
            elif r_matches > b_matches and len(extracted_risks) < 4:
                clean_title = art.title.replace("  ", " ").strip()
                extracted_risks.append(clean_title)

        # Calculate sentiment score 0 - 100
        total_signals = bull_count + bear_count
        if total_signals == 0:
            score = 52
            verdict = "Neutral"
        else:
            raw_score = 50 + int(((bull_count - bear_count) / total_signals) * 45)
            score = max(10, min(95, raw_score))
            if score >= 60:
                verdict = "Bullish"
            elif score <= 40:
                verdict = "Bearish"
            else:
                verdict = "Neutral"

        # Generate dynamic, stock-specific & headline-aware catalysts and risks
        dyn_catalysts, dyn_risks = cls._generate_intelligent_risks_and_catalysts(
            symbol=symbol,
            articles=articles,
            verdict=verdict,
            bull_count=bull_count,
            bear_count=bear_count
        )
        if not extracted_catalysts:
            extracted_catalysts = dyn_catalysts
        else:
            extracted_catalysts = (extracted_catalysts + dyn_catalysts)[:4]

        if not extracted_risks:
            extracted_risks = dyn_risks
        else:
            extracted_risks = (extracted_risks + dyn_risks)[:3]


        summary = (
            f"Recent news flow for {symbol} indicates a predominantly {verdict.lower()} bias (Sentiment Score: {score}/100) "
            f"across {len(articles)} analyzed media publications. Coverage highlights active developments including '{articles[0].title}' "
            f"with core focus on revenue growth, institutional positioning, and operational execution."
        )

        tech_correlation = (
            f"Given the {verdict.lower()} news backdrop, monitor technical trigger zones on {symbol}. "
            f"If RSI shows oversold conditions or price touches key moving averages, this fundamental narrative provides "
            f"favorable risk-reward confirmation for trend continuation."
        )

        return NewsAnalysisResponse(
            symbol=symbol,
            company_name=f"{symbol} (NSE)",
            sentiment=verdict,
            sentiment_score=score,
            analysis_engine="Institutional Financial NLP Engine",
            executive_summary=summary,
            catalysts=extracted_catalysts[:4],
            risks=extracted_risks[:3],
            technical_correlation=tech_correlation,
            articles=articles,
            timestamp=time.time(),
        )

    @classmethod
    def _generate_intelligent_risks_and_catalysts(
        cls, symbol: str, articles: list[NewsArticle], verdict: str, bull_count: int, bear_count: int
    ) -> tuple[list[str], list[str]]:
        """Intelligently generate dynamic, stock-specific, sector-aware, and headline-driven catalysts and risks."""
        all_titles = [a.title for a in articles]
        combined_text = (" ".join(all_titles) + " " + " ".join([a.summary for a in articles])).lower()

        # 1. Dynamic Headline-Triggered Risks
        risks: list[str] = []
        if any(w in combined_text for w in ("f&o", "derivative", "contracts", "expiry")):
            risks.append(f"Derivative rollover volatility: High open-interest activity in {symbol} F&O contracts introduces heightened speculative beta and rollover volatility around monthly expiry.")
        if any(w in combined_text for w in ("block deal", "stake", "bulk deal", "picks up", "sbi mf", "promoter")):
            risks.append(f"Institutional block absorption: Secondary market digestion of fund equity placements or block deal supply in {symbol} may temporarily cap momentum until liquidity balances.")
        if any(w in combined_text for w in ("lacking", "growth", "optimism", "valuation", "rich", "expensive")):
            risks.append(f"Valuation scrutiny vs organic growth: Elevated forward multiples in {symbol} leave little room for quarterly topline misses if organic expansion moderates.")
        if any(w in combined_text for w in ("margin", "ebitda", "input cost", "expenses", "wage")):
            risks.append(f"Operating margin sensitivity: Escalating operational overhead or input cost inflation testing gross EBITDA margin defense.")
        if any(w in combined_text for w in ("sebi", "rbi", "regulatory", "probe", "penalty", "scrutiny")):
            risks.append(f"Regulatory & compliance tracking: Administrative disclosures and regulatory compliance mandates in {symbol} requiring close governance monitoring.")
        if any(w in combined_text for w in ("all-time high", "record high", "surge", "rally", "52-week")):
            risks.append(f"Overhead technical resistance: Extended price trajectory near cyclical peaks heightens vulnerability to profit-booking on volume deceleration.")
        if any(w in combined_text for w in ("slowdown", "weak", "slump", "curb", "tariffs")):
            risks.append(f"Sector cyclical demand moderation: Macro economic headwinds potentially dampening sequential order intake and channel dispatches.")

        # 2. Sector-Aware Fundamental Risks
        wealth_tickers = {"360ONE", "HDFCAMC", "NAM-INDIA", "CDSL", "BSE", "ANGELONE", "MOTILALOFS", "NUVAMA", "ANANDRATHI", "MCX", "IEX"}
        auto_tickers = {"TVSMOTOR", "TATAMOTORS", "M&M", "BAJAJ-AUTO", "HEROMOTOCO", "MARUTI", "EICHERMOT", "BHARATFORG", "SAMVARDHANA", "SONACOMS"}
        bank_tickers = {"HDFCBANK", "ICICIBANK", "SBIN", "AXISBANK", "KOTAKBANK", "IDFCFIRSTB", "INDUSINDBK", "BANKBARODA", "PNB", "FEDERALBNK", "AUBANK"}
        nbfc_tickers = {"BAJFINANCE", "BAJAJFINSV", "CHOLAFIN", "MUTHOOTFIN", "SHRIRAMFIN", "PFC", "RECLTD", "L&TFH"}
        it_tickers = {"INFY", "TCS", "WIPRO", "HCLTECH", "TECHM", "LTIM", "COFORGE", "PERSISTENT", "MPHASIS"}
        pharma_tickers = {"SUNPHARMA", "CIPLA", "DRREDDY", "DIVISLAB", "LUPIN", "AUROPHARMA", "APOLLOHOSP"}
        retail_tickers = {"TRENT", "TITAN", "DMART", "HINDUNILVR", "ITC", "NESTLEIND", "BRITANNIA", "DABUR", "VBL"}
        metal_tickers = {"TATASTEEL", "JSWSTEEL", "HINDALCO", "VEDL", "JINDALSTEL", "NMDC", "SAIL"}
        energy_tickers = {"RELIANCE", "ONGC", "BPCL", "IOC", "NTPC", "TATAPOWER", "POWERGRID", "GAIL", "ADANIENT"}

        if symbol in wealth_tickers:
            risks.append(f"AUM mark-to-market sensitivity: Broad equity benchmark corrections directly reduce asset-under-management (AUM) base and high-margin incentive fee earnings for {symbol}.")
            risks.append("Regulatory fee ceilings: Scrutiny by SEBI regarding distributor commissions and alternative investment fund (AIF) disclosure norms.")
        elif symbol in auto_tickers:
            risks.append(f"EV capital expenditure: Accelerated transition to electric vehicle architectures in {symbol} testing gross unit economics and component localization.")
            risks.append("Export forex headwinds: Currency liquidity volatility in key developing export corridors impacting overseas two-wheeler and commercial vehicle dispatches.")
        elif symbol in bank_tickers:
            risks.append(f"Cost of deposits & NIM compression: Persistent competition for low-cost retail CASA deposits keeping funding costs elevated for {symbol}.")
            risks.append("Unsecured retail credit cycle: Normalization of credit costs across personal loans and credit card portfolios during tight liquidity.")
        elif symbol in nbfc_tickers:
            risks.append(f"Asset-liability mismatch & borrowing costs: Tight money market liquidity elevating marginal cost of funds for {symbol}.")
            risks.append("Regulatory risk weights: Stricter capital adequacy norms on consumer finance dampening loan book expansion.")
        elif symbol in it_tickers:
            risks.append(f"Discretionary IT budget reprioritization: US and European banking / retail clients delaying discretionary digital transformation projects with {symbol}.")
            risks.append("Traditional contract pricing pressure: Legacy maintenance contracts facing productivity deflation from generative AI tools.")
        elif symbol in pharma_tickers:
            risks.append(f"US FDA inspection outcomes: Regulatory compliance observations or Form 483 citations across formulation manufacturing facilities of {symbol}.")
            risks.append("US generic price erosion: Competitive pricing pressures on oral solid dosage portfolios in international markets.")
        elif symbol in retail_tickers:
            risks.append(f"Same-store-sales growth (SSSG) moderation: High base effects and discretionary spending moderation in urban retail stores of {symbol}.")
            risks.append("New store gestation drag: Accelerated retail footprint expansion temporarily diluting store-level return on capital employed (ROCE).")
        elif symbol in metal_tickers:
            risks.append(f"Global commodity price volatility: Chinese steel export flows and international demand swings pressuring domestic realizations for {symbol}.")
            risks.append("Coking coal cost spikes: Volatility in imported metallurgical coal impacting per-ton operating EBITDA.")
        elif symbol in energy_tickers:
            risks.append(f"Crack spread & refining margin volatility: Fluctuations in international crude benchmarks and petrochemical demand impacting {symbol} O2C earnings.")
            risks.append("Capital-intensive green transition: Substantial long-gestation investments in renewable hydrogen and new energy ecosystems.")
        else:
            risks.append(f"Sectoral valuation ceiling: {symbol} requires sustained quarterly delivery to defend premium multiples against sectoral peers.")
            risks.append(f"Technical support monitorable: Breakdown below key moving average clusters would prompt systematic trailing stop execution in {symbol}.")

        # Deduplicate while preserving order
        seen_r = set()
        clean_risks = []
        for r in risks:
            if r not in seen_r:
                seen_r.add(r)
                clean_risks.append(r)

        # 3. Dynamic Catalysts
        catalysts: list[str] = []
        for art in articles:
            t = art.title.strip()
            if any(w in t.lower() for w in ("record", "rise", "soar", "profit", "gain", "buy", "target", "expansion", "growth", "jump", "order", "stake")):
                if t not in catalysts:
                    catalysts.append(t)

        if symbol in wealth_tickers:
            catalysts.append(f"Financialization of Indian household savings driving structural AUM expansion for {symbol}.")
            catalysts.append("Expanding high-net-worth (HNW) client franchise with robust alternative asset inflows.")
        elif symbol in auto_tickers:
            catalysts.append(f"Premiumization trend and rising consumer preference for higher-margin premium variants in {symbol}.")
            catalysts.append("Aggressive ramp-up in electric vehicle deliveries and export channel re-stocking.")
        elif symbol in bank_tickers:
            catalysts.append(f"Robust asset quality metrics and multi-year low Gross NPA trajectory supporting credit growth in {symbol}.")
            catalysts.append("Strong digital banking adoption driving operating leverage and branch productivity.")
        elif symbol in it_tickers:
            catalysts.append(f"Expanding deal pipeline in cloud modernization, enterprise AI, and cost-takeout programs for {symbol}.")
            catalysts.append("High cash conversion and steady shareholder return through dividend payouts.")
        elif symbol in retail_tickers:
            catalysts.append(f"Rapid retail store network rollout capturing market share from unorganized players for {symbol}.")
            catalysts.append("Strong brand loyalty and superior inventory turnover accelerating unit economics.")
        elif symbol in energy_tickers:
            catalysts.append(f"Integration advantages across telecom, retail, and digital platforms unlocking sustained shareholder value in {symbol}.")
            catalysts.append("Favorable long-term domestic energy transition demand.")
        else:
            catalysts.append(f"Sustained institutional investor accumulation and market share defense in {symbol}.")
            catalysts.append(f"Favorable industry positioning with potential for positive surprise in quarterly operational updates.")

        seen_c = set()
        clean_catalysts = []
        for c in catalysts:
            if c not in seen_c:
                seen_c.add(c)
                clean_catalysts.append(c)

        return clean_catalysts[:4], clean_risks[:3]

    @classmethod
    def _analyze_with_claude(cls, symbol: str, articles: list[NewsArticle], api_key: str) -> NewsAnalysisResponse:

        """Call Anthropic Claude API for deep reasoning and institutional synthesis."""
        import json
        articles_text = "\n".join([f"- Title: {a.title}\n  Publisher: {a.publisher}\n  Date: {a.published_at}\n  Summary: {a.summary}" for a in articles[:8]])

        prompt = f"""You are a senior institutional equity research analyst.
Analyze the following recent news articles for Indian stock ticker {symbol} and generate an institutional equity synthesis.

News Articles:
{articles_text}

Respond ONLY in valid JSON with this exact schema:
{{
  "company_name": "Full official company name",
  "sentiment": "Bullish" | "Bearish" | "Neutral",
  "sentiment_score": integer between 0 and 100,
  "executive_summary": "2-3 concise sentences synthesizing the overall news and business trajectory.",
  "catalysts": ["Key catalyst 1", "Key catalyst 2", "Key catalyst 3"],
  "risks": ["Key risk or headwind 1", "Key risk 2"],
  "technical_correlation": "1-2 sentences on how this news context supports technical setups (e.g. RSI reversals, 200 MA support)."
}}
"""
        req_data = {
            "model": "claude-3-5-sonnet-20241022",
            "max_tokens": 1000,
            "temperature": 0.2,
            "messages": [{"role": "user", "content": prompt}],
        }

        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=json.dumps(req_data).encode("utf-8"),
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
        )

        with urllib.request.urlopen(req, timeout=25) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            content_text = data["content"][0]["text"].strip()
            # Clean possible markdown block
            if content_text.startswith("```json"):
                content_text = content_text[7:]
            if content_text.endswith("```"):
                content_text = content_text[:-3]
            parsed = json.loads(content_text.strip())

            return NewsAnalysisResponse(
                symbol=symbol,
                company_name=parsed.get("company_name", f"{symbol} (NSE)"),
                sentiment=parsed.get("sentiment", "Neutral"),
                sentiment_score=parsed.get("sentiment_score", 50),
                analysis_engine="Claude 3.5 Sonnet (Live AI)",
                executive_summary=parsed.get("executive_summary", ""),
                catalysts=parsed.get("catalysts", []),
                risks=parsed.get("risks", []),
                technical_correlation=parsed.get("technical_correlation", ""),
                articles=articles,
                timestamp=time.time(),
            )

    @classmethod
    def analyze_article_chat(
        cls,
        symbol: str,
        article_title: str,
        article_summary: str = "",
        article_link: str = "",
        user_question: str | None = None,
        api_key: str | None = None,
    ) -> dict[str, Any]:
        """Deep dive breakdown (100-150 words + key bullets) and interactive Q&A for an individual news article."""
        clean_sym = symbol.strip().upper()
        anthropic_key = (api_key or os.getenv("ANTHROPIC_API_KEY", "")).strip()

        # Try Claude 3.5 Sonnet if API key is provided
        if anthropic_key:
            try:
                import json
                prompt = f"""You are a senior institutional equity research analyst covering Indian stock markets ({clean_sym}.NSE).
Analyze this specific news article and provide a concise, high-value breakdown for an equity trader:

Article Title: {article_title}
Article Snippet/Summary: {article_summary}
Article URL: {article_link}
User Specific Question: {user_question or "None (Provide general 100-150w analysis and key bullets)"}

Respond ONLY with valid JSON with this exact structure:
{{
  "short_analysis": "A concise 100 to 150 words institutional analysis of what this development means for {clean_sym}, its business momentum, and trading valuation.",
  "bullet_points": [
    "🎯 Core Catalyst: One clear sentence on the main growth/deal driver.",
    "📊 Financial & Margin Impact: Projected impact on EBITDA, revenue, or market share.",
    "⚠️ Key Risk to Watch: Potential risk, execution hurdle, or valuation headwind.",
    "💡 Trader Takeaway: Actionable trading insight on momentum or price levels."
  ],
  "sentiment": "Bullish" | "Bearish" | "Neutral",
  "confidence_score": integer between 50 and 95,
  "answer": "Direct 1-3 sentence institutional answer to user's question, or null if no question asked."
}}
"""
                req_data = {
                    "model": "claude-3-5-sonnet-20241022",
                    "max_tokens": 800,
                    "temperature": 0.2,
                    "messages": [{"role": "user", "content": prompt}],
                }
                req = urllib.request.Request(
                    "https://api.anthropic.com/v1/messages",
                    data=json.dumps(req_data).encode("utf-8"),
                    headers={
                        "x-api-key": anthropic_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                )
                with urllib.request.urlopen(req, timeout=18) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    content_text = data["content"][0]["text"].strip()
                    if content_text.startswith("```json"):
                        content_text = content_text[7:]
                    if content_text.endswith("```"):
                        content_text = content_text[:-3]
                    parsed = json.loads(content_text.strip())
                    parsed["symbol"] = clean_sym
                    parsed["article_title"] = article_title
                    parsed["engine"] = "Claude 3.5 Sonnet (Live AI)"
                    parsed["user_question"] = user_question
                    return parsed
            except Exception as exc:
                logger.warning(f"Claude article chat analysis failed, using institutional NLP engine: {exc}")

        # Fallback to Built-in Financial Intelligence NLP Kernel
        text = f"{article_title} {article_summary}".lower()
        bullish_keywords = ["surge", "jump", "growth", "profit", "gain", "rally", "upgrade", "buy", "target", "record", "order", "contract", "expansion", "dividend", "revenue", "outperform", "bullish", "acquisition", "high", "soar", "deal", "positive", "strong", "beats", "guidance", "boost", "inflows", "ebitda"]
        bearish_keywords = ["fall", "drop", "loss", "decline", "slump", "downgrade", "sell", "plunge", "cut", "weak", "probe", "penalty", "fine", "lawsuit", "debt", "default", "underperform", "bearish", "crash", "low", "negative", "cautious", "slowdown", "headwind", "margin pressure"]

        b_score = sum(1 for kw in bullish_keywords if kw in text)
        r_score = sum(1 for kw in bearish_keywords if kw in text)

        sentiment = "Bullish" if b_score > r_score else ("Bearish" if r_score > b_score else "Neutral")
        confidence = min(95, max(50, 50 + (b_score - r_score) * 12))

        short_analysis = (
            f"This corporate development for {clean_sym} regarding '{article_title}' indicates notable fundamental movement. "
            f"According to latest media and filing reports, {article_summary or 'operational metrics and order flow trends continue to evolve'}. "
            f"From an institutional valuation standpoint, prevailing business cues skew {sentiment.lower()} (estimated confidence {confidence}%). "
            f"Sustained quarterly delivery on these operating metrics will be critical for defending gross EBITDA margins, supporting return on equity, and commanding premium multiples within the peer group. "
            f"While macroeconomic benchmark volatility and sector-wide input cost fluctuations present near-term monitorables, the headline affirms constructive business direction. "
            f"Traders should monitor immediate price action around prevailing support and resistance bands to evaluate whether market participants have already priced in this announcement or if fresh accumulation volume will follow."
        )


        bullets = [
            f"🎯 Core Development: {article_title}.",
            f"📊 Financial & Growth Impact: Signals a {sentiment.lower()} trajectory with an estimated confidence of {confidence}%.",
            f"⚠️ Key Risk to Watch: Market-wide volatility or profit-taking if expectations were already priced into the stock.",
            f"💡 Trader Takeaway: Monitor 15m/1h candle volume expansion to confirm whether institutional desks are participating in this move."
        ]

        answer = None
        if user_question:
            q_low = user_question.lower()
            if "revenue" in q_low or "financial" in q_low or "impact" in q_low:
                answer = f"The financial impact of '{article_title}' carries a {sentiment.lower()} tone. If sustained, this supports positive top-line growth and operating leverage for {clean_sym}."
            elif "priced in" in q_low:
                answer = f"Initial news reaction typically triggers fast algorithmic positioning. If {clean_sym} has rallied over the last 3-5 sessions, look for consolidation before fresh upward expansion."
            elif "risk" in q_low or "downside" in q_low:
                answer = f"Key risks include overall benchmark index corrections, execution slippage, or rising input costs that could temporarily compress margins."
            elif "tomorrow" in q_low or "open" in q_low or "target" in q_low:
                answer = f"Depending on prevailing market open sentiment, '{article_title}' provides a {sentiment.lower()} catalyst. Watch the opening 15-minute range high/low for breakout confirmation."
            else:
                answer = f"Regarding '{user_question}': Analysis of this announcement indicates a {sentiment.lower()} baseline. Watch volume confirmation and trendline support on the daily chart."

        return {
            "symbol": clean_sym,
            "article_title": article_title,
            "short_analysis": short_analysis,
            "bullet_points": bullets,
            "sentiment": sentiment,
            "confidence_score": confidence,
            "user_question": user_question,
            "answer": answer,
            "engine": "Financial Intelligence NLP Engine",
        }


