import html
import json
import re
import pandas as pd
import yfinance as yf


MARKET_FILE = "russell2000_top100.html"
ARRAYS = {
    "r2kRaw": "Russell 2000",
    "spRaw": "S&P 500",
    "ndqRaw": "Nasdaq 100",
}
MAX_ABS_DAILY_CHANGE = 300


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
        rf"m2:(?P<m2>{number}),q:(?P<q>{number}),h:(?P<h>{number})",
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


def has_price_dislocation(series):
    changes = series.pct_change().dropna().abs() * 100
    if changes.empty:
        return False
    return changes.max() > MAX_ABS_DAILY_CHANGE


def get_close_frame(symbols):
    yf_symbols = sorted({yahoo_symbol(symbol) for symbol in symbols})
    data = yf.download(
        yf_symbols,
        period="1y",
        interval="1d",
        auto_adjust=False,
        group_by="ticker",
        progress=False,
        threads=True,
        timeout=30,
    )
    return data


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


def get_close_series_map(symbols):
    unique_symbols = sorted(set(symbols))
    batch_data = get_close_frame(unique_symbols)
    result = {}
    missing = []
    for symbol in unique_symbols:
        series = series_from_download(batch_data, symbol)
        if series.empty:
            missing.append(symbol)
        else:
            result[symbol] = series

    for symbol in missing:
        data = yf.download(
            yahoo_symbol(symbol),
            period="1y",
            interval="1d",
            auto_adjust=False,
            progress=False,
            timeout=30,
        )
        series = series_from_download(data, symbol)
        if not series.empty:
            print(f"Retried {symbol} individually")
            result[symbol] = series

    return result


def latest_price_date(series_map):
    if not series_map:
        raise RuntimeError("No price data was downloaded")
    latest = max(series.index.max() for series in series_map.values() if not series.empty)
    return pd.Timestamp(latest).strftime("%Y-%m-%d")


def update_rows(rows, series_map):
    updated = []
    refreshed_count = 0
    for row in rows:
        series = series_map.get(row["t"], pd.Series(dtype=float))
        if not series.empty:
            refreshed_count += 1
            if has_price_dislocation(series):
                row["p"] = 0.0
                for key in ("d", "w", "m", "m2", "q", "h", "y"):
                    row[key] = 0.0
                print(f"Skipped anomalous price history for {row['t']}")
                updated.append(row)
                continue

            latest = series.iloc[-1]
            row["p"] = round(float(latest), 2)
            metrics = {
                "d": pct_change(series, 1),
                "w": pct_change(series, 5),
                "m": pct_change(series, 21),
                "m2": pct_change(series, 42),
                "q": pct_change(series, 63),
                "h": pct_change(series, 126),
                "y": ytd_change(series),
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
    return (
        f'  {{r:{row["r"]},t:{js_string(row["t"])},n:{js_string(row["n"])},'
        f'y:{row["y"]:.2f},c:{js_string(row["c"])},mn:{row["mn"]:g},'
        f's:{js_string(row["s"])},p:{row["p"]:.2f},d:{row["d"]:.2f},'
        f'w:{row["w"]:.2f},m:{row["m"]:.2f},m2:{row["m2"]:.2f},'
        f'q:{row["q"]:.2f},h:{row["h"]:.2f}}}'
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
    series_map = get_close_series_map(symbols)

    for name, rows in static_data.items():
        text = replace_array(text, name, update_rows(rows, series_map))

    today = latest_price_date(series_map)
    text = ensure_daily_button(text)
    text = re.sub(r"更新于\s*\d{4}-\d{2}-\d{2}", f"更新于 {today}", text)
    text = re.sub(r"·\s*\d{4}-\d{2}-\d{2}更新", f"· {today}更新", text)

    with open(MARKET_FILE, "w", encoding="utf-8") as file:
        file.write(text)

    print(f"Updated {MARKET_FILE} for {today}")


if __name__ == "__main__":
    main()
