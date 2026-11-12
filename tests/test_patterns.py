import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from generate_patterns import clean_bars, detect, scan, universe, parse_members, parse_iwm, load_members


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
    def test_structure_tiers_are_independent_of_breakout_and_volume(self):
        for tier in ('clear','potential'):
            for tail in (103,98):
                base=fixture(tail)
                if tier=='potential':
                    for i in range(61,80):
                        c=101+15*(i-60)/10 if i<=70 else 116+(tail-116)*(i-70)/9
                        base[i].update(open=c,high=c+.2,low=c-.2,close=c)
                for kind,bars in [('top',base),('bottom',invert(base))]:
                    with self.subTest(tier=tier,tail=tail,kind=kind):
                        result=detect(bars,kind)
                        self.assertEqual(result['structure'],tier)
                        self.assertEqual(result['has_breakout'],tail==98)
                        self.assertEqual(result['volume_state'],'unavailable' if tail==98 else 'not_applicable')
                        if tier=='potential': self.assertIn('shoulder_asymmetry',result['structure_notes'])
                        for b in bars: b['volume']=100
                        result=detect(bars,kind)
                        self.assertEqual(result['volume_state'],'not_expanded' if tail==98 else 'not_applicable')
                        if tail==98:
                            next(b for b in bars if b['time']==result['breakout_date'])['volume']=160
                            result=detect(bars,kind)
                            self.assertEqual(result['volume_state'],'expanded')
                            self.assertEqual(result['structure'],tier)

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
    def test_iwm_equities_classes_and_dedup(self):
        csv='iShares Russell 2000 ETF\nFund Holdings as of,"Nov 10, 2026"\nTicker,Name,Asset Class,Exchange\n'
        csv+=''.join(f'X{i},Stock {i},Equity,NASDAQ\n' for i in range(1800))
        csv+='MOG A,Moog,Equity,NYSE\nMOG.A,Moog duplicate,Equity,NYSE\nUSD,Cash,Cash,-\nRTYZ6,Future,Futures,CME\n-,Restricted,Equity,NASDAQ\nCVR,Claim,Equity,NO MARKET (E.G. UNLISTED)\n'
        rows=parse_members(csv,'russell2000');self.assertEqual(len(rows),1801)
        self.assertIn('MOG-A',{r['symbol'] for r in rows})
        _,meta=parse_iwm(csv);self.assertEqual(meta['source_as_of'],'2026-11-10')
        self.assertEqual(meta['excluded_equity_holdings'],2)
        with self.assertRaises(ValueError):parse_members(csv.split('X1,')[0],'russell2000')
        with self.assertRaises(ValueError):parse_iwm('<html>unavailable</html>')
    def test_iwm_stale_source_date_cannot_be_refreshed_by_retrieval(self):
        from unittest.mock import patch,Mock
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            root.joinpath('pattern_constituents.json').write_text(json.dumps({'russell2000':{'date':'2026-11-12','source_as_of':'2026-11-01','items':[{'symbol':'A'}]}}))
            response=Mock(text='Fund Holdings as of,"Nov 01, 2026"\nTicker,Name,Asset Class\nA,A,Equity\n')
            with patch('generate_patterns.SOURCES',{'russell2000':'https://example.test'}),patch('requests.get',return_value=response):
                with self.assertRaises(RuntimeError):load_members(root,date(2026,11,12))
    def test_each_index_requires_coverage_not_only_combined_total(self):
        groups={k:{'date':'2026-01-01','source':'test','items':[]} for k in ['sp500','nasdaq100','russell2000']}
        groups['sp500']['items']=[{'symbol':'A','name':'A'}]
        groups['nasdaq100']['items']=[{'symbol':'B','name':'B'}]
        groups['russell2000']['items']=[{'symbol':s,'name':s} for s in 'BCDEFGHIJ']
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);root.joinpath('market_data').mkdir();bars=fixture()
            for symbol in 'BCDEFGHIJ':root.joinpath('market_data',symbol+'.json').write_text(json.dumps({'prices':bars}))
            with self.assertRaisesRegex(RuntimeError,'sp500 charts: 0/1'):scan(root,groups,bars[-1]['time'])
    def test_scope_dedup_and_missing_coverage(self):
        groups={'sp500':{'date':'2026-01-01','source':'test','items':[{'symbol':'A','name':'A'}]},'nasdaq100':{'date':'2026-01-01','source':'test','items':[{'symbol':'A','name':'A'},{'symbol':'B','name':'B'}]},'russell2000':{'date':'2026-01-01','source':'test','items':[{'symbol':'B','name':'B'}]}}
        self.assertEqual(len(universe(groups)),2)
        self.assertEqual(universe(groups)['A']['indexes'],['S&P 500','Nasdaq 100'])
        self.assertEqual(universe(groups)['B']['indexes'],['Nasdaq 100','Russell 2000 (IWM近似)'])
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'market_data').mkdir();bars=fixture()
            for sym in ['A','B','OUTSIDE']:(root/'market_data'/f'{sym}.json').write_text(json.dumps({'prices':bars}))
            result=scan(root,groups,bars[-1]['time'])
            self.assertEqual({r['symbol'] for r in result['patterns']},{'A','B'})
            (root/'market_data/B.json').unlink()
            with self.assertRaises(RuntimeError):scan(root,groups,bars[-1]['time'])

if __name__=='__main__':unittest.main()
