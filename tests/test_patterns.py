import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from generate_patterns import clean_bars, detect, scan, universe, parse_members


def fixture(tail=103):
    anchors=[(0,80),(20,95),(30,110),(40,100),(50,120),(60,101),(70,111),(79,tail)]
    closes=[]
    for (i,a),(j,b) in zip(anchors,anchors[1:]):
        closes.extend(a+(b-a)*k/(j-i) for k in range(j-i))
    closes.append(tail)
    return [{'time':(date(2026,1,1)+timedelta(days=i)).isoformat(),'open':c,'high':c+.2,'low':c-.2,'close':c} for i,c in enumerate(closes)]


def invert(bars):
    return [{**b,'open':250-b['open'],'close':250-b['close'],'high':250-b['low'],'low':250-b['high']} for b in bars]


class PatternTests(unittest.TestCase):
    def test_candidates_both_directions(self):
        for kind,bars in [('top',fixture()),('bottom',invert(fixture()))]:
            result=detect(bars,kind)
            self.assertIsNotNone(result);self.assertEqual(result['status'],'candidate')
            self.assertEqual(result['right_shoulder'],bars[70]['time'])
            self.assertIsNone(result['confirmed_on'])
    def test_close_breakout_and_inverse(self):
        for kind,bars in [('top',fixture(98)),('bottom',invert(fixture(98)))]:
            result=detect(bars,kind)
            self.assertEqual(result['status'],'breakout')
            self.assertIsNone(result['confirmed_on'])
            self.assertGreaterEqual(result['price_breakout_on'],result['detected_on'])
    def test_volume_confirmation_is_separate(self):
        for kind,bars in [('top',fixture(98)),('bottom',invert(fixture(98)))]:
            for b in bars: b['volume']=100
            first=detect(bars,kind)
            breakout=next(b for b in bars if b['time']==first['breakout_date'])
            breakout['volume']=160
            result=detect(bars,kind)
            self.assertEqual(result['status'],'confirmed')
            self.assertAlmostEqual(result['volume_ratio'],1.6)
            self.assertIsNotNone(result['confirmed_on'])
            breakout['volume']=100
            self.assertEqual(detect(bars,kind)['status'],'breakout')
    def test_pivots_lie_on_displayed_close_curve(self):
        bars=fixture();result=detect(bars,'top')
        by_date={b['time']:b['close'] for b in bars}
        for point in result['points']:
            self.assertAlmostEqual(point['price'],by_date[point['date']])
    def test_reviewed_rounding_bottom_false_positives(self):
        path=Path(__file__).parent/'fixtures'/'rounding_bottoms_2026_11_11.json'
        samples=json.loads(path.read_text())
        for symbol,bars in samples.items():
            with self.subTest(symbol=symbol): self.assertIsNone(detect(bars,'bottom'))
    def test_wide_head_with_incidental_shoulders_is_rejected(self):
        anchors=[(0,80),(20,95),(30,110),(33,107),(55,120),(77,107),(80,110),(89,106)]
        values=[]
        for (i,a),(j,b) in zip(anchors,anchors[1:]): values.extend(a+(b-a)*k/(j-i) for k in range(j-i))
        values.append(106)
        bars=[{'time':(date(2026,1,1)+timedelta(days=i)).isoformat(),'open':c,'high':c+.2,'low':c-.2,'close':c} for i,c in enumerate(values)]
        self.assertIsNone(detect(bars,'top'))
        self.assertIsNone(detect(invert(bars),'bottom'))
    def test_wick_alone_does_not_confirm(self):
        bars=fixture();bars[-1]['low']=90
        self.assertEqual(detect(bars,'top')['status'],'candidate')
    def test_reclaim_invalidates_breakout(self):
        bars=fixture(98);bars.append({**bars[-1],'time':'2026-03-22','open':105,'high':106,'low':104,'close':105})
        self.assertIsNone(detect(bars,'top'))
    def test_flat_and_monotonic_have_no_pattern(self):
        for closes in ([100]*100,list(range(100,200))):
            bars=[{'high':c+1,'low':c-1,'close':c} for c in closes]
            self.assertIsNone(detect(bars,'top'));self.assertIsNone(detect(bars,'bottom'))
    def test_no_prior_uptrend(self):
        bars=fixture()
        for i in range(21):bars[i].update(open=112,high=113,low=111,close=112)
        self.assertIsNone(detect(bars,'top'))
    def test_new_high_invalidates(self):
        bars=fixture();bars[-1]['high']=130
        self.assertIsNone(detect(bars,'top'))
    def test_no_lookahead_unconfirmed_shoulder(self):
        self.assertIsNone(detect(fixture()[:73],'top'))
    def test_stale_invalid_and_intraday_data(self):
        bars=fixture();expected=bars[-1]['time']
        self.assertEqual(clean_bars(bars+[{'time':'2099-01-01'}],expected),bars)
        with self.assertRaises(ValueError):clean_bars(bars,'2026-03-22')
        bars[-1]['close']=float('nan')
        with self.assertRaises(ValueError):clean_bars(bars,expected)
    def test_full_membership_validation(self):
        with self.assertRaises(ValueError):parse_members('Symbol,Security\nA,Apple\n','sp500')
    def test_scope_dedup_and_missing_coverage(self):
        groups={'sp500':{'date':'2026-01-01','source':'test','items':[{'symbol':'A','name':'A'}]},'nasdaq100':{'date':'2026-01-01','source':'test','items':[{'symbol':'A','name':'A'},{'symbol':'B','name':'B'}]}}
        self.assertEqual(len(universe(groups)),2)
        self.assertEqual(universe(groups)['A']['indexes'],['S&P 500','Nasdaq 100'])
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'market_data').mkdir();bars=fixture()
            for sym in ['A','B','OUTSIDE']:(root/'market_data'/f'{sym}.json').write_text(json.dumps({'prices':bars}))
            result=scan(root,groups,bars[-1]['time'])
            self.assertEqual({r['symbol'] for r in result['patterns']},{'A','B'})
            (root/'market_data/B.json').unlink()
            with self.assertRaises(RuntimeError):scan(root,groups,bars[-1]['time'])

if __name__=='__main__':unittest.main()
