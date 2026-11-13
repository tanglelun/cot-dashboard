import json
import subprocess
import unittest
from pathlib import Path
from test_patterns import fixture, invert
from generate_patterns import detect

ROOT=Path(__file__).resolve().parents[1]
def js(bars, method='scan', kind='top'):
    script="const d=require('./pattern_detector.js');let s='';process.stdin.on('data',c=>s+=c);process.stdin.on('end',()=>console.log(JSON.stringify(d[process.argv[1]](JSON.parse(s),process.argv[2]))));"
    return json.loads(subprocess.check_output(['node','-e',script,method,kind],input=json.dumps(bars).encode(),cwd=ROOT))

class HistoryTests(unittest.TestCase):
    def test_matches_existing_geometry_both_directions(self):
        for kind,bars in [('top',fixture(98)),('bottom',invert(fixture(98)))]:
            for b in bars:b['volume']=100
            expected=detect(bars,kind);actual=js(bars,'detect',kind)[0]
            for key in ['structure','structure_notes','has_breakout','volume_state','breakout_date']:
                self.assertEqual(actual[key],expected[key])
    def test_no_future_confirmation(self):
        self.assertEqual(js(fixture()[:73]),[])
    def test_old_patterns_retained_beyond_current_window(self):
        from datetime import date,timedelta
        bars=fixture(98)
        for i in range(400):
            c=90-i*.01
            bars.append({'time':(date(2026,3,22)+timedelta(days=i)).isoformat(),'open':c,'high':c+.2,'low':c-.2,'close':c})
        rows=js(bars)
        self.assertTrue(rows)
        self.assertTrue(all(r['historical'] for r in rows))
        self.assertEqual(rows[0]['points'][2]['date'],fixture()[50]['time'])
    def test_rounding_bottom_regressions(self):
        samples=json.loads((ROOT/'tests/fixtures/rounding_bottoms_2026_11_11.json').read_text())
        for symbol,bars in samples.items():
            with self.subTest(symbol=symbol):self.assertEqual(js(bars,'detect','bottom'),[])
