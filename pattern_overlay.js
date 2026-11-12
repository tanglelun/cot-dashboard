// Shares the homepage scan instead of maintaining a second recognition algorithm.
window.patternOverlay = (() => {
  let data, error=false, loading;
  function load(){
    if(!loading) loading=fetch('patterns_data.json',{cache:'no-store'}).then(r=>{if(!r.ok)throw Error();return r.json();}).then(value=>{if(value.method_version<3 || !Array.isArray(value.patterns))throw Error();data=value;}).catch(()=>{error=true;});
    return loading;
  }
  function draw(ctx, symbol, candles, xFor, yFor, bounds, notice){
    if(!data){notice.textContent=error?'头肩形态数据读取失败，请刷新重试。':'正在加载头肩形态…';return;}
    const rows=data.patterns.filter(r=>r.symbol.replaceAll('.','-')===symbol.replaceAll('.','-'));
    notice.textContent=`头肩形态 · 扫描截至 ${data.as_of} · `+(rows.length?rows.map(r=>`${r.kind==='bottom'?'头肩底':'头肩顶'} / ${r.structure==='clear'?'明确':'潜在'} / ${r.has_breakout?'已突破':'未突破'} / ${{expanded:'突破放量',not_expanded:'突破未放量',unavailable:'量能资料不足',not_applicable:'量能待突破'}[r.volume_state]}`).join('；'):'当前扫描无匹配结构（范围：标普500、纳指100、IWM近似罗素2000）。');
    const indices=new Map(candles.map((c,i)=>[c.time,i]));
    let visible=false;
    ctx.save();ctx.beginPath();ctx.rect(bounds.left,bounds.top,bounds.right-bounds.left,bounds.bottom-bounds.top);ctx.clip();
    for(const row of rows){
      const points=row.points.map(p=>({...p,index:indices.get(p.date)}));
      // Only draw complete structures in the visible window; never invent endpoints.
      if(points.some(p=>p.index===undefined))continue;
      visible=true;
      const color=row.kind==='bottom'?'#45d6ae':'#ff7859';
      ctx.strokeStyle=color;ctx.lineWidth=1.5;ctx.setLineDash([3,3]);ctx.beginPath();
      points.forEach((p,i)=>{const x=xFor(p.index),y=yFor(p.price);if(i)ctx.lineTo(x,y);else ctx.moveTo(x,y);});ctx.stroke();ctx.setLineDash([]);
      [0,2,4].forEach((n,j)=>{const p=points[n],x=xFor(p.index),y=yFor(p.price);ctx.fillStyle=color;ctx.beginPath();ctx.arc(x,y,3,0,Math.PI*2);ctx.fill();ctx.font='bold 12px Arial';ctx.textAlign='center';const ty=Math.max(bounds.top+14,Math.min(bounds.bottom-5,y+(row.kind==='bottom'?18:-12)));ctx.strokeStyle='#000';ctx.lineWidth=3;ctx.strokeText(['左肩','头部','右肩'][j],x,ty);ctx.fillText(['左肩','头部','右肩'][j],x,ty);});
      const a=points[1],b=points[3];ctx.strokeStyle='#e4b85b';ctx.lineWidth=1.5;ctx.beginPath();ctx.moveTo(xFor(a.index),yFor(a.price));ctx.lineTo(xFor(b.index),yFor(b.price));ctx.stroke();
      ctx.fillStyle='#e4b85b';ctx.textAlign='center';ctx.fillText('颈线',(xFor(a.index)+xFor(b.index))/2,Math.max(bounds.top+14,yFor((a.price+b.price)/2)-8));
    }
    ctx.restore();
    if(rows.length&&!visible)notice.textContent+=' · 请扩大时间范围查看完整结构';
  }
  return {load,draw};
})();
