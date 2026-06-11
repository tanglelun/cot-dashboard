#!/usr/bin/env python3
"""
CFTC COT Data Update Script
Run this weekly to fetch recent history, merge it into the existing file,
and preserve older records.
"""

import requests
import pandas as pd
import io
from datetime import datetime
import zipfile
import os

HISTORY_FILE = 'cot_noncommercial_history.csv'

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

def download_latest_data():
    base_url = "https://www.cftc.gov/files/dea/history/"
    current_year = datetime.now().year
    
    for year in [current_year, current_year - 1]:
        url = f"{base_url}deacot{year}.zip"
        response = requests.head(url)
        if response.status_code == 200:
            print(f"Downloading: {url}")
            response = requests.get(url)
            with zipfile.ZipFile(io.BytesIO(response.content)) as z:
                for fname in z.namelist():
                    if fname.endswith('.txt'):
                        df = pd.read_csv(z.open(fname))
                        return df
    return None

def get_latest_week_data(df, futures_list):
    date_col = 'As of Date in Form YYYY-MM-DD'
    market_col = 'Market and Exchange Names'
    noncomm_long = 'Noncommercial Positions-Long (All)'
    noncomm_short = 'Noncommercial Positions-Short (All)'
    
    df[date_col] = pd.to_datetime(df[date_col])
    latest_date = df[date_col].max()
    print(f"Latest report date: {latest_date.strftime('%Y-%m-%d')}")
    
    latest_df = df[df[date_col] == latest_date].copy()
    
    new_records = []
    for name, code in futures_list:
        row = find_contract(latest_df, market_col, code)
        if row is not None:
            long_val = parse_position(row[noncomm_long])
            short_val = parse_position(row[noncomm_short])
            net_val = long_val - short_val
            
            new_records.append({
                'Date': latest_date.strftime('%Y-%m-%d'),
                'Commodity': name,
                'Code': code,
                'NonComm Long': long_val,
                'NonComm Short': short_val,
                'NonComm Net': net_val,
            })
    
    return pd.DataFrame(new_records), latest_date

def main():
    print("=" * 60)
    print("CFTC COT Data Update")
    print("=" * 60)

    from cot_historical import collect_historical_data

    result_df = collect_historical_data(years_back=10, history_file=HISTORY_FILE)
    if result_df.empty:
        print("Failed to update data")
        return

    print(f"\nLatest data: {result_df['Date'].max()}")
    print("Done!")

if __name__ == "__main__":
    main()
