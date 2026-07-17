import io
import json
import os
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

import pandas as pd
import requests
import yfinance as yf


OUTPUT_FILE = Path("market_pulse_data.json")
MARKET_DATA_DIR = Path("market_data")
INDEXES_DATA_DIR = Path("indexes_data")
MIN_BREADTH_SAMPLE = 200
SP500_CONSTITUENTS_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
SP500_CONSTITUENTS_CACHE = Path("sp500_constituents.json")
BREADTH_LOOKBACK_YEARS = int(os.getenv("MARKET_PULSE_BREADTH_YEARS", "20") or 20)
BREADTH_DOWNLOAD_YEARS = BREADTH_LOOKBACK_YEARS + 2
BREADTH_CHUNK_SIZE = int(os.getenv("MARKET_PULSE_BREADTH_CHUNK_SIZE", "80") or 80)
BREADTH_DOWNLOAD_SLEEP = float(os.getenv("MARKET_PULSE_BREADTH_SLEEP", "0.5") or 0)
CNN_FEAR_GREED_URL = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
CNN_FEAR_GREED_START_DATE = os.getenv("CNN_FEAR_GREED_START_DATE", "2021-02-01")
CNN_FEAR_GREED_MIN_VALID_DATE = os.getenv("CNN_FEAR_GREED_MIN_VALID_DATE", CNN_FEAR_GREED_START_DATE)
CNN_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json,text/plain,*/*",
    "Referer": "https://edition.cnn.com/markets/fear-and-greed",
    "Origin": "https://edition.cnn.com",
}
CNN_COMPONENTS = [
    ("market_momentum_sp500", "Market Momentum"),
    ("stock_price_strength", "Stock Price Strength"),
    ("stock_price_breadth", "Stock Price Breadth"),
    ("put_call_options", "Put/Call Options"),
    ("market_volatility_vix", "Market Volatility"),
    ("junk_bond_demand", "Junk Bond Demand"),
    ("safe_haven_demand", "Safe Haven Demand"),
]

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
    cleaned = []
    for item in points:
        if not item.get("date") or item.get("value") is None or pd.isna(item.get("value")):
            continue
        point = {"date": item["date"], "value": rounded(item["value"])}
        if item.get("sample") is not None and pd.notna(item.get("sample")):
            point["sample"] = int(item["sample"])
        cleaned.append(point)
    return cleaned


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


def merge_points(existing_points, new_points):
    by_date = {}
    for point in clean_points(existing_points or []):
        by_date[point["date"]] = point
    for point in clean_points(new_points or []):
        by_date[point["date"]] = point
    return [by_date[date] for date in sorted(by_date)]


def merge_series(existing_series, new_series):
    existing_by_key = {item.get("key"): item for item in existing_series or [] if item.get("key")}
    merged = []
    seen = set()
    for item in new_series or []:
        key = item.get("key")
        old = existing_by_key.get(key)
        if old:
            points = merge_points(old.get("points"), item.get("points"))
            if key == "cnn_fear_greed" and CNN_FEAR_GREED_MIN_VALID_DATE:
                points = [point for point in points if point["date"] >= CNN_FEAR_GREED_MIN_VALID_DATE]
            item = {**old, **item, "points": points, "latest": points[-1] if points else item.get("latest")}
        merged.append(item)
        seen.add(key)
    for key, item in existing_by_key.items():
        if key not in seen:
            merged.append(item)
    return merged


def merge_existing_payload(payload):
    if not OUTPUT_FILE.exists():
        return payload
    try:
        existing = json.loads(OUTPUT_FILE.read_text())
    except Exception as exc:
        print(f"Could not read existing {OUTPUT_FILE}: {exc}")
        return payload
    payload["series"] = merge_series(existing.get("series"), payload.get("series"))
    return payload


def date_from_cnn_timestamp(value):
    if value is None:
        return None
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).strftime("%Y-%m-%d")
        except ValueError:
            return None
    timestamp = float(value)
    if timestamp > 10_000_000_000:
        timestamp = timestamp / 1000
    return datetime.fromtimestamp(timestamp, timezone.utc).strftime("%Y-%m-%d")


def fetch_cnn_fear_greed():
    try:
        url = f"{CNN_FEAR_GREED_URL}/{CNN_FEAR_GREED_START_DATE}" if CNN_FEAR_GREED_START_DATE else CNN_FEAR_GREED_URL
        response = requests.get(url, headers=CNN_HEADERS, timeout=30)
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        print(f"CNN Fear & Greed failed: {exc}")
        return [], None

    historical = data.get("fear_and_greed_historical") or {}
    points = [
        {"date": date_from_cnn_timestamp(point.get("x")), "value": point.get("y")}
        for point in historical.get("data", [])
        if point.get("x") is not None and point.get("y") is not None
    ]
    series = series_payload(
        {
            "key": "cnn_fear_greed",
            "label": "CNN Fear & Greed Index",
            "category": "Sentiment",
            "unit": "",
            "color": "#00d109",
        },
        points,
        "CNN Fear & Greed Index",
    )

    current = data.get("fear_and_greed") or {}
    snapshot = {
        "key": "cnn_fear_greed",
        "label": "CNN Fear & Greed Index",
        "category": "Sentiment",
        "unit": "",
        "value": rounded(current.get("score"), 2),
        "rating": current.get("rating"),
        "date": date_from_cnn_timestamp(current.get("timestamp")) or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "source": "CNN Fear & Greed Index",
        "previous_close": rounded(current.get("previous_close"), 2),
        "previous_1_week": rounded(current.get("previous_1_week"), 2),
        "previous_1_month": rounded(current.get("previous_1_month"), 2),
        "previous_1_year": rounded(current.get("previous_1_year"), 2),
        "components": [],
    }
    for key, label in CNN_COMPONENTS:
        item = data.get(key) or {}
        snapshot["components"].append(
            {
                "key": key,
                "label": label,
                "score": rounded(item.get("score"), 2),
                "rating": item.get("rating"),
                "date": date_from_cnn_timestamp(item.get("timestamp")),
            }
        )
    return [series], snapshot


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


def normalize_yahoo_symbol(symbol):
    return str(symbol).strip().replace(".", "-")


class ConstituentsTableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_constituents = False
        self.in_cell = False
        self.cell = []
        self.row = []
        self.rows = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "table" and attrs.get("id") == "constituents":
            self.in_constituents = True
        if self.in_constituents and tag in {"td", "th"}:
            self.in_cell = True
            self.cell = []

    def handle_endtag(self, tag):
        if not self.in_constituents:
            return
        if tag in {"td", "th"} and self.in_cell:
            text = " ".join("".join(self.cell).split())
            self.row.append(text)
            self.in_cell = False
        elif tag == "tr":
            if self.row:
                self.rows.append(self.row)
            self.row = []
        elif tag == "table":
            self.in_constituents = False

    def handle_data(self, data):
        if self.in_cell:
            self.cell.append(data)


def parse_sp500_constituents_html(html):
    parser = ConstituentsTableParser()
    parser.feed(html)
    if not parser.rows:
        return []
    headers = parser.rows[0]
    try:
        symbol_index = headers.index("Symbol")
        name_index = headers.index("Security")
    except ValueError:
        return []
    rows = []
    for row in parser.rows[1:]:
        if len(row) <= max(symbol_index, name_index):
            continue
        symbol = normalize_yahoo_symbol(row[symbol_index])
        if not symbol:
            continue
        rows.append({"symbol": symbol, "name": row[name_index]})
    return rows


def load_sp500_constituent_cache():
    if not SP500_CONSTITUENTS_CACHE.exists():
        return []
    try:
        return json.loads(SP500_CONSTITUENTS_CACHE.read_text())
    except Exception:
        return []


def fetch_sp500_constituents():
    try:
        response = requests.get(
            SP500_CONSTITUENTS_URL,
            headers={"User-Agent": CNN_HEADERS["User-Agent"]},
            timeout=30,
        )
        response.raise_for_status()
        rows = parse_sp500_constituents_html(response.text)
        if rows:
            SP500_CONSTITUENTS_CACHE.write_text(
                json.dumps(
                    {
                        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
                        "source": SP500_CONSTITUENTS_URL,
                        "items": rows,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return rows
    except Exception as exc:
        print(f"S&P 500 constituents fetch failed: {exc}")

    cached = load_sp500_constituent_cache()
    if isinstance(cached, dict):
        cached = cached.get("items") or []
    return cached


def close_frame_from_download(data, symbols):
    if data.empty:
        return pd.DataFrame()
    close = pd.DataFrame()
    if isinstance(data.columns, pd.MultiIndex):
        level0 = data.columns.get_level_values(0)
        level1 = data.columns.get_level_values(1)
        if "Close" in level0:
            close = data["Close"].copy()
        elif "Adj Close" in level0:
            close = data["Adj Close"].copy()
        elif "Close" in level1:
            frames = []
            for symbol in symbols:
                if symbol in level0:
                    frame = data[symbol]
                    if "Close" in frame.columns:
                        frames.append(frame["Close"].rename(symbol))
            close = pd.concat(frames, axis=1) if frames else pd.DataFrame()
    elif "Close" in data.columns:
        close = data[["Close"]].copy()
        if len(symbols) == 1:
            close.columns = [symbols[0]]

    if close.empty:
        return close
    close = close.apply(pd.to_numeric, errors="coerce")
    close = close.loc[:, ~close.columns.duplicated()]
    return close.dropna(axis=1, how="all")


def download_sp500_closes(symbols):
    frames = []
    for start in range(0, len(symbols), BREADTH_CHUNK_SIZE):
        chunk = symbols[start : start + BREADTH_CHUNK_SIZE]
        try:
            data = yf.download(
                chunk,
                period=f"{BREADTH_DOWNLOAD_YEARS}y",
                interval="1d",
                group_by="ticker",
                auto_adjust=True,
                progress=False,
                threads=True,
                timeout=60,
            )
            frame = close_frame_from_download(data, chunk)
            if not frame.empty:
                frames.append(frame)
            print(
                f"S&P 500 breadth chunk {start + 1}-{start + len(chunk)}: "
                f"{frame.shape[1] if not frame.empty else 0} symbols"
            )
        except Exception as exc:
            print(f"S&P 500 breadth chunk {start + 1}-{start + len(chunk)} failed: {exc}")
        if BREADTH_DOWNLOAD_SLEEP:
            time.sleep(BREADTH_DOWNLOAD_SLEEP)
    if not frames:
        return pd.DataFrame()
    closes = pd.concat(frames, axis=1).sort_index()
    closes = closes.loc[:, ~closes.columns.duplicated()]
    return closes.dropna(axis=1, how="all")


def breadth_points_from_closes(closes, window):
    if closes.empty:
        return []
    moving_average = closes.rolling(window=window, min_periods=window).mean()
    valid = closes.notna() & moving_average.notna()
    sample = valid.sum(axis=1)
    above = ((closes > moving_average) & valid).sum(axis=1)
    start_date = pd.Timestamp.now(tz=None).normalize() - pd.DateOffset(years=BREADTH_LOOKBACK_YEARS)
    points = []
    for timestamp in closes.index:
        date = pd.Timestamp(timestamp).tz_localize(None)
        current_sample = int(sample.loc[timestamp])
        if date < start_date or current_sample < MIN_BREADTH_SAMPLE:
            continue
        points.append(
            {
                "date": date.strftime("%Y-%m-%d"),
                "value": (float(above.loc[timestamp]) / current_sample) * 100,
                "sample": current_sample,
            }
        )
    return points


def compute_sp500_breadth():
    constituents = fetch_sp500_constituents()
    symbols = [item["symbol"] for item in constituents if item.get("symbol")]
    closes = download_sp500_closes(symbols)
    if closes.empty:
        print("S&P 500 breadth failed: no close data, using local breadth fallback")
        return compute_breadth()
    source = "Current S&P 500 constituents via Wikipedia and Yahoo Finance"
    return [
        series_payload(
            {
                "key": "above_ma50",
                "label": "S&P 500 Stocks above MA50",
                "category": "Breadth",
                "unit": "%",
                "color": "#76d7c4",
            },
            breadth_points_from_closes(closes, 50),
            source,
        ),
        series_payload(
            {
                "key": "above_ma200",
                "label": "S&P 500 Stocks above MA200",
                "category": "Breadth",
                "unit": "%",
                "color": "#ff4d00",
            },
            breadth_points_from_closes(closes, 200),
            source,
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
    cnn_series, cnn_snapshot = fetch_cnn_fear_greed()
    series.extend(cnn_series)
    series.extend(fetch_yahoo_series())
    series.extend(compute_sp500_breadth())
    series.extend(fetch_fred_series())
    snapshots = [fetch_sp500_pe_snapshot()]
    if cnn_snapshot:
        snapshots.insert(0, cnn_snapshot)
    payload = {
        "updated": updated,
        "source": "CNN Fear & Greed, Yahoo Finance, FRED, S&P 500 constituents",
        "notes": [
            "Fear & Greed uses CNN's public JSON data when available, with local calculation as fallback.",
            "Breadth is calculated from current S&P 500 constituents using Yahoo Finance history.",
            "S&P 500 PE is a valuation snapshot when available, not a licensed historical valuation series.",
        ],
        "series": series,
        "snapshots": snapshots,
    }
    payload = merge_existing_payload(payload)
    OUTPUT_FILE.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    print(f"Wrote {OUTPUT_FILE} with {len(series)} series")


if __name__ == "__main__":
    main()
