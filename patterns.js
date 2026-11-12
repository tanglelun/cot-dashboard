(() => {
  const root = document.getElementById('patternSection');
  if (!root) return;
  const list = document.getElementById('patternList');
  const meta = document.getElementById('patternMeta');
  let data, kind = 'top';
  const money = value => Number(value).toLocaleString('en-US', {maximumFractionDigits:2, minimumFractionDigits:2});
  function el(tag, text, cls) {
    const node = document.createElement(tag);
    if (text != null) node.textContent = text;
    if (cls) node.className = cls;
    return node;
  }
  function miniChart(row) {
    const ns = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(ns, 'svg');
    svg.setAttribute('viewBox', '0 0 180 66'); svg.setAttribute('role', 'img');
    svg.setAttribute('aria-label', `${row.symbol} ${kind === 'top' ? '头肩顶' : '头肩底'}：三点为左肩、头部、右肩，虚线为颈线`);
    const values = row.chart.map(p => p.close).concat(row.points.map(p => p.price), [row.neck_start, row.neck_end]);
    const lo = Math.min(...values), hi = Math.max(...values);
    const x = i => 6 + i * 168 / Math.max(1, row.chart.length - 1);
    const y = v => 58 - (v-lo)*48 / Math.max(.0001,hi-lo);
    function shape(tag, attrs) {
      const node = document.createElementNS(ns, tag);
      Object.entries(attrs).forEach(([k,v]) => node.setAttribute(k,v)); svg.append(node); return node;
    }
    shape('polyline', {points:row.chart.map((p,i)=>`${x(i)},${y(p.close)}`).join(' '), fill:'none', stroke:'#9ba8b8', 'stroke-width':1.4});
    shape('line', {x1:6,y1:y(row.neck_start),x2:174,y2:y(row.neck_end),stroke:'#e4b85b','stroke-width':1,'stroke-dasharray':'4 3'});
    [0,2,4].forEach((index,j)=>{
      const p=row.points[index];
      const dot=shape('circle',{cx:x(p.offset),cy:y(p.price),r:2.8,fill:kind==='top'?'#ff7859':'#45d6ae'});
      const title=document.createElementNS(ns,'title');title.textContent=`${['左肩','头部','右肩'][j]} · ${p.date} · ${money(p.price)}`;dot.append(title);
    });
    return svg;
  }
  function render() {
    if (!data) return;
    const rows=data.patterns.filter(r=>r.kind===kind && (!document.getElementById('patternsConfirmed').checked || r.status==='confirmed'));
    list.replaceChildren();
    if (!rows.length) {list.append(el('div','当前筛选下没有符合规则的形态。','pattern-empty'));return;}
    rows.forEach(row=>{
      const card=el('a',null,'pattern-row');
      card.href='stock_chart.html?symbol='+encodeURIComponent(row.symbol)+'&universe=all&name='+encodeURIComponent(row.name);
      const identity=el('div'); identity.append(el('strong',row.symbol),el('span',row.name,'pattern-name'),el('small',row.indexes.join(' · '),'pattern-index'));
      const chart=el('div',null,'pattern-mini');chart.append(miniChart(row));
      const price=el('div',null,'pattern-price');price.append(el('strong','$'+money(row.price)),el('small','颈线 $'+money(row.neckline)),el('small','距颈线 '+(row.distance_pct>0?'+':'')+row.distance_pct.toFixed(2)+'%'));
      const status=el('div',null,'pattern-state');status.append(el('span',row.status==='confirmed'?'已突破颈线':'候选 · 未突破',row.status==='confirmed'?'pattern-badge confirmed':'pattern-badge'));
      status.append(el('small','右肩 '+row.right_shoulder),el('small',row.status==='confirmed'?'确认 '+row.confirmed_on:'识别 '+row.detected_on));
      card.append(identity,chart,price,status);list.append(card);
    });
  }
  root.querySelectorAll('[data-pattern]').forEach(button=>button.addEventListener('click',()=>{
    kind=button.dataset.pattern;
    root.querySelectorAll('[data-pattern]').forEach(b=>{b.classList.toggle('active',b===button);b.setAttribute('aria-pressed',String(b===button));});
    render();
  }));
  document.getElementById('patternsConfirmed').addEventListener('change',render);
  async function load() {
    meta.textContent='正在读取形态扫描结果…';
    try {
      const response=await fetch('patterns_data.json',{cache:'no-store'});
      if(!response.ok) throw new Error('unavailable');
      data=await response.json();
      if(!Array.isArray(data.patterns) || !data.as_of) throw new Error('invalid');
      meta.textContent=`日线截至 ${data.as_of} · 已扫描 ${data.scanned}/${data.universe_count} 只（去重）`;
      root.querySelectorAll('[data-pattern]').forEach(button=>{const k=button.dataset.pattern;button.textContent=(k==='top'?'头肩顶':'头肩底')+' ('+data.patterns.filter(r=>r.kind===k).length+')';});
      const coverage=document.getElementById('patternCoverage');
      coverage.textContent=data.skipped.length?`${data.skipped.length} 只因行情缺失、过期或无效未参与：${data.skipped.map(r=>r.symbol).join('、')}`:'完整成分股扫描，无缺失行情。';
      const members=document.getElementById('patternMembership');
      members.textContent=Object.entries(data.constituents).map(([k,v])=>`${k==='sp500'?'S&P 500':'Nasdaq 100'}：${v.count} 只，名单读取日期 ${v.date}`).join('；');
      render();
    } catch(error) {
      data=null;meta.textContent='形态数据暂时无法读取';list.replaceChildren(el('div','请稍后重试。原有行情页面不受影响。','pattern-empty'));
      const retry=el('button','重新加载','cross-tab');retry.type='button';retry.addEventListener('click',load);list.append(retry);
    }
  }
  load();
})();
