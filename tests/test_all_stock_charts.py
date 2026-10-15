import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import pandas as pd
import update_market as market

class AllStockChartsTests(unittest.TestCase):
    def test_non_top_chart_refreshes_and_preserves_old_history(self):
        row={'t':'OTHER','n':'Other Stock','s':'US','c':'1B'}
        frame=pd.DataFrame({'Open':[101,102],'High':[103,104],'Low':[100,101],'Close':[102,103]},index=pd.to_datetime(['2026-07-02','2026-10-14']))
        with tempfile.TemporaryDirectory() as directory, patch.object(market,'MARKET_DATA_DIR',Path(directory)), patch.object(market,'GENERATE_ALL_STOCK_CHARTS',True):
            path=Path(directory)/'OTHER.json'
            path.write_text(json.dumps({'prices':[{'time':'2020-01-02','close':50},{'time':'2026-07-02','close':99}]}))
            market.write_chart_data({}, {'OTHER':frame}, '2026-10-14',universe_rows=[row])
            result=json.loads(path.read_text())
            self.assertEqual([c['time'] for c in result['prices']], ['2020-01-02','2026-07-02','2026-10-14'])
            self.assertEqual(result['prices'][1]['close'],102)
            self.assertEqual(result['updated'],'2026-10-14')

    def test_new_stock_gets_chart_without_full_history_download(self):
        row={'t':'NEW','n':'New Stock','s':'US','c':'1B'}
        frame=pd.DataFrame({key:[10.] for key in ['Open','High','Low','Close']},index=pd.to_datetime(['2026-10-14']))
        with tempfile.TemporaryDirectory() as directory, patch.object(market,'MARKET_DATA_DIR',Path(directory)), patch.object(market,'GENERATE_ALL_STOCK_CHARTS',True):
            market.write_chart_data({}, {'NEW':frame}, '2026-10-14',universe_rows=[row])
            self.assertEqual(json.loads((Path(directory)/'NEW.json').read_text())['updated'],'2026-10-14')

if __name__=='__main__': unittest.main()
