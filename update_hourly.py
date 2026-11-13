"""Publish real Yahoo 60-minute bars; never synthesize intraday from daily prices."""
import argparse
from bisect import bisect_right
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import time
import requests

ROOT=Path(__file__).resolve().parent

def filename(symbol):
    return re.sub(r'[^\w.-]', '_', symbol, flags=re.ASCII)+'.json'

def sessions(value):
    if isinstance(value,dict):
        if 'start' in value and 'end' in value: yield (value['start'],value['end'])
        else:
            for v in value.values(): yield from sessions(v)
    elif isinstance(value,list):
        for v in value: yield from sessions(v)

def parse_chart(chart, symbol, now):
    meta=chart['meta'];trading=meta.get('tradingPeriods',[])
    if isinstance(trading,dict) and 'regular' in trading:trading=trading['regular']
    periods=sorted(set(sessions(trading)))
    if not periods: raise ValueError('Missing trading sessions')
    starts=[p[0] for p in periods];quotes=chart['indicators']['quote'][0];bars=[]
    for i,ts in enumerate(chart.get('timestamp',[])):
        idx=bisect_right(starts,ts)-1
        if idx<0: continue
        start,end=periods[idx];bar_end=min(ts+3600,end)
        if not start<=ts<end or bar_end>now: continue
        values={k:quotes.get(k,[])[i] if i<len(quotes.get(k,[])) else None for k in ('open','high','low','close','volume')}
        if not all(isinstance(values[k],(float,int)) and math.isfinite(values[k]) for k in ('open','high','low','close')):continue
        if values['low']>min(values['open'],values['close']) or values['high']<max(values['open'],values['close']):continue
        volume=values['volume'];values['volume']=volume if isinstance(volume,(float,int)) and math.isfinite(volume) and volume>=0 else None
        bars.append({'time':datetime.fromtimestamp(ts,timezone.utc).isoformat().replace('+00:00','Z'),'timestamp':ts,'end':bar_end,'session':start,'sessionEnd':end,**values})
    bars=sorted({b['timestamp']:b for b in bars}.values(),key=lambda b:b['timestamp'])
    if not bars:raise ValueError('No completed hourly bars')
    return {'symbol':symbol,'interval':'1h','source':'Yahoo Finance','timezone':meta.get('exchangeTimezoneName','UTC'),'fetched_at':datetime.fromtimestamp(now,timezone.utc).isoformat(),'as_of':bars[-1]['time'],'prices':bars}

def inventory(root):
    result=[]
    for group,path,key in [('stocks','market_data/index.json','stocks'),('commodities','commodities_data.json','commodities'),('indexes','indexes_data.json','indexes')]:
        data=json.loads((root/path).read_text())
        for symbol in sorted({r['symbol'] for r in data[key] if r.get('symbol')}):result.append((group,symbol))
    return result

def download(item,root):
    group,symbol=item;provider=symbol.replace('.','-') if group=='stocks' else symbol
    for attempt in range(3):
        try:
            r=requests.get('https://query1.finance.yahoo.com/v8/finance/chart/'+requests.utils.quote(provider,safe=''),params={'interval':'60m','range':'1mo','includePrePost':'false'},headers={'User-Agent':'Mozilla/5.0'},timeout=25)
            if r.status_code==429:
                time.sleep(5*(attempt+1));continue
            r.raise_for_status();body=r.json()['chart'];chart=body['result'][0]
            payload=parse_chart(chart,symbol,int(time.time()));target=root/'hourly_data'/group/filename(symbol);target.parent.mkdir(parents=True,exist_ok=True)
            tmp=target.with_suffix('.tmp');tmp.write_text(json.dumps(payload,separators=(',',':'))+'\n');tmp.replace(target)
            return {'group':group,'symbol':symbol,'status':'ok','as_of':payload['as_of'],'bars':len(payload['prices'])}
        except (requests.RequestException,ValueError,KeyError,TypeError,IndexError) as exc:
            error=str(exc)[:160]
            if attempt<2:time.sleep(1+attempt)
    return {'group':group,'symbol':symbol,'status':'unavailable','error':locals().get('error','Rate limited')}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,default=ROOT);parser.add_argument('--symbols',default='');parser.add_argument('--workers',type=int,default=6);args=parser.parse_args()
    items=inventory(args.root)
    if args.symbols:
        wanted=set(args.symbols.split(','));items=[r for r in items if r[1] in wanted]
    output=args.root/'hourly_data';output.mkdir(exist_ok=True);results=[]
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        jobs=[pool.submit(download,item,args.root) for item in items]
        for i,job in enumerate(as_completed(jobs),1):
            results.append(job.result())
            if i%100==0:print(f'Hourly {i}/{len(items)}; success {sum(r["status"]=="ok" for r in results)}',flush=True)
    report={'updated':datetime.now(timezone.utc).isoformat(),'source':'Yahoo Finance','range':'1mo','interval':'1h','total':len(items),'success':sum(r['status']=='ok' for r in results),'results':results}
    (output/('status-smoke.json' if args.symbols else 'status.json')).write_text(json.dumps(report,separators=(',',':'))+'\n');print(f'Hourly: {report["success"]}/{len(items)}')
    if items and report['success']<len(items)*.9:raise SystemExit('Hourly coverage below 90%; review status.json')

if __name__=='__main__':main()
