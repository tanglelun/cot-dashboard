// Full-history recognition runs off the UI thread, once per loaded price series.
window.patternOverlay = (() => {
  const cache=new WeakMap();
  function load(){return Promise.resolve();}
  function history(bars,refresh){
    if(cache.has(bars))return cache.get(bars);
    const entry={rows:null,error:false};cache.set(bars,entry);
    try{
      const worker=new Worker('pattern_worker.js?v=1');
      worker.onmessage=event=>{entry.rows=event.data.rows;entry.error=!!event.data.error;worker.terminate();refresh();};
      worker.onerror=()=>{entry.error=true;worker.terminate();refresh();};
      worker.postMessage(bars.map(({time,open,high,low,close,volume})=>({time,open,high,low,close,volume})));
    }catch(error){entry.error=true;}
    return entry;
  }
  function draw(ctx, symbol, candles, xFor, yFor, bounds, notice, allBars, refresh){
    const entry=history(allBars,refresh);
    if(!entry.rows){notice.textContent=entry.error?'历史形态识别失败，请刷新重试。':'正在识别完整历史形态…';return;}
    const first=candles[0].time,last=candles.at(-1).time;
    const rows=entry.rows.filter(r=>r.points[4].date>=first&&r.points[0].date<=last);
    notice.title=rows.map(r=>`${r.points[2].date} ${r.kind==='bottom'?'头肩底':'头肩顶'} · ${r.structure==='clear'?'明确':'潜在'} · ${r.historical?'历史，非当前信号':'当前有效'} · ${r.has_breakout?'已突破':'未突破'} · ${{expanded:'放量',not_expanded:'未放量',unavailable:'量能缺失',not_applicable:'待突破'}[r.volume_state]} · 首次识别 ${r.first_seen} / 最后有效 ${r.last_seen}`).join('\n');
    const count=rows.filter(r=>r.historical).length;
    notice.textContent=`头肩形态 · 已扫描全部 ${allBars.length} 根日线 · 当前窗口 ${rows.length} 个结构（历史 ${count} / 当前有效 ${rows.length-count}）· 历史标记不代表当前信号`;
    const offset=allBars.findIndex(c=>c.time===first);
    const indices=new Map(allBars.map((c,i)=>[c.time,i-offset]));
    let visible=false;
    ctx.save();ctx.beginPath();ctx.rect(bounds.left,bounds.top,bounds.right-bounds.left,bounds.bottom-bounds.top);ctx.clip();
    for(const row of rows){
      const points=row.points.map(p=>({...p,index:indices.get(p.date)}));
      // Use actual global bar positions; canvas clipping handles partial structures.
      if(points.some(p=>p.index===undefined))continue;
      visible=true;
      ctx.globalAlpha=row.historical?.55:1;
      const color=row.kind==='bottom'?'#45d6ae':'#ff7859';
      ctx.strokeStyle=color;ctx.lineWidth=1.5;ctx.setLineDash([3,3]);ctx.beginPath();
      points.forEach((p,i)=>{const x=xFor(p.index),y=yFor(p.price);if(i)ctx.lineTo(x,y);else ctx.moveTo(x,y);});ctx.stroke();ctx.setLineDash([]);
      [0,2,4].forEach((n,j)=>{const p=points[n],x=xFor(p.index),y=yFor(p.price);ctx.fillStyle=color;ctx.beginPath();ctx.arc(x,y,3,0,Math.PI*2);ctx.fill();ctx.font='bold 12px Arial';ctx.textAlign='center';const ty=Math.max(bounds.top+14,Math.min(bounds.bottom-5,y+(row.kind==='bottom'?18:-12)));ctx.strokeStyle='#000';ctx.lineWidth=3;const label=['左肩',(row.historical?'历史':'')+'头部'+(row.structure==='potential'?'?':''),'右肩'][j];ctx.strokeText(label,x,ty);ctx.fillText(label,x,ty);});
      const a=points[1],b=points[3];ctx.strokeStyle='#e4b85b';ctx.lineWidth=1.5;ctx.beginPath();ctx.moveTo(xFor(a.index),yFor(a.price));ctx.lineTo(xFor(b.index),yFor(b.price));ctx.stroke();
      ctx.fillStyle='#e4b85b';ctx.textAlign='center';ctx.fillText('颈线',(xFor(a.index)+xFor(b.index))/2,Math.max(bounds.top+14,yFor((a.price+b.price)/2)-8));
    }
    ctx.restore();
    if(rows.length&&!visible)notice.textContent+=' · 当前窗口没有可绘制的结构';
  }
  return {load,draw};
})();
