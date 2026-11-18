import unittest
from datetime import date,timedelta
from double_patterns import detect_double


def sample(tail=103, second=110):
    anchors=[(0,80),(20,95),(30,110),(43,100),(56,second),(65,tail)]
    values=[]
    for (i,a),(j,b) in zip(anchors,anchors[1:]): values.extend(a+(b-a)*k/(j-i) for k in range(j-i))
    values.append(tail)
    return [dict(time=(date(2026,1,1)+timedelta(days=i)).isoformat(),open=c,high=c+.2,low=c-.2,close=c,volume=100) for i,c in enumerate(values)]


def invert(bars):
    return [{**b,'open':250-b['open'],'close':250-b['close'],'high':250-b['low'],'low':250-b['high']} for b in bars]


class DoublePatternsTests(unittest.TestCase):
    def test_both_directions_and_breakout(self):
        for tail in (103,98):
            for kind,bars in [('top',sample(tail)),('bottom',invert(sample(tail)))]:
                r=detect_double(bars,kind)
                self.assertIsNotNone(r);self.assertEqual(r['has_breakout'],tail==98)
                self.assertEqual(len(r['points']),3)
                self.assertEqual(r['structure'],'clear')
                if tail==98:
                    next(b for b in bars if b['time']==r['breakout_date'])['volume']=160
                    self.assertEqual(detect_double(bars,kind)['volume_state'],'expanded')
    def test_reject_unequal_extremes_and_single_rounding(self):
        self.assertIsNone(detect_double(sample(second=120),'top'))
        bars=sample()
        for i,b in enumerate(bars):
            c=120-((i-32)/10)**2;b.update(open=c,close=c,high=c+.2,low=c-.2)
        self.assertIsNone(detect_double(bars,'top'))
    def test_invalidation_and_confirmation(self):
        self.assertIsNone(detect_double(sample()[:59],'top'))
        bars=sample(98);bars.append({**bars[-1],'time':'2026-03-08','open':105,'close':105,'high':105.2,'low':104.8})
        self.assertIsNone(detect_double(bars,'top'))
    def test_no_prior_trend(self):
        bars=sample()
        for b in bars[:21]:b.update(open=112,close=112,high=112.2,low=111.8)
        self.assertIsNone(detect_double(bars,'top'))

if __name__=='__main__':unittest.main()
