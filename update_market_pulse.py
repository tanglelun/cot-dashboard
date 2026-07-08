import io
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests
import yfinance as yf


OUTPUT_FILE = Path("market_pulse_data.json")
MARKET_DATA_DIR = Path("market_data")
INDEXES_DATA_DIR = Path("indexes_data")
MIN_BREADTH_SAMPLE = 200

YAHOO_SERIES = [
    {
        "key": "us500",
        "label": "S&P 500",
        "category": "Trend",
        "symbol": "^GSPC",
        "unit": "Index Points",
        "color": "#d1d4dc",
    },
    {
        "key": "us100",
        "label": "Nasdaq 100",
        "category": "Trend",
        "symbol": "^NDX",
        "unit": "Index Points",
        "color": "#2962ff",
    },
    {
        "key": "russell2000",
        "label": "Russell 2000",
        "category": "Trend",
        "symbol": "^RUT",
        "unit": "Index Points",
        "color": "#f6a821",
    },
    {
        "key": "vix",
        "label": "VIX",
        "category": "Sentiment",
        "symbol": "^VIX",
        "unit": "Index Points",
        "color": "#ff4d00",
    },
]

FRED_SERIES = [
    {
        "key": "dgs10",
        "label": "US 10Y Yield",
        "category": "Liquidity",
        "series_id": "DGS10",
        "unit": "%",
        "color": "#00b8a9",
    },
    {
        "key": "t10y2y",
        "label": "10Y-2Y Spread",
        "category": "Liquidity",
        "series_id": "T10Y2Y",
        "unit": "%",
        "color": "#8b5cf6",
    },
    {
        "key": "dff",
        "label": "Fed Funds Rate",
        "category": "Liquidity",
        "series_id": "DFF",
        "unit": "%",
        "color": "#ff4d00",
    },
    {
        "key": "hy_spread",
        "label": "High Yield Spread",
        "category": "Liquidity",
        "series_id": "BAMLH0A0HYM2",
        "unit": "%",
        "color": "#ef5350",
    },
    {
        "key": "walcl",
        "label": "Fed Balance Sheet",
        "category": "Liquidity",
        "series_id": "WALCL",
        "unit": "USD Millions",
        "color": "#787b86",
    },
]


def rounded(value, digits=4):
    if value is None or pd.isna(value):
        return None
    return round(float(value), digits)


def clean_points(points):
    return [
        {"date": item["date"], "value": rounded(item["value"])}
        for item in points
        if item.get("date") and item.get("value") is not None and pd.notna(item.get("value"))
    ]


def series_payload(item, points, source):
    points = clean_points(points)
    return {
        "key": item["key"],
        "label": item["label"],
        "category": item["category"],
        "unit": item["unit"],
        "color": item["color"],
        "source": source,
        "latest": points[-1] if points else None,
        "points": points,
    }


def close_from_download(data, symbol):
    if data.empty:
        return pd.Series(dtype=float)
    if isinstance(data.columns, pd.MultiIndex):
        if "Close" in data.columns.get_level_values(0):
            close = data["Close"]
            if isinstance(close, pd.DataFrame):
                if symbol in close.columns:
                    return close[symbol].dropna()
                return close.iloc[:, 0].dropna()
            return close.dropna()
        if symbol in data.columns.get_level_values(0):
            frame = data[symbol]
            if "Close" in frame.columns:
                return frame["Close"].dropna()
    elif "Close" in data.columns:
        return data["Close"].dropna()
    return pd.Series(dtype=float)


def points_from_series(series):
    points = []
    for timestamp, value in series.dropna().items():
        points.append({"date": pd.Timestamp(timestamp).strftime("%Y-%m-%d"), "value": rounded(value)})
    return points


def load_local_index_history(key):
    path = INDEXES_DATA_DIR / f"{key}.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text())
    return [
        {"date": row.get("time"), "value": row.get("close")}
        for row in data.get("prices", [])
        if row.get("time") and row.get("close") is not None
    ]


def fetch_yahoo_series():
    result = []
    symbols = [item["symbol"] for item in YAHOO_SERIES]
    try:
        data = yf.download(
            symbols,
            period="max",
            interval="1d",
            group_by="ticker",
            auto_adjust=False,
            progress=False,
            timeout=40,
        )
    except Exception as exc:
        print(f"Yahoo download failed: {exc}")
        data = pd.DataFrame()

    fallback_keys = {"^GSPC": "GSPC", "^NDX": "NDX", "^RUT": "RUT", "^VIX": "VIX"}
    for item in YAHOO_SERIES:
        series = close_from_download(data, item["symbol"])
        points = points_from_series(series)
        if not points:
            points = load_local_index_history(fallback_keys.get(item["symbol"], item["symbol"].strip("^")))
        result.append(series_payload(item, points, "Yahoo Finance"))
    return result


def fetch_fred_points(series_id):
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    frame = pd.read_csv(io.StringIO(response.text))
    frame[series_id] = pd.to_numeric(frame[series_id].replace(".", pd.NA), errors="coerce")
    return [
        {"date": row["observation_date"], "value": row[series_id]}
        for _, row in frame.dropna(subset=[series_id]).iterrows()
    ]


def fetch_fred_series():
    result = []
    for item in FRED_SERIES:
        try:
            points = fetch_fred_points(item["series_id"])
        except Exception as exc:
            print(f"FRED {item['series_id']} failed: {exc}")
            points = []
        result.append(series_payload(item, points, f"FRED {item['series_id']}"))
    return result


def load_stock_price_file(path):
    try:
        data = json.loads(path.read_text())
    except Exception:
        return pd.Series(dtype=float)
    rows = data.get("prices") or []
    if not rows:
        return pd.Series(dtype=float)
    frame = pd.DataFrame(rows)
    if "time" not in frame.columns or "close" not in frame.columns:
        return pd.Series(dtype=float)
    frame["time"] = pd.to_datetime(frame["time"], errors="coerce")
    frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
    frame = frame.dropna(subset=["time", "close"]).sort_values("time")
    if frame.empty:
        return pd.Series(dtype=float)
    return pd.Series(frame["close"].to_numpy(), index=frame["time"])


def compute_breadth():
    above50 = {}
    total50 = {}
    above200 = {}
    total200 = {}

    for path in MARKET_DATA_DIR.glob("*.json"):
        if path.name == "index.json":
            continue
        closes = load_stock_price_file(path)
        if len(closes) < 50:
            continue
        ma50 = closes.rolling(50).mean()
        ma200 = closes.rolling(200).mean() if len(closes) >= 200 else pd.Series(dtype=float)
        ma50_values = ma50.to_numpy()
        ma200_values = ma200.to_numpy() if len(ma200) else []
        for index, (date, close) in enumerate(zip(closes.index, closes.to_numpy())):
            key = pd.Timestamp(date).strftime("%Y-%m-%d")
            m50 = ma50_values[index]
            if pd.notna(m50):
                total50[key] = total50.get(key, 0) + 1
                if close > m50:
                    above50[key] = above50.get(key, 0) + 1
            if len(ma200_values):
                m200 = ma200_values[index]
                if pd.notna(m200):
                    total200[key] = total200.get(key, 0) + 1
                    if close > m200:
                        above200[key] = above200.get(key, 0) + 1

    def build_points(above, total):
        points = []
        for date in sorted(total):
            sample = total[date]
            if sample < MIN_BREADTH_SAMPLE:
                continue
            points.append(
                {
                    "date": date,
                    "value": round((above.get(date, 0) / sample) * 100, 2),
                    "sample": sample,
                }
            )
        return points

    return [
        series_payload(
            {
                "key": "above_ma50",
                "label": "US Stocks above MA50",
                "category": "Breadth",
                "unit": "%",
                "color": "#00b8a9",
            },
            build_points(above50, total50),
            "Local US stock chart history",
        ),
        series_payload(
            {
                "key": "above_ma200",
                "label": "US Stocks above MA200",
                "category": "Breadth",
                "unit": "%",
                "color": "#2962ff",
            },
            build_points(above200, total200),
            "Local US stock chart history",
        ),
    ]


def fetch_sp500_pe_snapshot():
    for symbol in ("SPY", "^GSPC"):
        try:
            info = yf.Ticker(symbol).info or {}
        except Exception as exc:
            print(f"Valuation snapshot failed for {symbol}: {exc}")
            continue
        value = info.get("trailingPE") or info.get("forwardPE")
        if value:
            return {
                "key": "sp500_pe",
                "label": "S&P 500 PE",
                "category": "Valuation",
                "unit": "x",
                "value": rounded(value, 2),
                "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "source": f"Yahoo Finance {symbol} valuation snapshot",
            }
    return {
        "key": "sp500_pe",
        "label": "S&P 500 PE",
        "category": "Valuation",
        "unit": "x",
        "value": None,
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "source": "Unavailable",
    }


def main():
    updated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    series = []
    series.extend(fetch_yahoo_series())
    series.extend(compute_breadth())
    series.extend(fetch_fred_series())
    payload = {
        "updated": updated,
        "source": "Yahoo Finance, FRED, local US stock chart history",
        "notes": [
            "Breadth is calculated from locally tracked US stock chart history.",
            "S&P 500 PE is a valuation snapshot when available, not a licensed historical valuation series.",
        ],
        "series": series,
        "snapshots": [fetch_sp500_pe_snapshot()],
    }
    OUTPUT_FILE.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    print(f"Wrote {OUTPUT_FILE} with {len(series)} series")


if __name__ == "__main__":
    main()
