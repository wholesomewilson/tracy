"""Application configuration (env and defaults)."""

import os
from dotenv import load_dotenv

load_dotenv()

# Risk-free rate (decimal, e.g. 0.05 = 5%). Used for Black-Scholes Greeks.
RISK_FREE_RATE = float(os.environ.get("RISK_FREE_RATE", "0.037"))

# CORS: comma-separated origins, e.g. "http://localhost:3000,http://localhost:8000"
CORS_ORIGINS = (
    os.environ.get("CORS_ORIGINS", "http://localhost:3000").strip().split(",")
)

# Finnhub API key (required for /finnhub/* endpoints). Get one at https://finnhub.io
FINNHUB_API_KEY = os.environ.get("FINNHUB_API_KEY") or ""

# If set (1, true, yes), get_earnings_calendar calls Finnhub API; otherwise reads from finnhub_earnings.json
FINNHUB_EARNINGS_USE_API = os.environ.get("FINNHUB_EARNINGS_USE_API", "").lower() in ("1", "true", "yes")

# Earnings calendar stock screening (yfinance Wheel filter). See backend/services/earnings_calendar_filter.py
EARNINGS_ALLOWED_EXCHANGES = frozenset(
    x.strip()
    for x in os.environ.get("EARNINGS_ALLOWED_EXCHANGES", "NMS,NYQ").split(",")
    if x.strip()
)
EARNINGS_MIN_MARKET_CAP = float(os.environ.get("EARNINGS_MIN_MARKET_CAP", "10000000000"))
EARNINGS_MAX_DEBT_TO_EQUITY = float(os.environ.get("EARNINGS_MAX_DEBT_TO_EQUITY", "1.5"))
EARNINGS_MIN_CURRENT_RATIO = float(os.environ.get("EARNINGS_MIN_CURRENT_RATIO", "1.1"))
EARNINGS_MIN_ROE = float(os.environ.get("EARNINGS_MIN_ROE", "0.15"))
EARNINGS_MIN_INSTITUTIONAL_OWNERSHIP = float(
    os.environ.get("EARNINGS_MIN_INSTITUTIONAL_OWNERSHIP", "0.30")
)

# Options chain filters (used when building chains for /feed sorting). See backend/services/options_service.py
OPTIONS_MIN_DELTA = float(os.environ.get("OPTIONS_MIN_DELTA", "-0.99"))
