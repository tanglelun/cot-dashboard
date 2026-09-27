"""Validate daily stock downloads against the last completed NYSE session."""

import time

import pandas as pd
import pandas_market_calendars as mcal


class StaleMarketDataError(RuntimeError):
    pass


def expected_market_date(now=None):
    now = pd.Timestamp.now(tz="UTC") if now is None else pd.Timestamp(now)
    if now.tzinfo is None:
        raise ValueError("now must include a timezone")
    schedule = mcal.get_calendar("NYSE").schedule(
        start_date=(now - pd.Timedelta(days=30)).date(), end_date=now.date()
    )
    completed = schedule.loc[schedule["market_close"] <= now]
    if completed.empty:
        raise RuntimeError("No completed market session in the calendar")
    return completed.index[-1].strftime("%Y-%m-%d")


def completed_prices(frame, expected):
    frame = frame.copy()
    # Daily timestamps describe exchange-local dates, not UTC calendar dates.
    frame.index = pd.DatetimeIndex(frame.index).tz_localize(None).normalize()
    frame = frame.loc[frame.index <= pd.Timestamp(expected)]
    return frame.loc[~frame.index.duplicated(keep="last")].sort_index()


def ensure_fresh_prices(symbols, frames, expected, download, min_coverage=0.95,
                        retries=2, retry_delay=15):
    """Retry stale/missing symbols with recent history, retaining older candles.

    A small stale minority is allowed for suspended/illiquid stocks; their own
    dates must remain visible. Broad stale downloads must never be published.
    """
    symbols = sorted(set(symbols))
    result = {symbol: completed_prices(frame, expected)
              for symbol, frame in frames.items() if symbol in symbols}

    def stale_symbols():
        return [symbol for symbol in symbols
                if symbol not in result or result[symbol].empty
                or result[symbol].index.max() < pd.Timestamp(expected)]

    stale = stale_symbols()
    for attempt in range(retries):
        if not stale:
            break
        print(f"Retrying {len(stale)}/{len(symbols)} stale or missing stocks "
              f"for {expected} (attempt {attempt + 1}/{retries})", flush=True)
        time.sleep(retry_delay)
        # A short request can expose the latest bar before the max-history
        # endpoint refreshes. Never replace the complete history with it.
        recent = download(stale, period="1mo", chunk_size=80, retry_missing=False)
        for symbol, frame in recent.items():
            frame = completed_prices(frame, expected)
            previous = result.get(symbol, pd.DataFrame())
            result[symbol] = completed_prices(pd.concat([previous, frame]), expected)
        stale = stale_symbols()

    fresh = len(symbols) - len(stale)
    coverage = fresh / len(symbols) if symbols else 0
    print(f"Fresh stock coverage for {expected}: {fresh}/{len(symbols)}", flush=True)
    if coverage < min_coverage:
        raise StaleMarketDataError(
            f"Only {fresh}/{len(symbols)} stocks have a close for {expected}; "
            f"required {min_coverage:.0%}. Refusing to publish stale data. "
            f"Examples: {', '.join(stale[:10])}"
        )
    if stale:
        print(f"Stocks still stale/missing: {', '.join(stale)}", flush=True)
    return result
