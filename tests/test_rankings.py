import unittest
from generate_rankings import returns,cap_number
from datetime import date,timedelta

class RankingTests(unittest.TestCase):
    def test_history_requirements_and_period_returns(self):
        bars=[{'time':(date(2025,12,30)+timedelta(days=i)).isoformat(),'close':100+i} for i in range(200)]
        metrics=returns(bars,bars[-1]['time'])
        self.assertAlmostEqual(metrics['d'],(299/298-1)*100)
        self.assertAlmostEqual(metrics['w'],(299/294-1)*100)
        self.assertAlmostEqual(metrics['h'],(299/173-1)*100)
        self.assertAlmostEqual(metrics['y'],(299/101-1)*100)
        ipo=returns(bars[-3:],bars[-1]['time'])
        self.assertIsNone(ipo['w']);self.assertIsNone(ipo['y'])
    def test_stale_or_invalid_never_ranked_as_zero(self):
        for bars in [[{'time':'2026-01-01','close':10}],[{'time':'2026-01-02','close':float('nan')}]]:
            with self.assertRaises(ValueError):returns(bars,'2026-01-02')
    def test_cap(self):self.assertEqual(cap_number('$1.55B'),1550)
if __name__=='__main__':unittest.main()
