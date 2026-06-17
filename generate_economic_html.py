import json
from datetime import date, datetime, timezone
from pathlib import Path

import requests


COUNTRIES = [
    {"code": "AR", "api": "AR", "name": "Argentina"},
    {"code": "AU", "api": "AU", "name": "Australia"},
    {"code": "BR", "api": "BR", "name": "Brazil"},
    {"code": "CA", "api": "CA", "name": "Canada"},
    {"code": "CN", "api": "CN", "name": "China"},
    {"code": "FR", "api": "FR", "name": "France"},
    {"code": "DE", "api": "DE", "name": "Germany"},
    {"code": "IN", "api": "IN", "name": "India"},
    {"code": "ID", "api": "ID", "name": "Indonesia"},
    {"code": "IT", "api": "IT", "name": "Italy"},
    {"code": "JP", "api": "JP", "name": "Japan"},
    {"code": "MX", "api": "MX", "name": "Mexico"},
    {"code": "RU", "api": "RU", "name": "Russia"},
    {"code": "SA", "api": "SA", "name": "Saudi Arabia"},
    {"code": "ZA", "api": "ZA", "name": "South Africa"},
    {"code": "KR", "api": "KR", "name": "South Korea"},
    {"code": "TR", "api": "TR", "name": "Turkiye"},
    {"code": "GB", "api": "GB", "name": "United Kingdom"},
    {"code": "US", "api": "US", "name": "United States"},
    {"code": "EU", "api": "EUU", "name": "European Union"},
]

COUNTRY_BY_API_ID = {country["code"]: country["code"] for country in COUNTRIES}
COUNTRY_BY_API_ID.update({country["api"]: country["code"] for country in COUNTRIES})
COUNTRY_BY_API_ID["EUU"] = "EU"

INDICATORS = [
    {
        "key": "gdp_growth",
        "label": "GDP Growth Rate",
        "short": "GDP",
        "unit": "%",
        "decimals": 2,
        "world_bank": "NY.GDP.MKTP.KD.ZG",
        "source": "GDP growth (annual %)",
        "note": "Annual real GDP growth.",
    },
    {
        "key": "interest_rate",
        "label": "Interest Rate",
        "short": "Rate",
        "unit": "%",
        "decimals": 2,
        "world_bank": "FR.INR.LEND",
        "source": "Lending interest rate (%)",
        "note": "World Bank lending interest rate proxy; policy-rate coverage differs by country.",
    },
    {
        "key": "inflation",
        "label": "Inflation Rate",
        "short": "CPI",
        "unit": "%",
        "decimals": 2,
        "world_bank": "FP.CPI.TOTL.ZG",
        "source": "Inflation, consumer prices (annual %)",
        "note": "Annual consumer price inflation.",
    },
    {
        "key": "unemployment",
        "label": "Unemployment Rate",
        "short": "Jobs",
        "unit": "%",
        "decimals": 2,
        "world_bank": "SL.UEM.TOTL.ZS",
        "source": "Unemployment, total (% of total labor force)",
        "note": "Modeled ILO estimate.",
    },
    {
        "key": "government_debt",
        "label": "Government Debt to GDP",
        "short": "Debt",
        "unit": "%",
        "decimals": 2,
        "world_bank": "GC.DOD.TOTL.GD.ZS",
        "source": "Central government debt, total (% of GDP)",
        "note": "Central government debt series; some G20 members have sparse coverage.",
    },
    {
        "key": "balance_trade",
        "label": "Balance of Trade",
        "short": "Trade",
        "unit": "$B",
        "decimals": 1,
        "derived": "exports_minus_imports",
        "source": "Exports of goods and services minus imports of goods and services",
        "note": "Annual goods and services balance, current US dollars.",
    },
    {
        "key": "current_account",
        "label": "Current Account to GDP",
        "short": "Account",
        "unit": "%",
        "decimals": 2,
        "world_bank": "BN.CAB.XOKA.GD.ZS",
        "source": "Current account balance (% of GDP)",
        "note": "Annual current account balance as a share of GDP.",
    },
]

CREDIT_RATINGS = {
    "AR": "CCC",
    "AU": "AAA",
    "BR": "BB",
    "CA": "AAA",
    "CN": "A+",
    "FR": "AA-",
    "DE": "AAA",
    "IN": "BBB-",
    "ID": "BBB",
    "IT": "BBB",
    "JP": "A+",
    "MX": "BBB",
    "RU": "NR",
    "SA": "A+",
    "ZA": "BB-",
    "KR": "AA",
    "TR": "BB-",
    "GB": "AA",
    "US": "AA+",
    "EU": "AAA",
}

RATING_SCORE = {
    "AAA": 22,
    "AA+": 21,
    "AA": 20,
    "AA-": 19,
    "A+": 18,
    "A": 17,
    "A-": 16,
    "BBB+": 15,
    "BBB": 14,
    "BBB-": 13,
    "BB+": 12,
    "BB": 11,
    "BB-": 10,
    "B+": 9,
    "B": 8,
    "B-": 7,
    "CCC+": 6,
    "CCC": 5,
    "CCC-": 4,
    "CC": 3,
    "C": 2,
    "D": 1,
    "NR": None,
}

WORLD_BANK_API = "https://api.worldbank.org/v2/country/{countries}/indicator/{indicator}"


def fetch_world_bank_indicator(indicator, start_year, end_year):
    country_list = ";".join(country["api"] for country in COUNTRIES)
    response = requests.get(
        WORLD_BANK_API.format(countries=country_list, indicator=indicator),
        params={
            "format": "json",
            "date": f"{start_year}:{end_year}",
            "per_page": 20000,
        },
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    if len(payload) < 2 or payload[1] is None:
        return {country["code"]: {} for country in COUNTRIES}

    result = {country["code"]: {} for country in COUNTRIES}
    for row in payload[1]:
        api_id = row.get("country", {}).get("id") or row.get("countryiso3code")
        country_code = COUNTRY_BY_API_ID.get(api_id)
        if country_code is None:
            continue
        value = row.get("value")
        try:
            year = int(row.get("date"))
        except (TypeError, ValueError):
            continue
        result[country_code][year] = None if value is None else float(value)
    return result


def select_years(values_by_country, fallback_start, fallback_end):
    years = sorted(
        {
            year
            for rows in values_by_country.values()
            for year, value in rows.items()
            if value is not None
        }
    )
    if not years:
        return list(range(fallback_start, fallback_end + 1))[-10:]
    return years[-10:]


def build_series(values_by_country, years, decimals):
    series = {}
    for country in COUNTRIES:
        country_values = values_by_country.get(country["code"], {})
        series[country["code"]] = [
            None if country_values.get(year) is None else round(country_values[year], decimals)
            for year in years
        ]
    return series


def latest_non_null(values, years):
    for index in range(len(values) - 1, -1, -1):
        if values[index] is not None:
            return {"year": years[index], "value": values[index]}
    return {"year": None, "value": None}


def build_indicator_payload(config, values_by_country, start_year, end_year):
    years = select_years(values_by_country, start_year, end_year)
    series = build_series(values_by_country, years, config["decimals"])
    latest = {
        country["code"]: latest_non_null(series[country["code"]], years)
        for country in COUNTRIES
    }
    return {
        "key": config["key"],
        "label": config["label"],
        "short": config["short"],
        "unit": config["unit"],
        "decimals": config["decimals"],
        "source": config["source"],
        "note": config["note"],
        "years": years,
        "series": series,
        "latest": latest,
    }


def build_trade_balance(start_year, end_year):
    exports = fetch_world_bank_indicator("NE.EXP.GNFS.CD", start_year, end_year)
    imports = fetch_world_bank_indicator("NE.IMP.GNFS.CD", start_year, end_year)
    result = {country["code"]: {} for country in COUNTRIES}
    for country in COUNTRIES:
        code = country["code"]
        years = set(exports.get(code, {})) | set(imports.get(code, {}))
        for year in years:
            export_value = exports.get(code, {}).get(year)
            import_value = imports.get(code, {}).get(year)
            result[code][year] = (
                None
                if export_value is None or import_value is None
                else (export_value - import_value) / 1_000_000_000
            )
    return result


def build_credit_payload():
    values = {}
    latest = {}
    for country in COUNTRIES:
        rating = CREDIT_RATINGS.get(country["code"], "NR")
        score = RATING_SCORE.get(rating)
        values[country["code"]] = rating
        latest[country["code"]] = {"year": "Current", "value": rating, "score": score}
    return {
        "key": "credit_rating",
        "label": "Credit Rating",
        "short": "Rating",
        "unit": "",
        "decimals": 0,
        "kind": "rating",
        "source": "S&P long-term foreign-currency sovereign rating snapshot",
        "note": "Latest snapshot only; World Bank does not provide a 10-year sovereign credit-rating time series.",
        "values": values,
        "scores": RATING_SCORE,
        "latest": latest,
    }


def build_payload():
    end_year = date.today().year - 1
    start_year = end_year - 10
    indicators = []
    for config in INDICATORS:
        if config.get("derived") == "exports_minus_imports":
            values = build_trade_balance(start_year, end_year)
        else:
            values = fetch_world_bank_indicator(config["world_bank"], start_year, end_year)
        indicators.append(build_indicator_payload(config, values, start_year, end_year))

    indicators.append(build_credit_payload())
    return {
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "source": "World Bank WDI API",
        "sourceUrl": "https://api.worldbank.org/v2/",
        "countries": [{"code": item["code"], "name": item["name"]} for item in COUNTRIES],
        "indicators": indicators,
    }


HTML_TEMPLATE = r'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Economic - G20 Macro Dashboard</title>
<style>
:root{
  --tv-bg:#0b0f19;
  --tv-panel:#131722;
  --tv-panel-2:#0f131d;
  --tv-border:#2a2e39;
  --tv-border-soft:#1f2430;
  --tv-text:#d1d4dc;
  --tv-muted:#787b86;
  --tv-faint:#5d606b;
  --tv-blue:#2962ff;
  --tv-green:#26a69a;
  --tv-red:#ef5350;
  --tv-amber:#f6a821;
  --tv-hover:#1e222d;
}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;background:var(--tv-bg);color:var(--tv-text);padding:0}
.site-nav{min-height:64px;display:flex;align-items:center;gap:28px;padding:0 24px;background:#000;border-bottom:1px solid #1b1f2a;position:relative;z-index:30}
.site-brand{display:inline-flex;align-items:center;gap:10px;color:#fff;text-decoration:none;font-size:25px;font-weight:800;letter-spacing:0;white-space:nowrap}
.brand-mark{position:relative;width:22px;height:26px;display:inline-block}
.brand-mark::before{content:"";position:absolute;left:7px;top:1px;width:10px;height:24px;background:#fff;border-radius:10px 10px 10px 1px;transform:skew(-18deg) rotate(22deg);transform-origin:center}
.brand-mark::after{content:"";position:absolute;left:2px;bottom:2px;width:13px;height:3px;background:#fff;border-radius:999px;transform:rotate(-34deg)}
.nav-check{position:absolute;opacity:0;pointer-events:none}
.nav-toggle{display:none;width:38px;height:38px;border:1px solid #2a2e39;border-radius:999px;align-items:center;justify-content:center;flex-direction:column;gap:4px;cursor:pointer;margin-left:auto}
.nav-toggle span{width:16px;height:2px;background:#fff;border-radius:999px}
.nav-links{display:flex;align-items:center;gap:28px;flex:0 1 auto}
.nav-link{position:relative;color:#f3f4f6;text-decoration:none;font-size:15px;font-weight:650;white-space:nowrap}
.nav-link:hover{color:#b8ff00}
.nav-link.active{color:#b8ff00}
.nav-link.active::after{content:"";position:absolute;left:0;right:0;bottom:-10px;height:2px;background:#b8ff00;border-radius:999px}
.nav-search{position:relative;flex:0 1 360px;min-width:220px;margin-left:auto}
.nav-search input{width:100%;height:42px;border:1px solid #2a2e39;border-radius:999px;background:#090c12;color:#fff;padding:0 16px 0 42px;font-size:15px;font-weight:650;outline:none}
.nav-search input::placeholder{color:#787b86}
.nav-search input:focus{border-color:#b8ff00;box-shadow:0 0 0 1px rgba(184,255,0,.24)}
.nav-search-mark{position:absolute;left:16px;top:50%;width:13px;height:13px;border:2px solid #b8ff00;border-radius:50%;transform:translateY(-50%);pointer-events:none}
.nav-search-mark::after{content:"";position:absolute;width:7px;height:2px;background:#b8ff00;border-radius:999px;right:-6px;bottom:-4px;transform:rotate(45deg)}
.container{max-width:1600px;margin:0 auto;padding:10px}
.dashboard-head{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:8px;padding:10px 12px;background:var(--tv-panel);border:1px solid var(--tv-border);border-radius:6px;flex-wrap:wrap}
.title-block{display:flex;flex-direction:column;gap:3px;min-width:220px}
h1{font-size:22px;color:#fff;font-weight:800;letter-spacing:0}
.subtitle{font-size:12px;color:var(--tv-muted)}
.source-link{color:var(--tv-blue);text-decoration:none}
.source-link:hover{text-decoration:underline;color:#fff}
.controls{display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.control{height:32px;border:1px solid var(--tv-border);background:var(--tv-panel-2);color:var(--tv-text);border-radius:4px;padding:0 10px;font-size:12px;outline:none}
.control:focus{border-color:var(--tv-blue)}
.tabs{display:flex;gap:4px;margin-bottom:8px;border:1px solid var(--tv-border);background:var(--tv-panel);border-radius:6px;padding:5px;overflow:auto}
.tab{height:30px;padding:0 12px;border:none;border-radius:4px;background:transparent;color:var(--tv-muted);font-size:12px;font-weight:800;cursor:pointer;white-space:nowrap}
.tab:hover{background:var(--tv-hover);color:var(--tv-text)}
.tab.active{background:var(--tv-blue);color:#fff}
.metric-strip{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center;gap:10px;margin-bottom:8px;padding:9px 12px;background:var(--tv-panel);border:1px solid var(--tv-border);border-radius:6px}
.metric-title{font-size:15px;font-weight:800;color:#fff}
.metric-note{margin-top:2px;color:var(--tv-muted);font-size:12px;line-height:1.4}
.metric-count{font-family:"SF Mono","Fira Code",monospace;font-size:11px;color:var(--tv-muted);white-space:nowrap}
.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px}
.country-card{min-width:0;background:var(--tv-panel);border:1px solid var(--tv-border);border-radius:6px;overflow:hidden}
.country-card:hover{border-color:#3a4050;background:#161b27}
.card-head{display:flex;justify-content:space-between;gap:10px;align-items:flex-start;padding:9px 10px 0}
.country-name{font-size:13px;font-weight:800;color:#fff;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.country-code{font-family:"SF Mono","Fira Code",monospace;font-size:10px;color:var(--tv-muted)}
.latest-year{font-family:"SF Mono","Fira Code",monospace;font-size:10px;color:var(--tv-faint);padding-top:2px}
.value-line{display:flex;align-items:baseline;gap:8px;padding:4px 10px 0}
.latest-value{font-family:"SF Mono","Fira Code",monospace;font-size:20px;font-weight:800;color:var(--tv-text)}
.latest-value.up{color:var(--tv-green)}
.latest-value.down{color:var(--tv-red)}
.delta{font-family:"SF Mono","Fira Code",monospace;font-size:11px;font-weight:800}
.delta.up{color:var(--tv-green)}
.delta.down{color:var(--tv-red)}
.chart-box{height:112px;padding:2px 8px 6px}
.spark{width:100%;height:100%;display:block}
.axis{display:flex;justify-content:space-between;padding:0 10px 8px;color:var(--tv-faint);font-family:"SF Mono","Fira Code",monospace;font-size:10px}
.empty{padding:42px 12px;color:var(--tv-muted);font-size:12px;text-align:center}
.rating-pill{display:inline-flex;align-items:center;justify-content:center;min-width:72px;height:34px;border-radius:4px;border:1px solid var(--tv-border);background:var(--tv-panel-2);font-family:"SF Mono","Fira Code",monospace;font-size:18px;font-weight:800;color:#fff}
.rating-meter{height:112px;padding:12px 10px 10px;display:flex;align-items:flex-end}
.rating-track{position:relative;width:100%;height:10px;background:var(--tv-panel-2);border:1px solid var(--tv-border);border-radius:999px}
.rating-fill{position:absolute;left:0;top:0;bottom:0;background:var(--tv-blue);border-radius:999px}
.rating-dot{position:absolute;top:50%;width:12px;height:12px;border-radius:50%;background:#fff;border:2px solid var(--tv-blue);transform:translate(-50%,-50%)}
@media(max-width:1100px){
  .grid{grid-template-columns:repeat(3,minmax(0,1fr))}
}
@media(max-width:820px){
  .grid{grid-template-columns:repeat(2,minmax(0,1fr))}
}
@media(max-width:768px){
  .site-nav{min-height:58px;padding:10px 14px;gap:10px;flex-wrap:wrap}
  .site-brand{font-size:21px}
  .brand-mark{width:20px;height:24px}
  .nav-toggle{display:flex}
  .nav-links,.nav-search{display:none;flex:0 0 100%;width:100%}
  .nav-check:checked ~ .nav-links{display:flex}
  .nav-check:checked ~ .nav-search{display:block}
  .nav-links{order:3;flex-direction:column;align-items:stretch;gap:4px;padding-top:8px}
  .nav-link{height:40px;display:flex;align-items:center;padding:0 4px;font-size:14px}
  .nav-link.active::after{left:0;right:auto;bottom:4px;width:32px}
  .nav-search{order:4;min-width:0;margin-left:0;padding-top:8px}
  .nav-search input{height:40px;font-size:14px}
  .container{padding:10px}
  .dashboard-head{align-items:stretch}
  .title-block,.controls{width:100%}
  .control{flex:1;min-width:132px}
  .metric-strip{grid-template-columns:1fr}
  .metric-count{white-space:normal}
}
@media(max-width:520px){
  .grid{grid-template-columns:1fr}
  h1{font-size:20px}
  .tabs{scrollbar-width:none}
  .latest-value{font-size:19px}
  .chart-box{height:118px}
}
</style>
</head>
<body>
<nav class="site-nav" aria-label="Primary">
  <a class="site-brand" href="index.html" aria-label="Net Data home"><span class="brand-mark" aria-hidden="true"></span><span>Net Data</span></a>
  <input class="nav-check" type="checkbox" id="navMenu">
  <label class="nav-toggle" for="navMenu" aria-label="Toggle navigation"><span></span><span></span><span></span></label>
  <div class="nav-links">
    <a class="nav-link" href="index.html">Non-Commercial</a>
    <a class="nav-link" href="russell2000_top100.html">Market</a>
    <a class="nav-link active" href="economic.html">Economic</a>
  </div>
  <form class="nav-search" role="search" data-root="">
    <span class="nav-search-mark" aria-hidden="true"></span>
    <input type="search" name="q" placeholder="Search stocks" autocomplete="off" aria-label="Search stocks">
  </form>
</nav>

<main class="container">
  <section class="dashboard-head">
    <div class="title-block">
      <h1>Economic</h1>
      <p class="subtitle">G20 macro dashboard · Updated __UPDATED__ · <a class="source-link" href="https://api.worldbank.org/v2/" target="_blank" rel="noopener">World Bank API</a></p>
    </div>
    <div class="controls">
      <input class="control" id="countrySearch" type="search" placeholder="Search country" autocomplete="off">
      <select class="control" id="sortSelect" aria-label="Sort countries">
        <option value="name">Country</option>
        <option value="latest-desc">Latest high to low</option>
        <option value="latest-asc">Latest low to high</option>
        <option value="change-desc">10Y change high to low</option>
        <option value="change-asc">10Y change low to high</option>
      </select>
    </div>
  </section>
  <div class="tabs" id="indicatorTabs"></div>
  <section class="metric-strip">
    <div>
      <div class="metric-title" id="metricTitle"></div>
      <div class="metric-note" id="metricNote"></div>
    </div>
    <div class="metric-count" id="metricCount"></div>
  </section>
  <section class="grid" id="countryGrid"></section>
</main>

<script>
const ECONOMIC_DATA = __DATA__;
const state = { indicator: ECONOMIC_DATA.indicators[0].key, query: '', sort: 'name' };
const tabs = document.getElementById('indicatorTabs');
const grid = document.getElementById('countryGrid');
const metricTitle = document.getElementById('metricTitle');
const metricNote = document.getElementById('metricNote');
const metricCount = document.getElementById('metricCount');
const countrySearch = document.getElementById('countrySearch');
const sortSelect = document.getElementById('sortSelect');

function setupNavSearch(){
  const form = document.querySelector('.nav-search');
  if(!form) return;
  const input = form.querySelector('input[name="q"]');
  const runSearch = async () => {
    const query = (input.value || '').trim();
    if(!query) return;
    const root = form.dataset.root || '';
    let target = { symbol: query.toUpperCase(), name: query };
    try{
      const response = await fetch(root + 'market_data/index.json', { cache: 'no-store' });
      if(response.ok){
        const index = await response.json();
        const groups = index.groups || {};
        const rows = Object.keys(groups).length
          ? Object.values(groups).flatMap(group => group.stocks || [])
          : (index.stocks || []);
        const normalized = query.toLowerCase();
        const match = rows.find(row => String(row.symbol || '').toLowerCase() === normalized)
          || rows.find(row => String(row.name || '').toLowerCase().includes(normalized));
        if(match) target = { symbol: match.symbol, name: match.name || match.symbol };
      }
    }catch(error){}
    const params = new URLSearchParams();
    params.set('symbol', target.symbol);
    params.set('name', target.name);
    window.location.href = root + 'stock_chart.html?' + params.toString();
  };
  form.addEventListener('submit', event => {
    event.preventDefault();
    runSearch();
  });
  input.addEventListener('keydown', event => {
    if(event.key !== 'Enter') return;
    event.preventDefault();
    runSearch();
  });
}

function currentIndicator(){
  return ECONOMIC_DATA.indicators.find(item => item.key === state.indicator) || ECONOMIC_DATA.indicators[0];
}

function formatValue(value, indicator){
  if(value === null || value === undefined || value === '') return 'No data';
  if(indicator.kind === 'rating') return value;
  const number = Number(value);
  const suffix = indicator.unit || '';
  return `${number.toLocaleString(undefined, {maximumFractionDigits: indicator.decimals, minimumFractionDigits: indicator.decimals})}${suffix}`;
}

function seriesStats(country, indicator){
  if(indicator.kind === 'rating'){
    const rating = indicator.values[country.code] || 'NR';
    return { latest: rating, latestYear: 'Current', first: null, change: null, score: indicator.scores[rating] };
  }
  const values = indicator.series[country.code] || [];
  const years = indicator.years || [];
  let latest = null;
  let latestYear = null;
  let first = null;
  for(let i = 0; i < values.length; i += 1){
    if(values[i] === null) continue;
    if(first === null) first = values[i];
    latest = values[i];
    latestYear = years[i];
  }
  return { latest, latestYear, first, change: latest !== null && first !== null ? latest - first : null };
}

function sortCountries(countries, indicator){
  return [...countries].sort((a, b) => {
    const aStats = seriesStats(a, indicator);
    const bStats = seriesStats(b, indicator);
    if(state.sort === 'name') return a.name.localeCompare(b.name);
    const key = indicator.kind === 'rating' ? 'score' : state.sort.startsWith('change') ? 'change' : 'latest';
    const direction = state.sort.endsWith('asc') ? 1 : -1;
    const av = aStats[key];
    const bv = bStats[key];
    if(av === null || av === undefined) return 1;
    if(bv === null || bv === undefined) return -1;
    return (av - bv) * direction;
  });
}

function classForNumber(value){
  if(value === null || value === undefined || Number.isNaN(Number(value))) return '';
  return Number(value) >= 0 ? 'up' : 'down';
}

function drawSpark(canvas, values){
  const dpr = window.devicePixelRatio || 1;
  const width = canvas.clientWidth || 260;
  const height = canvas.clientHeight || 112;
  canvas.width = Math.floor(width * dpr);
  canvas.height = Math.floor(height * dpr);
  const ctx = canvas.getContext('2d');
  ctx.setTransform(dpr,0,0,dpr,0,0);
  ctx.clearRect(0,0,width,height);
  ctx.strokeStyle = '#1f2430';
  ctx.lineWidth = 1;
  for(let i = 1; i <= 3; i += 1){
    const y = Math.round((height / 4) * i) + .5;
    ctx.beginPath();
    ctx.moveTo(0,y);
    ctx.lineTo(width,y);
    ctx.stroke();
  }
  const points = values.map((value, index) => ({ value, index })).filter(item => item.value !== null);
  if(points.length < 2){
    ctx.fillStyle = '#787b86';
    ctx.font = '12px -apple-system,BlinkMacSystemFont,Segoe UI,sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('No 10Y series', width / 2, height / 2);
    return;
  }
  const min = Math.min(...points.map(item => item.value));
  const max = Math.max(...points.map(item => item.value));
  const spread = max - min || Math.abs(max) || 1;
  const xStep = width / Math.max(values.length - 1, 1);
  const yFor = value => height - 12 - ((value - min) / spread) * (height - 24);
  const gradient = ctx.createLinearGradient(0,0,width,0);
  gradient.addColorStop(0,'#2962ff');
  gradient.addColorStop(1,'#26a69a');
  ctx.strokeStyle = gradient;
  ctx.lineWidth = 2;
  ctx.beginPath();
  points.forEach((point, index) => {
    const x = point.index * xStep;
    const y = yFor(point.value);
    if(index === 0) ctx.moveTo(x,y);
    else ctx.lineTo(x,y);
  });
  ctx.stroke();
  const last = points[points.length - 1];
  ctx.fillStyle = '#fff';
  ctx.beginPath();
  ctx.arc(last.index * xStep, yFor(last.value), 3, 0, Math.PI * 2);
  ctx.fill();
}

function renderTabs(){
  tabs.innerHTML = ECONOMIC_DATA.indicators.map(indicator => (
    `<button class="tab ${indicator.key === state.indicator ? 'active' : ''}" data-key="${indicator.key}">${indicator.label}</button>`
  )).join('');
  tabs.querySelectorAll('.tab').forEach(button => {
    button.addEventListener('click', () => {
      state.indicator = button.dataset.key;
      render();
    });
  });
}

function renderMetric(indicator, countries){
  metricTitle.textContent = indicator.label;
  metricNote.textContent = `${indicator.source}. ${indicator.note}`;
  metricCount.textContent = indicator.kind === 'rating'
    ? `${countries.length} G20 members · latest snapshot`
    : `${countries.length} G20 members · ${indicator.years[0]}-${indicator.years[indicator.years.length - 1]}`;
}

function renderRatingMeter(score){
  if(score === null || score === undefined) return '<div class="empty">No rating</div>';
  const pct = Math.max(0, Math.min(100, score / 22 * 100));
  return `<div class="rating-meter"><div class="rating-track"><span class="rating-fill" style="width:${pct}%"></span><span class="rating-dot" style="left:${pct}%"></span></div></div>`;
}

function renderGrid(indicator){
  const normalized = state.query.trim().toLowerCase();
  const filtered = ECONOMIC_DATA.countries.filter(country => (
    !normalized || country.name.toLowerCase().includes(normalized) || country.code.toLowerCase().includes(normalized)
  ));
  const countries = sortCountries(filtered, indicator);
  renderMetric(indicator, countries);
  if(!countries.length){
    grid.innerHTML = '<div class="empty">No matching country</div>';
    return;
  }
  grid.innerHTML = countries.map(country => {
    const stats = seriesStats(country, indicator);
    const latestClass = indicator.kind === 'rating' ? '' : classForNumber(stats.latest);
    const deltaClass = classForNumber(stats.change);
    const delta = indicator.kind === 'rating'
      ? 'S&P snapshot'
      : stats.change === null ? 'No 10Y change' : `${stats.change >= 0 ? '+' : ''}${stats.change.toFixed(indicator.decimals)}${indicator.unit}`;
    const chart = indicator.kind === 'rating'
      ? renderRatingMeter(stats.score)
      : '<div class="chart-box"><canvas class="spark"></canvas></div>';
    const axis = indicator.kind === 'rating'
      ? '<div class="axis"><span>Lowest</span><span>Highest</span></div>'
      : `<div class="axis"><span>${indicator.years[0]}</span><span>${indicator.years[indicator.years.length - 1]}</span></div>`;
    return `<article class="country-card" data-code="${country.code}">
      <div class="card-head">
        <div><div class="country-name">${country.name}</div><div class="country-code">${country.code}</div></div>
        <div class="latest-year">${stats.latestYear || '--'}</div>
      </div>
      <div class="value-line">
        ${indicator.kind === 'rating' ? `<span class="rating-pill">${formatValue(stats.latest, indicator)}</span>` : `<span class="latest-value ${latestClass}">${formatValue(stats.latest, indicator)}</span>`}
        <span class="delta ${deltaClass}">${delta}</span>
      </div>
      ${chart}
      ${axis}
    </article>`;
  }).join('');
  if(indicator.kind !== 'rating'){
    grid.querySelectorAll('.country-card').forEach(card => {
      const countryCode = card.dataset.code;
      const canvas = card.querySelector('canvas');
      drawSpark(canvas, indicator.series[countryCode] || []);
    });
  }
}

function render(){
  renderTabs();
  renderGrid(currentIndicator());
}

countrySearch.addEventListener('input', () => {
  state.query = countrySearch.value;
  renderGrid(currentIndicator());
});
sortSelect.addEventListener('change', () => {
  state.sort = sortSelect.value;
  renderGrid(currentIndicator());
});
window.addEventListener('resize', () => renderGrid(currentIndicator()));
setupNavSearch();
render();
</script>
</body>
</html>
'''


def write_outputs(payload):
    data_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    Path("economic_data.json").write_text(data_json, encoding="utf-8")
    html = HTML_TEMPLATE.replace("__DATA__", data_json).replace("__UPDATED__", payload["updated"])
    Path("economic.html").write_text(html, encoding="utf-8")


def main():
    payload = build_payload()
    write_outputs(payload)
    print(f"Generated economic.html with {len(payload['countries'])} countries")


if __name__ == "__main__":
    main()
