import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import pandas as pd

from market_freshness import (
    StaleMarketDataError, completed_prices, ensure_fresh_prices, expected_market_date,
)
import update_market


def prices(dates, closes=None):
    values = closes or list(range(100, 100 + len(dates)))
    return pd.DataFrame({key: values for key in ('Open', 'High', 'Low', 'Close')},
                        index=pd.to_datetime(dates))


class FreshnessTests(unittest.TestCase):
    def test_calendar_weekend_holiday_early_close_and_dst(self):
        cases = {
            '2026-09-27T04:00:00Z': '2026-09-25',
            '2026-09-07T22:30:00Z': '2026-09-04',  # Labor Day
            '2026-11-27T17:59:00Z': '2026-11-25',  # Thanksgiving Friday
            '2026-11-27T18:01:00Z': '2026-11-27',
            '2026-03-06T20:30:00Z': '2026-03-05',  # winter: still open
            '2026-03-09T20:30:00Z': '2026-03-09',  # summer: closed
        }
        for now, expected in cases.items():
            with self.subTest(now=now):
                self.assertEqual(expected_market_date(now), expected)

    def test_retries_stale_and_missing_without_truncating_history(self):
        old = prices(['2020-01-02', '2026-09-24'], [10, 20])
        recent = prices(['2026-09-24', '2026-09-25'], [21, 22])
        download = Mock(return_value={'A': recent, 'B': recent})
        result = ensure_fresh_prices(['A', 'B'], {'A': old}, '2026-09-25',
                                     download, retry_delay=0)
        self.assertEqual(result['A']['Close'].tolist(), [10, 21, 22])
        self.assertEqual(len(result['B']), 2)
        download.assert_called_once_with(['A', 'B'], period='1mo', chunk_size=80,
                                         retry_missing=False)

    def test_stale_after_retries_fails(self):
        old = {'A': prices(['2026-09-24'])}
        download = Mock(return_value=old)
        with self.assertRaisesRegex(StaleMarketDataError, '2026-09-25'):
            ensure_fresh_prices(['A'], old, '2026-09-25', download, retry_delay=0)
        self.assertEqual(download.call_count, 2)

    def test_current_data_needs_no_retry(self):
        download = Mock()
        ensure_fresh_prices(['A'], {'A': prices(['2026-09-25'])},
                            '2026-09-25', download)
        download.assert_not_called()

    def test_one_fresh_stock_cannot_mask_stale_universe(self):
        frames = {'A': prices(['2026-09-25']), 'B': prices(['2026-09-24'])}
        with self.assertRaises(StaleMarketDataError):
            ensure_fresh_prices(['A', 'B'], frames, '2026-09-25', Mock(), retries=0)

    def test_suspended_minority_is_allowed(self):
        symbols = [str(i) for i in range(20)]
        frames = {s: prices(['2026-09-25']) for s in symbols[:-1]}
        frames['19'] = prices(['2026-09-24'])
        result = ensure_fresh_prices(symbols, frames, '2026-09-25', Mock(), retries=0)
        self.assertEqual(result['19'].index[-1], pd.Timestamp('2026-09-24'))

    def test_partial_current_session_removed_and_timezone_preserved_as_date(self):
        frame = prices(['2026-09-25', '2026-09-28'])
        frame.index = frame.index.tz_localize('America/New_York')
        result = completed_prices(frame, '2026-09-25')
        self.assertEqual(list(result.index), [pd.Timestamp('2026-09-25')])

    def test_empty_download_fails(self):
        with self.assertRaises(StaleMarketDataError):
            ensure_fresh_prices(['A'], {}, '2026-09-25', Mock(), retries=0)

    def test_stale_run_does_not_write_output(self):
        with tempfile.TemporaryDirectory() as directory:
            page = Path(directory) / 'market.html'
            original = update_market.MARKET_FILE.read_text(encoding='utf-8-sig')
            page.write_text(original)
            with patch.object(update_market, 'MARKET_FILE', page), \
                 patch.object(update_market, 'TRACK_ALL_US_STOCKS', False), \
                 patch.object(update_market, 'expected_market_date', return_value='2026-09-25'), \
                 patch.object(update_market, 'get_price_frame_map', return_value={}), \
                 patch('market_freshness.time.sleep'), \
                 patch.object(update_market, 'write_chart_data') as write:
                with self.assertRaises(StaleMarketDataError):
                    update_market.main()
                write.assert_not_called()
                self.assertEqual(page.read_text(), original)

    def test_chart_reports_own_last_date(self):
        import json
        row = {'t': 'A', 'n': 'Example', 's': 'Tech', 'c': '1B', 'mn': 1,
               'r': 1, 'p': 100, 'd': 0, 'w': 0, 'm': 0, 'm2': 0, 'q': 0, 'h': 0, 'y': 0}
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(update_market, 'MARKET_DATA_DIR', Path(directory)):
            update_market.write_chart_data({'r2kRaw': [row]},
                                           {'A': prices(['2026-09-24'])}, '2026-09-25')
            data = json.loads((Path(directory) / 'A.json').read_text())
            self.assertEqual(data['updated'], '2026-09-24')


if __name__ == '__main__':
    unittest.main()
