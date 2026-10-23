"""Skip hourly recovery downloads only when their published outputs are current."""
import argparse
import json
import os
from pathlib import Path

from market_freshness import expected_market_date

BASE_DIR = Path(__file__).resolve().parent


def read_json(root, name):
    return json.loads((root / name).read_text(encoding='utf-8'))


def recovery_reasons(kind, root=BASE_DIR, expected=None):
    expected = expected or expected_market_date()
    reasons = []
    try:
        if kind == 'market':
            index = read_json(root, 'market_data/index.json')
            if not index.get('stocks') or index.get('updated', '') < expected:
                reasons.append('stock directory is behind the completed session')
            # The index alone cannot detect the old all-chart-refresh regression.
            symbols = [row['symbol'] for row in index.get('stocks', [])]
            fresh = 0
            for symbol in symbols:
                try:
                    bars = read_json(root, f'market_data/{symbol}.json').get('prices', [])
                    fresh += bool(bars and bars[-1]['time'] >= expected)
                except (OSError, ValueError, KeyError, TypeError):
                    pass
            if not symbols or fresh < len(symbols) * 0.90:
                reasons.append(f'fresh stock charts: {fresh}/{len(symbols)}')
            for name in ['indexes_data/GSPC.json', 'commodities_data/GC-F.json', 'commodities_data/CL-F.json']:
                bars = read_json(root, name).get('prices', [])
                if not bars or bars[-1].get('time', '') < expected:
                    reasons.append(f'{name} is behind the completed session')
            if read_json(root, 'crossover_data.json').get('updated', '')[:10] < expected:
                reasons.append('crossover signals have not been regenerated')
        else:
            payload = read_json(root, 'market_pulse_view.json')
            series = {item['key']: item for item in payload.get('series', [])}
            for key in ['us500', 'above_ma50', 'above_ma200']:
                latest = series.get(key, {}).get('latest') or {}
                if latest.get('date', '') < expected:
                    reasons.append(f'{key} is behind the completed session')
                elif key.startswith('above_') and latest.get('sample', 0) < 450:
                    reasons.append(f'{key} has an incomplete sample')
    except (OSError, ValueError, KeyError, TypeError) as exc:
        reasons.append(f'published data could not be verified: {exc}')
    return expected, reasons


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('kind', choices=['market', 'insight'])
    args = parser.parse_args()
    expected, reasons = recovery_reasons(args.kind)
    # Keep manual runs and the two regular daily refreshes unconditional.
    needed = bool(reasons) or os.getenv('RECOVERY_ONLY') != 'true'
    print(f'{args.kind}: expected session {expected}; ' + ('; '.join(reasons) or 'published data is current'))
    print('Refresh needed:', needed)
    if os.getenv('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as output:
            output.write(f'needed={str(needed).lower()}\n')


if __name__ == '__main__':
    main()
