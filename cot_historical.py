import requests
import pandas as pd
import io
from datetime import datetime, timedelta
import zipfile
import os

HISTORY_FILE = 'cot_noncommercial_history.csv'
LOOKBACK_YEARS = 10
EARLIEST_ARCHIVE_YEAR = 1986
REQUEST_HEADERS = {'User-Agent': 'Mozilla/5.0 NetData COT updater'}

PRIORITY_HISTORY_MARKETS = [
    'Coffee', 'Cocoa', 'Cotton', 'Sugar', 'S&P 500 Micro', 'Soybean Oil', 'Copper',
]

def get_all_futures():
    return [
        ('Corn', 'CORN'),
        ('Soybeans', 'SOYBEANS'),
        ('Soybean Meal', 'SOYBEAN MEAL'),
        ('Soybean Oil', 'SOYBEAN OIL'),
        ('Wheat', 'WHEAT'),
        ('Hard Red Winter Wheat', 'WHEAT-HRW'),
        ('Spring Wheat Mpls', 'WHEAT-HRSpring'),
        ('Rough Rice', 'RICE'),
        ('Canola', 'CANOLA'),
        ('Oats', 'OATS'),
        ('Crude Oil', 'CRUDE OIL'),
        ('Natural Gas', 'NATURAL GAS'),
        ('Gold', 'GOLD'),
        ('Silver', 'SILVER'),
        ('Copper', 'COPPER'),
        ('Platinum', 'PLATINUM'),
        ('Palladium', 'PALLADIUM'),
        ('Coffee', 'COFFEE'),
        ('Sugar', 'SUGAR'),
        ('Cocoa', 'COCOA'),
        ('Cotton', 'COTTON'),
        ('Orange Juice', 'ORANGE JUICE'),
        ('Live Cattle', 'LIVE CATTLE'),
        ('Lean Hogs', 'LEAN HOGS'),
        ('Feeder Cattle', 'FEEDER CATTLE'),
        ('Euro FX', 'EURO FX'),
        ('British Pound', 'BRITISH POUND'),
        ('Japanese Yen', 'JAPANESE YEN'),
        ('Swiss Franc', 'SWISS FRANC'),
        ('Australian Dollar', 'AUSTRALIAN DOLLAR'),
        ('Canadian Dollar', 'CANADIAN DOLLAR'),
        ('Mexican Peso', 'MEXICAN PESO'),
        ('U.S. Dollar Index', 'USD INDEX'),
        ('S&P 500', 'S&P 500'),
        ('Nasdaq 100', 'NASDAQ-100'),
        ('Dow Jones', 'DOW JONES'),
        ('Russell 2000', 'RUSSELL'),
        ('S&P 500 Micro', 'MICRO E-MINI S&P'),
        ('10-Year T-Note', 'UST 10Y NOTE'),
        ('5-Year T-Note', 'UST 5Y NOTE'),
        ('2-Year T-Note', 'UST 2Y NOTE'),
        ('30-Year T-Bond', 'UST BOND'),
    ]

def find_contract(df, market_col, code):
    matches = df[df[market_col].str.upper().str.contains(code, na=False)]
    if not matches.empty:
        return matches.iloc[0]
    return None

def parse_position(val):
    if pd.isna(val) or str(val).strip() == '':
        return 0
    try:
        return int(str(val).replace(',', '').replace(' ', ''))
    except:
        return 0

def download_legacy_data_for_year(year):
    base_url = "https://www.cftc.gov/files/dea/history/"
    archive_name = f"deacot{year}.zip"
    url = f"{base_url}{archive_name}"
    local_zip = archive_name
    content = None

    for attempt in range(1, 4):
        try:
            response = requests.get(url, headers=REQUEST_HEADERS, timeout=60)
            if response.status_code == 200:
                content = response.content
                break
            print(f"Failed to download {year}: {response.status_code} (attempt {attempt}/3)")
        except requests.RequestException as exc:
            print(f"Failed to download {year}: {exc} (attempt {attempt}/3)")

    if content is None and os.path.exists(local_zip):
        print(f"Using cached {local_zip}")
        with open(local_zip, 'rb') as f:
            content = f.read()

    if content is None:
        print(f"Skipping {year}: no downloadable or cached CFTC file")
        return None

    with zipfile.ZipFile(io.BytesIO(content)) as z:
        for fname in z.namelist():
            # Older CFTC archives use upper-case .TXT names.
            if fname.lower().endswith(('.txt', '.csv')):
                df = pd.read_csv(z.open(fname), low_memory=False)
                return df
    return None

def parse_legacy_year(df, futures_list, cutoff):
    date_col = 'As of Date in Form YYYY-MM-DD'
    market_col = 'Market and Exchange Names'
    noncomm_long = 'Noncommercial Positions-Long (All)'
    noncomm_short = 'Noncommercial Positions-Short (All)'

    df[date_col] = pd.to_datetime(df[date_col])
    df = df[df[date_col] >= cutoff]

    records = []
    for report_date in sorted(df[date_col].unique()):
        date_str = pd.Timestamp(report_date).strftime('%Y-%m-%d')
        daily_df = df[df[date_col] == report_date].copy()

        for name, code in futures_list:
            row = find_contract(daily_df, market_col, code)
            if row is None:
                continue

            long_val = parse_position(row[noncomm_long])
            short_val = parse_position(row[noncomm_short])
            net_val = long_val - short_val

            records.append({
                'Date': date_str,
                'Commodity': name,
                'NonComm Long': long_val,
                'NonComm Short': short_val,
                'NonComm Net': net_val,
                'Code': code,
            })

    return records

def merge_history_records(records, history_file):
    downloaded_df = pd.DataFrame(records)
    if downloaded_df.empty:
        return pd.DataFrame()
    if os.path.exists(history_file):
        existing_df = pd.read_csv(history_file)
        existing_df = existing_df[~existing_df.set_index(['Date', 'Commodity']).index.isin(
            downloaded_df.set_index(['Date', 'Commodity']).index
        )]
        result_df = pd.concat([existing_df, downloaded_df], ignore_index=True)
    else:
        result_df = downloaded_df
    result_df['Date'] = pd.to_datetime(result_df['Date']).dt.strftime('%Y-%m-%d')
    result_df = result_df.drop_duplicates(['Date', 'Commodity'], keep='last')
    result_df = result_df.sort_values(['Date', 'Commodity'], ascending=[False, True])
    result_df = result_df[['Date', 'Commodity', 'NonComm Long', 'NonComm Short', 'NonComm Net', 'Code']]
    result_df.to_csv(history_file, index=False)
    return result_df

def collect_historical_data(years_back=LOOKBACK_YEARS, history_file=HISTORY_FILE,
                            commodity_names=None, start_year=None):
    print("=" * 80)
    period = f"from {start_year}" if start_year is not None else f"Past {years_back} Years"
    print(f"CFTC COT - Historical Data Collection ({period})")
    print("=" * 80)

    current_year = datetime.now().year
    futures_list = get_all_futures()
    if commodity_names is not None:
        wanted = set(commodity_names)
        futures_list = [item for item in futures_list if item[0] in wanted]
        missing = wanted - {item[0] for item in futures_list}
        if missing:
            raise ValueError(f"Unknown commodities: {', '.join(sorted(missing))}")

    if start_year is not None:
        start_year = max(EARLIEST_ARCHIVE_YEAR, int(start_year))
        cutoff = datetime(start_year, 1, 1)
        years = range(start_year, current_year + 1)
    else:
        cutoff = datetime.now() - timedelta(days=366 * years_back)
        years = range(current_year - years_back, current_year + 1)
    downloaded_records = []

    if start_year is not None and start_year <= 2016:
        print("\nDownloading combined archive 1986_2016...")
        df = download_legacy_data_for_year('1986_2016')
        if df is not None:
            records = parse_legacy_year(df, futures_list, cutoff)
            downloaded_records.extend(records)
            merge_history_records(records, history_file)
            report_dates = sorted({record['Date'] for record in records})
            print(f"  Matched records: {len(records)}")
            print(f"  Report dates: {len(report_dates)}")
        years = range(2017, current_year + 1)

    for year in years:
        print(f"\nDownloading year {year}...")
        df = download_legacy_data_for_year(year)
        if df is not None:
            records = parse_legacy_year(df, futures_list, cutoff)
            downloaded_records.extend(records)
            merge_history_records(records, history_file)
            report_dates = sorted({record['Date'] for record in records})
            print(f"  Matched records: {len(records)}")
            print(f"  Report dates: {len(report_dates)}")

    downloaded_df = pd.DataFrame(downloaded_records)
    if downloaded_df.empty:
        print("\nNo downloaded data matched the configured markets.")
        return pd.DataFrame()

    if os.path.exists(history_file):
        existing_df = pd.read_csv(history_file)
        before_count = len(existing_df)
        existing_df = existing_df[~existing_df.set_index(['Date', 'Commodity']).index.isin(
            downloaded_df.set_index(['Date', 'Commodity']).index
        )]
        result_df = pd.concat([existing_df, downloaded_df], ignore_index=True)
        replaced_count = before_count - len(existing_df)
    else:
        result_df = downloaded_df
        replaced_count = 0

    result_df['Date'] = pd.to_datetime(result_df['Date']).dt.strftime('%Y-%m-%d')
    result_df = result_df.drop_duplicates(['Date', 'Commodity'], keep='last')
    result_df = result_df.sort_values(['Date', 'Commodity'], ascending=[False, True])
    result_df = result_df[['Date', 'Commodity', 'NonComm Long', 'NonComm Short', 'NonComm Net', 'Code']]

    result_df.to_csv(history_file, index=False)
    print(f"\n✓ Historical data saved to: {history_file}")
    print(f"  Downloaded/updated records: {len(downloaded_df)}")
    print(f"  Replaced existing records: {replaced_count}")
    print(f"  Total records: {len(result_df)}")
    print(f"  Date range: {result_df['Date'].min()} to {result_df['Date'].max()}")

    return result_df

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Backfill CFTC legacy COT history')
    parser.add_argument('--all-history', action='store_true',
                        help=f'fetch archives from {EARLIEST_ARCHIVE_YEAR}')
    parser.add_argument('--priority-markets', action='store_true',
                        help='only fetch Coffee/Cocoa/Cotton/Sugar/MES/Soybean Oil/Copper')
    args = parser.parse_args()

    collect_historical_data(
        commodity_names=PRIORITY_HISTORY_MARKETS if args.priority_markets else None,
        start_year=EARLIEST_ARCHIVE_YEAR if args.all_history else None,
    )
