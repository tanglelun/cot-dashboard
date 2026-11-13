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
 function mount(toolbar,onChange){
  let daily=[],period='1d';
  const label=document.createElement('label');label.style.cssText='display:flex;align-items:center;gap:6px;font-size:12px;color:#d1d4dc';label.textContent='K线周期';
  const select=document.createElement('select');select.id='klinePeriod';select.setAttribute('aria-label','K线周期');select.style.cssText='padding:6px;background:#090d12;color:#d1d4dc;border:1px solid #202932;border-radius:4px';
  for(const [key,text] of Object.entries(labels)){const o=document.createElement('option');o.value=key;o.textContent=text;if(key.endsWith('h')){o.disabled=true;o.textContent+='（待接入行情）';}select.append(o);}
  select.value='1d';label.append(select);toolbar.prepend(label);
  select.addEventListener('change',()=>{period=select.value;onChange(aggregate(daily,period));});
  return {setData(bars){daily=bars;return aggregate(daily,period);},label(){return labels[period];},count(range,candles){if(range==='all')return candles.length;const n=Number(range);if(!Number.isFinite(n))return candles.length;if(period==='1d')return Math.min(n,candles.length);const cutoff=daily[Math.max(0,daily.length-n)]?.time;return candles.filter(b=>(b.periodEnd||b.time)>=cutoff).length;}};
 }
 root.klinePeriods={aggregate,mount};
 if(typeof module!=='undefined')module.exports=root.klinePeriods;
})(typeof window!=='undefined'?window:globalThis);
