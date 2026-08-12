import json
import re
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
STOCK_DIR = BASE_DIR / "market_data"
COMMODITY_DIR = BASE_DIR / "commodities_data"
OUTPUT_FILE = BASE_DIR / "crossover_data.json"


def extract_tops_symbols():
    """Extract all unique stock symbols from the 3 Tops lists."""
    html = (BASE_DIR / "russell2000_top100.html").read_text()
    symbols = set()
    for match in re.finditer(r't:"([^"]+)"', html):
        sym = match.group(1).strip()
        if len(sym) >= 2 and sym.isascii():
            symbols.add(sym)
    return symbols


def compute_ma(values, period):
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def detect_crossover(prices):
    """
    Check if latest close crossed MA20.
    Returns 'up' (crossed above), 'down' (crossed below), or None.
    """
    if len(prices) < 22:
        return None
    closes = [p["close"] for p in prices]
    ma20_now = compute_ma(closes[:-1], 20)  # MA20 as of yesterday
    ma20_prev = compute_ma(closes[:-2], 20)  # MA20 as of day before yesterday
    close_now = closes[-1]
    close_prev = closes[-2]

    if ma20_now is None or ma20_prev is None:
        return None

    if close_prev <= ma20_prev and close_now > ma20_now:
        return "up"
    if close_prev >= ma20_prev and close_now < ma20_now:
        return "down"
    return None


def compute_stock_crossovers():
    symbols = extract_tops_symbols()
    results = []
    for symbol in symbols:
        fpath = STOCK_DIR / f"{symbol}.json"
        if not fpath.exists():
            continue
        try:
            data = json.loads(fpath.read_text())
            prices = data.get("prices") or data.get("data")
            if not prices or len(prices) < 22:
                continue
            # normalize format
            candles = []
            for p in prices:
                if isinstance(p, dict):
                    candles.append(p)
                elif isinstance(p, list) and len(p) >= 5:
                    candles.append({
                        "time": str(p[0]),
                        "open": float(p[1]),
                        "high": float(p[4]),
                        "low": float(p[3]),
                        "close": float(p[2]),
                    })
            direction = detect_crossover(candles)
            if direction is None:
                continue
            last = candles[-1]
            prev = candles[-2]
            chg_pct = round((last["close"] - prev["close"]) / prev["close"] * 100, 2) if prev["close"] != 0 else 0
            ma20 = compute_ma([c["close"] for c in candles[:-1]], 20)
            results.append({
                "symbol": symbol,
                "name": data.get("name", symbol),
                "price": round(last["close"], 2),
                "change_pct": chg_pct,
                "ma20": round(ma20, 2) if ma20 else None,
                "direction": direction,
                "date": str(last.get("time", ""))[:10],
            })
        except Exception:
            continue
    results.sort(key=lambda x: abs(x.get("change_pct", 0)), reverse=True)
    return results


def compute_commodity_crossovers():
    results = []
    for fpath in sorted(COMMODITY_DIR.glob("*.json")):
        try:
            data = json.loads(fpath.read_text())
            prices = data.get("prices") or data.get("data")
            if not prices or len(prices) < 22:
                continue
            candles = []
            for p in prices:
                if isinstance(p, dict):
                    candles.append(p)
                elif isinstance(p, list) and len(p) >= 5:
                    candles.append({
                        "time": str(p[0]),
                        "open": float(p[1]),
                        "high": float(p[4]),
                        "low": float(p[3]),
                        "close": float(p[2]),
                    })
            direction = detect_crossover(candles)
            if direction is None:
                continue
            last = candles[-1]
            prev = candles[-2]
            chg_pct = round((last["close"] - prev["close"]) / prev["close"] * 100, 2) if prev["close"] != 0 else 0
            ma20 = compute_ma([c["close"] for c in candles[:-1]], 20)
            name = data.get("name", fpath.stem)
            sector = data.get("sector", "")
            results.append({
                "symbol": data.get("symbol", fpath.stem),
                "name": name,
                "sector": sector,
                "price": round(last["close"], 2),
                "change_pct": chg_pct,
                "ma20": round(ma20, 2) if ma20 else None,
                "direction": direction,
                "date": str(last.get("time", ""))[:10],
            })
        except Exception:
            continue
    results.sort(key=lambda x: abs(x.get("change_pct", 0)), reverse=True)
    return results


def collect():
    stocks = compute_stock_crossovers()
    commodities = compute_commodity_crossovers()
    payload = {
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "stocks": stocks,
        "commodities": commodities,
    }
    OUTPUT_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    up_stocks = sum(1 for s in stocks if s["direction"] == "up")
    dn_stocks = sum(1 for s in stocks if s["direction"] == "down")
    up_comm = sum(1 for c in commodities if c["direction"] == "up")
    dn_comm = sum(1 for c in commodities if c["direction"] == "down")
    print(f"Stocks: {len(stocks)} crossovers (↑{up_stocks} ↓{dn_stocks})")
    print(f"Commodities: {len(commodities)} crossovers (↑{up_comm} ↓{dn_comm})")
    print(f"Saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    collect()
