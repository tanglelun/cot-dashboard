import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import update_market_pulse as pulse


def response(score=32.33, timestamp='2026-10-15T00:00:00+00:00'):
    result = Mock()
    result.json.return_value = {
        'fear_and_greed': {'score': score, 'rating': 'fear', 'timestamp': timestamp,
                          'previous_close': 32.33},
        'fear_and_greed_historical': {'data': []},
    }
    return result


class CNNRefreshTests(unittest.TestCase):
    def setUp(self):
        calendar = patch.object(pulse, 'expected_market_date', return_value='2026-10-14')
        calendar.start()
        self.addCleanup(calendar.stop)

    def test_stale_source_is_rejected(self):
        with patch.object(pulse.requests, 'get', return_value=response(timestamp='2026-10-13T00:00:00Z')), patch.object(pulse.time, 'sleep'):
            self.assertEqual(pulse.fetch_cnn_fear_greed(), ([], None))

    def test_current_snapshot_wins_over_history_cache(self):
        with patch.object(pulse.requests, 'get', side_effect=[response(), response(45, '2026-10-14T00:00:00Z')]):
            series, snapshot = pulse.fetch_cnn_fear_greed()
        self.assertEqual(snapshot['value'], 32.33)
        self.assertEqual(snapshot['date'], '2026-10-15')
        self.assertEqual(series[0]['latest']['value'], 32.33)

    def test_missing_source_timestamp_is_not_replaced_with_today(self):
        with patch.object(pulse.requests, 'get', return_value=response(timestamp=None)), patch.object(pulse.time, 'sleep'):
            self.assertEqual(pulse.fetch_cnn_fear_greed(), ([], None))

    def test_transient_failure_retries(self):
        with patch.object(pulse.requests, 'get', side_effect=[RuntimeError('timeout'), response()]) as get, patch.object(pulse.time, 'sleep'):
            _, snapshot = pulse.fetch_cnn_fear_greed(include_history=False)
        self.assertEqual(snapshot['value'], 32.33)
        self.assertEqual(get.call_count, 2)

    def test_independent_update_preserves_other_data_and_history(self):
        payload = {'updated': '2026-10-14 09:49 UTC', 'series': [
            {'key': 'cnn_fear_greed', 'points': [{'date': '2021-02-01', 'value': 50}]},
            {'key': 'us500', 'points': [{'date': '2026-10-14', 'value': 6000}]},
        ], 'snapshots': [{'key': 'sp500_pe', 'value': 25}]}
        with tempfile.TemporaryDirectory() as directory:
            output, view = Path(directory) / 'full.json', Path(directory) / 'view.json'
            output.write_text(json.dumps(payload))
            with patch.object(pulse, 'OUTPUT_FILE', output), patch.object(pulse, 'VIEW_OUTPUT_FILE', view), patch.object(pulse.requests, 'get', return_value=response()):
                pulse.refresh_cnn_only()
            saved = json.loads(output.read_text())
            self.assertEqual(saved['updated'], payload['updated'])
            self.assertEqual(saved['series'][1], payload['series'][1])
            self.assertEqual(saved['series'][0]['points'][0]['date'], '2021-02-01')
            self.assertEqual(saved['snapshots'][0], payload['snapshots'][0])
            self.assertEqual(json.loads(view.read_text())['snapshots'][-1]['value'], 32.33)

    def test_failed_cnn_refresh_does_not_touch_files(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'full.json'
            output.write_text('{"unchanged":true}')
            with patch.object(pulse, 'OUTPUT_FILE', output), patch.object(pulse, 'fetch_cnn_fear_greed', return_value=([], None)):
                with self.assertRaises(RuntimeError):
                    pulse.refresh_cnn_only()
            self.assertEqual(output.read_text(), '{"unchanged":true}')

    def test_full_update_preserves_snapshot_on_cnn_failure(self):
        old = {'key': 'cnn_fear_greed', 'date': '2026-10-15', 'value': 32.33}
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'full.json'
            output.write_text(json.dumps({'series': [], 'snapshots': [old]}))
            with patch.object(pulse, 'OUTPUT_FILE', output):
                result = pulse.merge_existing_payload({'series': [], 'snapshots': []})
            self.assertEqual(result['snapshots'], [old])

    def test_older_snapshot_cannot_replace_newer_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'full.json'
            payload = {'snapshots': [{'key': 'cnn_fear_greed', 'timestamp': '2026-10-16T00:00:00+00:00', 'value': 30}]}
            output.write_text(json.dumps(payload))
            before = output.read_text()
            with patch.object(pulse, 'OUTPUT_FILE', output), patch.object(pulse.requests, 'get', return_value=response()):
                with self.assertRaisesRegex(RuntimeError, 'older snapshot'):
                    pulse.refresh_cnn_only()
            self.assertEqual(output.read_text(), before)

if __name__ == '__main__':
    unittest.main()
