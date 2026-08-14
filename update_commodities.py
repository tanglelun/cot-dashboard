import os
import sys
import json
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
import yfinance as yf


BASE_DIR = Path(__file__).resolve().parent
OUTPUT_FILE = BASE_DIR / "commodities_data.json"
CHART_DATA_DIR = BASE_DIR / "commodities_data"
SUMMARY_PERIOD = "18mo"
HISTORY_PERIOD = "max"

COMMODITIES = [
    {"name": "CRB Index", "symbol": "DBC", "category": "Indexes", "unit": "USD"},
    {"name": "GSCI", "symbol": "^SPGSCI", "category": "Indexes", "unit": "Index Points"},
    {"name": "SSE Commodity Index", "symbol": "000066.SS", "category": "Indexes", "unit": "Index Points"},
    {"name": "World Container Index", "symbol": "BOAT", "category": "Indexes", "unit": "USD"},
    {"name": "Containerized Freight Index", "symbol": "BDRY", "category": "Indexes", "unit": "Points"},
    {"name": "EU Carbon Permits", "symbol": "KRBN", "category": "Indexes", "unit": "USD"},
    {"name": "Wind Energy Index", "symbol": "FAN", "category": "Indexes", "unit": "USD"},
    {"name": "Nuclear Energy Index", "symbol": "URA", "category": "Indexes", "unit": "USD"},
    {"name": "Solar Energy Index", "symbol": "TAN", "category": "Indexes", "unit": "USD"},
    {"name": "Crude Oil WTI", "symbol": "CL=F", "category": "Energy", "unit": "USD/bbl"},
    {"name": "Brent Crude Oil", "symbol": "BZ=F", "category": "Energy", "unit": "USD/bbl"},
    {"name": "Natural Gas", "symbol": "NG=F", "category": "Energy", "unit": "USD/MMBtu"},
    {"name": "Heating Oil", "symbol": "HO=F", "category": "Energy", "unit": "USD/gal"},
    {"name": "RBOB Gasoline", "symbol": "RB=F", "category": "Energy", "unit": "USD/gal"},
    {"name": "Gold", "symbol": "GC=F", "category": "Metals", "unit": "USD/oz"},
    {"name": "Silver", "symbol": "SI=F", "category": "Metals", "unit": "USD/oz"},
    {"name": "Copper", "symbol": "HG=F", "category": "Metals", "unit": "USD/lb"},
    {"name": "Platinum", "symbol": "PL=F", "category": "Metals", "unit": "USD/oz"},
    {"name": "Palladium", "symbol": "PA=F", "category": "Metals", "unit": "USD/oz"},
    {"name": "Corn", "symbol": "ZC=F", "category": "Agriculture", "unit": "USd/bu"},
    {"name": "Soybeans", "symbol": "ZS=F", "category": "Agriculture", "unit": "USd/bu"},
    {"name": "Soybean Meal", "symbol": "ZM=F", "category": "Agriculture", "unit": "USD/ton"},
    {"name": "Soybean Oil", "symbol": "ZL=F", "category": "Agriculture", "unit": "USd/lb"},
    {"name": "Wheat", "symbol": "ZW=F", "category": "Agriculture", "unit": "USd/bu"},
    {"name": "Oats", "symbol": "ZO=F", "category": "Agriculture", "unit": "USd/bu"},
    {"name": "Hard Red Winter Wheat", "symbol": "KE=F", "category": "Agriculture", "unit": "USd/bu"},
    {"name": "Spring Wheat Mpls", "symbol": "MWE=F", "category": "Agriculture", "unit": "USd/bu"},
    {"name": "Canola", "symbol": "RS=F", "category": "Agriculture", "unit": "CAD/mt"},
    {"name": "Rough Rice", "symbol": "ZR=F", "category": "Agriculture", "unit": "USD/cwt"},
    {"name": "Coffee", "symbol": "KC=F", "category": "Agriculture", "unit": "USd/lb"},
    {"name": "Cocoa", "symbol": "CC=F", "category": "Agriculture", "unit": "USD/mt"},
    {"name": "Sugar", "symbol": "SB=F", "category": "Agriculture", "unit": "USd/lb"},
    {"name": "Cotton", "symbol": "CT=F", "category": "Agriculture", "unit": "USd/lb"},
    {"name": "Orange Juice", "symbol": "OJ=F", "category": "Agriculture", "unit": "USd/lb"},
    {"name": "Live Cattle", "symbol": "LE=F", "category": "Livestock", "unit": "USd/lb"},
    {"name": "Lean Hogs", "symbol": "HE=F", "category": "Livestock", "unit": "USd/lb"},
    {"name": "Feeder Cattle", "symbol": "GF=F", "category": "Livestock", "unit": "USd/lb"},
    {"name": "S&P 500 Micro", "symbol": "MES=F", "category": "Indexes", "unit": "Index Points"},
]


def rounded(value, decimals=4):
    if value is None:
        return None
    if not isinstance(value, (int, float)) or pd.isna(value):
        return None
    return round(float(value), decimals)


def safe_symbol(symbol):
    return symbol.replace("=", "-").replace("/", "-").replace(".", "-")


ROLL_GAP_THRESHOLD = 0.08


def back_adjust_frame(frame):
    """Remove futures roll gaps using proportional (ratio) back-adjustment.

    Continuous futures contracts (e.g. ``CL=F``) are simple front-month
    concatenations, so switching to the next contract month creates a large
    price gap. We detect roll days by their outsized overnight open gap and
    scale all earlier OHLC prices so the series is continuous across rolls.
    """
    if frame is None or frame.empty or len(frame) < 2:
        return frame
    frame = frame.sort_index().copy()
    opens = frame["Open"].astype(float)
    highs = frame["High"].astype(float)
    lows = frame["Low"].astype(float)
    closes = frame["Close"].astype(float)

    n = len(frame)
    roll_ratio = {}
    for i in range(1, n):
        prev_close = closes.iloc[i - 1]
        if prev_close is None or pd.isna(prev_close) or prev_close <= 0:
            continue
        open_gap = opens.iloc[i] / prev_close - 1
        if abs(open_gap) >= ROLL_GAP_THRESHOLD:
            ratio = opens.iloc[i] / prev_close
            if ratio > 0:
                roll_ratio[i] = ratio

    if not roll_ratio:
        return frame

    adj = [1.0] * n
    running = 1.0
    for i in range(n - 1, -1, -1):
        adj[i] = running
        if i in roll_ratio:
            running *= roll_ratio[i]

    adj = pd.Series(adj, index=frame.index)
    frame["Open"] = opens * adj
    frame["High"] = highs * adj
    frame["Low"] = lows * adj
    frame["Close"] = closes * adj
    return frame


def series_from_download(data, symbol):
    try:
        if symbol not in data.columns.get_level_values(0):
            return pd.Series(dtype=float)
        frame = data[symbol]
        if "Close" not in frame.columns:
            return pd.Series(dtype=float)
        if symbol.endswith("=F"):
            frame = back_adjust_frame(frame)
        return frame["Close"].dropna()
    except Exception:
        return pd.Series(dtype=float)


def frame_from_download(data, symbol):
    try:
        if symbol not in data.columns.get_level_values(0):
            return pd.DataFrame()
        frame = data[symbol]
        return frame.dropna()
    except Exception:
        return pd.DataFrame()


def pct_change(series, periods):
    try:
        if len(series) <= periods:
            return None
        current = series.iloc[-1]
        base = series.iloc[-periods - 1]
        if base == 0:
            return None
        return (current - base) / base * 100
    except Exception:
        return None


def ytd_change(series):
    try:
        latest = series.iloc[-1]
        year = pd.Timestamp(series.index[-1]).year
        start = pd.Timestamp(year=year, month=1, day=1, tz=series.index.tz)
        before = series[series.index < start]
        base = before.iloc[-1] if not before.empty else series[series.index >= start].iloc[0]
        if base == 0:
            return None
        return (latest - base) / base * 100
    except Exception:
        return None


def history_payload(item, frame, updated):
    if frame.empty:
        return None
    frame = frame.sort_index()
    candles = []
    for timestamp, values in frame.iterrows():
        candle = {
            "time": pd.Timestamp(timestamp).strftime("%Y-%m-%d"),
            "open": rounded(values["Open"], 4),
            "high": rounded(values["High"], 4),
            "low": rounded(values["Low"], 4),
            "close": rounded(values["Close"], 4),
            "volume": int(values["Volume"]) if "Volume" in values and not pd.isna(values["Volume"]) else 0,
        }
        candles.append(candle)
    return {
        "symbol": item["symbol"],
        "safeSymbol": safe_symbol(item["symbol"]),
        "name": item["name"],
        "sector": item.get("category", ""),
        "unit": item.get("unit", ""),
        "marketCap": item.get("unit", ""),
        "updated": updated,
        "prices": candles,
    }


def fallback_history_frame(symbol):
    try:
        data = yf.download(
            symbol,
            period="max",
            interval="1d",
            group_by="ticker",
            auto_adjust=False,
            progress=False,
            timeout=30,
        )
        frame = frame_from_download(data, symbol)
        if frame.empty:
            return frame
        return frame.sort_index()
    except Exception:
        return pd.DataFrame()


def main():
    symbols = [item["symbol"] for item in COMMODITIES]
    summary_data = yf.download(
        symbols,
        period=SUMMARY_PERIOD,
        interval="1d",
        group_by="ticker",
        auto_adjust=False,
        progress=False,
        threads=True,
        timeout=30,
    )

    recent_data = yf.download(
        symbols,
        period="10d",
        interval="1d",
        group_by="ticker",
        auto_adjust=False,
        progress=False,
        threads=True,
        timeout=30,
    )

    rows = []
    for item in COMMODITIES:
        series = series_from_download(summary_data, item["symbol"])
        recent = series_from_download(recent_data, item["symbol"])
        if series.empty:
            continue
        latest = series.iloc[-1]
        previous = recent.iloc[-2] if len(recent) > 1 else None
        day_change = pct_change(recent, 1) if len(recent) > 1 else 0
        week_change = pct_change(recent, 5) if len(recent) > 5 else pct_change(series, 5)
        rows.append(
            {
                "name": item["name"],
                "symbol": item["symbol"],
                "category": item["category"],
                "unit": item["unit"],
                "price": rounded(latest, 4),
                "day": rounded(day_change),
                "week": rounded(week_change),
                "month": rounded(pct_change(series, 21)),
                "ytd": rounded(ytd_change(series)),
                "year": rounded(pct_change(series, 252)),
                "previous": rounded(previous, 4),
                "date": pd.Timestamp(recent.index[-1]).strftime("%Y-%m-%d") if not recent.empty else pd.Timestamp(series.index[-1]).strftime("%Y-%m-%d"),
            }
        )

    if len(rows) < 15:
        raise RuntimeError(f"Only fetched {len(rows)} commodity rows; aborting partial update")

    updated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    payload = {"updated": updated, "commodities": rows}
    OUTPUT_FILE.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    history_data = yf.download(
        symbols,
        period=HISTORY_PERIOD,
        interval="1d",
        group_by="ticker",
        auto_adjust=False,
        progress=False,
        threads=True,
        timeout=60,
    )

    rows_by_symbol = {row["symbol"]: row for row in rows}
    CHART_DATA_DIR.mkdir(parents=True, exist_ok=True)
    history_rows = []
    for item in COMMODITIES:
        frame = frame_from_download(history_data, item["symbol"])
        if frame.empty:
            recent_frame = frame_from_download(summary_data, item["symbol"])
            if not recent_frame.empty:
                frame = recent_frame
            else:
                frame = fallback_history_frame(item["symbol"])
        if frame.empty:
            continue
        if item["symbol"].endswith("=F"):
            frame = back_adjust_frame(frame)
        payload = history_payload(item, frame, updated)
        if payload is None:
            continue
        (CHART_DATA_DIR / f"{safe_symbol(item['symbol'])}.json").write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
        )
        summary = rows_by_symbol.get(item["symbol"], {})
        history_rows.append(
            {
                "name": item["name"],
                "symbol": item["symbol"],
                "safeSymbol": safe_symbol(item["symbol"]),
                "sector": item.get("category", ""),
                "unit": item.get("unit", ""),
                "price": summary.get("price"),
                "d": summary.get("day"),
                "w": summary.get("week"),
                "m": summary.get("month"),
                "y": summary.get("ytd"),
                "year": summary.get("year"),
                "rank": len(history_rows) + 1,
            }
        )

    if len(history_rows) < 15:
        raise RuntimeError(f"Only wrote {len(history_rows)} commodity history files; aborting partial update")

    index_json = {"type": "commodities", "updated": updated, "stocks": history_rows}
    (CHART_DATA_DIR / "index.json").write_text(
        json.dumps(index_json, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )

    print(f"Updated {OUTPUT_FILE} with {len(rows)} rows through {updated}")


if __name__ == "__main__":
    main()
