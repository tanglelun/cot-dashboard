import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf


OUTPUT_FILE = Path("commodities_data.json")
PERIOD = "18mo"

COMMODITIES = [
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
    {"name": "Rough Rice", "symbol": "ZR=F", "category": "Agriculture", "unit": "USD/cwt"},
    {"name": "Coffee", "symbol": "KC=F", "category": "Agriculture", "unit": "USd/lb"},
    {"name": "Cocoa", "symbol": "CC=F", "category": "Agriculture", "unit": "USD/mt"},
    {"name": "Sugar", "symbol": "SB=F", "category": "Agriculture", "unit": "USd/lb"},
    {"name": "Cotton", "symbol": "CT=F", "category": "Agriculture", "unit": "USd/lb"},
    {"name": "Orange Juice", "symbol": "OJ=F", "category": "Agriculture", "unit": "USd/lb"},
    {"name": "Live Cattle", "symbol": "LE=F", "category": "Livestock", "unit": "USd/lb"},
    {"name": "Lean Hogs", "symbol": "HE=F", "category": "Livestock", "unit": "USd/lb"},
    {"name": "Feeder Cattle", "symbol": "GF=F", "category": "Livestock", "unit": "USd/lb"},
]


def pct_change(series, periods):
    if len(series) <= periods:
        return None
    latest = series.iloc[-1]
    base = series.iloc[-periods - 1]
    if pd.isna(latest) or pd.isna(base) or base == 0:
        return None
    return (latest / base - 1) * 100


def ytd_change(series):
    if series.empty:
        return None
    latest = series.iloc[-1]
    year = series.index[-1].year
    start = pd.Timestamp(year=year, month=1, day=1, tz=series.index.tz)
    before = series[series.index < start]
    base = before.iloc[-1] if not before.empty else series[series.index >= start].iloc[0]
    if pd.isna(latest) or pd.isna(base) or base == 0:
        return None
    return (latest / base - 1) * 100


def rounded(value, digits=2):
    if value is None or pd.isna(value):
        return None
    return round(float(value), digits)


def series_from_download(data, symbol):
    if data.empty:
        return pd.Series(dtype=float)
    if isinstance(data.columns, pd.MultiIndex):
        if symbol not in data.columns.get_level_values(0):
            return pd.Series(dtype=float)
        frame = data[symbol]
        if "Close" not in frame:
            return pd.Series(dtype=float)
        return frame["Close"].dropna()
    if "Close" not in data:
        return pd.Series(dtype=float)
    return data["Close"].dropna()


def main():
    symbols = [item["symbol"] for item in COMMODITIES]
    data = yf.download(
        symbols,
        period=PERIOD,
        interval="1d",
        group_by="ticker",
        auto_adjust=False,
        progress=False,
        threads=True,
        timeout=30,
    )

    rows = []
    for item in COMMODITIES:
        series = series_from_download(data, item["symbol"])
        if series.empty:
            continue
        latest = series.iloc[-1]
        previous = series.iloc[-2] if len(series) > 1 else None
        rows.append(
            {
                "name": item["name"],
                "symbol": item["symbol"],
                "category": item["category"],
                "unit": item["unit"],
                "price": rounded(latest, 4),
                "day": rounded(pct_change(series, 1)),
                "week": rounded(pct_change(series, 5)),
                "month": rounded(pct_change(series, 21)),
                "ytd": rounded(ytd_change(series)),
                "year": rounded(pct_change(series, 252)),
                "previous": rounded(previous, 4),
                "date": pd.Timestamp(series.index[-1]).strftime("%Y-%m-%d"),
            }
        )

    if len(rows) < 15:
        raise RuntimeError(f"Only fetched {len(rows)} commodity rows; aborting partial update")

    rows.sort(key=lambda row: (row["category"], row["name"]))
    payload = {
        "updated": max(row["date"] for row in rows),
        "source": "Yahoo Finance futures quotes via yfinance",
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "commodities": rows,
    }
    OUTPUT_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Updated {OUTPUT_FILE} with {len(rows)} rows through {payload['updated']}")


if __name__ == "__main__":
    main()
