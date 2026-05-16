"""Wheel stock criteria from yfinance (market cap, financials, ratios, dividends, etc.)."""

from datetime import date, timedelta
import logging

import pandas as pd
import yfinance as yf

MAX_YEARS = 7
logger = logging.getLogger(__name__)


def _safe_float(val) -> float | None:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _safe_str(val) -> str | None:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    s = str(val).strip()
    return s if s else None


def _row_from_df(df: pd.DataFrame | None, *candidates: str) -> float | None:
    """Get latest (first column) value from a DataFrame row; try candidate index names."""
    if df is None or df.empty:
        return None
    index = getattr(df, "index", None)
    if index is None:
        return None
    for name in candidates:
        for idx in index:
            if name in str(idx):
                try:
                    col = df.loc[idx].iloc[0]
                    return _safe_float(col)
                except Exception:
                    pass
    return None


def _series_from_df(df: pd.DataFrame | None, *candidates: str) -> list[dict]:
    """Get time series as list of {period, value} from a DataFrame row."""
    out = []
    if df is None or df.empty:
        return out
    index = getattr(df, "index", None)
    columns = getattr(df, "columns", None)
    if index is None or columns is None:
        return out
    for name in candidates:
        for idx in index:
            if name in str(idx):
                try:
                    row = df.loc[idx]
                    for col in columns:
                        val = _safe_float(row.get(col))
                        if val is not None:
                            period = str(col)[:10] if len(str(col)) >= 10 else str(col)
                            out.append({"period": period, "value": val})
                    return out
                except Exception:
                    pass
    return out


def _dividends_to_list(
    series: pd.Series | None, max_years: int = MAX_YEARS
) -> list[dict]:
    if series is None or series.empty:
        return []
    cutoff = date.today() - timedelta(days=max_years * 365)
    out = []
    for dt, val in series.items():
        try:
            d = dt.date() if hasattr(dt, "date") else date.fromisoformat(str(dt)[:10])
        except (TypeError, ValueError):
            continue
        if d < cutoff:
            continue
        out.append({"date": str(d), "amount": _safe_float(val)})
    return out


def _df_to_list(
    df: pd.DataFrame | None,
    *,
    exclude_keys: tuple[str, ...] = (),
) -> list[dict]:
    """Convert DataFrame to list of dicts (ISO dates for index if datetime).
    exclude_keys: keys to omit from each row (e.g. '_index', 'Date Reported').
    """
    if df is None or df.empty:
        return []
    out = []
    for idx, row in df.iterrows():
        d = {} if "_index" in exclude_keys else {"_index": str(idx)}
        for k, v in row.items():
            key = str(k)[:10] if hasattr(k, "strftime") else str(k)
            if key in exclude_keys:
                continue
            if pd.isna(v):
                d[key] = None
            elif isinstance(v, (int, float)):
                d[key] = v
            else:
                d[key] = str(v)
        out.append(d)
    return out


def _institutional_ownership_to_csv(inst_list: list[dict]) -> str | None:
    """Format institutional holders as CSV string: format line then one line per holder (Holder quoted)."""
    if not inst_list:
        return None
    columns = ("Holder", "pctHeld", "Shares", "Value", "pctChange")
    lines = ["Format: Holder,pctHeld,Shares,Value,pctChange"]
    for row in inst_list:
        cells = []
        for i, key in enumerate(columns):
            v = row.get(key)
            if i == 0:  # Holder: quote and escape internal "
                raw = "" if v is None else str(v)
                cells.append('"' + raw.replace('"', '""') + '"')
            else:
                cells.append("" if v is None else str(v))
        lines.append(",".join(cells))
    return "\n".join(lines)


def _consolidate_analyst_recommendations(rec_list: list[dict]) -> dict | None:
    """Sum strongBuy, buy, hold, sell, strongSell across all period rows. Returns None if empty."""
    if not rec_list:
        return None
    strong_buy = 0
    buy = 0
    hold = 0
    sell = 0
    strong_sell = 0
    for row in rec_list:
        sb = row.get("strongBuy")
        if isinstance(sb, (int, float)) and not pd.isna(sb):
            strong_buy += int(sb)
        b = row.get("buy")
        if isinstance(b, (int, float)) and not pd.isna(b):
            buy += int(b)
        h = row.get("hold")
        if isinstance(h, (int, float)) and not pd.isna(h):
            hold += int(h)
        s = row.get("sell")
        if isinstance(s, (int, float)) and not pd.isna(s):
            sell += int(s)
        ss = row.get("strongSell")
        if isinstance(ss, (int, float)) and not pd.isna(ss):
            strong_sell += int(ss)
    return {
        "strongBuy": strong_buy,
        "buy": buy,
        "hold": hold,
        "sell": sell,
        "strongSell": strong_sell,
    }
    return out


def get_stock_criteria_from_ticker(t, symbol: str) -> dict:
    """
    Build Wheel stock criteria dict from an existing yfinance Ticker instance.
    Returns a dict with market cap, sector/industry, financials, ratios,
    dividend data, analyst recommendations, institutional ownership, valuation, and trends.
    """
    sym = symbol.strip().upper()
    info = getattr(t, "info", None) or {}

    # --- Info-based scalars ---
    market_cap = _safe_float(info.get("marketCap"))
    sector = _safe_str(info.get("sector"))
    industry = _safe_str(info.get("industry"))
    name = _safe_str(info.get("shortName") or info.get("longName"))
    profit_margins = _safe_float(info.get("profitMargins"))
    return_on_equity = _safe_float(info.get("returnOnEquity"))
    dividend_yield = _safe_float(info.get("dividendYield"))
    if dividend_yield is not None and dividend_yield <= 1:
        dividend_yield = dividend_yield  # often 0.005 = 0.5%
    payout_ratio = _safe_float(info.get("payoutRatio"))
    trailing_pe = _safe_float(info.get("trailingPE"))
    forward_pe = _safe_float(info.get("forwardPE"))
    price_to_book = _safe_float(info.get("priceToBook"))
    forward_earnings_estimate = _safe_float(info.get("forwardEps"))

    # --- Financial statements ---
    income_stmt = getattr(t, "income_stmt", None)
    if income_stmt is None or (hasattr(income_stmt, "empty") and income_stmt.empty):
        income_stmt = getattr(t, "financials", None)
    balance_sheet = getattr(t, "balance_sheet", None)
    cashflow = getattr(t, "cashflow", None)

    net_income = _row_from_df(
        income_stmt, "Net Income", "Net Income Common Stockholders"
    )
    free_cash_flow = _row_from_df(cashflow, "Free Cash Flow")
    total_revenue = _row_from_df(income_stmt, "Total Revenue", "Revenue")
    if (
        net_income is not None
        and total_revenue is not None
        and total_revenue != 0
        and profit_margins is None
    ):
        profit_margins = net_income / total_revenue

    eps = _row_from_df(income_stmt, "Basic EPS", "Diluted EPS")
    if eps is None:
        eps = _safe_float(info.get("trailingEps"))

    # --- Balance sheet ratios ---
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

    # --- Trends (time series) ---
    revenue_trends = _series_from_df(income_stmt, "Total Revenue", "Revenue")
    eps_trends = _series_from_df(income_stmt, "Basic EPS", "Diluted EPS")

    # --- YoY growth if we have at least 2 periods ---
    revenue_growth_yoy = None
    if len(revenue_trends) >= 2:
        v0, v1 = revenue_trends[-1]["value"], revenue_trends[-2]["value"]
        if v1 and v1 != 0:
            revenue_growth_yoy = (v0 - v1) / v1
    eps_growth_yoy = None
    if len(eps_trends) >= 2:
        v0, v1 = eps_trends[-1]["value"], eps_trends[-2]["value"]
        if v1 and v1 != 0:
            eps_growth_yoy = (v0 - v1) / v1

    # --- Revenue estimate from Ticker.get_revenue_estimate() ---
    revenue_estimate = None
    try:
        rev_est = getattr(t, "get_revenue_estimate", None)
        if callable(rev_est):
            rev_df = rev_est()
            if rev_df is not None and not rev_df.empty and hasattr(rev_df, "columns"):
                # Index: 0q, +1q, 0y, +1y; columns include 'avg'
                if "avg" in rev_df.columns:
                    revenue_estimate = _safe_float(rev_df["avg"].iloc[0])
                elif len(rev_df.columns):
                    first_col = rev_df.iloc[:, 0]
                    if len(first_col):
                        revenue_estimate = _safe_float(first_col.iloc[0])
    except Exception:
        pass

    # --- Dividends (last 5 years): single string "date: $amount,..." ---
    dividends_series = getattr(t, "dividends", None)
    dividend_list = _dividends_to_list(dividends_series)
    dividend_history = (
        ",".join(
            f"{x['date']}: ${x['amount']:.2f}"
            for x in dividend_list
            if x.get("amount") is not None
        )
        if dividend_list
        else None
    )

    # --- Analyst recommendations (consolidated across periods) ---
    rec_df = getattr(t, "recommendations", None)
    rec_list = (
        _df_to_list(rec_df) if rec_df is not None and not rec_df.empty else []
    )
    analyst_recommendations = _consolidate_analyst_recommendations(rec_list)

    # --- Institutional holders: CSV string with format line, Holder quoted ---
    inst_df = getattr(t, "institutional_holders", None)
    inst_list = (
        _df_to_list(
            inst_df,
            exclude_keys=("_index", "Date Reported"),
        )
        if inst_df is not None and not inst_df.empty
        else []
    )
    institutional_ownership = _institutional_ownership_to_csv(inst_list)

    result = {
        "symbol": sym,
        "name": name,
        "market_cap": market_cap,
        "sector": sector,
        "industry": industry,
        "net_income": net_income,
        "free_cash_flow": free_cash_flow,
        "eps": eps,
        "debt_to_equity": debt_to_equity,
        "current_ratio": current_ratio,
        "profit_margins": profit_margins,
        "return_on_equity": return_on_equity,
        "dividend_yield": dividend_yield,
        "payout_ratio": payout_ratio,
        "trailing_pe": trailing_pe,
        "forward_pe": forward_pe,
        "price_to_book": price_to_book,
        "forward_earnings_estimate": forward_earnings_estimate,
        "revenue_estimate": revenue_estimate,
        "revenue_growth_yoy": revenue_growth_yoy,
        "eps_growth_yoy": eps_growth_yoy,
        "revenue_trends": revenue_trends,
        "eps_trends": eps_trends,
        "dividend_history": dividend_history,
        "analyst_recommendations": analyst_recommendations,
        "institutional_ownership": institutional_ownership,
    }
    return result


def get_stock_criteria(symbol: str) -> dict:
    """
    Fetch Wheel stock criteria for a symbol from yfinance.
    Returns a dict with market cap, sector/industry, financials, ratios,
    dividend data, analyst recommendations, institutional ownership, valuation, and trends.
    """
    sym = symbol.strip().upper()
    t = yf.Ticker(sym)
    return get_stock_criteria_from_ticker(t, sym)
