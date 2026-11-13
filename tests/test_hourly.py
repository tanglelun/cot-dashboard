import unittest
from update_hourly import parse_chart,filename

class HourlyTests(unittest.TestCase):
    def chart(self):
        return {'meta':{'exchangeTimezoneName':'America/New_York','tradingPeriods':[[{'start':10000,'end':33400}]]},'timestamp':[10000,13600,31600,33400], 'indicators':{'quote':[{'open':[10]*4,'high':[12]*4,'low':[9]*4,'close':[11]*4,'volume':[100,None,300,0]}]}}
    def test_completed_bars_and_short_close_session(self):
        result=parse_chart(self.chart(),'AAPL',40000)
        self.assertEqual(len(result['prices']),3)
        self.assertEqual(result['prices'][-1]['end'],33400)
        self.assertIsNone(result['prices'][1]['volume'])
        self.assertEqual(result['timezone'],'America/New_York')
    def test_no_incomplete_or_after_close_snapshot(self):
        result=parse_chart(self.chart(),'AAPL',32000)
        self.assertEqual(len(result['prices']),2)
    def test_sessions_required_and_bad_ohlc_not_published(self):
        chart=self.chart();chart['indicators']['quote'][0]['low']=[20]*4
        with self.assertRaises(ValueError):parse_chart(chart,'AAPL',40000)
        chart=self.chart();chart['meta']['tradingPeriods']=[]
        with self.assertRaises(ValueError):parse_chart(chart,'AAPL',40000)
    def test_symbol_filenames(self):
        self.assertEqual(filename('^GSPC'),'_GSPC.json')
        self.assertEqual(filename('GC=F'),'GC_F.json')
        self.assertEqual(filename('BRK.B'),'BRK.B.json')
