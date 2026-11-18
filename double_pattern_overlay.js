// Draw the same daily screening records used by the homepage.
window.doublePatternOverlay = (() => {
  let payload = null, error = false, pending = null;
  function load(refresh) {
    if(payload) return;
    if(!pending) pending = fetch('patterns_data.json', {cache:'no-store'})
      .then(response=>{if(!response.ok)throw Error('Unavailable');return response.json();})
      .then(data=>{if(!Array.isArray(data.double_patterns))throw Error('Invalid data');payload=data;})
      .catch(()=>{error=true;}).finally(()=>refresh());
  }
  function draw(ctx, symbol, candles, xFor, yFor, bounds, notice, allBars, refresh) {
    load(refresh);
    if(!payload){notice.textContent=error?'双底／双顶日线形态读取失败，请刷新重试。':'正在读取双底／双顶日线形态…';return;}
    if(allBars[0]?.time.includes('T')){
      notice.textContent='双底／双顶：当前标记来自首页日线扫描，请切换日、周或月K线查看。';return;
    }
    const rows=payload.double_patterns.filter(r=>r.symbol===symbol);
    const first=candles[0].time, last=candles.at(-1).periodEnd || candles.at(-1).time;
    const offset=allBars.findIndex(b=>b.time===first);
    const indexFor=date=>allBars.findIndex(b=>b.time<=date && date<=(b.periodEnd || b.time));
    let visible=0;
    ctx.save();ctx.beginPath();ctx.rect(bounds.left,bounds.top,bounds.right-bounds.left,bounds.bottom-bounds.top);ctx.clip();
    for(const row of rows){
      if(row.points[0].date>last || row.as_of<first)continue;
      const points=row.points.map(p=>({...p,index:indexFor(p.date)}));
      if(points.some(p=>p.index<0))continue;
      visible++;
      const color=row.kind==='bottom'?'#45d6ae':'#ff7859';
      const xy=p=>[xFor(p.index-offset),yFor(p.price)];
      ctx.strokeStyle=color;ctx.lineWidth=1.5;ctx.setLineDash([3,3]);ctx.beginPath();
      points.forEach((p,i)=>{const [x,y]=xy(p);if(i)ctx.lineTo(x,y);else ctx.moveTo(x,y);});ctx.stroke();ctx.setLineDash([]);
      ctx.font='bold 12px Arial';ctx.textAlign='center';
      const label=(text,x,y,fill)=>{ctx.strokeStyle='#000';ctx.lineWidth=3;ctx.strokeText(text,x,y);ctx.fillStyle=fill;ctx.fillText(text,x,y);};
      [0,2].forEach((n,j)=>{
        const [x,y]=xy(points[n]);ctx.fillStyle=color;ctx.beginPath();ctx.arc(x,y,4,0,Math.PI*2);ctx.fill();
        const text=(j===0?'第一':'第二')+(row.kind==='bottom'?'底':'顶');
        label(text,x,Math.max(bounds.top+14,Math.min(bounds.bottom-5,y+(row.kind==='bottom'?19:-12))),color);
      });
      const x1=xFor(points[0].index-offset),x2=xFor(points[2].index-offset),y=yFor(row.neckline);
      ctx.strokeStyle='#e4b85b';ctx.lineWidth=1.5;ctx.beginPath();ctx.moveTo(x1,y);ctx.lineTo(x2,y);ctx.stroke();
      ctx.setLineDash([5,4]);ctx.beginPath();ctx.moveTo(x2,y);ctx.lineTo(Math.min(bounds.right,xFor(indexFor(row.as_of)-offset)),y);ctx.stroke();ctx.setLineDash([]);
      const text=(row.kind==='bottom'?'双底':'双顶')+'颈线 '+Number(row.neckline).toFixed(2);
      label(text,Math.max(bounds.left+65,Math.min(bounds.right-65,(x1+x2)/2)),Math.max(bounds.top+14,y-8),'#e4b85b');
    }
    ctx.restore();
    notice.textContent=`双底／双顶 · 首页日线扫描截至 ${payload.as_of} · `+(rows.length?`当前窗口显示 ${visible}/${rows.length} 个结构 · 实线为颈线，虚线为延伸`:'当前股票暂无符合首页筛选规则的结构');
    notice.title=rows.map(r=>`${r.kind==='bottom'?'双底':'双顶'} · ${r.structure==='clear'?'明确结构':'潜在结构'} · ${r.has_breakout?'已突破':'未突破'} · ${r.points[0].date} / ${r.points[2].date}`).join('\n');
  }
  return {draw};
})();
