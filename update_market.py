import html
import io
import json
import os
import re
import time
from pathlib import Path

import pandas as pd
import requests
import yfinance as yf


MARKET_FILE = "russell2000_top100.html"
MARKET_DATA_DIR = Path("market_data")
CHART_PERIOD = "max"
SUMMARY_PERIOD = os.getenv("MARKET_SUMMARY_PERIOD", "1y")
MARKET_DOWNLOAD_SLEEP = float(os.getenv("MARKET_DOWNLOAD_SLEEP", "0.8"))
TRACK_ALL_US_STOCKS = os.getenv("TRACK_ALL_US_STOCKS", "1") != "0"
GENERATE_ALL_STOCK_CHARTS = os.getenv("GENERATE_ALL_STOCK_CHARTS", "0") == "1"
NASDAQ_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
OTHER_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"
ARRAYS = {
    "r2kRaw": "Russell 2000",
    "spRaw": "S&P 500",
    "ndqRaw": "Nasdaq 100",
}
MAX_ABS_DAILY_CHANGE = 300
SPLIT_FACTORS = (10,)
EXCHANGE_LABELS = {
    "A": "NYSE American",
    "N": "NYSE",
    "P": "NYSE Arca",
    "Q": "NASDAQ",
    "V": "IEX",
    "Z": "Cboe BZX",
}
NON_COMMON_NAME_RE = re.compile(
    r"\b("
    r"warrant|right|unit|preferred|preference|depositary|depository|"
    r"note|notes|bond|debenture|etf|etn|fund|index|certificate"
    r")\b",
    re.I,
)


def extract_array_source(text, name):
    pattern = rf"const {name} = \[(.*?)\];"
    match = re.search(pattern, text, flags=re.S)
    if not match:
        raise ValueError(f"Cannot find {name} in {MARKET_FILE}")
    return match.group(1)


def parse_static_rows(array_source):
    rows = []
    number = r"[-+eE\d.]+"
    object_pattern = re.compile(
        rf'\{{r:(?P<r>\d+),t:"(?P<t>[^"]+)",n:"(?P<n>[^"]*)",'
        rf'y:(?P<y>{number}),c:"(?P<c>[^"]*)",mn:(?P<mn>{number}),s:"(?P<s>[^"]*)",'
        rf"p:(?P<p>{number}),(?:d:(?P<d>{number}),)?w:(?P<w>{number}),m:(?P<m>{number}),"
        rf"m2:(?P<m2>{number}),q:(?P<q>{number}),h:(?P<h>{number})(?:,split:(?P<split>true|false))?",
        flags=re.S,
    )
    for match in object_pattern.finditer(array_source):
        data = match.groupdict()
        rows.append(
            {
                "r": int(data["r"]),
                "t": html.unescape(data["t"]),
                "n": html.unescape(data["n"]),
                "c": html.unescape(data["c"]),
                "mn": float(data["mn"]),
                "s": html.unescape(data["s"]),
                "p": float(data["p"]),
                "d": float(data["d"] or 0),
                "w": float(data["w"]),
                "m": float(data["m"]),
                "m2": float(data["m2"]),
                "q": float(data["q"]),
                "h": float(data["h"]),
                "y": float(data["y"]),
                "split": data["split"] == "true",
            }
        )
    if not rows:
        raise ValueError("Cannot parse market rows from the page")
    return rows


def yahoo_symbol(symbol):
    return symbol.replace(".", "-")


def pct_change(series, periods):
    if len(series) <= periods:
        return None
    base = series.iloc[-periods - 1]
    latest = series.iloc[-1]
    if pd.isna(base) or base == 0 or pd.isna(latest):
        return None
    return (latest / base - 1) * 100


def ytd_change(series):
    if series.empty:
        return None
    latest = series.iloc[-1]
    current_year = series.index[-1].year
    year_start = pd.Timestamp(year=current_year, month=1, day=1, tz=series.index.tz)
    before_year = series[series.index < year_start]
    if not before_year.empty:
        base = before_year.iloc[-1]
    else:
        in_year = series[series.index >= year_start]
        if in_year.empty:
            return None
        base = in_year.iloc[0]
    if pd.isna(base) or base == 0 or pd.isna(latest):
        return None
    return (latest / base - 1) * 100


def nearest_split_factor(ratio):
    if ratio <= 0:
        return None
    factor = min(SPLIT_FACTORS, key=lambda item: abs(item - ratio))
    if abs(ratio / factor - 1) <= 0.25:
        return factor
    return None


def normalize_split_dislocations(series, symbol):
    adjusted = series.astype(float).copy()
    values = adjusted.dropna()
    if len(values) < 2:
        return adjusted

    for index in range(1, len(values)):
        previous = values.iloc[index - 1]
        current = values.iloc[index]
        if previous == 0 or pd.isna(previous) or pd.isna(current):
            continue

        ratio = current / previous
        if ratio > 4:
            factor = nearest_split_factor(ratio)
            if factor:
                adjusted.loc[values.index[index] :] /= factor
                values = adjusted.dropna()
                print(f"Adjusted split history for {symbol} by /{factor}")
        elif ratio < 0.25:
            factor = nearest_split_factor(1 / ratio)
            if factor:
                adjusted.loc[values.index[index] :] *= factor
                values = adjusted.dropna()
                print(f"Adjusted split history for {symbol} by x{factor}")

    return adjusted


def normalize_price_frame_dislocations(frame, symbol):
    adjusted = frame.copy()
    values = adjusted["Close"].dropna()
    if len(values) < 2:
        return adjusted

    price_columns = [column for column in ("Open", "High", "Low", "Close") if column in adjusted.columns]
    for index in range(1, len(values)):
        previous = values.iloc[index - 1]
        current = values.iloc[index]
        if previous == 0 or pd.isna(previous) or pd.isna(current):
            continue

        ratio = current / previous
        if ratio > 4:
            factor = nearest_split_factor(ratio)
            if factor:
                adjusted.loc[values.index[index] :, price_columns] /= factor
                values = adjusted["Close"].dropna()
        elif ratio < 0.25:
            factor = nearest_split_factor(1 / ratio)
            if factor:
                adjusted.loc[values.index[index] :, price_columns] *= factor
                values = adjusted["Close"].dropna()

    return adjusted


def get_close_frame(symbols, period=CHART_PERIOD):
    yf_symbols = sorted({yahoo_symbol(symbol) for symbol in symbols})
    if not yf_symbols:
        return pd.DataFrame()
    data = yf.download(
        yf_symbols,
        period=period,
        interval="1d",
        auto_adjust=False,
        group_by="ticker",
        progress=False,
        threads=True,
        timeout=30,
    )
    return data


def clean_price_frame(frame):
    columns = [column for column in ("Open", "High", "Low", "Close", "Volume") if column in frame.columns]
    if not {"Open", "High", "Low", "Close"}.issubset(columns):
        return pd.DataFrame()
    result = frame[columns].copy()
    return result.dropna(subset=["Open", "High", "Low", "Close"])


def price_frame_from_download(data, display_symbol):
    symbol = yahoo_symbol(display_symbol)
    if data.empty:
        return pd.DataFrame()
    if isinstance(data.columns, pd.MultiIndex):
        if symbol in data.columns.get_level_values(0):
            return clean_price_frame(data[symbol])
        if "Close" in data.columns.get_level_values(0):
            result = pd.DataFrame(index=data.index)
            for column in ("Open", "High", "Low", "Close", "Volume"):
                if column not in data.columns.get_level_values(0):
                    continue
                values = data[column]
                if isinstance(values, pd.DataFrame):
                    result[column] = values[symbol] if symbol in values.columns else values.iloc[:, 0]
                else:
                    result[column] = values
            return clean_price_frame(result)
        return pd.DataFrame()
    return clean_price_frame(data)


def series_from_download(data, display_symbol):
    symbol = yahoo_symbol(display_symbol)
    if data.empty:
        return pd.Series(dtype=float)
    if isinstance(data.columns, pd.MultiIndex):
        if symbol in data.columns.get_level_values(0):
            frame = data[symbol]
            if "Close" in frame.columns:
                return frame["Close"].dropna()
        if "Close" in data.columns.get_level_values(0):
            close = data["Close"]
            if isinstance(close, pd.DataFrame):
                if symbol in close.columns:
                    return close[symbol].dropna()
                return close.iloc[:, 0].dropna()
            return close.dropna()
        return pd.Series(dtype=float)
    if "Close" in data.columns:
        return data["Close"].dropna()
    return pd.Series(dtype=float)


def get_price_frame_map(symbols, period=CHART_PERIOD, chunk_size=180, retry_missing=True):
    unique_symbols = sorted(set(symbols))
    result = {}
    missing = []
    for start in range(0, len(unique_symbols), chunk_size):
        chunk = unique_symbols[start : start + chunk_size]
        batch_data = get_close_frame(chunk, period=period)
        for symbol in chunk:
            frame = price_frame_from_download(batch_data, symbol)
            if frame.empty:
                missing.append(symbol)
            else:
                result[symbol] = frame
        if MARKET_DOWNLOAD_SLEEP and start + chunk_size < len(unique_symbols):
            time.sleep(MARKET_DOWNLOAD_SLEEP)

    if not retry_missing:
        return result

    for symbol in missing:
        data = yf.download(
            yahoo_symbol(symbol),
            period=period,
            interval="1d",
            auto_adjust=False,
            progress=False,
            timeout=30,
        )
        frame = price_frame_from_download(data, symbol)
        if not frame.empty:
            print(f"Retried {symbol} individually")
            result[symbol] = frame

    return result


def read_pipe_table(text):
    lines = [line for line in text.splitlines() if line and not line.startswith("File Creation Time")]
    return pd.read_csv(io.StringIO("\n".join(lines)), sep="|", keep_default_na=False)


def is_common_stock(symbol, name, is_etf, is_test):
    if str(is_test).strip().upper() == "Y" or str(is_etf).strip().upper() == "Y":
        return False
    if not symbol or "^" in symbol or "/" in symbol or "$" in symbol:
        return False
    if re.search(r"-(W|WS|WT|R|U)$", symbol, re.I):
        return False
    clean_name = str(name or "")
    return not NON_COMMON_NAME_RE.search(clean_name)


def fetch_us_stock_universe():
    rows = []

    nasdaq_text = requests.get(NASDAQ_LISTED_URL, timeout=30).text
    nasdaq_table = read_pipe_table(nasdaq_text)
    for _, item in nasdaq_table.iterrows():
        symbol = str(item.get("Symbol", "")).strip()
        name = str(item.get("Security Name", "")).strip()
        if not is_common_stock(symbol, name, item.get("ETF", ""), item.get("Test Issue", "")):
            continue
        rows.append(
            {
                "t": symbol,
                "n": name,
                "s": "NASDAQ",
                "exchange": "NASDAQ",
                "c": "",
                "mn": 0.0,
            }
        )

    other_text = requests.get(OTHER_LISTED_URL, timeout=30).text
    other_table = read_pipe_table(other_text)
    for _, item in other_table.iterrows():
        symbol = str(item.get("ACT Symbol", "")).strip()
        name = str(item.get("Security Name", "")).strip()
        if not is_common_stock(symbol, name, item.get("ETF", ""), item.get("Test Issue", "")):
            continue
        exchange_code = str(item.get("Exchange", "")).strip()
        exchange = EXCHANGE_LABELS.get(exchange_code, exchange_code or "US")
        rows.append(
            {
                "t": symbol,
                "n": name,
                "s": exchange,
                "exchange": exchange,
                "c": "",
                "mn": 0.0,
            }
        )

    seen = {}
    for row in rows:
        seen.setdefault(row["t"], row)
    return [seen[symbol] for symbol in sorted(seen)]


def metrics_from_frame(symbol, row, frame):
    if frame.empty or "Close" not in frame.columns:
        return None
    frame = normalize_price_frame_dislocations(frame, symbol)
    series = normalize_split_dislocations(frame["Close"].dropna(), symbol)
    if series.empty:
        return None
    latest = float(series.iloc[-1])
    metrics = {
        "d": pct_change(series, 1),
        "w": pct_change(series, 5),
        "m": pct_change(series, 21),
        "m2": pct_change(series, 42),
        "q": pct_change(series, 63),
        "h": pct_change(series, 126),
        "y": ytd_change(series),
    }
    result = {
        "r": row.get("r", 0),
        "t": row["t"],
        "n": row["n"],
        "c": row.get("c", ""),
        "mn": float(row.get("mn", 0) or 0),
        "s": row.get("s", "US"),
        "exchange": row.get("exchange", row.get("s", "US")),
        "p": round(latest, 2),
    }
    for key, value in metrics.items():
        result[key] = round(float(value), 2) if value is not None else 0.0
    return result


def latest_price_date(series_map):
    if not series_map:
        raise RuntimeError("No price data was downloaded")
    latest = max(series.index.max() for series in series_map.values() if not series.empty)
    return pd.Timestamp(latest).strftime("%Y-%m-%d")


def index_row_from_market_row(row):
    return {
        "symbol": row["t"],
        "name": row["n"],
        "sector": row["s"],
        "marketCap": row["c"],
        "marketCapNum": row["mn"],
        "rank": row["r"],
        "price": row["p"],
        "d": row["d"],
        "w": row["w"],
        "m": row["m"],
        "m2": row["m2"],
        "q": row["q"],
        "h": row["h"],
        "y": row["y"],
    }


def write_chart_data(static_data, chart_price_frames, updated_at, universe_rows=None):
    MARKET_DATA_DIR.mkdir(exist_ok=True)
    rows_by_symbol = {}
    for rows in static_data.values():
        for row in rows:
            rows_by_symbol.setdefault(row["t"], row)

    chart_symbols = rows_by_symbol
    if GENERATE_ALL_STOCK_CHARTS and universe_rows:
        chart_symbols = {row["t"]: row for row in universe_rows}

    for symbol, row in sorted(chart_symbols.items()):
        frame = chart_price_frames.get(symbol, pd.DataFrame())
        if frame.empty:
            continue
        frame = normalize_price_frame_dislocations(frame, symbol)
        candles = []
        for timestamp, values in frame.iterrows():
            candle = {
                "time": pd.Timestamp(timestamp).strftime("%Y-%m-%d"),
                "open": round(float(values["Open"]), 4),
                "high": round(float(values["High"]), 4),
                "low": round(float(values["Low"]), 4),
                "close": round(float(values["Close"]), 4),
            }
            if "Volume" in values and not pd.isna(values["Volume"]):
                candle["volume"] = int(values["Volume"])
            candles.append(candle)

        payload = {
            "symbol": symbol,
            "name": row["n"],
            "sector": row["s"],
            "marketCap": row["c"],
            "updated": updated_at,
            "prices": candles,
        }
        (MARKET_DATA_DIR / f"{symbol}.json").write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )

    if universe_rows:
        index_source = universe_rows
    else:
        index_source = [row for symbol, row in sorted(rows_by_symbol.items())]
    index_rows = [
        {
            "symbol": row["t"],
            "name": row["n"],
            "sector": row["s"],
            "exchange": row.get("exchange", row["s"]),
            "marketCap": row.get("c", ""),
            "marketCapNum": row.get("mn", 0),
            "price": row.get("p", 0),
            "d": row.get("d", 0),
            "w": row.get("w", 0),
            "m": row.get("m", 0),
            "m2": row.get("m2", 0),
            "q": row.get("q", 0),
            "h": row.get("h", 0),
            "y": row.get("y", 0),
        }
        for row in index_source
    ]

    groups = {}
    for array_name, label in ARRAYS.items():
        groups[array_name] = {
            "label": label,
            "stocks": [index_row_from_market_row(row) for row in static_data.get(array_name, [])],
        }

    (MARKET_DATA_DIR / "index.json").write_text(
        json.dumps(
            {"updated": updated_at, "stocks": index_rows, "groups": groups},
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )


def update_rows(rows, series_map):
    updated = []
    refreshed_count = 0
    for row in rows:
        series = series_map.get(row["t"], pd.Series(dtype=float))
        if not series.empty:
            refreshed_count += 1
            row["split"] = False
            metric_series = normalize_split_dislocations(series, row["t"])
            latest = series.iloc[-1]
            row["p"] = round(float(latest), 2)
            metrics = {
                "d": pct_change(metric_series, 1),
                "w": pct_change(metric_series, 5),
                "m": pct_change(metric_series, 21),
                "m2": pct_change(metric_series, 42),
                "q": pct_change(metric_series, 63),
                "h": pct_change(metric_series, 126),
                "y": ytd_change(metric_series),
            }
            for key, value in metrics.items():
                if value is not None:
                    row[key] = round(float(value), 2)
        updated.append(row)

    if refreshed_count < max(10, len(rows) * 0.75):
        raise RuntimeError(
            f"Only refreshed {refreshed_count}/{len(rows)} rows. "
            "Aborting so the page is not overwritten with stale or partial data."
        )

    updated.sort(key=lambda item: item["y"], reverse=True)
    for index, row in enumerate(updated, start=1):
        row["r"] = index
    return updated[:100]


def update_universe_rows(rows, price_frames):
    updated = []
    for row in rows:
        symbol = row["t"]
        metrics = metrics_from_frame(symbol, row, price_frames.get(symbol, pd.DataFrame()))
        updated.append(
            metrics
            if metrics
            else {
                "r": row.get("r", 0),
                "t": row["t"],
                "n": row["n"],
                "c": row.get("c", ""),
                "mn": float(row.get("mn", 0) or 0),
                "s": row.get("s", "US"),
                "exchange": row.get("exchange", row.get("s", "US")),
                "p": 0.0,
                "d": 0.0,
                "w": 0.0,
                "m": 0.0,
                "m2": 0.0,
                "q": 0.0,
                "h": 0.0,
                "y": 0.0,
            }
        )
    updated.sort(key=lambda item: item["d"], reverse=True)
    for index, row in enumerate(updated, start=1):
        row["r"] = index
    return updated


def js_string(value):
    return json.dumps(str(value), ensure_ascii=False)


def format_row(row):
    split_flag = ",split:true" if row.get("split") else ""
    return (
        f'  {{r:{row["r"]},t:{js_string(row["t"])},n:{js_string(row["n"])},'
        f'y:{row["y"]:.2f},c:{js_string(row["c"])},mn:{row["mn"]:g},'
        f's:{js_string(row["s"])},p:{row["p"]:.2f},d:{row["d"]:.2f},'
        f'w:{row["w"]:.2f},m:{row["m"]:.2f},m2:{row["m2"]:.2f},'
        f'q:{row["q"]:.2f},h:{row["h"]:.2f}{split_flag}}}'
    )


def replace_array(text, name, rows):
    block = ",\n".join(format_row(row) for row in rows)
    return re.sub(rf"const {name} = \[.*?\];", f"const {name} = [\n{block}\n];", text, flags=re.S)


def ensure_daily_button(text):
    if 'data-t="d"' in text:
        return text
    return text.replace(
        '<button class="cb active" data-t="w">近1周</button>',
        '<button class="cb active" data-t="d">近1日</button>' +
        '<button class="cb" data-t="w">近1周</button>',
    ).replace("let curTime = 'w'", "let curTime = 'd'")


def main():
    with open(MARKET_FILE, "r", encoding="utf-8-sig") as file:
        text = file.read()

    static_data = {name: parse_static_rows(extract_array_source(text, name)) for name in ARRAYS}
    static_symbols = [row["t"] for rows in static_data.values() for row in rows]
    chart_symbols = static_symbols
    universe_rows = None

    if TRACK_ALL_US_STOCKS:
        try:
            raw_universe = fetch_us_stock_universe()
            print(f"Fetched {len(raw_universe)} US listed common stocks")
            summary_frames = get_price_frame_map(
                [row["t"] for row in raw_universe],
                period=SUMMARY_PERIOD,
                chunk_size=80,
                retry_missing=False,
            )
            universe_rows = update_universe_rows(raw_universe, summary_frames)
            print(f"Refreshed {len(universe_rows)} US stock summary rows")
            if GENERATE_ALL_STOCK_CHARTS:
                chart_symbols = [row["t"] for row in universe_rows]
        except Exception as error:
            print(f"Full US stock universe unavailable, using Tops universe only: {error}")

    price_frames = get_price_frame_map(chart_symbols, period=CHART_PERIOD)
    series_map = {symbol: frame["Close"] for symbol, frame in price_frames.items() if "Close" in frame.columns}

    for name, rows in static_data.items():
        text = replace_array(text, name, update_rows(rows, series_map))

    today = latest_price_date(series_map)
    write_chart_data(static_data, price_frames, today, universe_rows=universe_rows)
    text = ensure_daily_button(text)
    text = re.sub(r"更新于\s*\d{4}-\d{2}-\d{2}", f"更新于 {today}", text)
    text = re.sub(r"·\s*\d{4}-\d{2}-\d{2}更新", f"· {today}更新", text)

    with open(MARKET_FILE, "w", encoding="utf-8") as file:
        file.write(text)

    print(f"Updated {MARKET_FILE} for {today}")


if __name__ == "__main__":
    main()
