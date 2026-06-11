import requests
import pandas as pd
import io
from datetime import datetime, timedelta
import zipfile
import os

HISTORY_FILE = 'cot_noncommercial_history.csv'
LOOKBACK_YEARS = 10

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
    url = f"{base_url}deacot{year}.zip"
    response = requests.get(url)
    if response.status_code != 200:
        print(f"Failed to download {year}: {response.status_code}")
        return None
    
    with zipfile.ZipFile(io.BytesIO(response.content)) as z:
        for fname in z.namelist():
            if fname.endswith('.txt'):
                df = pd.read_csv(z.open(fname))
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

def collect_historical_data(years_back=LOOKBACK_YEARS, history_file=HISTORY_FILE):
    print("=" * 80)
    print(f"CFTC COT - Historical Data Collection (Past {years_back} Years)")
    print("=" * 80)

    current_year = datetime.now().year
    futures_list = get_all_futures()
    cutoff = datetime.now() - timedelta(days=366 * years_back)
    years = range(current_year - years_back, current_year + 1)
    downloaded_records = []

    for year in years:
        print(f"\nDownloading year {year}...")
        df = download_legacy_data_for_year(year)
        if df is not None:
            records = parse_legacy_year(df, futures_list, cutoff)
            downloaded_records.extend(records)
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
    collect_historical_data()
