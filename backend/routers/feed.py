"""Consolidated feed: filtered earnings + option chain + quote + stock criteria per symbol."""

from datetime import date, datetime
import logging

from fastapi import APIRouter, HTTPException, Query

from backend.models.finnhub import (
    EarningsCalendarEvent,
    EarningsWithOptionsItem,
    EarningsWithOptionsResponse,
    StockCriteriaResponse,
)
from backend.services import (
    earnings_calendar_filter,
    finnhub_service,
    yfinance_bundle,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def _parse_event_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


@router.get("", response_model=EarningsWithOptionsResponse)
def get_feed(
    from_date: date | None = Query(
        None, description="Start date (YYYY-MM-DD) for earnings range. Default: today."
    ),
    to_date: date = Query(..., description="End date (YYYY-MM-DD) for earnings range."),
    symbol: str = Query("", description="Filter by symbol. Empty for all."),
    include_calls: bool = Query(
        False, description="Include call contracts in option chain. Default: puts only."
    ),
    seller_roi: float = Query(1.0, description="Minimum seller ROI (%). Default: 1%."),
    percent_below_quote: float = Query(
        10.0,
        ge=0,
        le=100,
        description="Filter option chain puts to strikes at least this % below quote. Default 10%.",
    ),
):
    """
    Consolidated feed: filtered earnings calendar with option chain and stock criteria per symbol.
    Option chain includes quote (current underlying price). Replaces standalone earnings-calendar, chain, and stock-criteria routes.
    """
    if from_date is None:
        from_date = date.today()
    try:
        data = finnhub_service.get_earnings_calendar(
            from_date=from_date,
            to_date=to_date,
            symbol=symbol,
        )
    except ValueError as e:
        if "not configured" in str(e).lower():
            raise HTTPException(
                status_code=503,
                detail="Finnhub is not configured: set FINNHUB_API_KEY.",
            )
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Feed get_earnings_calendar error")
        raise HTTPException(
            status_code=502, detail="Earnings calendar temporarily unavailable."
        )

    if not data or "earningsCalendar" not in data:
        return EarningsWithOptionsResponse(items=[])
    events = data["earningsCalendar"] or []
    if events:
        events = earnings_calendar_filter.filter_earnings_calendar_by_yfinance(events)

    def _max_roi_from_bundle(b):
        if not b or not b.option_chain_response or not b.option_chain_response.puts:
            return -float("inf")
        rois = (
            c.seller_roi
            for c in b.option_chain_response.puts
            if getattr(c, "seller_roi", None) is not None
        )
        return max(rois, default=-float("inf"))

    no_sym_items: list[EarningsWithOptionsItem] = []
    candidates: list[tuple[EarningsCalendarEvent, object]] = []
    for ev in events:
        event_model = EarningsCalendarEvent.model_validate(ev)
        sym = (ev.get("symbol") or "").strip().upper()
        if not sym:
            no_sym_items.append(
                EarningsWithOptionsItem(
                    event=event_model,
                    quote=None,
                    stock_criteria=None,
                )
            )
            continue

        event_date = _parse_event_date(ev.get("date"))

        bundle = yfinance_bundle.get_ticker_bundle(
            sym,
            event_date,
            include_calls=include_calls,
            min_seller_roi=seller_roi,
            percent_below_quote=percent_below_quote,
        )

        candidates.append((event_model, bundle))

    candidates.sort(key=lambda x: _max_roi_from_bundle(x[1]), reverse=True)
    items = [
        EarningsWithOptionsItem(
            event=event_model,
            quote=bundle.quote,
            stock_criteria=StockCriteriaResponse(**bundle.stock_criteria),
        )
        for event_model, bundle in candidates
    ]
    items.extend(no_sym_items)
    return EarningsWithOptionsResponse(items=items)
