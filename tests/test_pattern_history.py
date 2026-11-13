import json
import subprocess
import unittest
from pathlib import Path
from test_patterns import fixture, invert
from generate_patterns import detect

ROOT=Path(__file__).resolve().parents[1]
def js(bars, method='scan', kind='top', radius=3):
    script="const d=require('./pattern_detector.js');let s='';process.stdin.on('data',c=>s+=c);process.stdin.on('end',()=>console.log(JSON.stringify(d[process.argv[1]](JSON.parse(s),process.argv[2],Number(process.argv[3])))));"
    return json.loads(subprocess.check_output(['node','-e',script,method,kind,str(radius)],input=json.dumps(bars).encode(),cwd=ROOT))

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
            for radius in (3,5,8,13):
                with self.subTest(symbol=symbol,radius=radius):self.assertEqual(js(bars,'detect','bottom',radius),[])

    def test_one_bad_range_does_not_discard_valid_structure(self):
        bars=fixture(98)
        bars[5]['high']=bars[5]['close']-.01
        rows=js(bars)
        self.assertTrue(any(r['kind']=='top' for r in rows))

    def test_inconsistent_range_in_structure_is_disclosed_and_downgraded(self):
        bars=fixture(98)
        bars[35]['high']=bars[35]['close']-.01
        row=next(r for r in js(bars) if r['kind']=='top')
        self.assertTrue(row['range_adjusted'])
        self.assertEqual(row['structure'],'potential')
        self.assertIn('inconsistent_ohlc',row['structure_notes'])

    def test_real_multiscale_bottom_and_pivot_confirmation(self):
        bars=json.loads((ROOT/'tests/fixtures/tnk_multiscale_2021.json').read_text())
        rows=js(bars)
        row=next(r for r in rows if r['kind']=='bottom' and r['points'][2]['date']=='2021-08-20')
        self.assertGreater(row['pivot_radius'],3)
        indices={b['time']:i for i,b in enumerate(bars)}
        self.assertGreaterEqual(indices[row['first_seen']]-indices[row['points'][4]['date']],row['pivot_radius'])
        self.assertEqual(len(rows),len({(r['kind'],r['points'][2]['date']) for r in rows}))
