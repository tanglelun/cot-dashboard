import requests
import pandas as pd
import io
from datetime import datetime
import zipfile

def download_disaggregated_data():
    base_url = "https://www.cftc.gov/files/dea/history/"
    current_year = datetime.now().year
    
    years = [current_year, current_year - 1, current_year - 2]
    for year in years:
        url = f"{base_url}fut_disagg_txt_{year}.zip"
        response = requests.head(url)
        if response.status_code == 200:
            print(f"Found Disaggregated data for year: {year}")
            response = requests.get(url)
            with zipfile.ZipFile(io.BytesIO(response.content)) as z:
                for fname in z.namelist():
                    if fname.endswith('.txt'):
                        df = pd.read_csv(z.open(fname))
                        return df
    return None

def download_legacy_data():
    base_url = "https://www.cftc.gov/files/dea/history/"
    current_year = datetime.now().year
    
    years = [current_year, current_year - 1, current_year - 2]
    for year in years:
        url = f"{base_url}deacot{year}.zip"
        response = requests.head(url)
        if response.status_code == 200:
            print(f"Found Legacy data for year: {year}")
            response = requests.get(url)
            with zipfile.ZipFile(io.BytesIO(response.content)) as z:
                for fname in z.namelist():
                    if fname.endswith('.txt'):
                        df = pd.read_csv(z.open(fname))
                        return df
    return None

def get_all_futures():
    return [
        ('Corn', 'CORN'),
        ('Soybeans', 'SOYBEANS'),
        ('Wheat', 'WHEAT'),
        ('Soybean Oil', 'SOYBEAN OIL'),
        ('Soybean Meal', 'SOYBEAN MEAL'),
        ('Oats', 'OATS'),
        ('Rice', 'RICE'),
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
        ('S&P 500', 'S&P 500'),
        ('Nasdaq 100', 'NASDAQ-100'),
        ('Dow Jones', 'DOW JONES'),
        ('Russell 2000', 'RUSSELL'),
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

def create_barchart_table(df, futures_list, use_disaggregated=True):
    if df.empty:
        print("No data available")
        return None, None
    
    if use_disaggregated:
        date_col = 'Report_Date_as_YYYY-MM-DD'
        market_col = 'Market_and_Exchange_Names'
        noncomm_long = 'M_Money_Positions_Long_All'
        noncomm_short = 'M_Money_Positions_Short_All'
    else:
        date_col = 'As of Date in Form YYYY-MM-DD'
        market_col = 'Market and Exchange Names'
        noncomm_long = 'Noncommercial Positions-Long (All)'
        noncomm_short = 'Noncommercial Positions-Short (All)'
    
    df[date_col] = pd.to_datetime(df[date_col])
    latest_date = df[date_col].max()
    print(f"Latest report date: {latest_date}")
    
    latest_df = df[df[date_col] == latest_date].copy()
    
    results = []
    for name, code in futures_list:
        row = find_contract(latest_df, market_col, code)
        if row is not None:
            long_val = parse_position(row[noncomm_long])
            short_val = parse_position(row[noncomm_short])
            net_val = long_val - short_val
        else:
            long_val = 0
            short_val = 0
            net_val = 0
        
        results.append({
            'Commodity': name,
            'Code': code,
            'NonComm Long': long_val,
            'NonComm Short': short_val,
            'NonComm Net': net_val,
        })
    
    result_df = pd.DataFrame(results)
    if not result_df.empty:
        result_df['NonComm Net'] = result_df['NonComm Net'].apply(lambda x: f"{x:,}")
        result_df['NonComm Long'] = result_df['NonComm Long'].apply(lambda x: f"{x:,}")
        result_df['NonComm Short'] = result_df['NonComm Short'].apply(lambda x: f"{x:,}")
    
    return result_df, latest_date

def main():
    print("=" * 80)
    print("CFTC Commitments of Traders - Non-Commercial Positions")
    print("=" * 80)
    
    futures_list = get_all_futures()
    
    df_disagg = download_disaggregated_data()
    if df_disagg is not None:
        print(f"Disaggregated data rows: {len(df_disagg)}")
    
    df_legacy = download_legacy_data()
    if df_legacy is not None:
        print(f"Legacy data rows: {len(df_legacy)}")
    
    if df_legacy is not None:
        table, date = create_barchart_table(df_legacy, futures_list, use_disaggregated=False)
    elif df_disagg is not None:
        table, date = create_barchart_table(df_disagg, futures_list, use_disaggregated=True)
    else:
        print("No data available")
        return
    
    if table is not None and not table.empty and date is not None:
        print(f"\nAs of: {date.strftime('%Y-%m-%d')}")
        print("-" * 80)
        print(table.to_string(index=False))
        print("-" * 80)
        
        output_file = 'cot_noncommercial.csv'
        table.to_csv(output_file, index=False)
        print(f"\nData saved to: {output_file}")
        
        generate_html_table(table, date)

def generate_html_table(df, date):
    categories = {
        'Grains': ['Corn', 'Soybeans', 'Wheat', 'Soybean Oil', 'Soybean Meal', 'Rice', 'Oats'],
        'Energies': ['Crude Oil', 'Natural Gas'],
        'Metals': ['Gold', 'Silver', 'Copper', 'Platinum', 'Palladium'],
        'Softs': ['Coffee', 'Sugar', 'Cocoa', 'Cotton', 'Orange Juice'],
        'Livestock': ['Live Cattle', 'Lean Hogs', 'Feeder Cattle'],
        'Currencies': ['Euro FX', 'British Pound', 'Japanese Yen', 'Swiss Franc', 'Australian Dollar', 'Canadian Dollar', 'Mexican Peso'],
        'Indices': ['S&P 500', 'Nasdaq 100', 'Dow Jones', 'Russell 2000'],
        'Treasuries': ['10-Year T-Note', '5-Year T-Note', '2-Year T-Note', '30-Year T-Bond']
    }
    
    code_map = {
        'Corn': 'ZC', 'Soybeans': 'ZS', 'Wheat': 'ZW', 'Soybean Oil': 'ZL', 'Soybean Meal': 'ZM',
        'Oats': 'ZO', 'Rice': 'ZR', 'Crude Oil': 'CL', 'Natural Gas': 'NG', 'Gold': 'GC',
        'Silver': 'SI', 'Copper': 'HG', 'Platinum': 'PL', 'Palladium': 'PA', 'Coffee': 'KC',
        'Sugar': 'SB', 'Cocoa': 'CC', 'Cotton': 'CT', 'Orange Juice': 'OJ', 'Live Cattle': 'LE',
        'Lean Hogs': 'HE', 'Feeder Cattle': 'GF', 'Euro FX': 'EC', 'British Pound': 'BP',
        'Japanese Yen': 'JY', 'Swiss Franc': 'SF', 'Australian Dollar': 'AD', 'Canadian Dollar': 'CD',
        'Mexican Peso': 'MP', 'S&P 500': 'ES', 'Nasdaq 100': 'NQ', 'Dow Jones': 'YM',
        'Russell 2000': 'TF', '10-Year T-Note': 'TY', '5-Year T-Note': 'FV', '2-Year T-Note': 'TU',
        '30-Year T-Bond': 'US'
    }
    
    rows_html = ''
    for category, commodities in categories.items():
        rows_html += f'<tr class="category"><td colspan="5">{category}</td></tr>\n'
        for commodity in commodities:
            row = df[df['Commodity'] == commodity]
            if row.empty:
                long_val = short_val = net_val = '-'
                net_class = 'neutral'
            else:
                long_val = row.iloc[0]['NonComm Long']
                short_val = row.iloc[0]['NonComm Short']
                net_str = row.iloc[0]['NonComm Net'].replace(',', '')
                try:
                    net_num = int(net_str)
                    if net_num > 0:
                        net_val = f'+{row.iloc[0]["NonComm Net"]}'
                        net_class = 'positive'
                    elif net_num < 0:
                        net_val = row.iloc[0]['NonComm Net']
                        net_class = 'negative'
                    else:
                        net_val = '0'
                        net_class = 'neutral'
                except:
                    net_val = '-'
                    net_class = 'neutral'
            
            code = code_map.get(commodity, '')
            rows_html += f'''                <tr>
                    <td class="commodity">{commodity}</td>
                    <td>{code}</td>
                    <td>{long_val}</td>
                    <td>{short_val}</td>
                    <td class="{net_class}">{net_val}</td>
                </tr>
'''
    
    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CFTC Non-Commercial Positions</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f5f5; padding: 20px; }}
        .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        h1 {{ color: #333; margin-bottom: 5px; }}
        .subtitle {{ color: #666; margin-bottom: 20px; font-size: 14px; }}
        table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
        th {{ background: #2c3e50; color: white; padding: 12px 15px; text-align: left; font-weight: 600; }}
        td {{ padding: 10px 15px; border-bottom: 1px solid #eee; }}
        tr:hover {{ background: #f8f9fa; }}
        .commodity {{ font-weight: 600; color: #333; }}
        .positive {{ color: #27ae60; font-weight: 600; }}
        .negative {{ color: #e74c3c; font-weight: 600; }}
        .neutral {{ color: #7f8c8d; }}
        .category {{ background: #ecf0f1; font-weight: 600; color: #2c3e50; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>CFTC Non-Commercial Net Positions</h1>
        <p class="subtitle">Legacy Commitments of Traders Report | As of: {date.strftime('%Y-%m-%d')}</p>
        <table>
            <thead>
                <tr>
                    <th>Commodity</th>
                    <th>Code</th>
                    <th>Long Positions</th>
                    <th>Short Positions</th>
                    <th>Net Positions</th>
                </tr>
            </thead>
            <tbody>
{rows_html}            </tbody>
        </table>
    </div>
</body>
</html>'''
    
    with open('cot_noncommercial.html', 'w') as f:
        f.write(html)
    print(f"HTML saved to: cot_noncommercial.html")

if __name__ == "__main__":
    main()
