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


def compute_indicators(closes):
    """Compute lifeLine (EMA(EMA(C,10),10)), EMA5, MA20, and candle colors."""
    n = len(closes)
    if n < 22:
        return None

    # EMA(10) then EMA of that = lifeLine
    life_line = [0.0] * n
    ema1 = None
    ema2 = None
    k10 = 2 / 11
    for i in range(n):
        c = closes[i]
        ema1 = c if ema1 is None else c * k10 + ema1 * (1 - k10)
        ema2 = c if ema2 is None else ema1 * k10 + ema2 * (1 - k10)
        life_line[i] = ema2

    # EMA5
    ema5 = [0.0] * n
    e5 = None
    k5 = 2 / 6
    for i in range(n):
        c = closes[i]
        e5 = c if e5 is None else c * k5 + e5 * (1 - k5)
        ema5[i] = e5

    # MA20
    ma20 = [None] * n
    for i in range(n):
        if i >= 19:
            ma20[i] = sum(closes[i - 19:i + 1]) / 20

    # Candle colors using TD Sequential + LifeLine rule
    colors = [''] * n
    for i in range(n):
        cl = closes[i]
        ll = life_line[i]
        m20 = ma20[i]
        if m20 is not None:
            above = cl > m20
            below = cl < m20
            e5_above = ema5[i] > ll
            e5_below = ema5[i] < ll
            if (above and e5_below) or (below and e5_above):
                colors[i] = 'white'
            elif cl > ll:
                colors[i] = 'green'
            elif cl < ll:
                colors[i] = 'red'
            else:
                colors[i] = 'white'
        else:
            if cl > ll:
                colors[i] = 'green'
            elif cl < ll:
                colors[i] = 'red'
            else:
                colors[i] = 'white'

    return colors


def detect_signal(colors):
    """Detect color transition. red->green/white = up, green->red/white = down."""
    if len(colors) < 2:
        return None
    prev, cur = colors[-2], colors[-1]
    if prev == cur:
        return None
    if prev == 'red':
        return 'up'
    if prev == 'green':
        return 'down'
    if prev == 'white':
        if cur == 'green':
            return 'up'
        if cur == 'red':
            return 'down'
    return None


def normalize_candles(prices):
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
    return candles


def build_result(symbol, name, candles, extra):
    closes = [c["close"] for c in candles]
    colors = compute_indicators(closes)
    if colors is None:
        return None
    direction = detect_signal(colors)
    if direction is None:
        return None
    last = candles[-1]
    prev = candles[-2]
    chg_pct = round((last["close"] - prev["close"]) / prev["close"] * 100, 2) if prev["close"] != 0 else 0
    prev_color = colors[-2]
    cur_color = colors[-1]
    result = {
        "symbol": symbol,
        "name": name,
        "price": round(last["close"], 2),
        "change_pct": chg_pct,
        "direction": direction,
        "prev_color": prev_color,
        "cur_color": cur_color,
        "date": str(last.get("time", ""))[:10],
    }
    result.update(extra)
    return result


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
            if not prices:
                continue
            candles = normalize_candles(prices)
            if len(candles) < 22:
                continue
            result = build_result(symbol, data.get("name", symbol), candles, {})
            if result:
                results.append(result)
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
            if not prices:
                continue
            candles = normalize_candles(prices)
            if len(candles) < 22:
                continue
            symbol = data.get("symbol", fpath.stem)
            name = data.get("name", fpath.stem)
            sector = data.get("sector", "")
            result = build_result(symbol, name, candles, {"sector": sector})
            if result:
                results.append(result)
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
    print(f"Stocks: {len(stocks)} signals (↑{up_stocks} ↓{dn_stocks})")
    print(f"Commodities: {len(commodities)} signals (↑{up_comm} ↓{dn_comm})")
    print(f"Saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    collect()
