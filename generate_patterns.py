"""Daily head-and-shoulders screening for index constituents and IWM equities."""
import argparse
import csv
import io
import json
import math
import re
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCES = {
    'sp500': 'https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv',
    'nasdaq100': 'https://en.wikipedia.org/wiki/List_of_NASDAQ-100_companies',
    'russell2000': 'https://www.ishares.com/us/products/239710/ishares-russell-2000-etf/latest-holdings.csv',
}
LABELS = {'sp500': 'S&P 500', 'nasdaq100': 'Nasdaq 100', 'russell2000': 'Russell 2000 (IWM近似)'}


class Tables(HTMLParser):
    def __init__(self):
        super().__init__(); self.tables = []; self.table = None; self.row = []; self.cell = None
    def handle_starttag(self, tag, attrs):
        if tag == 'table': self.table = []
        elif tag == 'tr': self.row = []
        elif tag in ('td', 'th'): self.cell = []
    def handle_data(self, data):
        if self.cell is not None: self.cell.append(data)
    def handle_endtag(self, tag):
        if tag in ('td', 'th') and self.cell is not None:
            self.row.append(''.join(self.cell).strip()); self.cell = None
        elif tag == 'tr' and self.table is not None: self.table.append(self.row)
        elif tag == 'table' and self.table is not None:
            self.tables.append(self.table); self.table = None


def parse_iwm(text):
    records = list(csv.reader(io.StringIO(text.lstrip('\ufeff'))))
    as_of = None
    header = None
    for i, row in enumerate(records):
        if row and row[0].strip() == 'Fund Holdings as of' and len(row) > 1:
            as_of = datetime.strptime(row[1].strip(), '%b %d, %Y').date().isoformat()
        if row and row[0].strip() == 'Ticker' and 'Asset Class' in row:
            header = i; break
    if not as_of or header is None: raise ValueError('IWM holdings date/header missing')
    items = []; excluded = 0
    for values in records[header+1:]:
        row = dict(zip(records[header], values))
        if row.get('Asset Class') != 'Equity': continue
        symbol = row.get('Ticker', '').strip().upper().replace(' ', '-').replace('.', '-')
        if not re.fullmatch(r'[A-Z][A-Z0-9-]{0,11}',symbol) or 'UNLISTED' in row.get('Exchange','').upper():
            excluded += 1; continue
        items.append({'symbol':symbol, 'name':row.get('Name',symbol)})
    return items, {'source_as_of':as_of, 'proxy':True, 'excluded_equity_holdings':excluded}


def parse_members(text, group):
    if group == 'russell2000':
        rows, _ = parse_iwm(text)
    elif group == 'sp500':
        rows = [{'symbol': r['Symbol'], 'name': r['Security']} for r in csv.DictReader(io.StringIO(text))]
    else:
        parser = Tables(); parser.feed(text); rows = []
        for table in parser.tables:
            if not table: continue
            header = table[0]
            if 'Ticker' in header and 'Company' in header:
                a, b = header.index('Ticker'), header.index('Company')
                rows = [{'symbol': r[a], 'name': r[b]} for r in table[1:] if len(r) > max(a, b)]
                break
    unique = {}
    for row in rows:
        symbol = row['symbol'].strip().upper().replace('.', '-')
        if not re.fullmatch(r'[A-Z0-9-]{1,12}', symbol): raise ValueError('Invalid constituent symbol')
        unique[symbol] = {'symbol': symbol, 'name': row['name']}
    low, high = {'sp500':(490,510), 'nasdaq100':(95,110), 'russell2000':(1800,2200)}[group]
    if not low <= len(unique) <= high: raise ValueError(f'Incomplete {group} membership: {len(unique)}')
    return list(unique.values())


def load_members(root, now=None):
    import requests
    today = now or date.today()
    path = root / 'pattern_constituents.json'
    try: cache = json.loads(path.read_text())
    except (OSError, ValueError): cache = {}
    groups = {}
    for group, url in SOURCES.items():
        try:
            response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=30)
            response.raise_for_status()
            extra = parse_iwm(response.text)[1] if group == 'russell2000' else {}
            if extra and not 0 <= (today-date.fromisoformat(extra['source_as_of'])).days <= 7:
                raise ValueError('IWM holdings date is stale or in the future')
            groups[group] = {'date': today.isoformat(), 'source': url, 'items': parse_members(response.text, group), **extra}
        except Exception as exc:
            saved = cache.get(group, {})
            if not saved.get('items') or not 0 <= (today - date.fromisoformat(saved['date'])).days <= 7:
                raise RuntimeError(f'No current {group} constituent list: {exc}') from exc
            if group == 'russell2000' and (not saved.get('source_as_of') or not 0 <= (today-date.fromisoformat(saved['source_as_of'])).days <= 7):
                raise RuntimeError('IWM cached holdings are stale') from exc
            groups[group] = saved
            print(f'{group}: using dated constituent cache from {saved["date"]}')
    path.write_text(json.dumps(groups, ensure_ascii=False, indent=2) + '\n')
    return groups


def universe(groups):
    result = {}
    for group in SOURCES:
        for row in groups[group]['items']:
            symbol = row['symbol']
            if symbol not in result: result[symbol] = {**row, 'indexes': []}
            result[symbol]['indexes'].append(LABELS[group])
    return result


def clean_bars(prices, expected):
    bars = [r for r in prices if r.get('time', '') <= expected][-252:]
    if len(bars) < 80 or bars[-1]['time'] != expected: raise ValueError('Missing/stale daily history')
    if any(a['time'] >= b['time'] for a, b in zip(bars, bars[1:])): raise ValueError('Unordered bars')
    for r in bars:
        date.fromisoformat(r['time'])
        if not all(isinstance(r.get(k), (int, float)) and math.isfinite(r[k]) and r[k] > 0 for k in ('open','high','low','close')):
            raise ValueError('Invalid OHLC')
        if r['low'] > min(r['open'], r['close']) or r['high'] < max(r['open'], r['close']): raise ValueError('Invalid OHLC range')
    return bars


def detect(bars, kind):
    """Invert bottoms so the same geometry, prior-trend and breakout rules apply."""
    sign = 1 if kind == 'top' else -1
    close = [sign * b['close'] for b in bars]
    # Use the same close-price curve shown in the preview: no invisible wick pivots.
    high = low = close
    extreme = [b['high'] if sign == 1 else -b['low'] for b in bars]
    true_ranges = [max(b['high']-b['low'], abs(b['high']-bars[i-1]['close']),
                       abs(b['low']-bars[i-1]['close'])) if i else b['high']-b['low']
                   for i, b in enumerate(bars)]
    pivots = []
    for i in range(3, len(bars)-3):
        peak = high[i] > max(high[i-3:i]) and high[i] >= max(high[i+1:i+4])
        trough = low[i] < min(low[i-3:i]) and low[i] <= min(low[i+1:i+4])
        if peak == trough: continue
        p = (i, high[i] if peak else low[i], 'H' if peak else 'L')
        if pivots and pivots[-1][2] == p[2]:
            if (p[1] - pivots[-1][1]) * (1 if peak else -1) > 0: pivots[-1] = p
        else: pivots.append(p)
    found = []
    for start in range(len(pivots)-4):
        points = pivots[start:start+5]
        if ''.join(p[2] for p in points) != 'HLHLH': continue
        (ls,a,_),(n1,b,_),(head,h,_),(n2,d,_),(rs,e,_) = points
        if ls < 20 or not 20 <= rs-ls <= 120 or len(bars)-1-rs > 25: continue
        time_ratio = (head-ls)/(rs-head)
        if not 1/3 <= time_ratio <= 3: continue
        legs = [n1-ls, head-n1, n2-head, rs-n2]
        # Avoid a broad U with tiny shoulders at its far ends.
        if min(legs) < 3 or max(legs) > 4*min(legs): continue
        if n2-n1 > 2.5*((n1-ls)+(rs-n2)): continue
        neck = lambda i: b + (d-b)*(i-n1)/(n2-n1)
        height = h-neck(head)
        scale = abs(h)
        atr = sum(true_ranges[max(0,ls-14):rs+1])/len(true_ranges[max(0,ls-14):rs+1])
        if height <= 0 or h-max(a,e) < max(.015*scale, .2*height, atr): continue
        # Both rebounds around the head must be substantial, not incidental wiggles.
        if min(a-b, e-d) < max(.35*height, atr): continue
        # Visible recovery away from the right shoulder is required even for a candidate.
        if e-min(close[rs+1:]) < max(.2*height, atr): continue
        if abs(a-e) > min(.06*scale, .5*height): continue
        if min(a-neck(ls), e-neck(rs)) < .2*height: continue
        if abs(neck(rs)-neck(ls)) > .6*height: continue
        # Tiers relax symmetry, slope and rebound strength. Broad-U exclusion
        # above are mandatory for both tiers, irrespective of breakout/volume.
        structure_notes = []
        if min(a-b, e-d) < 1.5*atr: structure_notes.append('weaker_rebound')
        if not .5 <= time_ratio <= 2: structure_notes.append('time_asymmetry')
        if max(legs) > 3*min(legs): structure_notes.append('leg_asymmetry')
        if abs(a-e) > min(.04*scale, .3*height): structure_notes.append('shoulder_asymmetry')
        if abs(neck(rs)-neck(ls)) > .35*height: structure_notes.append('sloping_neckline')
        structure = 'potential' if structure_notes else 'clear'
        # A reversal must be preceded by a move into the left shoulder.
        if a-close[ls-20] < max(.03*abs(close[ls-20]), .3*height): continue
        if any(v >= extreme[head] for v in extreme[rs+1:]): continue
        breaks = [i for i in range(rs+1, len(bars)) if close[i] < neck(i)-.005*abs(neck(i))]
        breakout = breaks[0] if breaks else None
        if breakout is not None:
            if len(bars)-1-breakout > 10: continue
            if any(close[i] > neck(i)+.005*abs(neck(i)) for i in range(breakout+1,len(bars))): continue
        elif len(bars)-1-rs > 20: continue
        last = len(bars)-1
        neckline = sign*neck(last)
        if neckline <= 0: continue
        confirmation = max(rs+3, breakout) if breakout is not None else None
        volume_ratio = None
        volume_ok = False
        if breakout is not None:
            volumes = [r.get('volume') for r in bars[max(0,breakout-20):breakout+1]]
            if len(volumes) == 21 and all(isinstance(v,(int,float)) and math.isfinite(v) and v>0 for v in volumes):
                volume_ratio = volumes[-1]/(sum(volumes[:-1])/20)
                volume_ok = volume_ratio >= 1.2
        status = 'confirmed' if volume_ok else 'breakout' if breakout is not None else 'candidate'
        # Retain all daily closes in the pattern window for an auditable mini-chart.
        origin = max(0,ls-10)
        found.append({
            'kind':kind, 'structure':structure, 'structure_notes':structure_notes,
            'has_breakout':breakout is not None,
            'volume_state':('not_applicable' if breakout is None else 'unavailable' if volume_ratio is None else 'expanded' if volume_ok else 'not_expanded'),
            'status':status, 'volume_ratio':round(volume_ratio,2) if volume_ratio is not None else None,
            'as_of':bars[-1]['time'], 'price':bars[-1]['close'], 'neckline':round(neckline,4),
            'distance_pct':round((bars[-1]['close']/neckline-1)*100,2),
            'right_shoulder':bars[rs]['time'], 'detected_on':bars[rs+3]['time'],
            'breakout_date':bars[breakout]['time'] if breakout is not None else None,
            'price_breakout_on':bars[confirmation]['time'] if confirmation is not None else None,
            'confirmed_on':bars[confirmation]['time'] if volume_ok else None,
            'points':[{'date':bars[i]['time'], 'price':round(sign*v,4), 'offset':i-origin} for i,v,_ in points],
            'chart':[{'date':r['time'],'close':r['close']} for r in bars[origin:]],
            'neck_start':round(sign*neck(origin),4), 'neck_end':round(neckline,4),
        })
    return max(found,key=lambda r:(r['structure']=='clear',r['right_shoulder'])) if found else None


def scan(root, groups, expected):
    members = universe(groups); skipped=[]; results=[]; scanned=0; scanned_symbols=set()
    for symbol, member in sorted(members.items()):
        try:
            path = root/'market_data'/f'{symbol}.json'
            if not path.exists(): path = root/'market_data'/f'{symbol.replace("-", ".")}.json'
            bars = clean_bars(json.loads(path.read_text())['prices'], expected)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            skipped.append({'symbol':symbol,'reason':str(exc)[:120]}); continue
        scanned += 1; scanned_symbols.add(symbol)
        for kind in ('top','bottom'):
            result=detect(bars,kind)
            if result: results.append({**member,**result})
    coverage = {}
    for group, details in groups.items():
        symbols = {r['symbol'] for r in details['items']}
        count = len(symbols & scanned_symbols)
        if count < len(symbols)*.90:
            raise RuntimeError(f'Insufficient current {group} charts: {count}/{len(symbols)}; preserving previous scan')
        coverage[group] = {'date':details['date'], 'source':details['source'], 'label':LABELS[group],
                           'count':len(symbols), 'scanned':count, 'proxy':details.get('proxy',False)}
        for key in ('source_as_of','excluded_equity_holdings'):
            if key in details: coverage[group][key]=details[key]
    results.sort(key=lambda r:(r['structure']=='clear',{'confirmed':2,'breakout':1,'candidate':0}[r['status']],r['price_breakout_on'] or r['detected_on']), reverse=True)
    return {'updated':datetime.now(timezone.utc).isoformat(), 'as_of':expected, 'universe_count':len(members),
            'scanned':scanned, 'skipped':skipped, 'constituents':coverage,
            'method_version':3,'patterns':results}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,default=ROOT);parser.add_argument('--expected');parser.add_argument('--members-only',action='store_true');args=parser.parse_args()
    groups=load_members(args.root, datetime.now(timezone.utc).date())
    if args.members_only: return
    from market_freshness import expected_market_date
    payload=scan(args.root,groups,args.expected or expected_market_date())
    target=args.root/'patterns_data.json';temp=target.with_suffix('.tmp')
    temp.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n');temp.replace(target)
    print(f"Scanned {payload['scanned']}/{payload['universe_count']}; found {len(payload['patterns'])} patterns as of {payload['as_of']}")

if __name__ == '__main__': main()
