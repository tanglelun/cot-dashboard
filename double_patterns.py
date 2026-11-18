"""Daily double reversal screening. Thresholds are site screening heuristics."""
import math


def detect_double(bars, kind):
    sign = 1 if kind == 'top' else -1
    values = [sign*b['close'] for b in bars]
    found = []
    for radius in (3, 5, 8):
        pivots = []
        for i in range(radius, len(bars)-radius):
            peak = values[i] > max(values[i-radius:i]) and values[i] >= max(values[i+1:i+radius+1])
            trough = values[i] < min(values[i-radius:i]) and values[i] <= min(values[i+1:i+radius+1])
            if peak == trough: continue
            p = (i, values[i], 'H' if peak else 'L')
            if pivots and pivots[-1][2] == p[2]:
                if (p[1]-pivots[-1][1])*(1 if peak else -1)>0: pivots[-1]=p
            else: pivots.append(p)
        for a,b,c in zip(pivots,pivots[1:],pivots[2:]):
            if a[2]+b[2]+c[2] != 'HLH': continue
            first,second = a[0],c[0]; neck=b[1]; last=len(bars)-1
            if first<20 or not 10<=second-first<=100 or last-second>25: continue
            height=min(a[1],c[1])-neck
            atr=sum(max(x['high']-x['low'],abs(x['high']-bars[i-1]['close']),abs(x['low']-bars[i-1]['close'])) for i,x in enumerate(bars[first:second+1],first))/(second-first+1)
            scale=abs((a[1]+c[1])/2)
            if height<max(.03*scale,2*atr): continue
            difference=abs(a[1]-c[1])
            if difference>min(.05*scale,.4*height): continue
            ratio=(b[0]-first)/(second-b[0])
            if not .25<=ratio<=4: continue
            if a[1]-values[first-20]<max(.03*scale,.5*height): continue
            if c[1]-min(values[second+1:])<max(.2*height,atr): continue
            # A new extreme beyond both tests invalidates the reversal.
            if max(values[second+1:])>max(a[1],c[1])+.005*scale: continue
            breaks=[i for i in range(second+1,len(bars)) if values[i]<neck-.005*abs(neck)]
            breakout=breaks[0] if breaks else None
            if breakout is not None:
                if last-breakout>10 or any(v>neck+.005*abs(neck) for v in values[breakout+1:]): continue
            elif last-second>20: continue
            notes=[]
            if difference>min(.03*scale,.25*height): notes.append('unequal_extremes')
            if not .5<=ratio<=2: notes.append('time_asymmetry')
            ratio_volume=None
            if breakout is not None and breakout>=20:
                volumes=[x.get('volume') for x in bars[breakout-20:breakout+1]]
                if all(isinstance(v,(int,float)) and math.isfinite(v) and v>0 for v in volumes): ratio_volume=volumes[-1]/(sum(volumes[:-1])/20)
            expanded=ratio_volume is not None and ratio_volume>=1.2
            origin=max(0,first-10)
            found.append(dict(kind=kind,structure='potential' if notes else 'clear',structure_notes=notes,
                has_breakout=breakout is not None,status='confirmed' if expanded else 'breakout' if breakout is not None else 'candidate',
                volume_state='not_applicable' if breakout is None else 'unavailable' if ratio_volume is None else 'expanded' if expanded else 'not_expanded',
                volume_ratio=round(ratio_volume,2) if ratio_volume is not None else None,
                as_of=bars[-1]['time'],price=bars[-1]['close'],neckline=sign*neck,neck_start=sign*neck,neck_end=sign*neck,
                distance_pct=round((bars[-1]['close']/(sign*neck)-1)*100,2),
                second_extreme=bars[second]['time'],detected_on=bars[second+radius]['time'],
                breakout_date=bars[breakout]['time'] if breakout is not None else None,
                price_breakout_on=bars[max(second+radius,breakout)]['time'] if breakout is not None else None,
                points=[dict(date=bars[i]['time'],price=sign*v,offset=i-origin) for i,v,_ in (a,b,c)],
                chart=[dict(date=x['time'],close=x['close']) for x in bars[origin:]]))
    return max(found,key=lambda r:(r['structure']=='clear',r['second_extreme'])) if found else None
