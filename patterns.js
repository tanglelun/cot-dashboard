(() => {
  const root = document.getElementById('patternSection');
  if (!root) return;
  const list = document.getElementById('patternList');
  const definitions = {bottom:'头肩底：下跌后出现三个独立低谷，中间最低；两次明显反弹连接成颈线。',top:'头肩顶：上涨后出现三个独立高峰，中间最高；两次明显回落连接成颈线。'};
  const meta = document.getElementById('patternMeta');
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
    svg.setAttribute('aria-label', `${row.symbol} ${kind === 'top' ? '头肩顶' : '头肩底'}：彩色点为左肩、头部、右肩，黄点为两次反弹或回落的颈线连接点`);
    const values = row.chart.map(p => p.close).concat(row.points.map(p => p.price), [row.neck_start, row.neck_end]);
    const lo = Math.min(...values), hi = Math.max(...values);
    const x = i => 6 + i * 168 / Math.max(1, row.chart.length - 1);
    const y = v => 58 - (v-lo)*48 / Math.max(.0001,hi-lo);
    function shape(tag, attrs) {
      const node = document.createElementNS(ns, tag);
      Object.entries(attrs).forEach(([k,v]) => node.setAttribute(k,v)); svg.append(node); return node;
    }
    shape('polyline', {points:row.chart.map((p,i)=>`${x(i)},${y(p.close)}`).join(' '), fill:'none', stroke:'#9ba8b8', 'stroke-width':1.4});
    const [n1,n2]=[row.points[1],row.points[3]];
    shape('line', {x1:x(n1.offset),y1:y(n1.price),x2:x(n2.offset),y2:y(n2.price),stroke:'#e4b85b','stroke-width':1.4});
    shape('line', {x1:x(n2.offset),y1:y(n2.price),x2:174,y2:y(row.neck_end),stroke:'#e4b85b','stroke-width':1,'stroke-dasharray':'4 3'});
    [n1,n2].forEach((p,i)=>{
      const dot=shape('circle',{cx:x(p.offset),cy:y(p.price),r:2.4,fill:'#e4b85b'});
      const title=document.createElementNS(ns,'title');title.textContent=`颈线连接点 ${i+1} · ${p.date} · ${money(p.price)}`;dot.append(title);
    });
    [0,2,4].forEach((index,j)=>{
      const p=row.points[index];
      const dot=shape('circle',{cx:x(p.offset),cy:y(p.price),r:2.8,fill:kind==='top'?'#ff7859':'#45d6ae'});
      const title=document.createElementNS(ns,'title');title.textContent=`${['左肩','头部','右肩'][j]} · ${p.date} · ${money(p.price)}`;dot.append(title);
    });
    return svg;
  }
  function render() {
    if (!data) return;
    document.getElementById('patternDefinition').textContent=definitions[kind];
    const tier=document.getElementById('patternStructure').value;
    const rows=data.patterns.filter(r=>r.kind===kind && (tier==='all' || r.structure===tier) && (!document.getElementById('patternsConfirmed').checked || r.has_breakout));
    list.replaceChildren();
    if (!rows.length) {list.append(el('div','当前筛选下暂无符合条件的结构。两档均排除圆弧底和缺少独立肩部的走势。','pattern-empty'));return;}
    rows.forEach(row=>{
      const card=el('a',null,'pattern-row');
      card.href='stock_chart.html?symbol='+encodeURIComponent(row.symbol)+'&universe=all&name='+encodeURIComponent(row.name);
      const identity=el('div'); identity.append(el('strong',row.symbol),el('span',row.name,'pattern-name'),el('small',row.indexes.join(' · '),'pattern-index'));
      const chart=el('div',null,'pattern-mini');chart.append(miniChart(row));
      const price=el('div',null,'pattern-price');price.append(el('strong','$'+money(row.price)),el('small','颈线 $'+money(row.neckline)),el('small','距颈线 '+(row.distance_pct>0?'+':'')+row.distance_pct.toFixed(2)+'%'));
      const status=el('div',null,'pattern-state');
      const badges=el('div',null,'pattern-badges');
      badges.append(el('span',row.structure==='clear'?'明确结构':'潜在结构','pattern-badge '+(row.structure==='clear'?'structure-clear':'structure-potential')));
      badges.append(el('span',row.has_breakout?'颈线：已突破':'颈线：未突破','pattern-badge'));
      const volumeLabels={expanded:'突破量能：放量',not_expanded:'突破量能：未放量',unavailable:'突破量能：资料不足',not_applicable:'突破量能：待突破'};
      badges.append(el('span',volumeLabels[row.volume_state] || '突破量能：资料不足','pattern-badge '+(row.volume_state==='expanded'?'confirmed':'')));
      status.append(badges);
      const reasons={time_asymmetry:'两肩时间不对称',leg_asymmetry:'各段时长不均衡',shoulder_asymmetry:'两肩高度不对称',sloping_neckline:'颈线斜率较大',weaker_rebound:'反弹／回落力度较弱'};
      if(row.structure==='potential') status.append(el('small','待复核：'+row.structure_notes.map(k=>reasons[k] || k).join('、')));
      status.append(el('small','右肩 '+row.right_shoulder),el('small',row.has_breakout?'突破识别 '+row.price_breakout_on:'识别 '+row.detected_on));
      if(row.has_breakout && row.volume_ratio!=null) status.append(el('small','突破日量比 '+row.volume_ratio.toFixed(2)+'×（前20日均量）'));
      card.append(identity,chart,price,status);list.append(card);
    });
  }
  root.querySelectorAll('[data-pattern]').forEach(button=>button.addEventListener('click',()=>{
    kind=button.dataset.pattern;
    root.querySelectorAll('[data-pattern]').forEach(b=>{b.classList.toggle('active',b===button);b.setAttribute('aria-pressed',String(b===button));});
    render();
  }));
  document.getElementById('patternsConfirmed').addEventListener('change',render);
  document.getElementById('patternStructure').addEventListener('change',render);
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
      members.textContent=Object.entries(data.constituents).map(([k,v])=>`${v.label || ({sp500:'S&P 500',nasdaq100:'Nasdaq 100',russell2000:'Russell 2000 (IWM近似)'})[k]}：${v.scanned ?? v.count}/${v.count} 只可扫描，名单读取 ${v.date}${v.source_as_of ? '，持仓截至 '+v.source_as_of : ''}${v.excluded_equity_holdings ? '；另排除 '+v.excluded_equity_holdings+' 项未上市或无有效代码持仓' : ''}`).join('；');
      render();
    } catch(error) {
      data=null;meta.textContent='形态数据暂时无法读取';list.replaceChildren(el('div','请稍后重试。原有行情页面不受影响。','pattern-empty'));
      const retry=el('button','重新加载','cross-tab');retry.type='button';retry.addEventListener('click',load);list.append(retry);
    }
  }
  load();
})();
