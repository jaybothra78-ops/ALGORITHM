# ⚡ ALGORITHM — Stock Screener & Trading Strategy Engine

A high-performance algorithmic stock screener and technical analysis engine built with **FastAPI**, **vectorized NumPy/Pandas math**, and an ultra-clean **minimalist dark financial terminal dashboard**.

Tracks over 350+ Indian equities (Nifty 50, Bank Nifty, Nifty IT, Smallcap 100, F&O Universe, and custom TradingView watchlists).

---

## 🌟 Key Features

- **Dual RSI Strategy Confirmation**:
  - **Dual Oversold (BUY)**: Only triggers when **both** (14) < 30$ and the \text{-}MA(14) < 30$ simultaneously.
  - **Dual Overbought (SELL)**: Only triggers when **both** (14) > 70$ and the \text{-}MA(14) > 70$ simultaneously.
- **Rob Booker Knoxville Divergence**:
  - Vectorized 200-period momentum divergence detection with next-candle confirmation.
- **Multi-Period Lookback Screener**:
  - Real-time screening across **1-Day, 3-Day, 7-Day, and 14-Day** historical lookback windows in sub-15ms from memory cache.
- **🔗 Instant TradingView Watchlist Import**:
  - Paste any public TradingView watchlist link to auto-extract tickers and dynamically add them to your scanning universe.
- **Minimalist Dark UI Terminal**:
  - Built with responsive pure CSS & modern typography, instant symbol search, and direct TradingView chart links.
- **Automated Scheduling**:
  - Integrated APScheduler triggering daily market scans Monday–Friday at 15:45 IST.

---

## 🚀 Quick Start

### 1. Setup Environment
`ash
git clone https://github.com/<your-username>/algorithm.git
cd algorithm

# Create and activate virtual environment
python -m venv .venv
.\.venv\Scripts\activate   # On Windows
source .venv/bin/activate    # On Linux/macOS

# Install dependencies
pip install -r requirements.txt
`

### 2. Run Web Dashboard & API
`ash
uvicorn main:app --host 127.0.0.1 --port 8000
`
Open **[http://127.0.0.1:8000](http://127.0.0.1:8000)** in your browser.

### 3. Run Automated Tests
`ash
pytest tests/ -v
`

---

## 🛠️ API Reference

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| GET | /screener/lookback | Multi-period lookback screener (lookback_days=1,3,7,14, signal_filter, index). |
| GET | /signals/today | Active confirmed signals recorded for today. |
| GET | /signals/history | Historical confirmed trade signals for any date (date=YYYY-MM-DD). |
| POST | /scan/run | Trigger a manual full universe scan (strategy=RSI, RB_KnoxDiv, ALL). |
| POST | /watchlist/import | Import a TradingView public watchlist via URL. |
| GET | /watchlist/list | List all custom imported watchlists. |
| DELETE | /watchlist/{name} | Delete an imported custom watchlist. |

---

## 🏛️ Project Architecture

`
ALGORITHM/
├── api/                # FastAPI routes & request validation
├── config/             # Watchlists, F&O universe & fallback definitions
├── core/               # Configuration settings (Pydantic V2) & structured logging
├── db/                 # Thread-safe SQLite connection pool (WAL mode) & repository
├── frontend/           # Minimalist HTML/CSS/JS dashboard UI
├── models/             # Strongly typed Pydantic models & schemas
├── services/           # Indicators, strategies, market data cache & scanner engine
├── tests/              # Automated Pytest suite
├── main.py             # FastAPI entrypoint with async lifespan
└── scheduler.py        # Background daily scan scheduler
`
