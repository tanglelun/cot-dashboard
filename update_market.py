import html
import json
import re
from pathlib import Path

import pandas as pd
import yfinance as yf


MARKET_FILE = "russell2000_top100.html"
MARKET_DATA_DIR = Path("market_data")
CHART_PERIOD = "2y"
ARRAYS = {
    "r2kRaw": "Russell 2000",
    "spRaw": "S&P 500",
    "ndqRaw": "Nasdaq 100",
}
MAX_ABS_DAILY_CHANGE = 300
SPLIT_FACTORS = (10,)


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


def get_close_frame(symbols):
    yf_symbols = sorted({yahoo_symbol(symbol) for symbol in symbols})
    data = yf.download(
        yf_symbols,
        period=CHART_PERIOD,
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


def get_price_frame_map(symbols):
    unique_symbols = sorted(set(symbols))
    batch_data = get_close_frame(unique_symbols)
    result = {}
    missing = []
    for symbol in unique_symbols:
        frame = price_frame_from_download(batch_data, symbol)
        if frame.empty:
            missing.append(symbol)
        else:
            result[symbol] = frame

    for symbol in missing:
        data = yf.download(
            yahoo_symbol(symbol),
            period=CHART_PERIOD,
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


def latest_price_date(series_map):
    if not series_map:
        raise RuntimeError("No price data was downloaded")
    latest = max(series.index.max() for series in series_map.values() if not series.empty)
    return pd.Timestamp(latest).strftime("%Y-%m-%d")


def write_chart_data(static_data, price_frames, updated_at):
    MARKET_DATA_DIR.mkdir(exist_ok=True)
    rows_by_symbol = {}
    for rows in static_data.values():
        for row in rows:
            rows_by_symbol.setdefault(row["t"], row)

    index_rows = []
    for symbol, row in sorted(rows_by_symbol.items()):
        frame = price_frames.get(symbol, pd.DataFrame())
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
        index_rows.append(
            {
                "symbol": symbol,
                "name": row["n"],
                "sector": row["s"],
                "marketCap": row["c"],
            }
        )

    (MARKET_DATA_DIR / "index.json").write_text(
        json.dumps({"updated": updated_at, "stocks": index_rows}, ensure_ascii=False, separators=(",", ":")),
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
    symbols = [row["t"] for rows in static_data.values() for row in rows]
    price_frames = get_price_frame_map(symbols)
    series_map = {symbol: frame["Close"] for symbol, frame in price_frames.items() if "Close" in frame.columns}

    for name, rows in static_data.items():
        text = replace_array(text, name, update_rows(rows, series_map))

    today = latest_price_date(series_map)
    write_chart_data(static_data, price_frames, today)
    text = ensure_daily_button(text)
    text = re.sub(r"更新于\s*\d{4}-\d{2}-\d{2}", f"更新于 {today}", text)
    text = re.sub(r"·\s*\d{4}-\d{2}-\d{2}更新", f"· {today}更新", text)

    with open(MARKET_FILE, "w", encoding="utf-8") as file:
        file.write(text)

    print(f"Updated {MARKET_FILE} for {today}")


if __name__ == "__main__":
    main()
