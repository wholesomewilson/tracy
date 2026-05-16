# Tracy

*“Tell me the quality companies which offer the best put premium”*

Tracy is a backend API that screens stocks for **The Wheel Strategy** ([what's that?](https://www.moomoo.com/us/learn/detail-options-wheel-strategy-117831-250138079)) around their **earnings calls**.

1. You choose a date range
2. It loads upcoming earnings
3. Keeps only symbols that pass the screening criteria, with live quote and financial profile data, and **ranks results by short-put seller ROI** (using an options chain built in the background).

> **Disclaimer:** Tracy is for research and education only. It is not financial advice. Market data may be delayed or inaccurate. You are responsible for your own trading decisions.

## Prerequisites

- **Python 3.11+** (3.12 recommended)
- Optional: [Finnhub](https://finnhub.io) API key if you fetch earnings live
- A `finnhub_earnings.json` file at the project root when using offline mode (see [Quick start](#quick-start))

Third-party data is subject to each provider’s terms (Finnhub, Yahoo Finance via yfinance).

## What it does

1. **Earnings calendar** — pulls events from Finnhub (API or cached JSON)
2. **Stock screening** — filters to NASDAQ/NYSE names that meet Wheel-oriented rules (market cap, debt, liquidity, profitability, ROE, institutional ownership). Configure via [Screening criteria](#screening-criteria).
3. **Enrichment** — from [yfinance](https://github.com/ranaroussi/yfinance): current **quote** and **stock criteria** (sector, financials, dividends, analyst and institutional data, valuation)
4. **Options ranking** — builds a put-focused option chain (Greeks via Black-Scholes), applies ROI/delta/strike filters, and sorts the feed so higher **seller ROI** names appear first

**Note:** Ranking uses option chains internally. The JSON response includes `event`, `quote`, and `stock_criteria` only — not the full chain.

## Quick start

From the project root:

```bash
cp .env.example .env
# Edit .env: set FINNHUB_API_KEY if FINNHUB_EARNINGS_USE_API=true

python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r backend/requirements.txt
uvicorn backend.main:app --reload
```

- API: `http://localhost:8000`
- Interactive docs: `http://localhost:8000/docs`

### Earnings data: API vs offline

| Mode | Env | What you need |
|------|-----|----------------|
| **Offline** (default) | `FINNHUB_EARNINGS_USE_API=false` | `finnhub_earnings.json` in the project root with a top-level `earningsCalendar` array |
| **Live** | `FINNHUB_EARNINGS_USE_API=true` | Valid `FINNHUB_API_KEY`; the app also writes the response to `finnhub_earnings.json` |

## Example request

```bash
curl "http://localhost:8000/feed?from_date=2026-03-28&to_date=2026-04-04"
```

## API

### `GET /feed`

| Query | Required | Description |
|-------|----------|-------------|
| `to_date` | Yes | End of earnings window (`YYYY-MM-DD`) |
| `from_date` | No | Start date (default: today) |
| `symbol` | No | Limit to one ticker |
| `seller_roi` | No | Min seller ROI % for puts used in ranking (default `1.0`) |
| `percent_below_quote` | No | Only puts at least this % below spot (default `10`) |
| `include_calls` | No | Include calls when building chain (default `false`) |

### Example response

`items` are ordered by best put seller ROI (highest first). `stock_criteria` is abbreviated below; the live response includes full trends, dividend history, and institutional holders.

```json
{
  "items": [
    {
      "event": {
        "date": "2026-04-15",
        "symbol": "FTI",
        "hour": "bmo",
        "quarter": 1,
        "year": 2026,
        "epsActual": null,
        "epsEstimate": 0.5768,
        "revenueActual": null,
        "revenueEstimate": 2527877762.0
      },
      "quote": 70.555,
      "stock_criteria": {
        "symbol": "FTI",
        "name": "TechnipFMC plc",
        "market_cap": 28225169408.0,
        "sector": "Energy",
        "industry": "Oil & Gas Equipment & Services",
        "net_income": 963900000.0,
        "free_cash_flow": 1447400000.0,
        "debt_to_equity": 0.399,
        "current_ratio": 2.54,
        "return_on_equity": 0.296,
        "dividend_yield": 0.29,
        "trailing_pe": 30.68,
        "analyst_recommendations": {
          "strongBuy": 20,
          "buy": 40,
          "hold": 27,
          "sell": 0,
          "strongSell": 0
        }
      }
    }
  ]
}
```

## Configuration

Copy [.env.example](.env.example) to `.env`. All variables are loaded by `backend/config.py`. Restart the server after changes.

### External data sources

| Provider | Data | Config |
|----------|------|--------|
| Finnhub | Earnings calendar | `FINNHUB_API_KEY`, `FINNHUB_EARNINGS_USE_API` |
| yfinance | Quotes, financials, option chains | None |
| Local (Black-Scholes) | Greeks, seller ROI | `RISK_FREE_RATE` |
| Local (`iv_rank`) | IV rank / percentile (V1 proxy) | Uses yfinance history |

Finnhub client notes: [docs/FINNHUB.md](docs/FINNHUB.md).

### Secrets

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `FINNHUB_API_KEY` | For live Finnhub | *(empty)* | API key from [finnhub.io](https://finnhub.io) |

### Screening criteria

Stock filters for `/feed` (`backend/services/earnings_calendar_filter.py`).

| Variable | Default | Description |
|----------|---------|-------------|
| `EARNINGS_ALLOWED_EXCHANGES` | `NMS,NYQ` | yfinance exchange codes (NASDAQ, NYSE) |
| `EARNINGS_MIN_MARKET_CAP` | `10000000000` | Min market cap USD ($10B) |
| `EARNINGS_MAX_DEBT_TO_EQUITY` | `1.5` | Max debt-to-equity |
| `EARNINGS_MIN_CURRENT_RATIO` | `1.1` | Min current ratio |
| `EARNINGS_MIN_ROE` | `0.15` | Min ROE (decimal) |
| `EARNINGS_MIN_INSTITUTIONAL_OWNERSHIP` | `0.30` | Min institutional ownership (decimal) |

### Options filters

Option chain rules for ranking (`backend/services/options_service.py`). Not stock screening.

| Variable | Default | Description |
|----------|---------|-------------|
| `OPTIONS_MIN_DELTA` | `-0.99` | Exclude contracts with delta below this (puts are negative) |

### General

| Variable | Default | Description |
|----------|---------|-------------|
| `RISK_FREE_RATE` | `0.037` | Risk-free rate for Black-Scholes |
| `FINNHUB_EARNINGS_USE_API` | *(off)* | `1` / `true` / `yes` = live Finnhub; else `finnhub_earnings.json` |

## Project layout

| Path | Purpose |
|------|---------|
| `backend/` | FastAPI app (`GET /feed`) |
| `finnhub_earnings.json` | Offline earnings cache |
| `.env.example` | Environment template |
| `docs/FINNHUB.md` | Finnhub library reference |

## Caveats

- Yahoo Finance IV and quotes can be unreliable outside market hours.
- Greeks are model-based and depend on `RISK_FREE_RATE` and chain IV.
- IV Rank / Percentile (V1) use realized vol as a proxy, not historical option IV.

## Contributing

Issues and pull requests are welcome. For larger changes, open an issue first to discuss the approach.

## License

[MIT](LICENSE)
