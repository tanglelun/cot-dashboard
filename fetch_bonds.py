import io
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_FILE = BASE_DIR / "bonds_data.json"
HISTORY_DIR = BASE_DIR / "bonds_data"

BONDS = [
    {"name": "US 3M", "series_id": "DGS3MO", "category": "Treasury"},
    {"name": "US 6M", "series_id": "DGS6MO", "category": "Treasury"},
    {"name": "US 1Y", "series_id": "DGS1", "category": "Treasury"},
    {"name": "US 2Y", "series_id": "DGS2", "category": "Treasury"},
    {"name": "US 3Y", "series_id": "DGS3", "category": "Treasury"},
    {"name": "US 5Y", "series_id": "DGS5", "category": "Treasury"},
    {"name": "US 7Y", "series_id": "DGS7", "category": "Treasury"},
    {"name": "US 10Y", "series_id": "DGS10", "category": "Treasury"},
    {"name": "US 20Y", "series_id": "DGS20", "category": "Treasury"},
    {"name": "US 30Y", "series_id": "DGS30", "category": "Treasury"},
    {"name": "US 5Y TIPS", "series_id": "DFII5", "category": "TIPS"},
    {"name": "US 10Y TIPS", "series_id": "DFII10", "category": "TIPS"},
]

TRADING_DAYS_YEAR = 252
TRADING_DAYS_MONTH = 21
TRADING_DAYS_WEEK = 5


def fetch_all_fred_series(max_retries=3):
    ids = ",".join(item["series_id"] for item in BONDS)
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={ids}"
    for attempt in range(max_retries):
        try:
            response = requests.get(url, timeout=20)
            response.raise_for_status()
            frame = pd.read_csv(io.StringIO(response.text))
            frame["observation_date"] = pd.to_datetime(frame["observation_date"])
            frame = frame.sort_values("observation_date").reset_index(drop=True)
            for item in BONDS:
                sid = item["series_id"]
                if sid in frame.columns:
                    frame[sid] = pd.to_numeric(frame[sid].replace(".", pd.NA), errors="coerce")
            return frame
        except Exception:
            if attempt < max_retries - 1:
                time.sleep(2)
            else:
                raise


def compute_changes(series, current_date):
    if series.empty or len(series) < 2:
        return {}
    current_value = float(series.iloc[-1])

    changes = {}

    prev_val = float(series.iloc[-2])
    if not pd.isna(prev_val):
        changes["day"] = round(current_value - prev_val, 3)

    if len(series) > TRADING_DAYS_WEEK:
        w = float(series.iloc[-TRADING_DAYS_WEEK - 1])
        if not pd.isna(w):
            changes["week"] = round(current_value - w, 3)

    if len(series) > TRADING_DAYS_MONTH:
        m = float(series.iloc[-TRADING_DAYS_MONTH - 1])
        if not pd.isna(m):
            changes["month"] = round(current_value - m, 3)

    current_year = current_date.year
    ytd_series = series[series.index.year.isin([current_year, current_year - 1])]
    prev_year = ytd_series[ytd_series.index.year < current_year]
    if not prev_year.empty:
        ytd_base = float(prev_year.iloc[-1])
        if not pd.isna(ytd_base):
            changes["ytd"] = round(current_value - ytd_base, 3)

    if len(series) > TRADING_DAYS_YEAR:
        y = float(series.iloc[-TRADING_DAYS_YEAR - 1])
        if not pd.isna(y):
            changes["year"] = round(current_value - y, 3)

    return changes


def collect():
    bonds = []
    latest_date = None

    HISTORY_DIR.mkdir(parents=True, exist_ok=True)

    frame = fetch_all_fred_series()

    for item in BONDS:
        sid = item["series_id"]
        if sid not in frame.columns:
            print(f"  {item['name']} ({sid}): missing column", file=sys.stderr)
            continue

        series = frame.set_index("observation_date")[sid].dropna()
        if series.empty:
            print(f"  {item['name']} ({sid}): no data", file=sys.stderr)
            continue

        latest_idx = series.index[-1]
        date_str = latest_idx.strftime("%Y-%m-%d")
        value = float(series.iloc[-1])

        if latest_date is None or date_str > latest_date:
            latest_date = date_str

        changes = compute_changes(series, latest_idx)

        bonds.append({
            "name": item["name"],
            "yield": round(value, 3),
            "day": changes.get("day"),
            "week": changes.get("week"),
            "month": changes.get("month"),
            "ytd": changes.get("ytd"),
            "year": changes.get("year"),
            "date": date_str,
            "category": item["category"],
            "series_id": sid,
        })
        print(f"  {item['name']}: {value}% ({date_str})", file=sys.stderr)

        history_points = []
        for date_idx, val in series.items():
            if pd.notna(val):
                history_points.append({
                    "date": date_idx.strftime("%Y-%m-%d"),
                    "value": round(float(val), 3),
                })
        history = {
            "name": item["name"],
            "series_id": sid,
            "category": item["category"],
            "updated": latest_date or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "source": "FRED (Federal Reserve Economic Data)",
            "points": history_points,
        }
        (HISTORY_DIR / f"{sid}.json").write_text(
            json.dumps(history, ensure_ascii=False), encoding="utf-8"
        )

    payload = {
        "updated": latest_date or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "source": "FRED (Federal Reserve Economic Data)",
        "bonds": bonds,
    }

    OUTPUT_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSaved {len(bonds)} bonds to {OUTPUT_FILE}", file=sys.stderr)
    return payload


if __name__ == "__main__":
    collect()
