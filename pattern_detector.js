/* Close-based daily structures. Geometry mirrors generate_patterns.py v3.
   Replay completed bars so historical records never require future pivots. */
(function(root){
function detect(bars,kind,radius=3){
 const sign=kind==='top'?1:-1, close=bars.map(b=>sign*b.close), pivots=[], found=[];
 const extreme=bars.map(b=>sign===1?b.high:-b.low);
 const tr=bars.map((b,i)=>i?Math.max(b.high-b.low,Math.abs(b.high-bars[i-1].close),Math.abs(b.low-bars[i-1].close)):b.high-b.low);
 for(let i=radius;i<bars.length-radius;i++){
  const peak=close[i]>Math.max(...close.slice(i-radius,i))&&close[i]>=Math.max(...close.slice(i+1,i+radius+1));
  const trough=close[i]<Math.min(...close.slice(i-radius,i))&&close[i]<=Math.min(...close.slice(i+1,i+radius+1));
  if(peak===trough)continue;
  const p={i,v:close[i],type:peak?'H':'L'},prev=pivots.at(-1);
  if(prev&&prev.type===p.type){if((p.v-prev.v)*(peak?1:-1)>0)pivots[pivots.length-1]=p;}else pivots.push(p);
 }
 for(let k=0;k<pivots.length-4;k++){
  const pts=pivots.slice(k,k+5);if(pts.map(p=>p.type).join('')!=='HLHLH')continue;
  const [A,B,H,D,E]=pts,ls=A.i,n1=B.i,head=H.i,n2=D.i,rs=E.i,a=A.v,b=B.v,h=H.v,d=D.v,e=E.v,last=bars.length-1;
  if(ls<20||rs-ls<20||rs-ls>120||last-rs>25)continue;
  const ratio=(head-ls)/(rs-head),legs=[n1-ls,head-n1,n2-head,rs-n2];
  if(ratio<1/3||ratio>3||Math.min(...legs)<3||Math.max(...legs)>4*Math.min(...legs)||n2-n1>2.5*(n1-ls+rs-n2))continue;
  const neck=i=>b+(d-b)*(i-n1)/(n2-n1),height=h-neck(head),scale=Math.abs(h),ranges=tr.slice(Math.max(0,ls-14),rs+1),atr=ranges.reduce((x,y)=>x+y,0)/ranges.length;
  if(height<=0||h-Math.max(a,e)<Math.max(.015*scale,.2*height,atr))continue;
  if(Math.min(a-b,e-d)<Math.max(.35*height,atr)||e-Math.min(...close.slice(rs+1))<Math.max(.2*height,atr))continue;
  if(Math.abs(a-e)>Math.min(.06*scale,.5*height)||Math.min(a-neck(ls),e-neck(rs))<.2*height||Math.abs(neck(rs)-neck(ls))>.6*height)continue;
  if(a-close[ls-20]<Math.max(.03*Math.abs(close[ls-20]),.3*height)||extreme.slice(rs+1).some(v=>v>=extreme[head]))continue;
  const breakout=close.findIndex((v,i)=>i>rs&&v<neck(i)-.005*Math.abs(neck(i)));
  if(breakout>=0){if(last-breakout>10||close.some((v,i)=>i>breakout&&v>neck(i)+.005*Math.abs(neck(i))))continue;}else if(last-rs>20)continue;
  const notes=[];
  if(Math.min(a-b,e-d)<1.5*atr)notes.push('weaker_rebound');
  if(ratio<.5||ratio>2)notes.push('time_asymmetry');
  if(Math.max(...legs)>3*Math.min(...legs))notes.push('leg_asymmetry');
  if(Math.abs(a-e)>Math.min(.04*scale,.3*height))notes.push('shoulder_asymmetry');
  if(Math.abs(neck(rs)-neck(ls))>.35*height)notes.push('sloping_neckline');
  const vols=breakout>=0?bars.slice(Math.max(0,breakout-20),breakout+1).map(b=>b.volume):[];
  const volumeRatio=vols.length===21&&vols.every(v=>Number.isFinite(v)&&v>0)?vols[20]/(vols.slice(0,20).reduce((x,y)=>x+y,0)/20):null;
  found.push({kind,structure:notes.length?'potential':'clear',structure_notes:notes,has_breakout:breakout>=0,volume_state:breakout<0?'not_applicable':volumeRatio===null?'unavailable':volumeRatio>=1.2?'expanded':'not_expanded',volume_ratio:volumeRatio,breakout_date:breakout<0?null:bars[breakout].time,points:pts.map(p=>({date:bars[p.i].time,price:sign*p.v})),head_extreme:extreme[head],as_of:bars[last].time});
 }
 return found;
}
function scan(input){
 // Preserve real prices; use a conservative OHLC envelope only for inconsistent
 // vendor ranges. Never let a single bad bar discard 252 otherwise usable days.
 const bars=input.map(b=>({...b,high:Math.max(b.high,b.open,b.close),low:Math.min(b.low,b.open,b.close),rangeAdjusted:b.low>Math.min(b.open,b.close)||b.high<Math.max(b.open,b.close)}));
 const seen=new Map();let active=new Set();
 for(let end=79;end<bars.length;end++){
  active=new Set();
  const window=bars.slice(Math.max(0,end-251),end+1);
  if(window.some(b=>!['open','high','low','close'].every(k=>Number.isFinite(b[k]))||b.low>Math.min(b.open,b.close)||b.high<Math.max(b.open,b.close)))continue;
  for(const radius of [3,5,8,13])for(const kind of ['bottom','top'])for(const row of detect(window,kind,radius)){
   const key=kind+row.points.map(p=>p.date).join('|');active.add(key);
   const adjusted=window.some(b=>b.time>=row.points[0].date&&b.rangeAdjusted);
   if(adjusted){row.structure='potential';row.structure_notes.push('inconsistent_ohlc');}
   const prev=seen.get(key);seen.set(key,{...row,range_adjusted:adjusted,pivot_radius:radius,first_seen:prev?prev.first_seen:bars[end].time,last_seen:bars[end].time,historical:false});
  }
 }
 const byHead=new Map();
 for(const [key,value] of seen){
  const row={...value,historical:!active.has(key)},headKey=row.kind+row.points[2].date,prev=byHead.get(headKey);
  // Different pivot scales may describe the same head. Keep one representative,
  // preferring an active structure, then the most recently valid definition.
  if(!prev || (prev.historical&&!row.historical) || (prev.historical===row.historical && (row.last_seen>prev.last_seen || (row.last_seen===prev.last_seen&&row.structure==='clear'&&prev.structure!=='clear'))))byHead.set(headKey,row);
 }
 return [...byHead.values()];
}
root.patternDetector={detect,scan};
if(typeof module!=='undefined')module.exports=root.patternDetector;
})(typeof self!=='undefined'?self:globalThis);
