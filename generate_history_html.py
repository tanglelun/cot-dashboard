import pandas as pd
import os
import json
from html import escape

df = pd.read_csv('cot_noncommercial_history.csv')
if os.path.exists('price_history.csv'):
    df_prices = pd.read_csv('price_history.csv')
else:
    df_prices = pd.DataFrame(columns=['Date', 'Commodity', 'Price'])

categories = {
    'Grains': ['Corn', 'Soybeans', 'Soybean Meal', 'Soybean Oil', 'Wheat',
               'Hard Red Winter Wheat', 'Spring Wheat Mpls', 'Rough Rice', 'Canola', 'Oats'],
    'Energies': ['Crude Oil', 'Natural Gas'],
    'Metals': ['Gold', 'Silver', 'Copper', 'Platinum', 'Palladium'],
    'Softs': ['Coffee', 'Sugar', 'Cocoa', 'Cotton', 'Orange Juice'],
    'Livestock': ['Live Cattle', 'Lean Hogs', 'Feeder Cattle'],
    'Currencies': ['Euro FX', 'British Pound', 'Japanese Yen', 'Swiss Franc', 
                 'Australian Dollar', 'Canadian Dollar', 'Mexican Peso', 'U.S. Dollar Index'],
    'Indices': ['S&P 500', 'S&P 500 Micro', 'Nasdaq 100', 'Dow Jones', 'Russell 2000'],
    'Treasuries': ['10-Year T-Note', '5-Year T-Note', '2-Year T-Note', '30-Year T-Bond']
}

code_map = {
    'Corn': 'ZC', 'Soybeans': 'ZS', 'Soybean Meal': 'ZM', 'Soybean Oil': 'ZL',
    'Wheat': 'ZW', 'Hard Red Winter Wheat': 'KE', 'Spring Wheat Mpls': 'MWE',
    'Rough Rice': 'ZR', 'Canola': 'RS', 'Oats': 'ZO',
    'Crude Oil': 'CL', 'Natural Gas': 'NG', 'Gold': 'GC', 'Silver': 'SI',
    'Copper': 'HG', 'Platinum': 'PL', 'Palladium': 'PA', 'Coffee': 'KC', 'Sugar': 'SB',
    'Cocoa': 'CC', 'Cotton': 'CT', 'Orange Juice': 'OJ', 'Live Cattle': 'LE', 
    'Lean Hogs': 'HE', 'Feeder Cattle': 'GF', 'Euro FX': 'EC', 'British Pound': 'BP',
    'Japanese Yen': 'JY', 'Swiss Franc': 'SF', 'Australian Dollar': 'AD', 
    'Canadian Dollar': 'CD', 'Mexican Peso': 'MP', 'U.S. Dollar Index': 'DX',
    'S&P 500': 'ES', 'S&P 500 Micro': 'MES', 'Nasdaq 100': 'NQ', 'Dow Jones': 'YM',
    'Russell 2000': 'RTY', '10-Year T-Note': 'TY', '5-Year T-Note': 'FV',
    '2-Year T-Note': 'TU', '30-Year T-Bond': 'US'
}

def get_commodity_data(comm):
    return df[df['Commodity'] == comm].sort_values(by='Date')

os.makedirs('charts', exist_ok=True)

def get_futures_index_data(comm, chart_dates):
    price_data = df_prices[df_prices['Commodity'] == comm].copy()
    if price_data.empty:
        return [None] * len(chart_dates)

    price_data['Date'] = pd.to_datetime(price_data['Date'])
    price_data['Price'] = pd.to_numeric(price_data['Price'], errors='coerce')
    price_data = price_data.dropna(subset=['Date', 'Price']).sort_values('Date')
    if price_data.empty:
        return [None] * len(chart_dates)

    cot_dates = pd.DataFrame({'Date': pd.to_datetime(chart_dates)})
    aligned = pd.merge_asof(
        cot_dates.sort_values('Date'),
        price_data[['Date', 'Price']],
        on='Date',
        direction='backward',
        tolerance=pd.Timedelta(days=7),
    )

    first_price = aligned['Price'].dropna()
    if first_price.empty or first_price.iloc[0] == 0:
        return [None] * len(chart_dates)

    base_price = first_price.iloc[0]
    index_values = (aligned['Price'] / base_price * 100).round(2)
    return [None if pd.isna(value) else float(value) for value in index_values]

def write_chart_html(comm, code, chart_dates, net_values, filename):
    safe_title = escape(f"{comm} ({code})")
    index_values = get_futures_index_data(comm, chart_dates)
    chart_points = []
    for date, value, index_value in zip(chart_dates, net_values, index_values):
        try:
            numeric_value = int(value)
        except (TypeError, ValueError):
            continue
        chart_points.append({
            "date": str(date),
            "value": numeric_value,
            "index": index_value,
        })

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{safe_title}</title>
    <style>
        * {{ box-sizing: border-box; }}
        html, body {{ height: 100%; }}
        body {{ margin: 0; background: #f7f8fb; color: #172033; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
        .toolbar {{ display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 16px 20px 10px; }}
        h1 {{ margin: 0; font-size: 20px; font-weight: 700; }}
        .meta {{ color: #5e6a7d; font-size: 13px; white-space: nowrap; }}
        .legend-inline {{ display: flex; align-items: center; gap: 14px; margin-top: 4px; color: #5e6a7d; font-size: 12px; }}
        .legend-item {{ display: inline-flex; align-items: center; gap: 6px; }}
        .legend-swatch {{ width: 18px; height: 3px; border-radius: 999px; display: inline-block; }}
        .legend-bar {{ background: #0a8f62; }}
        .legend-line {{ background: #2f7df6; }}
        .chart-wrap {{ position: relative; height: calc(100vh - 62px); min-height: 420px; padding: 0 14px 14px; }}
        canvas {{ display: block; width: 100%; height: 100%; background: #ffffff; border: 1px solid #dbe1ea; border-radius: 8px; }}
        .tooltip {{ position: fixed; pointer-events: none; display: none; background: rgba(23, 32, 51, 0.95); color: white; padding: 8px 10px; border-radius: 6px; font-size: 12px; line-height: 1.35; box-shadow: 0 8px 24px rgba(23, 32, 51, 0.22); }}
        .value-pos {{ color: #0a8f62; }}
        .value-neg {{ color: #c7354f; }}
        .dragging {{ cursor: grabbing; }}
        @media (max-width: 640px) {{
            .toolbar {{ align-items: flex-start; flex-direction: column; gap: 4px; }}
            .meta {{ white-space: normal; }}
            .chart-wrap {{ height: calc(100vh - 92px); min-height: 360px; }}
        }}
    </style>
</head>
<body>
    <div class="toolbar">
        <div>
            <h1>{safe_title}</h1>
            <div class="legend-inline">
                <span class="legend-item"><span class="legend-swatch legend-bar"></span>Non-Commercial Net</span>
                <span class="legend-item"><span class="legend-swatch legend-line"></span>Futures Index (base=100)</span>
            </div>
        </div>
        <div id="meta" class="meta">Non-Commercial Net | Weekly bars | Last {len(chart_points)} reports</div>
    </div>
    <div class="chart-wrap">
        <canvas id="chart"></canvas>
        <div id="tooltip" class="tooltip"></div>
    </div>
    <script>
        const points = {json.dumps(chart_points, ensure_ascii=True)};
        const canvas = document.getElementById('chart');
        const tooltip = document.getElementById('tooltip');
        const meta = document.getElementById('meta');
        const ctx = canvas.getContext('2d');
        const defaultWeeks = Math.min(52, points.length);
        const state = {{
            hoverIndex: -1,
            start: Math.max(0, points.length - defaultWeeks),
            end: Math.max(0, points.length - 1),
            dragMode: null,
            dragStartX: 0,
            dragStartRange: null
        }};

        const formatNumber = value => value.toLocaleString('en-US');
        const getColor = value => value >= 0 ? '#0a8f62' : '#c7354f';
        const clamp = (value, min, max) => Math.max(min, Math.min(max, value));
        const minWindow = Math.min(4, points.length);
        let layout = null;

        function setRange(start, end) {{
            if (!points.length) return;
            let nextStart = clamp(Math.round(start), 0, points.length - 1);
            let nextEnd = clamp(Math.round(end), 0, points.length - 1);
            if (nextEnd < nextStart) [nextStart, nextEnd] = [nextEnd, nextStart];
            if (nextEnd - nextStart + 1 < minWindow) {{
                if (state.dragMode === 'start') {{
                    nextStart = Math.max(0, nextEnd - minWindow + 1);
                }} else {{
                    nextEnd = Math.min(points.length - 1, nextStart + minWindow - 1);
                }}
            }}
            state.start = nextStart;
            state.end = nextEnd;
            state.hoverIndex = -1;
            updateMeta();
            draw();
        }}

        function updateMeta() {{
            if (!points.length) return;
            const weeks = state.end - state.start + 1;
            const hasIndex = points.some(point => point.index !== null);
            const suffix = hasIndex ? ' | Futures Index base=100' : '';
            meta.textContent = `Non-Commercial Net | Weekly bars | ${{points[state.start].date}} to ${{points[state.end].date}} | ${{weeks}} weeks${{suffix}}`;
        }}

        function resizeCanvas() {{
            const ratio = window.devicePixelRatio || 1;
            const rect = canvas.getBoundingClientRect();
            canvas.width = Math.max(1, Math.round(rect.width * ratio));
            canvas.height = Math.max(1, Math.round(rect.height * ratio));
            ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
            draw();
        }}

        function draw() {{
            const width = canvas.clientWidth;
            const height = canvas.clientHeight;
            ctx.clearRect(0, 0, width, height);

            if (!points.length) {{
                ctx.fillStyle = '#5e6a7d';
                ctx.font = '14px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';
                ctx.fillText('No chart data available', 28, 38);
                return;
            }}

            const hasIndex = points.some(point => point.index !== null);
            const pad = {{ left: 76, right: hasIndex ? 76 : 24, top: 28, bottom: 122 }};
            const plotW = width - pad.left - pad.right;
            const plotH = height - pad.top - pad.bottom;
            const slider = {{
                left: pad.left,
                right: width - pad.right,
                top: height - 78,
                height: 34,
                bottom: height - 44
            }};
            layout = {{ pad, plotW, plotH, slider }};

            const visiblePoints = points.slice(state.start, state.end + 1);
            const values = visiblePoints.map(point => point.value);
            const indexValues = visiblePoints.map(point => point.index).filter(value => value !== null);
            const maxAbs = Math.max(1, ...values.map(value => Math.abs(value)));
            const minValue = Math.min(...values, 0);
            const maxValue = Math.max(...values, 0);
            const yMin = Math.min(minValue, -maxAbs * 0.08);
            const yMax = Math.max(maxValue, maxAbs * 0.08);
            const yRange = yMax - yMin || 1;
            const yFor = value => pad.top + (yMax - value) / yRange * plotH;
            const zeroY = yFor(0);
            const indexMin = indexValues.length ? Math.min(...indexValues) : null;
            const indexMax = indexValues.length ? Math.max(...indexValues) : null;
            const indexPadding = indexValues.length ? Math.max(2, (indexMax - indexMin) * 0.12) : 0;
            const indexYMin = indexValues.length ? indexMin - indexPadding : 0;
            const indexYMax = indexValues.length ? indexMax + indexPadding : 1;
            const indexRange = indexYMax - indexYMin || 1;
            const indexYFor = value => pad.top + (indexYMax - value) / indexRange * plotH;
            const visibleCount = visiblePoints.length;
            const step = plotW / visibleCount;
            const barW = Math.max(2, Math.min(22, step * 0.72));

            ctx.fillStyle = '#ffffff';
            ctx.fillRect(0, 0, width, height);

            ctx.strokeStyle = '#e3e8f0';
            ctx.lineWidth = 1;
            ctx.fillStyle = '#5e6a7d';
            ctx.font = '12px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';
            ctx.textAlign = 'right';
            ctx.textBaseline = 'middle';
            for (let tick = 0; tick <= 4; tick++) {{
                const value = yMin + (yRange * tick / 4);
                const y = yFor(value);
                ctx.beginPath();
                ctx.moveTo(pad.left, y);
                ctx.lineTo(width - pad.right, y);
                ctx.stroke();
                ctx.fillText(formatNumber(Math.round(value)), pad.left - 10, y);
            }}

            if (indexValues.length) {{
                ctx.fillStyle = '#2f7df6';
                ctx.textAlign = 'left';
                ctx.textBaseline = 'middle';
                for (let tick = 0; tick <= 4; tick++) {{
                    const value = indexYMin + (indexRange * tick / 4);
                    const y = indexYFor(value);
                    ctx.fillText(value.toFixed(1), width - pad.right + 10, y);
                }}
                ctx.fillText('Index', width - pad.right + 10, pad.top - 10);
            }}

            ctx.strokeStyle = '#9aa6b6';
            ctx.beginPath();
            ctx.moveTo(pad.left, zeroY);
            ctx.lineTo(width - pad.right, zeroY);
            ctx.stroke();

            visiblePoints.forEach((point, index) => {{
                const x = pad.left + index * step + step / 2;
                const y = yFor(point.value);
                const barTop = Math.min(y, zeroY);
                const barH = Math.max(1, Math.abs(zeroY - y));
                ctx.fillStyle = getColor(point.value);
                ctx.globalAlpha = index === state.hoverIndex ? 1 : 0.86;
                ctx.fillRect(x - barW / 2, barTop, barW, barH);
            }});
            ctx.globalAlpha = 1;

            const linePoints = visiblePoints
                .map((point, index) => ({{
                    x: pad.left + index * step + step / 2,
                    y: point.index === null ? null : indexYFor(point.index),
                    value: point.index
                }}))
                .filter(point => point.y !== null);
            if (linePoints.length > 1) {{
                ctx.strokeStyle = '#2f7df6';
                ctx.lineWidth = 2.5;
                ctx.beginPath();
                linePoints.forEach((point, index) => {{
                    if (index === 0) ctx.moveTo(point.x, point.y);
                    else ctx.lineTo(point.x, point.y);
                }});
                ctx.stroke();

                if (state.hoverIndex >= 0) {{
                    const point = visiblePoints[state.hoverIndex];
                    if (point.index !== null) {{
                        const x = pad.left + state.hoverIndex * step + step / 2;
                        const y = indexYFor(point.index);
                        ctx.fillStyle = '#ffffff';
                        ctx.strokeStyle = '#2f7df6';
                        ctx.lineWidth = 2;
                        ctx.beginPath();
                        ctx.arc(x, y, 4, 0, Math.PI * 2);
                        ctx.fill();
                        ctx.stroke();
                    }}
                }}
            }}

            ctx.fillStyle = '#5e6a7d';
            ctx.textAlign = 'center';
            ctx.textBaseline = 'top';
            const labelEvery = Math.max(1, Math.ceil(visibleCount / Math.max(4, Math.floor(plotW / 82))));
            visiblePoints.forEach((point, index) => {{
                if (index % labelEvery !== 0 && index !== visiblePoints.length - 1) return;
                const x = pad.left + index * step + step / 2;
                ctx.save();
                ctx.translate(x, height - pad.bottom + 26);
                ctx.rotate(-Math.PI / 4);
                ctx.fillText(point.date.slice(5), 0, 0);
                ctx.restore();
            }});

            if (state.hoverIndex >= 0) {{
                const x = pad.left + state.hoverIndex * step + step / 2;
                ctx.strokeStyle = '#172033';
                ctx.globalAlpha = 0.26;
                ctx.beginPath();
                ctx.moveTo(x, pad.top);
                ctx.lineTo(x, height - pad.bottom);
                ctx.stroke();
                ctx.globalAlpha = 1;
            }}

            drawSlider(slider);
        }}

        function drawSlider(slider) {{
            const trackW = slider.right - slider.left;
            const yMid = slider.top + slider.height / 2;
            const allValues = points.map(point => point.value);
            const maxAbs = Math.max(1, ...allValues.map(value => Math.abs(value)));
            const miniH = 24;
            const miniTop = slider.top + 5;
            const miniZero = miniTop + miniH / 2;
            const miniStep = trackW / points.length;
            const miniBarW = Math.max(1, miniStep * 0.72);
            const xForIndex = index => slider.left + index / Math.max(1, points.length - 1) * trackW;
            const startX = xForIndex(state.start);
            const endX = xForIndex(state.end);

            ctx.fillStyle = '#f4f7fb';
            ctx.fillRect(slider.left, slider.top, trackW, slider.height);
            ctx.strokeStyle = '#d8e0eb';
            ctx.strokeRect(slider.left, slider.top, trackW, slider.height);

            points.forEach((point, index) => {{
                const x = slider.left + index * miniStep + miniStep / 2;
                const barH = Math.max(1, Math.abs(point.value) / maxAbs * miniH / 2);
                ctx.fillStyle = getColor(point.value);
                ctx.globalAlpha = 0.34;
                if (point.value >= 0) {{
                    ctx.fillRect(x - miniBarW / 2, miniZero - barH, miniBarW, barH);
                }} else {{
                    ctx.fillRect(x - miniBarW / 2, miniZero, miniBarW, barH);
                }}
            }});
            ctx.globalAlpha = 1;

            ctx.fillStyle = 'rgba(23, 32, 51, 0.10)';
            ctx.fillRect(slider.left, slider.top, Math.max(0, startX - slider.left), slider.height);
            ctx.fillRect(endX, slider.top, Math.max(0, slider.right - endX), slider.height);

            ctx.fillStyle = 'rgba(76, 139, 245, 0.16)';
            ctx.fillRect(startX, slider.top, Math.max(2, endX - startX), slider.height);
            ctx.strokeStyle = '#3b74d7';
            ctx.lineWidth = 2;
            ctx.strokeRect(startX, slider.top, Math.max(2, endX - startX), slider.height);

            [startX, endX].forEach(x => {{
                ctx.fillStyle = '#ffffff';
                ctx.strokeStyle = '#3b74d7';
                ctx.lineWidth = 2;
                ctx.beginPath();
                ctx.roundRect(x - 6, slider.top - 4, 12, slider.height + 8, 5);
                ctx.fill();
                ctx.stroke();
                ctx.strokeStyle = '#9aa6b6';
                ctx.lineWidth = 1;
                ctx.beginPath();
                ctx.moveTo(x - 2, yMid - 7);
                ctx.lineTo(x - 2, yMid + 7);
                ctx.moveTo(x + 2, yMid - 7);
                ctx.lineTo(x + 2, yMid + 7);
                ctx.stroke();
            }});

            ctx.fillStyle = '#5e6a7d';
            ctx.font = '12px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';
            ctx.textAlign = 'left';
            ctx.textBaseline = 'top';
            ctx.fillText(points[state.start].date, slider.left, slider.bottom + 8);
            ctx.textAlign = 'right';
            ctx.fillText(points[state.end].date, slider.right, slider.bottom + 8);
        }}

        function updateHover(event) {{
            if (state.dragMode) return;
            const rect = canvas.getBoundingClientRect();
            const width = canvas.clientWidth;
            if (!layout) return;
            const {{ pad, plotW, slider }} = layout;
            const x = event.clientX - rect.left;
            const y = event.clientY - rect.top;
            const visibleCount = state.end - state.start + 1;
            const step = plotW / visibleCount;
            const index = Math.round((x - pad.left - step / 2) / step);

            if (y >= slider.top || index < 0 || index >= visibleCount) {{
                state.hoverIndex = -1;
                tooltip.style.display = 'none';
                draw();
                return;
            }}

            state.hoverIndex = index;
            const point = points[state.start + index];
            const indexLine = point.index === null ? '' : `<br><span style="color:#72a8ff">Futures Index: ${{point.index.toFixed(2)}}</span>`;
            tooltip.innerHTML = `<strong>${{point.date}}</strong><br><span class="${{point.value >= 0 ? 'value-pos' : 'value-neg'}}">Net: ${{formatNumber(point.value)}}</span>${{indexLine}}`;
            tooltip.style.display = 'block';
            tooltip.style.left = `${{Math.min(event.clientX + 12, window.innerWidth - tooltip.offsetWidth - 12)}}px`;
            tooltip.style.top = `${{Math.min(event.clientY + 12, window.innerHeight - tooltip.offsetHeight - 12)}}px`;
            draw();
        }}

        function getSliderHit(x, y) {{
            if (!layout || !points.length) return null;
            const {{ slider }} = layout;
            if (y < slider.top - 12 || y > slider.bottom + 12 || x < slider.left - 12 || x > slider.right + 12) return null;
            const trackW = slider.right - slider.left;
            const xForIndex = index => slider.left + index / Math.max(1, points.length - 1) * trackW;
            const startX = xForIndex(state.start);
            const endX = xForIndex(state.end);
            if (Math.abs(x - startX) <= 12) return 'start';
            if (Math.abs(x - endX) <= 12) return 'end';
            if (x > startX && x < endX) return 'window';
            return null;
        }}

        function pointerToIndex(x) {{
            const {{ slider }} = layout;
            const pct = clamp((x - slider.left) / (slider.right - slider.left), 0, 1);
            return Math.round(pct * (points.length - 1));
        }}

        function startDrag(event) {{
            const rect = canvas.getBoundingClientRect();
            const x = event.clientX - rect.left;
            const y = event.clientY - rect.top;
            const hit = getSliderHit(x, y);
            if (!hit) return;
            state.dragMode = hit;
            state.dragStartX = x;
            state.dragStartRange = {{ start: state.start, end: state.end }};
            canvas.classList.add('dragging');
            canvas.setPointerCapture(event.pointerId);
            tooltip.style.display = 'none';
            event.preventDefault();
        }}

        function moveDrag(event) {{
            const rect = canvas.getBoundingClientRect();
            const x = event.clientX - rect.left;
            if (!state.dragMode) {{
                const y = event.clientY - rect.top;
                const hit = getSliderHit(x, y);
                canvas.style.cursor = hit === 'start' || hit === 'end' ? 'ew-resize' : hit === 'window' ? 'grab' : 'default';
                return;
            }}

            if (state.dragMode === 'start') {{
                setRange(pointerToIndex(x), state.end);
            }} else if (state.dragMode === 'end') {{
                setRange(state.start, pointerToIndex(x));
            }} else if (state.dragMode === 'window') {{
                const deltaIndex = pointerToIndex(x) - pointerToIndex(state.dragStartX);
                const width = state.dragStartRange.end - state.dragStartRange.start;
                let nextStart = clamp(state.dragStartRange.start + deltaIndex, 0, points.length - width - 1);
                setRange(nextStart, nextStart + width);
            }}
            event.preventDefault();
        }}

        function endDrag(event) {{
            if (!state.dragMode) return;
            state.dragMode = null;
            state.dragStartRange = null;
            canvas.classList.remove('dragging');
            canvas.releasePointerCapture(event.pointerId);
            event.preventDefault();
        }}

        canvas.addEventListener('mousemove', updateHover);
        canvas.addEventListener('mouseleave', () => {{
            state.hoverIndex = -1;
            tooltip.style.display = 'none';
            draw();
        }});
        canvas.addEventListener('pointerdown', startDrag);
        canvas.addEventListener('pointermove', moveDrag);
        canvas.addEventListener('pointerup', endDrag);
        canvas.addEventListener('pointercancel', endDrag);
        window.addEventListener('resize', resizeCanvas);
        updateMeta();
        resizeCanvas();
    </script>
</body>
</html>'''

    with open(filename, 'w', encoding='utf-8') as f:
        f.write(html)

for category, comms in categories.items():
    for comm in comms:
        cot_data = get_commodity_data(comm)
        if cot_data.empty:
            continue
        
        dates = cot_data['Date'].tolist()
        net_values = cot_data['NonComm Net'].tolist()

        filename = f"charts/{code_map.get(comm, comm)}.html"
        write_chart_html(comm, code_map.get(comm, ''), dates, net_values, filename)

print(f"Generated {len(os.listdir('charts'))} chart files")

dates = sorted(df['Date'].unique(), reverse=True)

def get_commodity(comm):
    return df[df['Commodity'] == comm]

html_rows_net = ''
html_rows_all = ''

for category, comms in categories.items():
    html_rows_net += f'<tr class="category"><th colspan="{len(dates)+2}">{category}</th></tr>\n'
    html_rows_net += '<tr><th>Commodity</th><th>Chart</th>'
    for d in dates:
        html_rows_net += f'<th>{d[5:]}</th>'
    html_rows_net += '</tr>\n'
    
    html_rows_all += f'<tr class="category"><th colspan="{len(dates)+3}">{category}</th></tr>\n'
    html_rows_all += '<tr><th>Commodity</th><th>Chart</th>'
    for d in dates:
        html_rows_all += f'<th colspan="3">{d[5:]}</th>'
    html_rows_all += '</tr>\n'
    html_rows_all += '<tr><th></th><th></th>'
    for d in dates:
        html_rows_all += '<th>L</th><th>S</th><th>N</th>'
    html_rows_all += '</tr>\n'
    
    for comm in comms:
        code = code_map.get(comm, '')
        data = get_commodity(comm)
        
        html_rows_net += f'<tr><td class="comm">{comm} ({code})</td><td><a href="charts/{code}.html" target="_blank" class="chart-link">📊</a></td>'
        html_rows_all += f'<tr><td class="comm">{comm} ({code})</td><td><a href="charts/{code}.html" target="_blank" class="chart-link">📊</a></td>'
        
        for d in dates:
            row = data[data['Date'] == d]
            
            if not row.empty:
                net = row.iloc[0]['NonComm Net']
                long_val = row.iloc[0]['NonComm Long']
                short_val = row.iloc[0]['NonComm Short']
                
                try:
                    net_num = int(net)
                    if net_num > 0:
                        cls = 'pos'
                        val = f'+{net:,}'
                    elif net_num < 0:
                        cls = 'neg'
                        val = f'{net:,}'
                    else:
                        cls = 'neu'
                        val = '0'
                except:
                    cls = 'neu'
                    val = '-'
            else:
                cls = 'neu'
                val = '-'
                long_val = short_val = '-'
            
            html_rows_net += f'<td class="{cls}">{val}</td>'
            try:
                html_rows_all += f'<td class="pos">{int(long_val):,}</td><td class="neg">{int(short_val):,}</td><td class="{cls}">{val}</td>'
            except (ValueError, TypeError):
                html_rows_all += f'<td class="pos">{long_val}</td><td class="neg">{short_val}</td><td class="{cls}">{val}</td>'
        
        html_rows_net += '</tr>\n'
        html_rows_all += '</tr>\n'

html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CFTC Non-Commercial Positions</title>
    <style>
        * {{ box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #1a1a2e; color: #eee; padding: 20px; margin: 0; }}
        .container {{ max-width: 100%; overflow-x: auto; background: #16213e; border-radius: 12px; padding: 20px; box-shadow: 0 4px 20px rgba(0,0,0,0.3); }}
        h1 {{ color: #fff; margin: 0 0 10px 0; font-size: 24px; }}
        .subtitle {{ color: #888; margin-bottom: 20px; font-size: 14px; }}
        
        .tabs {{ display: flex; margin-bottom: 20px; border-bottom: 2px solid #0f3460; }}
        .tab {{ padding: 12px 24px; cursor: pointer; background: transparent; border: none; color: #888; font-size: 16px; font-weight: 600; transition: 0.3s; }}
        .tab:hover {{ color: #fff; }}
        .tab.active {{ color: #4cc9f0; border-bottom: 3px solid #4cc9f0; }}
        
        .tab-content {{ display: none; }}
        .tab-content.active {{ display: block; }}
        
        table {{ width: 100%; border-collapse: collapse; font-size: 11px; }}
        th {{ background: #0f3460; color: #fff; padding: 8px 6px; text-align: center; font-weight: 600; position: sticky; top: 0; }}
        th:first-child {{ text-align: left; position: sticky; left: 0; background: #0f3460; z-index: 10; }}
        td {{ padding: 6px 6px; text-align: center; border-bottom: 1px solid #1a1a2e; font-family: 'SF Mono', Monaco, monospace; font-size: 10px; }}
        td:first-child {{ text-align: left; position: sticky; left: 0; background: #16213e; font-weight: 600; z-index: 5; }}
        tr.category {{ background: #e94560 !important; }}
        tr.category th {{ background: #e94560; text-align: left; padding: 10px; font-size: 14px; }}
        .comm {{ color: #4cc9f0; }}
        .pos {{ color: #06d6a0; }}
        .neg {{ color: #ef476f; }}
        .neu {{ color: #666; }}
        tr:hover td {{ background: #1f4068; }}
        tr:hover td:first-child {{ background: #1f4068; }}
        .chart-link {{ text-decoration: none; font-size: 16px; }}
        .chart-link:hover {{ transform: scale(1.2); }}
        .legend {{ margin-top: 20px; padding: 15px; background: #0f3460; border-radius: 8px; }}
        .legend span {{ margin-right: 20px; }}
        .legend .pos {{ color: #06d6a0; font-weight: bold; }}
        .legend .neg {{ color: #ef476f; font-weight: bold; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>CFTC Non-Commercial Positions</h1>
        <p class="subtitle">Legacy COT Report | Full Available History | 📊 Click for Chart</p>
        
        <div class="tabs">
            <button class="tab active" onclick="showTab('net')">Net</button>
            <button class="tab" onclick="showTab('all')">All</button>
        </div>
        
        <div id="net" class="tab-content active">
            <table>
                <thead>
                    <tr>
                        <th>Commodity</th>
                        <th>📊</th>
                        {''.join(f'<th>{d[5:]}</th>' for d in dates)}
                    </tr>
                </thead>
                <tbody>
{html_rows_net}                </tbody>
            </table>
        </div>
        
        <div id="all" class="tab-content">
            <table>
                <thead>
                    <tr>
                        <th>Commodity</th>
                        <th>📊</th>
                        {''.join(f'<th>L</th><th>S</th><th>N</th>' for d in dates)}
                    </tr>
                </thead>
                <tbody>
{html_rows_all}                </tbody>
            </table>
        </div>
        
        <div class="legend">
            <span><span class="pos">+</span> Net Long</span>
            <span><span class="neg">-</span> Net Short</span>
            <span><span class="neu">-</span> No Data</span>
            <span>L = Long, S = Short, N = Net</span>
        </div>
    </div>
    
    <script>
        function showTab(tabName) {{
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab')[tabName === 'net' ? 0 : 1].classList.add('active');
            document.getElementById(tabName).classList.add('active');
        }}
    </script>
</body>
</html>'''

with open('cot_noncommercial_history.html', 'w') as f:
    f.write(html)

print("✓ Generated: cot_noncommercial_history.html with Net and All tabs")
