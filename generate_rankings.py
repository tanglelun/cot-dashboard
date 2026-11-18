"""Build current full constituent universes; never truncate before period selection."""
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from generate_patterns import load_members

ROOT=Path(__file__).resolve().parent
GROUPS={'r2kRaw':'russell2000','spRaw':'sp500','ndqRaw':'nasdaq100'}
SECTORS={'Information Technology':'科技','Technology':'科技','Health Care':'医疗','Healthcare':'医疗','Industrials':'工业','Energy':'能源','Financials':'金融','Materials':'基础材料','Communication Services':'通信','Consumer Discretionary':'消费周期','Consumer Staples':'消费防御','Utilities':'公用事业','Real Estate':'房地产'}

def cap_number(value):
    try:
        text=str(value).replace('$','').replace(',','').strip()
        return float(text[:-1])*{'T':1e6,'B':1e3,'M':1,'K':.001}[text[-1]]
    except (ValueError,KeyError,IndexError): return 0

PERIODS={'d':1,'w':5,'m':21,'m2':42,'q':63,'h':126}


def returns(bars, expected):
    bars=[b for b in bars if b.get('time','')<=expected]
    if not bars or bars[-1]['time']!=expected: raise ValueError('行情未到最新交易日')
    if any(a['time']>=b['time'] for a,b in zip(bars,bars[1:])): raise ValueError('行情日期顺序异常')
    if any(not isinstance(b.get('close'),(int,float)) or not math.isfinite(b['close']) or b['close']<=0 for b in bars): raise ValueError('无效收盘价')
    latest=bars[-1]['close']
    result={k:(latest/bars[-n-1]['close']-1)*100 if len(bars)>n else None for k,n in PERIODS.items()}
    previous=[b for b in bars if b['time']<expected[:4]+'-01-01']
    result['y']=(latest/previous[-1]['close']-1)*100 if previous else None
    return {'p':round(latest,2),**result}


def build(root, groups, expected):
    payload={'as_of':expected,'updated':datetime.now(timezone.utc).isoformat(),'groups':{}}
    for key,group in GROUPS.items():
        source=groups[group];rows=[];missing=[]
        for member in source['items']:
            symbol=member['symbol']
            try:
                path=root/'market_data'/f'{symbol}.json'
                if not path.exists(): path=root/'market_data'/f'{symbol.replace("-", ".")}.json'
                chart=json.loads(path.read_text());metrics=returns(chart['prices'],expected)
                rows.append({'t':symbol,'n':member['name'],'s':SECTORS.get(member.get('sector'),member.get('sector','未知')),'c':chart.get('marketCap',''),'mn':cap_number(chart.get('marketCap')),**metrics})
            except (OSError,ValueError,KeyError,TypeError) as exc:missing.append({'symbol':symbol,'reason':str(exc)[:100]})
        if len(rows)<.90*len(source['items']): raise ValueError(f'{group}: insufficient fresh coverage {len(rows)}/{len(source["items"])}')
        payload['groups'][key]={'label':{'russell2000':'Russell 2000（IWM完整持仓近似）','sp500':'S&P 500','nasdaq100':'Nasdaq 100'}[group],
            'source':source['source'],'membership_checked':source['date'],'source_as_of':source.get('source_as_of'),
            'proxy':group=='russell2000','total':len(source['items']),'missing':missing,'stocks':rows,
            'eligible':{k:sum(r[k] is not None for r in rows) for k in (*PERIODS,'y')}}
    return payload


def refresh_missing(root, groups, expected):
    """Try newly added constituents and stale charts before excluding them."""
    members={r['symbol']:r for g in groups.values() for r in g['items']}
    missing=[]
    for symbol in members:
        try:
            path=root/'market_data'/f'{symbol}.json'
            if not path.exists(): path=root/'market_data'/f'{symbol.replace(chr(45),chr(46))}.json'
            chart=json.loads(path.read_text())
            returns(chart['prices'],expected)
        except (OSError,ValueError,KeyError,TypeError): missing.append(symbol)
    if not missing: return
    from update_market import get_price_frame_map, normalize_price_frame_dislocations
    import pandas as pd
    frames=get_price_frame_map(missing,period='max',retry_missing=False)
    for symbol,frame in frames.items():
        if frame.empty: continue
        frame=normalize_price_frame_dislocations(frame,symbol)
        bars=[]
        for timestamp,row in frame.tail(1600).iterrows():
            bar={'time':pd.Timestamp(timestamp).strftime('%Y-%m-%d'),**{k:round(float(row[v]),4) for k,v in [('open','Open'),('high','High'),('low','Low'),('close','Close')]}}
            if 'Volume' in row and pd.notna(row['Volume']):bar['volume']=int(row['Volume'])
            bars.append(bar)
        try:returns(bars,expected)
        except ValueError:continue
        path=root/'market_data'/f'{symbol}.json'
        try:old=json.loads(path.read_text())
        except (OSError,ValueError):old={}
        path.write_text(json.dumps({**old,'symbol':symbol,'name':members[symbol]['name'],'updated':expected,'prices':bars},separators=(',',':')))


def main():
    from market_freshness import expected_market_date
    groups=load_members(ROOT,datetime.now(timezone.utc).date())
    expected=expected_market_date()
    refresh_missing(ROOT,groups,expected)
    data=build(ROOT,groups,expected)
    tmp=ROOT/'rankings_data.tmp';tmp.write_text(json.dumps(data,ensure_ascii=False,separators=(',',':'))+'\n');tmp.replace(ROOT/'rankings_data.json')
    for key,g in data['groups'].items(): print(key,g['total'],g['eligible'])

if __name__=='__main__': main()
