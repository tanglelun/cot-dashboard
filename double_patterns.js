(() => {
  const root = document.getElementById('doublePatternSection');
  if (!root) return;
  const list = document.getElementById('doublePatternList');
  const definitions = {bottom:'双底（W底）：下跌后两次测试相近低点，中间反弹高点为颈线。',top:'双顶（M顶）：上涨后两次测试相近高点，中间回落低点为颈线。'};
  const meta = document.getElementById('doublePatternMeta');
  let data, kind = 'bottom';
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
    svg.setAttribute('aria-label', `${row.symbol} ${kind === 'top' ? '双顶（M顶）' : '双底（W底）'}：彩色点为两次峰谷，黄点为颈线位置`);
    const values = row.chart.map(p => p.close).concat(row.points.map(p => p.price), [row.neck_start, row.neck_end]);
    const lo = Math.min(...values), hi = Math.max(...values);
    const x = i => 6 + i * 168 / Math.max(1, row.chart.length - 1);
    const y = v => 58 - (v-lo)*48 / Math.max(.0001,hi-lo);
    function shape(tag, attrs) {
      const node = document.createElementNS(ns, tag);
      Object.entries(attrs).forEach(([k,v]) => node.setAttribute(k,v)); svg.append(node); return node;
    }
    shape('polyline', {points:row.chart.map((p,i)=>`${x(i)},${y(p.close)}`).join(' '), fill:'none', stroke:'#9ba8b8', 'stroke-width':1.4});
    const n1=row.points[1], n2=n1;
    shape('line', {x1:x(row.points[0].offset),y1:y(n1.price),x2:x(n2.offset),y2:y(n2.price),stroke:'#e4b85b','stroke-width':1.4});
    shape('line', {x1:x(n2.offset),y1:y(n2.price),x2:174,y2:y(row.neck_end),stroke:'#e4b85b','stroke-width':1,'stroke-dasharray':'4 3'});
    [n1].forEach((p,i)=>{
      const dot=shape('circle',{cx:x(p.offset),cy:y(p.price),r:2.4,fill:'#e4b85b'});
      const title=document.createElementNS(ns,'title');title.textContent=`颈线连接点 ${i+1} · ${p.date} · ${money(p.price)}`;dot.append(title);
    });
    [0,2].forEach((index,j)=>{
      const p=row.points[index];
      const dot=shape('circle',{cx:x(p.offset),cy:y(p.price),r:2.8,fill:kind==='top'?'#ff7859':'#45d6ae'});
      const title=document.createElementNS(ns,'title');title.textContent=`${['第一次峰谷','第二次峰谷'][j]} · ${p.date} · ${money(p.price)}`;dot.append(title);
    });
    return svg;
  }
  function render() {
    if (!data) return;
    document.getElementById('doublePatternDefinition').textContent=definitions[kind];
    const tier=document.getElementById('doublePatternStructure').value;
    const index=document.getElementById('doublePatternIndex').value;
    const indexLabel=data.constituents[index]?.label || {sp500:'S&P 500',nasdaq100:'Nasdaq 100',russell2000:'Russell 2000 (IWM近似)'}[index];
    const scoped=data.double_patterns.filter(r=>index==='all'||r.indexes.includes(indexLabel));
    root.querySelectorAll('[data-pattern]').forEach(button=>{const k=button.dataset.pattern;button.textContent=(k==='top'?'双顶（M顶）':'双底（W底）')+' ('+scoped.filter(r=>r.kind===k).length+')';});
    const rows=scoped.filter(r=>r.kind===kind && (tier==='all' || r.structure===tier) && (!document.getElementById('doublePatternsConfirmed').checked || r.has_breakout));
    list.replaceChildren();
    if (!rows.length) {list.append(el('div','当前筛选下暂无符合条件的结构。两档均排除圆弧底和缺少两次独立测试的走势。','pattern-empty'));return;}
    rows.forEach(row=>{
      const card=el('div',null,'pattern-row');
      const href='stock_chart.html?symbol='+encodeURIComponent(row.symbol)+'&universe=home-patterns&sort=rank&dir=asc&list=double-patterns&kind='+kind+'&patternIndex='+encodeURIComponent(index)+'&structure='+encodeURIComponent(tier)+'&breakout='+String(document.getElementById('doublePatternsConfirmed').checked)+'&name='+encodeURIComponent(row.name);
      const identity=el('a',null,'pattern-link'); identity.href=href; identity.append(el('strong',row.symbol),el('span',row.name,'pattern-name'));
      const chart=el('a',null,'pattern-mini pattern-link');chart.href=href;chart.append(miniChart(row));
      const price=el('a',null,'pattern-price pattern-link');price.href=href;price.append(el('strong','$'+money(row.price)),el('small','颈线 $'+money(row.neckline)+' · '+(row.distance_pct>0?'+':'')+row.distance_pct.toFixed(2)+'%'));
      const status=el('div',null,'pattern-state');
      const badges=el('div',null,'pattern-badges');
      badges.append(el('span',row.structure==='clear'?'明确':'潜在','pattern-badge '+(row.structure==='clear'?'structure-clear':'structure-potential')));
      badges.append(el('span',row.has_breakout?'已突破':'待突破','pattern-badge'));
      const volumeLabels={expanded:'放量',not_expanded:'未放量',unavailable:'资料不足',not_applicable:'待突破'};
      if(row.has_breakout) badges.append(el('span',volumeLabels[row.volume_state] || '资料不足','pattern-badge '+(row.volume_state==='expanded'?'confirmed':'')));
      status.append(badges);
      const details=el('details',null,'pattern-details');details.append(el('summary','详情'));
      details.append(el('small',row.indexes.join(' · ')));
      status.append(details);
      const reasons={unequal_extremes:'两次峰谷高度差较大',time_asymmetry:'两肩时间不对称',leg_asymmetry:'各段时长不均衡',shoulder_asymmetry:'两肩高度不对称',sloping_neckline:'颈线斜率较大',weaker_rebound:'反弹／回落力度较弱'};
      if(row.structure==='potential') details.append(el('small','待复核：'+row.structure_notes.map(k=>reasons[k] || k).join('、')));
      details.append(el('small','第二峰谷 '+row.second_extreme),el('small',row.has_breakout?'突破识别 '+row.price_breakout_on:'识别 '+row.detected_on));
      if(row.has_breakout && row.volume_ratio!=null) details.append(el('small','突破日量比 '+row.volume_ratio.toFixed(2)+'×（前20日均量）'));
      card.append(identity,chart,price,status);list.append(card);
    });
  }
  root.querySelectorAll('[data-pattern]').forEach(button=>button.addEventListener('click',()=>{
    kind=button.dataset.pattern;
    root.querySelectorAll('[data-pattern]').forEach(b=>{b.classList.toggle('active',b===button);b.setAttribute('aria-pressed',String(b===button));});
    render();
  }));
  document.getElementById('doublePatternsConfirmed').addEventListener('change',render);
  document.getElementById('doublePatternStructure').addEventListener('change',render);
  document.getElementById('doublePatternIndex').addEventListener('change',render);
  async function load() {
    meta.textContent='正在读取形态扫描结果…';
    try {
      const response=await fetch('patterns_data.json',{cache:'no-store'});
      if(!response.ok) throw new Error('unavailable');
      data=await response.json();
      if(!Array.isArray(data.double_patterns) || !data.as_of) throw new Error('invalid');
      meta.textContent=`日线截至 ${data.as_of} · 已扫描 ${data.scanned}/${data.universe_count} 只（去重）`;
      root.querySelectorAll('[data-pattern]').forEach(button=>{const k=button.dataset.pattern;button.textContent=(k==='top'?'双顶（M顶）':'双底（W底）')+' ('+data.double_patterns.filter(r=>r.kind===k).length+')';});
      const coverage=document.getElementById('doublePatternCoverage');
      coverage.textContent=data.skipped.length?`${data.skipped.length} 只因行情缺失、过期或无效未参与：${data.skipped.map(r=>r.symbol).join('、')}`:'完整成分股扫描，无缺失行情。';
      const members=document.getElementById('doublePatternMembership');
      members.textContent=Object.entries(data.constituents).map(([k,v])=>`${v.label || ({sp500:'S&P 500',nasdaq100:'Nasdaq 100',russell2000:'Russell 2000 (IWM近似)'})[k]}：${v.scanned ?? v.count}/${v.count} 只可扫描，名单读取 ${v.date}${v.source_as_of ? '，持仓截至 '+v.source_as_of : ''}${v.excluded_equity_holdings ? '；另排除 '+v.excluded_equity_holdings+' 项未上市或无有效代码持仓' : ''}`).join('；');
      render();
    } catch(error) {
      data=null;meta.textContent='形态数据暂时无法读取';list.replaceChildren(el('div','请稍后重试。原有行情页面不受影响。','pattern-empty'));
      const retry=el('button','重新加载','cross-tab');retry.type='button';retry.addEventListener('click',load);list.append(retry);
    }
  }
  load();
})();
