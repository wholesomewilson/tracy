"""Options chain and IV data using yfinance."""

from datetime import date, datetime

import pandas as pd

from backend.config import OPTIONS_MIN_DELTA
from backend.models.options import (
    IVResponse,
    OptionContract,
    OptionChainResponse,
)


def _safe_float(val) -> float | None:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _safe_int(val) -> int | None:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def _premium_for_seller(row: pd.Series) -> float | None:
    """Premium credit for seller: bid, or mid (bid+ask)/2, or last price."""
    last = _safe_float(row.get("lastPrice"))
    return last


def _seller_roi(strike: float, premium: float | None) -> float | None:
    """Seller ROI %: (premium_received / capital_per_contract) * 100; capital = strike * 100."""
    if strike <= 0 or premium is None or premium <= 0:
        return None
    return round((premium / strike) * 100.0, 4)


def _df_row_to_contract(
    row: pd.Series, expiration: date, with_greeks: bool = False
) -> OptionContract:
    strike = _safe_float(row.get("strike")) or 0.0
    premium = _premium_for_seller(row)
    return OptionContract(
        contract_symbol=str(row.get("contractSymbol", "")),
        strike=strike,
        bid=_safe_float(row.get("bid")),
        ask=_safe_float(row.get("ask")),
        last_price=_safe_float(row.get("lastPrice")),
        volume=_safe_int(row.get("volume")),
        open_interest=_safe_int(row.get("openInterest")),
        in_the_money=bool(row.get("inTheMoney", False)),
        expiration=expiration,
        seller_roi=_seller_roi(strike, premium),
    )


def get_underlying_price_from_ticker(t) -> float | None:
    """Current underlying price from an existing yfinance Ticker (info or history)."""
    info = getattr(t, "info", None) or {}
    price = info.get("currentPrice") or info.get("regularMarketPrice")
    if price is not None:
        return float(price)
    hist = getattr(t, "history", None)
    if callable(hist):
        hist = hist(period="1d")
    if hist is not None and not hist.empty and "Close" in hist.columns:
        return float(hist["Close"].iloc[-1])
    return None


def get_expirations_from_ticker(t) -> list[date]:
    """List of option expiration dates from an existing yfinance Ticker."""
    opts = getattr(t, "options", None)
    if not opts:
        return []
    out = []
    for s in opts:
        try:
            out.append(datetime.strptime(s, "%Y-%m-%d").date())
        except ValueError:
            continue
    return sorted(out)


def _passes_chain_filters(
    contract: OptionContract,
    min_seller_roi: float | None,
    min_delta: float | None,
    max_delta: float | None,
) -> bool:
    """True if contract passes optional seller_roi and delta filters."""
    if min_seller_roi is not None:
        sr = getattr(contract, "seller_roi", None)
        if sr is None or sr < min_seller_roi:
            return False
    delta = getattr(contract, "delta", None)
    if min_delta is not None and (delta is None or delta < min_delta):
        return False
    if max_delta is not None and (delta is None or delta > max_delta):
        return False
    return True


def _build_option_chain_response(
    ticker: str,
    puts_df: pd.DataFrame | None,
    calls_df: pd.DataFrame | None,
    underlying: float | None,
    expiration: date,
    include_calls: bool,
    min_seller_roi: float | None,
    iv_metrics: IVResponse | None = None,
    percent_below_quote: float | None = None,
) -> OptionChainResponse:
    """
    Build OptionChainResponse from already-fetched chain DataFrames and quote.
    Applies Greeks (if underlying), min_seller_roi/delta filters, excludes ITM,
    and optionally filters puts to strikes at least percent_below_quote% below quote.
    """
    use_exp = expiration
    if underlying is not None:
        from backend.calculations.greeks import add_greeks_to_chain

        puts_list, calls_list = add_greeks_to_chain(
            puts_df=puts_df,
            calls_df=calls_df if include_calls else None,
            expiration=use_exp,
            spot=underlying,
        )
    else:
        puts_list = []
        if puts_df is not None and not puts_df.empty:
            for _, row in puts_df.iterrows():
                puts_list.append(_df_row_to_contract(row, use_exp))
        calls_list = []
        if include_calls and calls_df is not None and not calls_df.empty:
            for _, row in calls_df.iterrows():
                calls_list.append(_df_row_to_contract(row, use_exp))
        elif not include_calls:
            calls_list = None

    include_greeks = underlying is not None
    use_min_delta = OPTIONS_MIN_DELTA if include_greeks else None
    use_max_delta = None
    if min_seller_roi is not None or use_min_delta is not None or use_max_delta is not None:
        puts_list = [
            c
            for c in puts_list
            if _passes_chain_filters(c, min_seller_roi, use_min_delta, use_max_delta)
        ]
        if calls_list is not None:
            calls_list = [
                c
                for c in calls_list
                if _passes_chain_filters(
                    c, min_seller_roi, use_min_delta, use_max_delta
                )
            ]

    puts_list = [c for c in puts_list if not c.in_the_money]
    if calls_list is not None:
        calls_list = [c for c in calls_list if not c.in_the_money]

    if percent_below_quote is not None and underlying is not None and underlying > 0:
        threshold = underlying * (1.0 - percent_below_quote / 100.0)
        puts_list = [c for c in puts_list if c.strike <= threshold]

    return OptionChainResponse(
        ticker=ticker,
        puts=puts_list,
        calls=calls_list,
        quote=underlying,
        iv=iv_metrics,
    )
