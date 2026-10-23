import json
import tempfile
import unittest
from pathlib import Path
from check_update_needed import recovery_reasons

class UpdateRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
    def write(self, name, value):
        path=self.root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value))
    def market(self):
        self.write('market_data/index.json', {'updated':'2026-10-22','stocks':[{'symbol':'A'}]})
        for name in ['market_data/A.json','indexes_data/GSPC.json','commodities_data/GC-F.json','commodities_data/CL-F.json']:
            self.write(name, {'prices':[{'time':'2026-10-22'}]})
        self.write('crossover_data.json', {'updated':'2026-10-23 01:00 UTC'})
    def test_current_market_skips_recovery(self):
        self.market()
        self.assertEqual(recovery_reasons('market',self.root,'2026-10-22')[1],[])
    def test_old_chart_is_detected_even_with_current_directory(self):
        self.market();self.write('market_data/A.json',{'prices':[{'time':'2026-07-02'}]})
        self.assertIn('fresh stock charts: 0/1',recovery_reasons('market',self.root,'2026-10-22')[1])
    def test_failed_index_refresh_is_retried(self):
        self.market();self.write('indexes_data/GSPC.json',{'prices':[{'time':'2026-10-21'}]})
        self.assertTrue(recovery_reasons('market',self.root,'2026-10-22')[1])
    def test_current_insight_skips_recovery(self):
        self.write('market_pulse_view.json',{'series':[{'key':k,'latest':{'date':'2026-10-22','sample':500}} for k in ['us500','above_ma50','above_ma200']]})
        self.assertEqual(recovery_reasons('insight',self.root,'2026-10-22')[1],[])
    def test_updated_cnn_does_not_hide_stale_breadth(self):
        self.write('market_pulse_view.json',{'updated':'2026-10-23','series':[{'key':'cnn_fear_greed','latest':{'date':'2026-10-23'}}]})
        self.assertEqual(len(recovery_reasons('insight',self.root,'2026-10-22')[1]),3)
    def test_missing_data_requires_retry(self):
        self.assertTrue(recovery_reasons('market',self.root,'2026-10-22')[1])

if __name__=='__main__':unittest.main()
