"""Finnhub API: earnings calendar, quote, and company data."""

import json
from datetime import date, datetime, timedelta
from pathlib import Path

from backend.config import FINNHUB_API_KEY, FINNHUB_EARNINGS_USE_API

# Earnings calendar: load from this file (project root) instead of calling the API.
FINNHUB_EARNINGS_JSON = "finnhub_earnings.json"


def _earnings_json_path() -> Path:
    """Path to finnhub_earnings.json in project root."""
    return Path(__file__).resolve().parent.parent.parent / FINNHUB_EARNINGS_JSON


_client = None


def _get_client():
    """Lazy-init Finnhub client. Returns None if API key is missing."""
    global _client
    if _client is None and FINNHUB_API_KEY:
        import finnhub

        _client = finnhub.Client(api_key=FINNHUB_API_KEY)
    return _client


def _get(symbol: str):
    client = _get_client()
    if client is None:
        raise ValueError("Finnhub is not configured: FINNHUB_API_KEY is missing")
    return client, symbol.strip().upper()


def _load_earnings_calendar_from_json(
    from_date: date,
    to_date: date,
    symbol: str = "",
) -> dict:
    """Load earnings calendar from finnhub_earnings.json (project root). Filter by date range and symbol."""
    path = _earnings_json_path()
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    events = data.get("earningsCalendar") or []
    from_s = from_date.isoformat()
    to_s = to_date.isoformat()
    symbol_upper = (symbol or "").strip().upper()
    filtered = []
    for e in events:
        d = e.get("date")
        if d is None:
            continue
        if not (from_s <= d <= to_s):
            continue
        if symbol_upper and (e.get("symbol") or "").strip().upper() != symbol_upper:
            continue
        filtered.append(e)
    return {"earningsCalendar": filtered}


def get_earnings_calendar(
    from_date: date,
    to_date: date,
    symbol: str = "",
) -> dict:
    """
    Upcoming earnings calendar. When FINNHUB_EARNINGS_USE_API is set (env 1/true/yes),
    calls Finnhub API; otherwise reads from finnhub_earnings.json (project root).
    Returns raw API response dict with key 'earningsCalendar' (list of events).
    """
    if FINNHUB_EARNINGS_USE_API:
        client = _get_client()
        if client is None:
            raise ValueError("Finnhub is not configured: FINNHUB_API_KEY is missing")
        data = client.earnings_calendar(
            _from=from_date.isoformat(),
            to=to_date.isoformat(),
            symbol=symbol,
            international=False,
        )
        path = _earnings_json_path()
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except OSError:
            pass  # best-effort write; do not fail the request
        return data
    return _load_earnings_calendar_from_json(from_date, to_date, symbol)


def get_quote(symbol: str) -> dict:
    """
    Real-time stock quote from Finnhub.
    Returns raw API response dict (c, d, dp, h, l, o, pc, t).
    """
    client, sym = _get(symbol)
    return client.quote(sym)
