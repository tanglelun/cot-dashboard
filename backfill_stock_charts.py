import json
import os
import time
from pathlib import Path

import pandas as pd

from update_market import (
    CHART_MAX_ROWS,
    CHART_PERIOD,
    MARKET_DATA_DIR,
    MARKET_DOWNLOAD_SLEEP,
    get_price_frame_map,
    normalize_price_frame_dislocations,
)


INDEX_FILE = MARKET_DATA_DIR / "index.json"
BACKFILL_LIMIT = int(os.getenv("MARKET_CHART_BACKFILL_LIMIT", "250") or 0)
BACKFILL_OFFSET = int(os.getenv("MARKET_CHART_BACKFILL_OFFSET", "0") or 0)
BACKFILL_RETRY_MISSING = os.getenv("MARKET_CHART_RETRY_MISSING", "0") == "1"
BACKFILL_FALLBACK_PERIOD = os.getenv("MARKET_CHART_FALLBACK_PERIOD", "5d")
BACKFILL_SYMBOLS = [
    symbol.strip().upper()
    for symbol in os.getenv("MARKET_CHART_SYMBOLS", "").split(",")
    if symbol.strip()
]


def load_index_rows():
    payload = json.loads(INDEX_FILE.read_text(encoding="utf-8"))
    rows = payload.get("stocks", [])
    if not rows:
        raise RuntimeError(f"No stocks found in {INDEX_FILE}")
    return rows, payload.get("updated", "")


def stock_file(symbol):
    return MARKET_DATA_DIR / f"{symbol}.json"


def rows_to_backfill(rows):
    if BACKFILL_SYMBOLS:
        selected = [row for row in rows if row.get("symbol", "").upper() in BACKFILL_SYMBOLS]
    else:
        selected = [row for row in rows if not stock_file(row.get("symbol", "")).exists()]
        if BACKFILL_OFFSET:
            selected = selected[BACKFILL_OFFSET:]
        if BACKFILL_LIMIT:
            selected = selected[:BACKFILL_LIMIT]
    return selected


def candles_from_frame(symbol, frame):
    frame = normalize_price_frame_dislocations(frame, symbol)
    if CHART_MAX_ROWS and len(frame) > CHART_MAX_ROWS:
        frame = frame.tail(CHART_MAX_ROWS)
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
    return candles


def write_chart_file(row, frame, updated):
    symbol = row["symbol"]
    candles = candles_from_frame(symbol, frame)
    if not candles:
        return False
    payload = {
        "symbol": symbol,
        "name": row.get("name", symbol),
        "sector": row.get("sector", row.get("exchange", "US")),
        "marketCap": row.get("marketCap", ""),
        "updated": updated or candles[-1]["time"],
        "prices": candles,
    }
    stock_file(symbol).write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    return True


def main():
    rows, updated = load_index_rows()
    selected = rows_to_backfill(rows)
    if not selected:
        print("No missing stock chart files to backfill.")
        return

    symbols = [row["symbol"] for row in selected]
    print(f"Backfilling {len(symbols)} stock chart files")
    frames = get_price_frame_map(
        symbols,
        period=CHART_PERIOD,
        chunk_size=80,
        retry_missing=BACKFILL_RETRY_MISSING,
    )
    if BACKFILL_FALLBACK_PERIOD:
        missing_after_primary = [symbol for symbol in symbols if symbol not in frames]
        if missing_after_primary:
            print(f"Trying fallback period {BACKFILL_FALLBACK_PERIOD} for {len(missing_after_primary)} symbols")
            fallback_frames = get_price_frame_map(
                missing_after_primary,
                period=BACKFILL_FALLBACK_PERIOD,
                chunk_size=80,
                retry_missing=False,
            )
            frames.update(fallback_frames)

    written = 0
    missing = []
    by_symbol = {row["symbol"]: row for row in selected}
    for symbol in symbols:
        frame = frames.get(symbol, pd.DataFrame())
        if frame.empty:
            missing.append(symbol)
            continue
        if write_chart_file(by_symbol[symbol], frame, updated):
            written += 1
        if MARKET_DOWNLOAD_SLEEP:
            time.sleep(min(MARKET_DOWNLOAD_SLEEP, 0.2))

    print(f"Wrote {written}/{len(symbols)} stock chart files")
    if missing:
        print("Missing:", ", ".join(missing[:40]))


if __name__ == "__main__":
    main()
