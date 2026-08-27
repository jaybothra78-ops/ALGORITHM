"""Universe loader for NSE indices, F&O list, and custom watchlists."""
from __future__ import annotations

import csv
import json
import re
from io import StringIO
from pathlib import Path
import requests
from core.config import settings
from core.logging import logger

INDEX_URLS = {
    "Nifty50": "https://archives.nseindia.com/content/indices/ind_nifty50list.csv",
    "IT": "https://archives.nseindia.com/content/indices/ind_niftyitlist.csv",
    "Bank": "https://archives.nseindia.com/content/indices/ind_niftybanklist.csv",
    "Smallcap": "https://archives.nseindia.com/content/indices/ind_niftysmallcap100list.csv",
}
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; AlgoScanner/2.0)", "Accept": "text/csv,*/*"}


def _symbols_from_csv(text: str) -> set[str]:
    reader = csv.DictReader(StringIO(text.lstrip("\ufeff")))
    if not reader.fieldnames or "Symbol" not in reader.fieldnames:
        raise ValueError("NSE response is not a constituent CSV")
    return {row["Symbol"].strip().upper() for row in reader if row.get("Symbol")}


def _load_fallback() -> dict[str, set[str]]:
    if not settings.FALLBACK_PATH.exists():
        return {}
    try:
        values = json.loads(settings.FALLBACK_PATH.read_text(encoding="utf-8"))
        return {name: {str(s).upper() for s in syms} for name, syms in values.items()}
    except Exception:
        return {}


def _load_symbols_from_file(file_path: Path) -> set[str]:
    if not file_path.exists():
        return set()
    symbols = set()
    for line in file_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("//"):
            continue
        if "#" in line:
            line = line.split("#")[0]
        for token in re.split(r"[\s,]+", line):
            token_clean = token.upper().strip()
            token_clean = re.sub(r"1!$", "", token_clean)
            if token_clean.startswith("BSE:") or token_clean.startswith("NSE:"):
                prefix, sym = token_clean.split(":", 1)
                sym = sym.replace(".NS", "").replace(".BO", "").strip()
                if sym == "BAJAJ_AUTO":
                    sym = "BAJAJ-AUTO"
                if sym and re.match(r"^[A-Z0-9\-&]+$", sym):
                    symbols.add(f"{prefix}:{sym}" if prefix == "BSE" else sym)
            else:
                sym = token_clean.replace(".NS", "").replace(".BO", "").strip()
                if sym == "BAJAJ_AUTO":
                    sym = "BAJAJ-AUTO"
                if sym and re.match(r"^[A-Z0-9\-&]+$", sym):
                    symbols.add(sym)
    return symbols


def load_custom_watchlists() -> dict[str, list[str]]:
    """Load user-imported watchlists from JSON file."""
    if not settings.CUSTOM_WATCHLISTS_PATH.exists():
        return {}
    try:
        data = json.loads(settings.CUSTOM_WATCHLISTS_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except Exception as e:
        logger.error(f"Failed to read custom watchlists: {e}")
    return {}


def save_custom_watchlist(name: str, symbols: list[str]) -> None:
    """Save an imported watchlist."""
    watchlists = load_custom_watchlists()
    watchlists[name] = sorted(list(set(symbols)))
    settings.CUSTOM_WATCHLISTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    settings.CUSTOM_WATCHLISTS_PATH.write_text(json.dumps(watchlists, indent=2), encoding="utf-8")


def delete_custom_watchlist(name: str) -> bool:
    """Remove a custom watchlist."""
    watchlists = load_custom_watchlists()
    if name in watchlists:
        del watchlists[name]
        settings.CUSTOM_WATCHLISTS_PATH.write_text(json.dumps(watchlists, indent=2), encoding="utf-8")
        return True
    return False


def import_tradingview_watchlist(url: str, custom_name: str | None = None) -> dict:
    """Fetch a public TradingView watchlist URL and extract all constituent tickers."""
    url = url.strip()
    if not url.startswith("http"):
        raise ValueError("Invalid URL. Must start with http:// or https://")

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    response = requests.get(url, headers=headers, timeout=15)
    response.raise_for_status()
    html_text = response.text

    # Extract title if custom_name is not provided
    name = custom_name.strip() if custom_name and custom_name.strip() else ""
    if not name:
        title_match = re.search(r"<title>(.*?)</title>", html_text, re.IGNORECASE)
        if title_match:
            raw_title = title_match.group(1)
            clean_title = re.sub(r"(\s*—\s*Watchlist.*|\s*—\s*TradingView.*)", "", raw_title).strip()
            if clean_title and clean_title.lower() != "tradingview":
                name = clean_title
        if not name:
            id_match = re.search(r"/watchlists/(\d+)", url)
            name = f"Watchlist_{id_match.group(1)}" if id_match else "Imported Watchlist"

    # Extract tickers
    symbols: list[str] = []
    seen: set[str] = set()

    matches = re.findall(r'"symbol":"(?:NSE:|BSE:)?([A-Za-z0-9_&!]+)"', html_text)
    matches += re.findall(r'(?:NSE|BSE):([A-Za-z0-9_&!]+)', html_text)

    for sym in matches:
        sym_clean = sym.replace("1!", "").strip().upper()
        if sym_clean.startswith("NSE:"):
            sym_clean = sym_clean.replace("NSE:", "")
        if sym_clean == "BAJAJ_AUTO":
            sym_clean = "BAJAJ-AUTO"
        if sym_clean and sym_clean not in seen and len(sym_clean) <= 20:
            seen.add(sym_clean)
            symbols.append(sym_clean)

    if not symbols:
        raise ValueError("Could not find any tickers in the provided TradingView link. Ensure the watchlist is public.")

    save_custom_watchlist(name, symbols)
    logger.info(f"Imported TradingView watchlist '{name}' with {len(symbols)} symbols")

    return {
        "name": name,
        "count": len(symbols),
        "symbols": symbols,
        "url": url,
    }


def load_universe() -> dict[str, set[str]]:
    """Return map of symbol -> set of index/watchlist memberships."""
    fallback = _load_fallback()
    memberships: dict[str, set[str]] = {}

    for index_name, url in INDEX_URLS.items():
        try:
            response = requests.get(url, headers=HEADERS, timeout=10)
            response.raise_for_status()
            symbols = _symbols_from_csv(response.text)
        except Exception:
            symbols = fallback.get(index_name, set())

        for s in symbols:
            memberships.setdefault(s, set()).add(index_name)

    # Load custom Watchlist
    for s in _load_symbols_from_file(settings.WATCHLIST_PATH) | fallback.get("Watchlist", set()):
        memberships.setdefault(s, set()).add("Watchlist")

    # Load F&O List
    for s in _load_symbols_from_file(settings.FNO_PATH) | fallback.get("FNO", set()):
        memberships.setdefault(s, set()).add("FNO")

    # Load dynamically imported custom watchlists
    custom_lists = load_custom_watchlists()
    for list_name, syms in custom_lists.items():
        for s in syms:
            memberships.setdefault(s, set()).add(list_name)

    return memberships

