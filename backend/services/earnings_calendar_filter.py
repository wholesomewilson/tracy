"""Filter Finnhub earnings calendar by yfinance (market cap, exchange, Wheel criteria)."""

import logging

import yfinance as yf

logger = logging.getLogger(__name__)

from backend.config import (
    EARNINGS_ALLOWED_EXCHANGES,
    EARNINGS_MAX_DEBT_TO_EQUITY,
    EARNINGS_MIN_CURRENT_RATIO,
    EARNINGS_MIN_INSTITUTIONAL_OWNERSHIP,
    EARNINGS_MIN_MARKET_CAP,
    EARNINGS_MIN_ROE,
)
from backend.services.stock_criteria_service import _row_from_df, _safe_float


def _symbol_from_event(event: dict) -> str | None:
    """Get symbol from event dict (Finnhub uses 'symbol')."""
    s = event.get("symbol")
    if s is None or not isinstance(s, str):
        return None
    return s.strip().upper() or None


def _wheel_metrics_from_ticker(t):
    """
    Compute Wheel filter metrics from a yfinance Ticker (same sources as stock_criteria_service).
    Returns a dict with debt_to_equity, current_ratio, net_income, free_cash_flow, return_on_equity,
    dividend_yield, institutional_ownership_pct, analyst_buy_pct.
    Missing values are None; conservative filter treats None as fail for required metrics.
    """
    info = getattr(t, "info", None) or {}
    income_stmt = getattr(t, "income_stmt", None)
    if income_stmt is None or (getattr(income_stmt, "empty", True)):
        income_stmt = getattr(t, "financials", None)
    balance_sheet = getattr(t, "balance_sheet", None)
    cashflow = getattr(t, "cashflow", None)

    net_income = _row_from_df(
        income_stmt, "Net Income", "Net Income Common Stockholders"
    )
    free_cash_flow = _row_from_df(cashflow, "Free Cash Flow")

    total_debt = _row_from_df(balance_sheet, "Total Debt", "Long Term Debt")
    total_equity = _row_from_df(
        balance_sheet,
        "Total Stockholder Equity",
        "Stockholders Equity",
        "Total Equity Gross Minority Interest",
    )
    debt_to_equity = None
    if total_debt is not None and total_equity is not None and total_equity != 0:
        debt_to_equity = total_debt / total_equity

    current_assets = _row_from_df(balance_sheet, "Current Assets")
    current_liabilities = _row_from_df(balance_sheet, "Current Liabilities")
    current_ratio = None
    if (
        current_assets is not None
        and current_liabilities is not None
        and current_liabilities != 0
    ):
        current_ratio = current_assets / current_liabilities

    return_on_equity = _safe_float(info.get("returnOnEquity"))
    dividend_yield = _safe_float(info.get("dividendYield"))

    institutional_ownership_pct = None
    inst_df = getattr(t, "institutional_holders", None)
    if inst_df is not None and not getattr(inst_df, "empty", True):
        cols = getattr(inst_df, "columns", None)
        if cols is not None:
            for pct_col in ("pctHeld", "% Out", "Percent", "% Shares"):
                if pct_col not in getattr(inst_df, "columns", []):
                    continue
                try:
                    ser = inst_df[pct_col]
                    total = ser.apply(
                        lambda x: (
                            float(str(x).replace("%", "").strip())
                            if x is not None
                            else 0
                        )
                    ).sum()
                    if total > 1:
                        total = total / 100.0
                    institutional_ownership_pct = total
                except Exception:
                    pass
                break

    analyst_buy_pct = None
    rec_df = getattr(t, "recommendations", None)
    if rec_df is not None and not getattr(rec_df, "empty", True):
        grade_col = None
        for c in ("To Grade", "Grade", "Recommendation"):
            if c in rec_df.columns:
                grade_col = c
                break
        if grade_col is not None:
            grades = (
                rec_df[grade_col]
                .astype(str)
                .str.strip()
                .str.lower()
                .str.replace(" ", "_", regex=False)
            )
            total = len(grades)
            buy_strong = grades.isin(
                ("buy", "strong buy", "strong_buy", "outperform")
            ).sum()
            if total > 0:
                analyst_buy_pct = buy_strong / total

    return {
        "debt_to_equity": debt_to_equity,
        "current_ratio": current_ratio,
        "net_income": net_income,
        "free_cash_flow": free_cash_flow,
        "return_on_equity": return_on_equity,
        "dividend_yield": dividend_yield,
        "institutional_ownership_pct": institutional_ownership_pct,
        "analyst_buy_pct": analyst_buy_pct,
    }


def _passes_wheel_filters(m: dict) -> bool:
    """
    True if all Wheel criteria pass. Missing required metrics cause fail (conservative).
    """
    if (
        m.get("debt_to_equity") is not None
        and m["debt_to_equity"] > EARNINGS_MAX_DEBT_TO_EQUITY
    ):
        return False
    if m.get("current_ratio") is None or m["current_ratio"] < EARNINGS_MIN_CURRENT_RATIO:
        return False
    fcf = m.get("free_cash_flow")
    ni = m.get("net_income")
    if not ((fcf is not None and fcf > 0) or (ni is not None and ni > 0)):
        return False

    if m.get("return_on_equity") is None or m["return_on_equity"] <= EARNINGS_MIN_ROE:
        return False
    if (
        m.get("institutional_ownership_pct") is None
        or m["institutional_ownership_pct"] < EARNINGS_MIN_INSTITUTIONAL_OWNERSHIP
    ):
        return False
    return True


def filter_earnings_calendar_by_yfinance(events: list[dict]) -> list[dict]:
    """
    Filter earnings calendar events using yfinance.
    Keeps only events whose symbol has:
    - market cap >= EARNINGS_MIN_MARKET_CAP and exchange in EARNINGS_ALLOWED_EXCHANGES,
    - and passes Wheel criteria (debt-to-equity, current ratio, positive FCF or net income,
      ROE, institutional ownership). Thresholds from env (see backend/config.py).
      Missing required metrics exclude the symbol (conservative).
    """
    if not events:
        return []

    unique_symbols = set()
    for e in events:
        sym = _symbol_from_event(e)
        if sym:
            unique_symbols.add(sym)

    if not unique_symbols:
        return []

    symbols_str = " ".join(sorted(unique_symbols))
    tickers = yf.Tickers(symbols_str)

    passing_symbols = set()
    metrics_by_symbol = {}
    for sym in unique_symbols:
        try:
            t = tickers.tickers.get(sym)
            if t is None:
                continue
            info = getattr(t, "info", None) or {}
            cap = info.get("marketCap")
            try:
                cap_f = float(cap) if cap is not None else None
            except (TypeError, ValueError):
                cap_f = None
            if cap_f is None or cap_f < EARNINGS_MIN_MARKET_CAP:
                continue
            ex = info.get("exchange")
            if ex not in EARNINGS_ALLOWED_EXCHANGES:
                continue
            try:
                metrics = _wheel_metrics_from_ticker(t)
            except Exception:
                continue
            metrics_by_symbol[sym] = {"symbol": sym, **metrics}
            if _passes_wheel_filters(metrics):
                passing_symbols.add(sym)
        except Exception:
            continue

    return [e for e in events if _symbol_from_event(e) in passing_symbols]
