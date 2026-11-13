(function(root){
 const labels={'1h':'1小时','2h':'2小时','4h':'4小时','1d':'日','1w':'周','1mo':'月'};
 function aggregate(bars,period){
  if(period==='1d')return bars.map(b=>({...b}));
  if(!['1w','1mo'].includes(period))throw new Error('该周期需要真实小时行情');
  const groups=new Map();
  for(const b of bars){
   const date=new Date(b.time+'T00:00:00Z');
   if(!Number.isFinite(date.getTime()))continue;
   if(period==='1w')date.setUTCDate(date.getUTCDate()-((date.getUTCDay()+6)%7));
   else date.setUTCDate(1);
   const key=date.toISOString().slice(0,10),prev=groups.get(key);
   if(!prev)groups.set(key,{time:b.time,periodStart:key,periodEnd:b.time,open:b.open,high:b.high,low:b.low,close:b.close,volume:b.volume||0});
   else{prev.high=Math.max(prev.high,b.high);prev.low=Math.min(prev.low,b.low);prev.close=b.close;prev.volume+=b.volume||0;prev.periodEnd=b.time;}
  }
  return [...groups.values()];
 }
 function hourly(bars,period){
  const hours=Number(period.slice(0,-1));
  if(![1,2,4].includes(hours))throw new Error('无效小时周期');
  const groups=new Map();
  for(const b of bars){
   const slot=Math.floor((b.timestamp-b.session)/(hours*3600)),key=b.session+':'+slot;
   const targetEnd=Math.min(b.session+(slot+1)*hours*3600,b.sessionEnd),prev=groups.get(key);
   if(!prev)groups.set(key,{...b,targetEnd,missing:b.timestamp>b.session+slot*hours*3600,partial:b.end<targetEnd||b.timestamp>b.session+slot*hours*3600});
   else{prev.high=Math.max(prev.high,b.high);prev.low=Math.min(prev.low,b.low);prev.close=b.close;prev.volume=prev.volume==null||b.volume==null?null:prev.volume+b.volume;prev.missing=prev.missing||prev.end!==b.timestamp;prev.end=b.end;prev.partial=prev.missing||b.end<targetEnd;}
  }
  return [...groups.values()];
 }
 function mount(toolbar,onChange,group){
  let daily=[],period='1d',symbol='',requestId=0,hourData=null;
  const cache=new Map();
  const label=document.createElement('label');label.style.cssText='display:flex;align-items:center;gap:6px;font-size:12px;color:#d1d4dc';label.textContent='K线周期';
  const select=document.createElement('select');select.id='klinePeriod';select.setAttribute('aria-label','K线周期');select.style.cssText='padding:6px;background:#090d12;color:#d1d4dc;border:1px solid #202932;border-radius:4px';
  for(const [key,text] of Object.entries(labels)){const o=document.createElement('option');o.value=key;o.textContent=text;select.append(o);}
  select.value='1d';label.append(select);toolbar.prepend(label);
  const notice=document.createElement('div');notice.id='klineDataStatus';notice.setAttribute('role','status');notice.style.cssText='font-size:11px;color:#9ba8b8;padding:4px 12px;display:none';toolbar.closest('.chart-toolbar').after(notice);
  function status(text){notice.textContent=text;notice.style.display=text?'block':'none';}
  function apply(target,data){
   period=target;select.value=target;hourData=data||null;
   if(data)status(`真实小时行情 · ${data.source} · ${data.timezone} · 截至 ${format(data.as_of)} · 抓取 ${data.fetched_at} · 近一个月 / 每小时更新快照，非实时 · 尾部2/4小时柱可能尚未完整${Date.now()-Date.parse(data.fetched_at)>3*3600000?" · 快照超过3小时未刷新":""}`);
   else status('');
   onChange(data?hourly(data.prices,target):aggregate(daily,target));
  }
  async function change(target){
   const id=++requestId,requestedSymbol=symbol;
   select.value=period;
   if(!target.endsWith('h')){apply(target);return;}
   if(!symbol){status('请等待品种行情加载完成');return;}
   status('正在加载真实小时行情…');
   try{
    let data=cache.get(symbol);
    if(!data){
     const file=symbol.replace(/[^\w.-]/g,'_')+'.json';
     const path='hourly_data/'+group+'/'+encodeURIComponent(file);
     // Raw branch data updates independently of the static Pages deployment.
     for(const url of ['https://raw.githubusercontent.com/tanglelun/cot-dashboard/main/'+path,path]){
      try{
       const response=await fetch(url,{cache:'no-store'});if(!response.ok)continue;
       const payload=await response.json();
       if(payload.symbol===requestedSymbol&&payload.interval==='1h'&&Array.isArray(payload.prices)&&payload.prices.length){data=payload;break;}
      }catch(error){/* Try the local mirror when the remote host is unavailable. */}
     }
     if(!data)throw Error('该品种暂未获取到小时行情');
     cache.set(requestedSymbol,data);
    }
    if(id!==requestId||symbol!==requestedSymbol)return;
    apply(target,data);
   }catch(error){if(id===requestId)status((error.message||'小时行情加载失败')+'，仍显示'+labels[period]+'K线；重新选择可重试。');}
  }
  function format(time){
   if(!time.includes('T'))return time;
   const parts=Object.fromEntries(new Intl.DateTimeFormat('en-GB',{timeZone:hourData?.timezone||'UTC',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).formatToParts(new Date(time)).map(p=>[p.type,p.value]));
   return `${parts.month}-${parts.day} ${parts.hour}:${parts.minute}`;
  }
  select.addEventListener('change',()=>change(select.value));
  return {
   cancel(){++requestId;},
   setData(bars,newSymbol){
    ++requestId;daily=bars;symbol=newSymbol;
    if(period.endsWith('h')){const target=period;period='1d';select.value='1d';hourData=null;const id=requestId;queueMicrotask(()=>{if(id===requestId)change(target);});return aggregate(daily,'1d');}
    status('');return aggregate(daily,period);
   },label(){return labels[period];},format,
   count(range,candles){if(range==='all')return candles.length;const n=Number(range);if(!Number.isFinite(n))return candles.length;if(period==='1d')return Math.min(n,candles.length);const cutoff=daily[Math.max(0,daily.length-n)]?.time;return candles.filter(b=>(b.periodEnd||b.time)>=cutoff).length;}
  };
 }
 root.klinePeriods={aggregate,hourly,mount};
 if(typeof module!=='undefined')module.exports=root.klinePeriods;
})(typeof window!=='undefined'?window:globalThis);
