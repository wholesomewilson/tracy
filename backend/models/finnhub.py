"""Pydantic models for Finnhub API responses."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AnalystRecommendationsSummary(BaseModel):
    """Consolidated analyst recommendation counts (summed across periods)."""

    strongBuy: int = Field(0, description="Strong buy count")
    buy: int = Field(0, description="Buy count")
    hold: int = Field(0, description="Hold count")
    sell: int = Field(0, description="Sell count")
    strongSell: int = Field(0, description="Strong sell count")


class EarningsCalendarEvent(BaseModel):
    """Single earnings calendar entry from Finnhub."""

    date: str | None = Field(
        None, description="Earnings announcement date (YYYY-MM-DD)"
    )
    symbol: str | None = Field(None, description="Stock ticker symbol")
    hour: str | None = Field(
        None,
        description="Time of announcement e.g. amc (after market close), bmo (before market open)",
    )
    quarter: int | None = Field(None, description="Fiscal quarter")
    year: int | None = Field(None, description="Fiscal year")
    eps_actual: float | None = Field(
        None, alias="epsActual", description="Actual EPS reported"
    )
    eps_estimate: float | None = Field(
        None, alias="epsEstimate", description="EPS estimate"
    )
    revenue_actual: float | None = Field(
        None, alias="revenueActual", description="Actual revenue reported"
    )
    revenue_estimate: float | None = Field(
        None, alias="revenueEstimate", description="Revenue estimate"
    )

    class Config:
        populate_by_name = True


class EarningsCalendarResponse(BaseModel):
    """Earnings calendar API response."""

    earnings_calendar: list[EarningsCalendarEvent] = Field(
        ...,
        alias="earningsCalendar",
        description="List of earnings events in the date range",
    )

    class Config:
        populate_by_name = True


class QuoteResponse(BaseModel):
    """Real-time quote from Finnhub. All price fields in USD; t is Unix timestamp."""

    c: float | None = Field(None, description="Current price")
    d: float | None = Field(None, description="Change from previous close")
    dp: float | None = Field(None, description="Percent change from previous close")
    h: float | None = Field(None, description="High price of the day")
    l: float | None = Field(None, description="Low price of the day")
    o: float | None = Field(None, description="Open price of the day")
    pc: float | None = Field(None, description="Previous close price")
    t: int | None = Field(None, description="Timestamp (Unix) of the quote")


class StockCriteriaResponse(BaseModel):
    """
    Wheel stock criteria from yfinance: market cap, sector/industry, profitability,
    balance sheet ratios, revenue/EPS trends, dividends, analyst data, valuation.
    All fields optional; clients apply thresholds.
    """

    symbol: str | None = Field(None, description="Ticker symbol")
    name: str | None = Field(None, description="Company name")
    market_cap: float | None = Field(
        None, description="Market capitalization (e.g. USD)"
    )
    sector: str | None = Field(None, description="Sector")
    industry: str | None = Field(None, description="Industry")
    net_income: float | None = Field(None, description="Net income (latest period)")
    free_cash_flow: float | None = Field(
        None, description="Free cash flow (latest period)"
    )
    eps: float | None = Field(None, description="Earnings per share (latest or TTM)")
    debt_to_equity: float | None = Field(None, description="Debt-to-equity ratio")
    current_ratio: float | None = Field(None, description="Current ratio")
    profit_margins: float | None = Field(
        None, description="Profit margin (0-1 or percent)"
    )
    return_on_equity: float | None = Field(None, description="Return on equity")
    revenue_growth_yoy: float | None = Field(
        None, description="Revenue YoY growth (decimal)"
    )
    eps_growth_yoy: float | None = Field(None, description="EPS YoY growth (decimal)")
    dividend_yield: float | None = Field(
        None, description="Dividend yield (e.g. indicated annual)"
    )
    payout_ratio: float | None = Field(None, description="Payout ratio")
    trailing_pe: float | None = Field(None, description="Trailing P/E ratio")
    forward_pe: float | None = Field(None, description="Forward P/E ratio")
    price_to_book: float | None = Field(None, description="Price to book ratio")
    forward_earnings_estimate: float | None = Field(
        None, description="Forward EPS estimate"
    )
    revenue_estimate: float | None = Field(
        None, description="Revenue estimate from yfinance get_revenue_estimate()"
    )
    revenue_trends: list[dict] | None = Field(
        None, description="Revenue by period [{period, value}]"
    )
    eps_trends: list[dict] | None = Field(
        None, description="EPS by period [{period, value}]"
    )
    dividend_history: str | None = Field(
        None,
        description='Dividend history as string: "YYYY-MM-DD: $0.00,YYYY-MM-DD: $0.00,..."',
    )
    analyst_recommendations: AnalystRecommendationsSummary | None = Field(
        None,
        description="Consolidated analyst counts: strongBuy, buy, hold, sell, strongSell",
    )
    institutional_ownership: str | None = Field(
        None,
        description='Format: Holder,pctHeld,Shares,Value,pctChange then one CSV line per holder (Holder quoted).',
    )


class EarningsWithOptionsItem(BaseModel):
    """One consolidated feed item: earnings event + stock criteria + quote."""

    event: EarningsCalendarEvent = Field(..., description="Earnings calendar event")
    quote: float | None = Field(
        None, description="Current underlying stock price (from yfinance)."
    )
    stock_criteria: StockCriteriaResponse | None = Field(
        None, description="Wheel stock criteria from yfinance."
    )


class EarningsWithOptionsResponse(BaseModel):
    """Feed response: filtered earnings events, each enriched with stock criteria."""

    items: list[EarningsWithOptionsItem] = Field(
        ...,
        description="List of events with stock_criteria per symbol.",
    )
