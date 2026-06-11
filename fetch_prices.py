import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
import os

PRICE_FILE = 'price_history.csv'
LOOKBACK_MONTHS = 124

commodity_tickers = {
    'Corn': 'ZC=F',
    'Soybeans': 'ZS=F',
    'Soybean Meal': 'ZM=F',
    'Soybean Oil': 'ZL=F',
    'Wheat': 'ZW=F',
    'Hard Red Winter Wheat': 'KE=F',
    'Spring Wheat Mpls': 'MWE=F',
    'Rough Rice': 'ZR=F',
    'Canola': 'RS=F',
    'Oats': 'ZO=F',
    'Crude Oil': 'CL=F',
    'Natural Gas': 'NG=F',
    'Gold': 'GC=F',
    'Silver': 'SI=F',
    'Copper': 'HG=F',
    'Platinum': 'PL=F',
    'Palladium': 'PA=F',
    'Coffee': 'KC=F',
    'Sugar': 'SB=F',
    'Cocoa': 'CC=F',
    'Cotton': 'CT=F',
    'Orange Juice': 'OJ=F',
    'Live Cattle': 'LE=F',
    'Lean Hogs': 'HE=F',
    'Feeder Cattle': 'GF=F',
    'Euro FX': 'EC=F',
    'British Pound': 'BP=F',
    'Japanese Yen': 'JY=F',
    'Swiss Franc': 'SF=F',
    'Australian Dollar': 'AD=F',
    'Canadian Dollar': 'CD=F',
    'Mexican Peso': 'MP=F',
    'U.S. Dollar Index': 'DXY',
    'S&P 500': 'ES=F',
    'Nasdaq 100': 'NQ=F',
    'Dow Jones': 'YM=F',
    'Russell 2000': 'RTY=F',
    'S&P 500 Micro': 'MES=F',
    '10-Year T-Note': 'TY=F',
    '5-Year T-Note': 'FV=F',
    '2-Year T-Note': 'TU=F',
    '30-Year T-Bond': 'US=F',
}

def get_price_data(ticker, months=LOOKBACK_MONTHS):
    try:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=months*30)
        
        data = yf.download(ticker, start=start_date, end=end_date, progress=False)
        
        if data.empty:
            return None
        
        if 'Close' in data.columns:
            return data['Close']
        elif 'Adj Close' in data.columns:
            return data['Adj Close']
    except Exception as e:
        print(f"Error fetching {ticker}: {e}")
    return None

def generate_price_csv():
    print("Fetching price data from Yahoo Finance...")
    
    all_prices = []
    
    for name, ticker in commodity_tickers.items():
        print(f"Fetching {name} ({ticker})...", end=" ")
        price = get_price_data(ticker)
        if price is not None and len(price) > 0:
            df_temp = pd.DataFrame({
                'Date': price.index.strftime('%Y-%m-%d'),
                'Commodity': name,
                'Price': price.values.flatten()
            })
            all_prices.append(df_temp)
            print(f"Got {len(price)} data points")
        else:
            print("No data")
    
    if not all_prices:
        print("No price data fetched")
        return
    
    df = pd.concat(all_prices, ignore_index=True)
    df['Date'] = pd.to_datetime(df['Date']).dt.strftime('%Y-%m-%d')

    if os.path.exists(PRICE_FILE):
        existing_df = pd.read_csv(PRICE_FILE)
        df = pd.concat([existing_df, df], ignore_index=True)
        df['Date'] = pd.to_datetime(df['Date']).dt.strftime('%Y-%m-%d')
        df['Price'] = pd.to_numeric(df['Price'], errors='coerce')
        df = df.dropna(subset=['Date', 'Commodity', 'Price'])
        df = df.drop_duplicates(['Date', 'Commodity'], keep='last')

    df = df.sort_values(['Commodity', 'Date'])
    df.to_csv(PRICE_FILE, index=False)
    print(f"Saved price data to {PRICE_FILE}")
    print(f"Total records: {len(df)}")
    print(f"Date range: {df['Date'].min()} to {df['Date'].max()}")

if __name__ == "__main__":
    generate_price_csv()
