import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf


OUTPUT_FILE = Path("indexes_data.json")
CHART_DATA_DIR = Path("indexes_data")
SUMMARY_PERIOD = "18mo"
HISTORY_PERIOD = "max"

INDEXES = [
    {"name": "US500", "symbol": "^GSPC", "category": "Major", "country": "US", "flag": "🇺🇸", "unit": "Index Points"},
    {"name": "US30", "symbol": "^DJI", "category": "Major", "country": "US", "flag": "🇺🇸", "unit": "Index Points"},
    {"name": "US100", "symbol": "^NDX", "category": "Major", "country": "US", "flag": "🇺🇸", "unit": "Index Points"},
    {"name": "JP225", "symbol": "^N225", "category": "Major", "country": "JP", "flag": "🇯🇵", "unit": "Index Points"},
    {"name": "GB100", "symbol": "^FTSE", "category": "Major", "country": "GB", "flag": "🇬🇧", "unit": "Index Points"},
    {"name": "DE40", "symbol": "^GDAXI", "category": "Major", "country": "DE", "flag": "🇩🇪", "unit": "Index Points"},
    {"name": "FR40", "symbol": "^FCHI", "category": "Major", "country": "FR", "flag": "🇫🇷", "unit": "Index Points"},
    {"name": "IT40", "symbol": "FTSEMIB.MI", "category": "Major", "country": "IT", "flag": "🇮🇹", "unit": "Index Points"},
    {"name": "ES35", "symbol": "^IBEX", "category": "Major", "country": "ES", "flag": "🇪🇸", "unit": "Index Points"},
    {"name": "ASX200", "symbol": "^AXJO", "category": "Major", "country": "AU", "flag": "🇦🇺", "unit": "Index Points"},
    {"name": "SHANGHAI", "symbol": "000001.SS", "category": "Major", "country": "CN", "flag": "🇨🇳", "unit": "Index Points"},
    {"name": "SENSEX", "symbol": "^BSESN", "category": "Major", "country": "IN", "flag": "🇮🇳", "unit": "Index Points"},
    {"name": "TSX", "symbol": "^GSPTSE", "category": "Major", "country": "CA", "flag": "🇨🇦", "unit": "Index Points"},
    {"name": "MOEX", "symbol": "IMOEX.ME", "category": "Major", "country": "RU", "flag": "🇷🇺", "unit": "Index Points"},
    {"name": "Russell 2000", "symbol": "^RUT", "category": "Americas", "country": "US", "flag": "🇺🇸", "unit": "Index Points"},
    {"name": "VIX", "symbol": "^VIX", "category": "Americas", "country": "US", "flag": "🇺🇸", "unit": "Index Points"},
    {"name": "Mexico IPC", "symbol": "^MXX", "category": "Americas", "country": "MX", "flag": "🇲🇽", "unit": "Index Points"},
    {"name": "Bovespa", "symbol": "^BVSP", "category": "Americas", "country": "BR", "flag": "🇧🇷", "unit": "Index Points"},
    {"name": "Merval", "symbol": "^MERV", "category": "Americas", "country": "AR", "flag": "🇦🇷", "unit": "Index Points"},
    {"name": "IPSA", "symbol": "^IPSA", "category": "Americas", "country": "CL", "flag": "🇨🇱", "unit": "Index Points"},
    {"name": "Euro Stoxx 50", "symbol": "^STOXX50E", "category": "Europe", "country": "EU", "flag": "🇪🇺", "unit": "Index Points"},
    {"name": "SMI", "symbol": "^SSMI", "category": "Europe", "country": "CH", "flag": "🇨🇭", "unit": "Index Points"},
    {"name": "AEX", "symbol": "^AEX", "category": "Europe", "country": "NL", "flag": "🇳🇱", "unit": "Index Points"},
    {"name": "BEL20", "symbol": "^BFX", "category": "Europe", "country": "BE", "flag": "🇧🇪", "unit": "Index Points"},
    {"name": "ATX", "symbol": "^ATX", "category": "Europe", "country": "AT", "flag": "🇦🇹", "unit": "Index Points"},
    {"name": "OMX Stockholm", "symbol": "^OMX", "category": "Europe", "country": "SE", "flag": "🇸🇪", "unit": "Index Points"},
    {"name": "Hang Seng", "symbol": "^HSI", "category": "Asia", "country": "HK", "flag": "🇭🇰", "unit": "Index Points"},
    {"name": "Shenzhen", "symbol": "399001.SZ", "category": "Asia", "country": "CN", "flag": "🇨🇳", "unit": "Index Points"},
    {"name": "Taiwan Weighted", "symbol": "^TWII", "category": "Asia", "country": "TW", "flag": "🇹🇼", "unit": "Index Points"},
    {"name": "KOSPI", "symbol": "^KS11", "category": "Asia", "country": "KR", "flag": "🇰🇷", "unit": "Index Points"},
    {"name": "NIFTY 50", "symbol": "^NSEI", "category": "Asia", "country": "IN", "flag": "🇮🇳", "unit": "Index Points"},
    {"name": "STI", "symbol": "^STI", "category": "Asia", "country": "SG", "flag": "🇸🇬", "unit": "Index Points"},
    {"name": "Jakarta Composite", "symbol": "^JKSE", "category": "Asia", "country": "ID", "flag": "🇮🇩", "unit": "Index Points"},
    {"name": "FTSE Malaysia", "symbol": "^KLSE", "category": "Asia", "country": "MY", "flag": "🇲🇾", "unit": "Index Points"},
    {"name": "SET", "symbol": "^SET.BK", "category": "Asia", "country": "TH", "flag": "🇹🇭", "unit": "Index Points"},
    {"name": "PSEi", "symbol": "PSEI.PS", "category": "Asia", "country": "PH", "flag": "🇵🇭", "unit": "Index Points"},
    {"name": "NZ50", "symbol": "^NZ50", "category": "Pacific", "country": "NZ", "flag": "🇳🇿", "unit": "Index Points"},
    {"name": "TA125", "symbol": "^TA125.TA", "category": "Middle East & Africa", "country": "IL", "flag": "🇮🇱", "unit": "Index Points"},
    {"name": "Tadawul", "symbol": "^TASI.SR", "category": "Middle East & Africa", "country": "SA", "flag": "🇸🇦", "unit": "Index Points"},
    {"name": "EGX30", "symbol": "^CASE30", "category": "Middle East & Africa", "country": "EG", "flag": "🇪🇬", "unit": "Index Points"},
    {"name": "JSE Top 40", "symbol": "^J200.JO", "category": "Middle East & Africa", "country": "ZA", "flag": "🇿🇦", "unit": "Index Points"},
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


def safe_symbol(symbol):
    clean = re.sub(r"[^A-Za-z0-9_-]+", "-", symbol).strip("-")
    return clean or "index"


def frame_from_download(data, symbol):
    if data.empty or len(data.columns) == 0:
        return pd.DataFrame()
    if isinstance(data.columns, pd.MultiIndex):
        level0 = data.columns.get_level_values(0)
        level1 = data.columns.get_level_values(1)
        if symbol in level0:
            frame = data[symbol]
        elif symbol in level1:
            frame = pd.DataFrame(index=data.index)
            for column in ("Open", "High", "Low", "Close", "Volume"):
                if column in level0:
                    values = data[column]
                    if isinstance(values, pd.DataFrame):
                        if symbol in values.columns:
                            frame[column] = values[symbol]
                    else:
                        frame[column] = values
        else:
            return pd.DataFrame()
    else:
        frame = data
    if frame.empty or len(frame.columns) == 0:
        return pd.DataFrame()
    columns = [column for column in ("Open", "High", "Low", "Close", "Volume") if column in frame.columns]
    if not {"Open", "High", "Low", "Close"}.issubset(columns):
        return pd.DataFrame()
    return frame[columns].dropna(subset=["Open", "High", "Low", "Close"])


def history_payload(item, frame, updated):
    candles = []
    for timestamp, values in frame.iterrows():
        candle = {
            "time": pd.Timestamp(timestamp).strftime("%Y-%m-%d"),
            "open": rounded(values["Open"], 4),
            "high": rounded(values["High"], 4),
            "low": rounded(values["Low"], 4),
            "close": rounded(values["Close"], 4),
        }
        if "Volume" in values and not pd.isna(values["Volume"]):
            candle["volume"] = int(values["Volume"])
        candles.append(candle)
    return {
        "symbol": item["symbol"],
        "safeSymbol": safe_symbol(item["symbol"]),
        "name": item["name"],
        "country": item["country"],
        "flag": item["flag"],
        "sector": item["category"],
        "unit": item["unit"],
        "updated": updated,
        "prices": candles,
    }


def summarize(item, frame):
    if frame.empty or "Close" not in frame.columns:
        return None
    close = frame["Close"].dropna()
    if close.empty:
        return None
    latest = close.iloc[-1]
    previous = close.iloc[-2] if len(close) > 1 else None
    day_abs = latest - previous if previous is not None and not pd.isna(previous) else None
    day_pct = (latest / previous - 1) * 100 if previous is not None and previous != 0 and not pd.isna(previous) else None
    date = pd.Timestamp(close.index[-1]).strftime("%b/%d")
    return {
        "name": item["name"],
        "symbol": item["symbol"],
        "safeSymbol": safe_symbol(item["symbol"]),
        "category": item["category"],
        "country": item["country"],
        "flag": item["flag"],
        "unit": item["unit"],
        "price": rounded(latest, 2),
        "day": rounded(day_abs, 2),
        "pct": rounded(day_pct, 2),
        "week": rounded(pct_change(close, 5), 2),
        "month": rounded(pct_change(close, 21), 2),
        "ytd": rounded(ytd_change(close), 2),
        "year": rounded(pct_change(close, 252), 2),
        "date": date,
    }


def main():
    updated = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d")
    CHART_DATA_DIR.mkdir(exist_ok=True)
    symbols = [item["symbol"] for item in INDEXES]
    summary_data = yf.download(
        symbols,
        period=SUMMARY_PERIOD,
        interval="1d",
        auto_adjust=False,
        group_by="ticker",
        threads=True,
        progress=False,
    )
    rows = []
    for item in INDEXES:
        frame = frame_from_download(summary_data, item["symbol"])
        if frame.empty:
            single = yf.download(
                item["symbol"],
                period=SUMMARY_PERIOD,
                interval="1d",
                auto_adjust=False,
                progress=False,
            )
            frame = frame_from_download(single, item["symbol"])
        row = summarize(item, frame)
        if not row:
            print(f"skip {item['symbol']}: no summary data")
            continue
        rows.append(row)

        history = yf.download(
            item["symbol"],
            period=HISTORY_PERIOD,
            interval="1d",
            auto_adjust=False,
            progress=False,
        )
        history_frame = frame_from_download(history, item["symbol"])
        if history_frame.empty:
            history_frame = frame
        chart_file = CHART_DATA_DIR / f"{row['safeSymbol']}.json"
        chart_file.write_text(
            json.dumps(history_payload(item, history_frame, updated), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    groups = []
    for category in ("Major", "Americas", "Europe", "Asia", "Pacific", "Middle East & Africa"):
        category_rows = [row for row in rows if row["category"] == category]
        if category_rows:
            groups.append({"name": category, "indexes": category_rows})

    payload = {
        "updated": updated,
        "source": "Yahoo Finance index quotes via yfinance",
        "indexes": rows,
        "groups": groups,
    }
    OUTPUT_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(rows)} indexes to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
