import unittest
from unittest.mock import patch
import pandas as pd
import update_market_pulse as pulse

class InsightFreshnessTests(unittest.TestCase):
    def setUp(self):
        self.symbols = [f'S{i}' for i in range(500)]
        self.constituents = [{'symbol': symbol} for symbol in self.symbols]
        self.closes = pd.DataFrame(100., index=pd.bdate_range(end='2026-10-14', periods=230), columns=self.symbols)

    def compute(self, initial, retry):
        with patch.object(pulse, 'expected_market_date', return_value='2026-10-14'), patch.object(pulse, 'fetch_sp500_constituents', return_value=self.constituents), patch.object(pulse, 'download_sp500_closes', side_effect=[initial, retry, retry]):
            return pulse.compute_sp500_breadth()

    def test_stale_constituents_retried_and_latest_sample_validated(self):
        result = self.compute(self.closes.iloc[:-1], self.closes)
        self.assertTrue(all(item['latest']['date']=='2026-10-14' for item in result))
        self.assertTrue(all(item['latest']['sample']==500 for item in result))

    def test_partial_latest_day_is_not_published(self):
        partial = self.closes.copy()
        partial.iloc[-1, :250] = float('nan')
        with self.assertRaisesRegex(RuntimeError, 'stale or incomplete'):
            self.compute(partial, partial)

    def test_no_data_does_not_use_non_sp500_fallback(self):
        with patch.object(pulse, 'compute_breadth') as fallback:
            with self.assertRaises(RuntimeError):
                self.compute(pd.DataFrame(), pd.DataFrame())
            fallback.assert_not_called()

    def test_unfinished_session_is_excluded(self):
        frame = self.closes.copy()
        frame.loc[pd.Timestamp('2026-10-15')] = 101.
        result = self.compute(frame, frame)
        self.assertTrue(all(item['latest']['date']=='2026-10-14' for item in result))

if __name__ == '__main__':
    unittest.main()
