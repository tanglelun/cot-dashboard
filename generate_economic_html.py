import json
import csv
import io
import time
from datetime import date, datetime, timezone
from functools import lru_cache
from pathlib import Path

import requests


COUNTRIES = [
    {"code": "AR", "api": "AR", "oecd": "ARG", "name": "Argentina"},
    {"code": "AU", "api": "AU", "oecd": "AUS", "name": "Australia"},
    {"code": "BR", "api": "BR", "oecd": "BRA", "name": "Brazil"},
    {"code": "CA", "api": "CA", "oecd": "CAN", "name": "Canada"},
    {"code": "CN", "api": "CN", "oecd": "CHN", "name": "China"},
    {"code": "FR", "api": "FR", "oecd": "FRA", "name": "France"},
    {"code": "DE", "api": "DE", "oecd": "DEU", "name": "Germany"},
    {"code": "IN", "api": "IN", "oecd": "IND", "name": "India"},
    {"code": "ID", "api": "ID", "oecd": "IDN", "name": "Indonesia"},
    {"code": "IT", "api": "IT", "oecd": "ITA", "name": "Italy"},
    {"code": "JP", "api": "JP", "oecd": "JPN", "name": "Japan"},
    {"code": "MX", "api": "MX", "oecd": "MEX", "name": "Mexico"},
    {"code": "RU", "api": "RU", "oecd": "RUS", "name": "Russia"},
    {"code": "SA", "api": "SA", "oecd": "SAU", "name": "Saudi Arabia"},
    {"code": "ZA", "api": "ZA", "oecd": "ZAF", "name": "South Africa"},
    {"code": "KR", "api": "KR", "oecd": "KOR", "name": "South Korea"},
    {"code": "TR", "api": "TR", "oecd": "TUR", "name": "Turkiye"},
    {"code": "GB", "api": "GB", "oecd": "GBR", "name": "United Kingdom"},
    {"code": "US", "api": "US", "oecd": "USA", "name": "United States"},
    {"code": "EU", "api": "EUU", "oecd": "EA", "name": "European Union"},
]

COUNTRY_BY_API_ID = {country["code"]: country["code"] for country in COUNTRIES}
COUNTRY_BY_API_ID.update({country["api"]: country["code"] for country in COUNTRIES})
COUNTRY_BY_API_ID["EUU"] = "EU"
COUNTRY_BY_OECD = {country["oecd"]: country["code"] for country in COUNTRIES}

INDICATORS = [
    {
        "key": "gdp_growth",
        "label": "GDP Growth Rate",
        "short": "GDP",
        "unit": "%",
        "decimals": 2,
        "oecd": ["{area}.Q.B1GQ_Q.GR._T.Y.GY", "{area}.Q.B1GQ_Q.GR._T.Y.G1"],
        "world_bank": "NY.GDP.MKTP.KD.ZG",
        "source": "OECD KEI quarterly GDP growth; World Bank annual fallback",
        "note": "Quarterly where available; annual World Bank points are used only when OECD history is unavailable.",
    },
    {
        "key": "interest_rate",
        "label": "Interest Rate",
        "short": "Rate",
        "unit": "%",
        "decimals": 2,
        "oecd": ["{area}.M.IRSTCI.PA._Z._Z._Z", "{area}.M.IR3TIB.PA._Z._Z._Z", "{area}.M.IRLT.PA._Z._Z._Z"],
        "world_bank": "FR.INR.LEND",
        "source": "OECD KEI monthly interest rates; World Bank annual fallback",
        "note": "Monthly short-term or policy-rate series where available; coverage differs by country.",
    },
    {
        "key": "inflation",
        "label": "Inflation Rate",
        "short": "CPI",
        "unit": "%",
        "decimals": 2,
        "oecd": ["{area}.M.CP.GR._Z._Z.GY"],
        "world_bank": "FP.CPI.TOTL.ZG",
        "source": "OECD KEI monthly CPI inflation; World Bank annual fallback",
        "note": "Monthly year-over-year consumer price inflation where available.",
    },
    {
        "key": "unemployment",
        "label": "Unemployment Rate",
        "short": "Jobs",
        "unit": "%",
        "decimals": 2,
        "oecd": ["{area}.M.UNEMP.PT_LF._T.Y._Z"],
        "world_bank": "SL.UEM.TOTL.ZS",
        "source": "OECD KEI monthly unemployment rate; World Bank annual fallback",
        "note": "Monthly seasonally adjusted unemployment rate where available.",
    },
    {
        "key": "government_debt",
        "label": "Government Debt to GDP",
        "short": "Debt",
        "unit": "%",
        "decimals": 2,
        "world_bank": "GC.DOD.TOTL.GD.ZS",
        "source": "Central government debt, total (% of GDP)",
        "note": "World Bank annual series; many countries do not publish this as a monthly comparable G20 series.",
    },
    {
        "key": "balance_trade",
        "label": "Balance of Trade",
        "short": "Trade",
        "unit": "$B",
        "decimals": 1,
        "derived": "oecd_exports_minus_imports",
        "world_bank_derived": "exports_minus_imports",
        "source": "OECD KEI monthly exports minus imports; World Bank annual fallback",
        "note": "Monthly goods and services balance in billions of US dollars where available.",
    },
    {
        "key": "current_account",
        "label": "Current Account to GDP",
        "short": "Account",
        "unit": "%",
        "decimals": 2,
        "oecd": ["{area}.Q.CA_GDP.PT_B1GQ._T.Y._Z"],
        "world_bank": "BN.CAB.XOKA.GD.ZS",
        "source": "OECD KEI quarterly current account to GDP; World Bank annual fallback",
        "note": "Quarterly current account balance as a share of GDP where available.",
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
OECD_KEI_API = "https://sdmx.oecd.org/public/rest/v1/data/OECD.SDD.STES,DSD_KEI@DF_KEI/{key}"


def fetch_world_bank_indicator(indicator, start_year, end_year):
    country_list = ";".join(country["api"] for country in COUNTRIES)
    for attempt in range(3):
        try:
            response = requests.get(
                WORLD_BANK_API.format(countries=country_list, indicator=indicator),
                params={
                    "format": "json",
                    "date": f"{start_year}:{end_year}",
                    "per_page": 20000,
                },
                timeout=60,
            )
            if response.status_code == 429 and attempt < 2:
                time.sleep(2 + attempt)
                continue
            response.raise_for_status()
            break
        except requests.RequestException as error:
            if attempt < 2:
                time.sleep(1 + attempt)
                continue
            print(f"Skipped World Bank series {indicator}: {error}")
            return {country["code"]: {} for country in COUNTRIES}

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


def period_sort_key(period):
    parts = str(period).split("-")
    try:
        year = int(parts[0])
        month = 0
        if len(parts) > 1:
            if parts[1].startswith("Q"):
                month = (int(parts[1][1:]) - 1) * 3 + 1
            else:
                month = int(parts[1])
        return (year, month, str(period))
    except (TypeError, ValueError):
        return (9999, 99, str(period))


@lru_cache(maxsize=None)
def fetch_oecd_kei_rows(key):
    for attempt in range(2):
        try:
            response = requests.get(
                OECD_KEI_API.format(key=key),
                headers={"Accept": "text/csv"},
                timeout=30,
            )
            if response.status_code == 429 and attempt == 0:
                time.sleep(2)
                continue
            if response.status_code == 404 or response.text.strip() == "NoRecordsFound":
                return []
            response.raise_for_status()
            break
        except requests.RequestException as error:
            if attempt == 0:
                time.sleep(1)
                continue
            print(f"Skipped OECD series {key}: {error}")
            return []
    return list(csv.DictReader(io.StringIO(response.text)))


def fetch_oecd_kei_key(key):
    rows = {}
    for row in fetch_oecd_kei_rows(key):
        value = row.get("OBS_VALUE")
        period = row.get("TIME_PERIOD")
        if not value or not period:
            continue
        try:
            rows[str(period)] = float(value)
        except ValueError:
            continue
    return rows


def fetch_oecd_kei_grouped(key):
    result = {country["code"]: {} for country in COUNTRIES}
    for row in fetch_oecd_kei_rows(key):
        code = COUNTRY_BY_OECD.get(row.get("REF_AREA"))
        if not code:
            continue
        value = row.get("OBS_VALUE")
        period = row.get("TIME_PERIOD")
        if not value or not period:
            continue
        try:
            result[code][str(period)] = float(value)
        except ValueError:
            continue
    return result


def fetch_world_bank_series(indicator, start_year=1960, end_year=None):
    end_year = end_year or date.today().year
    rows_by_country = fetch_world_bank_indicator(indicator, start_year, end_year)
    result = {country["code"]: {} for country in COUNTRIES}
    for country in COUNTRIES:
        for year, value in rows_by_country.get(country["code"], {}).items():
            result[country["code"]][str(year)] = value
    return result


def build_world_bank_trade_balance(start_year=1960, end_year=None):
    end_year = end_year or date.today().year
    exports = fetch_world_bank_indicator("NE.EXP.GNFS.CD", start_year, end_year)
    imports = fetch_world_bank_indicator("NE.IMP.GNFS.CD", start_year, end_year)
    result = {country["code"]: {} for country in COUNTRIES}
    for country in COUNTRIES:
        code = country["code"]
        years = set(exports.get(code, {})) | set(imports.get(code, {}))
        for year in years:
            export_value = exports.get(code, {}).get(year)
            import_value = imports.get(code, {}).get(year)
            result[code][str(year)] = (
                None
                if export_value is None or import_value is None
                else (export_value - import_value) / 1_000_000_000
            )
    return result


def build_oecd_trade_balance():
    exports_by_country = fetch_oecd_kei_grouped(".M.EX.USD._T.Y._Z")
    imports_by_country = fetch_oecd_kei_grouped(".M.IM.USD._T.Y._Z")
    result = {}
    for country in COUNTRIES:
        code = country["code"]
        exports = exports_by_country.get(code, {})
        imports = imports_by_country.get(code, {})
        result[code] = {}
        for period in set(exports) | set(imports):
            export_value = exports.get(period)
            import_value = imports.get(period)
            if export_value is not None and import_value is not None:
                result[code][period] = export_value - import_value
    return result


def merge_with_fallback(primary, fallback):
    result = {}
    for country in COUNTRIES:
        code = country["code"]
        result[code] = primary.get(code) or fallback.get(code, {})
    return result


def sorted_periods(values_by_country):
    periods = sorted(
        {
            period
            for rows in values_by_country.values()
            for period, value in rows.items()
            if value is not None
        },
        key=period_sort_key,
    )
    return periods


def build_series(values_by_country, periods, decimals):
    series = {}
    for country in COUNTRIES:
        country_values = values_by_country.get(country["code"], {})
        series[country["code"]] = [
            None if country_values.get(period) is None else round(country_values[period], decimals)
            for period in periods
        ]
    return series


def latest_non_null(values, periods):
    for index in range(len(values) - 1, -1, -1):
        if values[index] is not None:
            return {"date": periods[index], "year": periods[index], "value": values[index]}
    return {"date": None, "year": None, "value": None}


def infer_frequency(periods):
    if any("-" in str(period) for period in periods):
        return "Monthly/quarterly"
    return "Annual"


def build_indicator_payload(config, values_by_country):
    periods = sorted_periods(values_by_country)
    series = build_series(values_by_country, periods, config["decimals"])
    latest = {
        country["code"]: latest_non_null(series[country["code"]], periods)
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
        "years": periods,
        "dates": periods,
        "frequency": infer_frequency(periods),
        "series": series,
        "latest": latest,
    }


def build_oecd_indicator_values(config):
    if not config.get("oecd"):
        return {country["code"]: {} for country in COUNTRIES}
    result = {country["code"]: {} for country in COUNTRIES}
    for pattern in config["oecd"]:
        grouped = fetch_oecd_kei_grouped(pattern.format(area=""))
        for country in COUNTRIES:
            code = country["code"]
            if not result[code] and grouped.get(code):
                result[code] = grouped[code]
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
    previous_indicators = load_previous_indicators()
    indicators = []
    for config in INDICATORS:
        if config.get("derived") == "oecd_exports_minus_imports":
            primary = build_oecd_trade_balance()
            fallback = build_world_bank_trade_balance()
            values = merge_with_fallback(primary, fallback)
        elif config.get("world_bank_derived") == "exports_minus_imports":
            values = build_world_bank_trade_balance()
        else:
            primary = build_oecd_indicator_values(config)
            fallback = fetch_world_bank_series(config["world_bank"])
            values = merge_with_fallback(primary, fallback)
        payload = build_indicator_payload(config, values)
        if not payload["dates"]:
            previous = previous_indicators.get(config["key"])
            if previous:
                print(f"Reused cached indicator {config['key']} because no fresh rows were available")
                payload = previous
        indicators.append(payload)

    indicators.append(build_credit_payload())
    return {
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "source": "OECD SDMX and World Bank WDI APIs",
        "sourceUrl": "https://sdmx.oecd.org/",
        "countries": [{"code": item["code"], "name": item["name"]} for item in COUNTRIES],
        "indicators": indicators,
    }


def load_previous_indicators():
    path = Path("economic_data.json")
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {
        indicator.get("key"): indicator
        for indicator in payload.get("indicators", [])
        if indicator.get("key") and indicator.get("kind") != "rating"
    }


HTML_TEMPLATE = r'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Economy - G20 Indicators</title>
<style>
:root{
  --bg:#fff;
  --ink:#111;
  --muted:#858585;
  --line:#e7e7e7;
  --line-strong:#d8d8d8;
  --blue:#0f67ff;
  --teal:#079b86;
  --red:#e44f55;
  --soft:#f5f5f5;
  --nav-active:#b8ff00;
}
*{margin:0;padding:0;box-sizing:border-box}
html,body{min-height:100%}
body{font-family:Inter,Arial,sans-serif;background:var(--bg);color:var(--ink);padding:0}
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
.nav-link:hover,.nav-link.active{color:var(--nav-active)}
.nav-link.active::after{display:none}
.nav-search{position:relative;flex:0 1 360px;min-width:220px;margin-left:auto}
.nav-search input{width:100%;height:42px;border:1px solid #2a2e39;border-radius:999px;background:#090c12;color:#fff;padding:0 16px 0 42px;font-size:15px;font-weight:650;outline:none}
.nav-search input::placeholder{color:#787b86}
.nav-search input:focus{border-color:var(--nav-active);box-shadow:0 0 0 1px rgba(184,255,0,.24)}
.nav-search-mark{position:absolute;left:16px;top:50%;width:13px;height:13px;border:2px solid var(--nav-active);border-radius:50%;transform:translateY(-50%);pointer-events:none}
.nav-search-mark::after{content:"";position:absolute;width:7px;height:2px;background:var(--nav-active);border-radius:999px;right:-6px;bottom:-4px;transform:rotate(45deg)}
.page{width:100%;max-width:2048px;margin:0 auto;padding:42px 40px 34px}
.home-head{text-align:center;padding:6px 0 78px}
.eyebrow{font-size:28px;font-weight:800;letter-spacing:0;margin-bottom:22px}
.country-picker{display:inline-flex;align-items:center;gap:14px;position:relative}
.flag{display:inline-flex;align-items:center;justify-content:center;width:70px;height:70px;border-radius:50%;background:#f5f5f5;box-shadow:inset 0 0 0 1px rgba(0,0,0,.05);font-size:50px;line-height:1;overflow:hidden}
.title-select{appearance:none;border:none;background:transparent;color:var(--ink);font-size:66px;font-weight:900;letter-spacing:0;line-height:1;padding:0 46px 0 0;outline:none;cursor:pointer;max-width:min(900px,calc(100vw - 180px))}
.picker-caret{position:absolute;right:4px;top:50%;width:24px;height:24px;border-right:6px solid var(--ink);border-bottom:6px solid var(--ink);transform:translateY(-66%) rotate(45deg);pointer-events:none}
.cards{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:26px}
.indicator-card{height:232px;border:1px solid var(--line);border-radius:20px;background:#fff;padding:22px;display:flex;flex-direction:column;text-decoration:none;color:var(--ink);box-shadow:0 1px 2px rgba(0,0,0,.02);transition:border-color .15s,box-shadow .15s,transform .15s}
.indicator-card:hover{border-color:var(--line-strong);box-shadow:0 12px 30px rgba(0,0,0,.08);transform:translateY(-1px)}
.card-title{font-size:24px;font-weight:850;letter-spacing:0;margin-bottom:18px}
.card-label{font-size:17px;font-weight:850;margin-bottom:7px}
.card-value{font-size:18px;color:#222;display:flex;align-items:baseline;gap:6px}
.card-unit{font-size:13px;letter-spacing:.06em;text-transform:uppercase;color:#333}
.mini-wrap{height:92px;margin-top:auto;position:relative}
.mini-chart{display:block;width:100%;height:100%}
.mini-caption{position:absolute;left:0;right:0;bottom:0;text-align:center;color:#777;font-size:15px}
.rating-box{height:92px;margin-top:auto;display:flex;align-items:center;gap:14px}
.rating-pill{min-width:82px;height:42px;border:1px solid #ddd;border-radius:8px;display:inline-flex;align-items:center;justify-content:center;font-size:22px;font-weight:900;background:#fafafa}
.rating-note{color:#777;font-size:15px}
.detail{display:none}
.detail-head{display:grid;grid-template-columns:224px minmax(0,1fr);gap:28px;align-items:center;padding-bottom:34px}
.detail-flag{width:212px;height:212px;border-radius:50%;font-size:150px}
.detail-title{font-size:60px;font-weight:900;line-height:1.06;letter-spacing:0;margin-bottom:14px}
.meta-row{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:24px}
.chip{height:42px;display:inline-flex;align-items:center;gap:10px;border:1px solid var(--line);border-radius:7px;background:#fff;padding:0 14px;color:#1f1f1f;font-size:22px}
.big-value{font-size:66px;font-weight:900;line-height:1;display:flex;align-items:baseline;gap:10px}
.big-unit{font-size:21px;font-weight:500}
.asof{margin-top:12px;color:#858585;font-size:21px}
.subtabs{display:flex;align-items:flex-end;gap:30px;border-bottom:4px solid #f0f0f0;margin-bottom:18px}
.subtab{height:56px;border:none;background:transparent;font-size:20px;font-weight:850;color:#111;cursor:pointer;padding:0}
.subtab.active{border-bottom:5px solid #333}
.chart-actions{display:flex;justify-content:flex-end;gap:10px;margin:0 0 8px}
.tool-btn{height:42px;border:1px solid var(--line);background:#fff;color:#111;border-radius:7px;padding:0 14px;font-size:18px;cursor:pointer}
.chart-panel{position:relative;height:500px}
.chart{width:100%;height:100%;display:block;touch-action:none}
.tooltip{position:fixed;display:none;pointer-events:none;background:#fff;border:1px solid var(--line);border-radius:8px;box-shadow:0 10px 30px rgba(0,0,0,.14);padding:8px 10px;font-size:13px;line-height:1.4;color:#111;z-index:50}
.range-panel{height:108px;margin-top:10px}
.range{width:100%;height:100%;display:block;touch-action:none;cursor:grab}
.range.dragging{cursor:grabbing}
.quick-ranges{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:16px;margin:18px auto 0;max-width:1500px}
.range-btn{height:58px;border:none;background:#fff;border-radius:14px;font-size:20px;font-weight:500;cursor:pointer}
.range-btn.active{background:#f1f1f1}
.back-link{display:inline-flex;margin-bottom:20px;color:#111;text-decoration:none;font-size:16px;font-weight:750}
.empty{display:flex;align-items:center;justify-content:center;height:100%;color:#777;font-size:18px}
@media(max-width:1200px){
  .cards{grid-template-columns:repeat(2,minmax(0,1fr))}
  .title-select{font-size:52px}
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
  .nav-search{order:4;min-width:0;margin-left:0;padding-top:8px}
  .nav-search input{height:40px;font-size:14px}
  .page{padding:24px 14px 28px}
  .home-head{padding-bottom:34px}
  .eyebrow{font-size:22px;margin-bottom:14px}
  .flag{width:46px;height:46px;font-size:32px}
  .title-select{font-size:36px;max-width:calc(100vw - 94px);padding-right:28px}
  .picker-caret{width:14px;height:14px;border-width:4px}
  .cards{grid-template-columns:1fr;gap:14px}
  .indicator-card{height:218px;border-radius:14px;padding:18px}
  .card-title{font-size:21px}
  .detail-head{grid-template-columns:80px minmax(0,1fr);gap:14px;padding-bottom:20px}
  .detail-flag{width:76px;height:76px;font-size:54px}
  .detail-title{font-size:34px}
  .chip{height:34px;font-size:15px}
  .big-value{font-size:48px}
  .asof{font-size:16px}
  .subtabs{gap:18px;overflow:auto;margin-bottom:12px}
  .subtab{height:48px;font-size:17px;white-space:nowrap}
  .chart-actions{display:none}
  .chart-panel{height:420px}
  .range-panel{height:92px}
  .quick-ranges{grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}
  .range-btn{height:48px;font-size:16px}
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
    <a class="nav-link active" href="economy.html">Economy</a>
    <a class="nav-link" href="calendar.html">Calendar</a>
  </div>
  <form class="nav-search" role="search" data-root="">
    <span class="nav-search-mark" aria-hidden="true"></span>
    <input type="search" name="q" placeholder="Search stocks" autocomplete="off" aria-label="Search stocks">
  </form>
</nav>

<main class="page">
  <section class="home" id="homeView">
    <header class="home-head">
      <div class="eyebrow">Economy</div>
      <div class="country-picker">
        <span class="flag" id="homeFlag" aria-hidden="true"></span>
        <select class="title-select" id="countrySelect" aria-label="Country"></select>
        <span class="picker-caret" aria-hidden="true"></span>
      </div>
    </header>
    <section class="cards" id="indicatorCards"></section>
  </section>

  <section class="detail" id="detailView">
    <a class="back-link" id="backLink" href="economy.html">Back to Economy</a>
    <header class="detail-head">
      <span class="flag detail-flag" id="detailFlag" aria-hidden="true"></span>
      <div>
        <h1 class="detail-title" id="detailTitle"></h1>
        <div class="meta-row">
          <span class="chip" id="detailCode"></span>
          <span class="chip" id="detailSource"></span>
        </div>
        <div class="big-value"><span id="detailValue"></span><span class="big-unit" id="detailUnit"></span></div>
        <div class="asof" id="detailAsof"></div>
      </div>
    </header>
    <nav class="subtabs" aria-label="Indicator sections">
      <button class="subtab active" type="button">Overview</button>
      <button class="subtab" type="button">History</button>
      <button class="subtab" type="button">News</button>
      <button class="subtab" type="button">Community</button>
    </nav>
    <div class="chart-actions">
      <button class="tool-btn" type="button" title="Snapshot">□</button>
      <button class="tool-btn" type="button" title="Embed">&lt;/&gt;</button>
      <button class="tool-btn" type="button" id="fullChart">Full chart</button>
    </div>
    <section class="chart-panel"><canvas class="chart" id="barChart"></canvas><div class="tooltip" id="tooltip"></div></section>
    <section class="range-panel"><canvas class="range" id="rangeChart"></canvas></section>
    <div class="quick-ranges">
      <button class="range-btn" data-range="1">1 year</button>
      <button class="range-btn" data-range="5">5 years</button>
      <button class="range-btn active" data-range="10">10 years</button>
      <button class="range-btn" data-range="all">All time</button>
    </div>
  </section>
</main>

<script>
const ECONOMIC_DATA = __DATA__;
const params = new URLSearchParams(window.location.search);
const homeView = document.getElementById('homeView');
const detailView = document.getElementById('detailView');
const countrySelect = document.getElementById('countrySelect');
const homeFlag = document.getElementById('homeFlag');
const indicatorCards = document.getElementById('indicatorCards');
const detailFlag = document.getElementById('detailFlag');
const detailTitle = document.getElementById('detailTitle');
const detailCode = document.getElementById('detailCode');
const detailSource = document.getElementById('detailSource');
const detailValue = document.getElementById('detailValue');
const detailUnit = document.getElementById('detailUnit');
const detailAsof = document.getElementById('detailAsof');
const barCanvas = document.getElementById('barChart');
const rangeCanvas = document.getElementById('rangeChart');
const tooltip = document.getElementById('tooltip');
const chartState = { start: 0, end: 0, hover: null, drag: null, dragOffset: 0 };

function countryByCode(code){ return ECONOMIC_DATA.countries.find(country => country.code === code) || ECONOMIC_DATA.countries.find(country => country.code === 'US') || ECONOMIC_DATA.countries[0]; }
function indicatorByKey(key){ return ECONOMIC_DATA.indicators.find(indicator => indicator.key === key) || ECONOMIC_DATA.indicators[0]; }
function countryFlag(code){
  if(code === 'EU') return 'EU';
  const base = 127397;
  return String.fromCodePoint(...code.slice(0,2).toUpperCase().split('').map(char => char.charCodeAt(0) + base));
}
function indicatorSlug(indicator){ return indicator.label.toLowerCase().replace(/\\s+/g,' '); }
function displayUnit(indicator){
  if(indicator.key === 'government_debt') return 'PCTGDP';
  if(indicator.key === 'balance_trade') return 'B USD';
  return indicator.unit === '%' ? 'PCT' : indicator.unit;
}
function valueText(value, indicator, withUnit = true){
  if(value === null || value === undefined || value === '') return 'No data';
  if(indicator.kind === 'rating') return value;
  const number = Number(value);
  const formatted = number.toLocaleString(undefined,{minimumFractionDigits:indicator.decimals,maximumFractionDigits:indicator.decimals});
  return withUnit ? `${formatted} ${displayUnit(indicator)}` : formatted;
}
function latestPoint(country, indicator){
  if(indicator.kind === 'rating') return { year:'Current', value:indicator.values[country.code] || 'NR' };
  const values = indicator.series[country.code] || [];
  const years = indicator.dates || indicator.years || [];
  for(let index = values.length - 1; index >= 0; index -= 1){
    if(values[index] !== null && values[index] !== undefined) return { year: years[index], value: values[index] };
  }
  return { year:null, value:null };
}
function seriesFor(country, indicator){
  if(indicator.kind === 'rating') return [];
  return (indicator.dates || indicator.years || []).map((year, index) => ({ year, value:(indicator.series[country.code] || [])[index] ?? null }));
}
function setupNavSearch(){
  const form = document.querySelector('.nav-search');
  if(!form) return;
  const input = form.querySelector('input[name="q"]');
  const runSearch = async () => {
    const query = (input.value || '').trim();
    if(!query) return;
    let target = { symbol: query.toUpperCase(), name: query };
    try{
      const response = await fetch('market_data/index.json', { cache:'no-store' });
      if(response.ok){
        const index = await response.json();
        const groups = index.groups || {};
        const rows = Object.keys(groups).length ? Object.values(groups).flatMap(group => group.stocks || []) : (index.stocks || []);
        const normalized = query.toLowerCase();
        const match = rows.find(row => String(row.symbol || '').toLowerCase() === normalized) || rows.find(row => String(row.name || '').toLowerCase().includes(normalized));
        if(match) target = { symbol: match.symbol, name: match.name || match.symbol };
      }
    }catch(error){}
    const next = new URLSearchParams();
    next.set('symbol', target.symbol);
    next.set('name', target.name);
    window.location.href = 'stock_chart.html?' + next.toString();
  };
  form.addEventListener('submit', event => { event.preventDefault(); runSearch(); });
  input.addEventListener('keydown', event => { if(event.key === 'Enter'){ event.preventDefault(); runSearch(); } });
}
function populateCountrySelect(activeCode){
  countrySelect.innerHTML = ECONOMIC_DATA.countries.map(country => `<option value="${country.code}">${country.code} indicators</option>`).join('');
  countrySelect.value = activeCode;
}
function drawMini(canvas, points){
  const width = canvas.clientWidth || 360;
  const height = canvas.clientHeight || 92;
  const dpr = window.devicePixelRatio || 1;
  canvas.width = Math.floor(width * dpr);
  canvas.height = Math.floor(height * dpr);
  const ctx = canvas.getContext('2d');
  ctx.setTransform(dpr,0,0,dpr,0,0);
  ctx.clearRect(0,0,width,height);
  const values = points.filter(point => point.value !== null);
  if(values.length < 2){
    ctx.fillStyle = '#777';
    ctx.font = '13px Inter,Arial,sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('No history', width / 2, height / 2);
    return;
  }
  const min = Math.min(...values.map(point => point.value));
  const max = Math.max(...values.map(point => point.value));
  const spread = max - min || Math.abs(max) || 1;
  const xStep = width / Math.max(points.length - 1, 1);
  const yFor = value => height - 20 - ((value - min) / spread) * (height - 30);
  ctx.strokeStyle = '#0f67ff';
  ctx.lineWidth = 4;
  ctx.lineJoin = 'round';
  ctx.beginPath();
  values.forEach((point, index) => {
    const x = point.index * xStep;
    const y = yFor(point.value);
    if(index === 0) ctx.moveTo(x,y);
    else ctx.lineTo(x,y);
  });
  ctx.stroke();
  const last = values[values.length - 1];
  ctx.fillStyle = '#0f67ff';
  ctx.beginPath();
  ctx.arc(last.index * xStep, yFor(last.value), 6, 0, Math.PI * 2);
  ctx.fill();
}
function renderHome(country){
  homeView.style.display = 'block';
  detailView.style.display = 'none';
  homeFlag.textContent = countryFlag(country.code);
  populateCountrySelect(country.code);
  indicatorCards.innerHTML = ECONOMIC_DATA.indicators.map(indicator => {
    const latest = latestPoint(country, indicator);
    const url = `economy.html?country=${encodeURIComponent(country.code)}&indicator=${encodeURIComponent(indicator.key)}`;
    if(indicator.kind === 'rating'){
      return `<a class="indicator-card" href="${url}" data-indicator="${indicator.key}">
        <div class="card-title">${indicator.label}</div>
        <div class="card-label">Last</div>
        <div class="card-value"><span class="rating-pill">${latest.value}</span><span class="rating-note">Current rating</span></div>
        <div class="rating-box"><span class="rating-note">${indicator.note}</span></div>
      </a>`;
    }
    return `<a class="indicator-card" href="${url}" data-indicator="${indicator.key}">
      <div class="card-title">${indicator.label}</div>
      <div class="card-label">Last</div>
      <div class="card-value">${valueText(latest.value, indicator)}</div>
      <div class="mini-wrap"><canvas class="mini-chart"></canvas><div class="mini-caption">All history</div></div>
    </a>`;
  }).join('');
  indicatorCards.querySelectorAll('.indicator-card').forEach(card => {
    const indicator = indicatorByKey(card.dataset.indicator);
    const canvas = card.querySelector('canvas');
    if(canvas) drawMini(canvas, seriesFor(country, indicator).map((point, index) => ({...point, index})));
  });
}
function resizeCanvas(canvas){
  const width = canvas.clientWidth || 1000;
  const height = canvas.clientHeight || 400;
  const dpr = window.devicePixelRatio || 1;
  canvas.width = Math.floor(width * dpr);
  canvas.height = Math.floor(height * dpr);
  const ctx = canvas.getContext('2d');
  ctx.setTransform(dpr,0,0,dpr,0,0);
  return { ctx, width, height };
}
function visiblePoints(points){ return points.slice(chartState.start, chartState.end + 1); }
function chartScale(points, height, top, bottom){
  const present = points.filter(point => point.value !== null);
  if(!present.length) return { min:0, max:1, yFor:() => height / 2 };
  let min = Math.min(...present.map(point => point.value));
  let max = Math.max(...present.map(point => point.value));
  if(min > 0) min = Math.min(0, min);
  if(max < 0) max = Math.max(0, max);
  const spread = max - min || Math.abs(max) || 1;
  return { min, max, yFor:value => top + (max - value) / spread * (height - top - bottom) };
}
function drawBarChart(country, indicator){
  const points = seriesFor(country, indicator);
  const { ctx, width, height } = resizeCanvas(barCanvas);
  ctx.clearRect(0,0,width,height);
  if(indicator.kind === 'rating' || !points.length){
    ctx.fillStyle = '#777';
    ctx.font = '18px Inter,Arial,sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('No chart series', width / 2, height / 2);
    return;
  }
  const top = 44, bottom = 54, left = 12, right = 82;
  const shown = visiblePoints(points);
  const scale = chartScale(shown, height, top, bottom);
  ctx.strokeStyle = '#ededed';
  ctx.lineWidth = 1;
  for(let i = 0; i <= 4; i += 1){
    const y = top + (height - top - bottom) * i / 4;
    ctx.beginPath(); ctx.moveTo(left, y); ctx.lineTo(width - right, y); ctx.stroke();
  }
  const zeroY = scale.yFor(0);
  ctx.strokeStyle = '#cfcfcf';
  ctx.beginPath(); ctx.moveTo(left, zeroY); ctx.lineTo(width - right, zeroY); ctx.stroke();
  const slot = (width - left - right) / Math.max(shown.length, 1);
  const barWidth = Math.max(1, Math.min(46, slot * .58));
  shown.forEach((point, index) => {
    const x = left + slot * index + slot / 2;
    if(point.value !== null){
      const y = scale.yFor(point.value);
      ctx.fillStyle = point.value >= 0 ? '#079b86' : '#e44f55';
      const yTop = Math.min(y, zeroY);
      const barHeight = Math.max(2, Math.abs(zeroY - y));
      ctx.fillRect(x - barWidth / 2, yTop, barWidth, barHeight);
    }
    const previous = shown[index - 1];
    const label = String(point.year);
    const yearText = label.slice(0, 4);
    const shouldLabel = shown.length <= 18 || index === 0 || index === shown.length - 1 || (label.endsWith('-01') && previous && String(previous.year).slice(0, 4) !== yearText);
    if(shouldLabel){
      ctx.fillStyle = '#111';
      ctx.font = '14px Inter,Arial,sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText(yearText, x, height - 18);
    }
  });
  ctx.fillStyle = '#111';
  ctx.font = '14px Inter,Arial,sans-serif';
  ctx.textAlign = 'left';
  ctx.fillText(String(shown[0]?.year || ''), left, height - 18);
  const latest = shown.filter(point => point.value !== null).at(-1);
  if(latest){
    const y = scale.yFor(latest.value);
    ctx.fillStyle = latest.value >= 0 ? '#079b86' : '#e44f55';
    ctx.fillRect(width - right + 18, y - 12, 50, 24);
    ctx.fillStyle = '#fff';
    ctx.font = '14px Inter,Arial,sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText(valueText(latest.value, indicator, false), width - right + 43, y + 5);
  }
  if(chartState.hover !== null && chartState.hover >= chartState.start && chartState.hover <= chartState.end){
    const index = chartState.hover - chartState.start;
    const point = points[chartState.hover];
    const x = left + slot * index + slot / 2;
    ctx.strokeStyle = 'rgba(0,0,0,.25)';
    ctx.beginPath(); ctx.moveTo(x, top); ctx.lineTo(x, height - bottom); ctx.stroke();
    if(point.value !== null){
      tooltip.style.display = 'block';
      tooltip.innerHTML = `<strong>${point.year}</strong><br>${valueText(point.value, indicator)}`;
      const rect = barCanvas.getBoundingClientRect();
      tooltip.style.left = `${Math.min(window.innerWidth - 150, rect.left + x + 12)}px`;
      tooltip.style.top = `${Math.max(80, rect.top + scale.yFor(point.value) - 40)}px`;
    }
  }else{
    tooltip.style.display = 'none';
  }
}
function drawRange(country, indicator){
  const points = seriesFor(country, indicator);
  const { ctx, width, height } = resizeCanvas(rangeCanvas);
  ctx.clearRect(0,0,width,height);
  if(indicator.kind === 'rating' || !points.length) return;
  const left = 24, right = 24, top = 18, bottom = 20;
  const scale = chartScale(points, height, top, bottom);
  const slot = (width - left - right) / Math.max(points.length, 1);
  const zeroY = scale.yFor(0);
  const barWidth = Math.max(6, Math.min(22, slot * .52));
  points.forEach((point, index) => {
    const x = left + slot * index + slot / 2;
    if(point.value === null) return;
    const y = scale.yFor(point.value);
    ctx.fillStyle = '#b8c7e8';
    ctx.fillRect(x - barWidth / 2, Math.min(y, zeroY), barWidth, Math.max(2, Math.abs(zeroY - y)));
  });
  const startX = left + slot * chartState.start;
  const endX = left + slot * (chartState.end + 1);
  ctx.fillStyle = 'rgba(15,103,255,.14)';
  ctx.fillRect(startX, 0, endX - startX, height);
  ctx.strokeStyle = '#0f67ff';
  ctx.lineWidth = 2;
  ctx.strokeRect(startX, 1, endX - startX, height - 2);
  ctx.fillStyle = '#0f67ff';
  ctx.fillRect(startX - 3, 0, 6, height);
  ctx.fillRect(endX - 3, 0, 6, height);
}
function periodYear(period){
  const year = Number(String(period || '').slice(0, 4));
  return Number.isFinite(year) ? year : null;
}
function setRangeByYears(years, points){
  if(years === 'all' || points.length <= 1){ chartState.start = 0; chartState.end = Math.max(0, points.length - 1); return; }
  const present = points.map((point, index) => ({...point, index})).filter(point => point.value !== null);
  if(!present.length){ chartState.start = 0; chartState.end = Math.max(0, points.length - 1); return; }
  const latest = present[present.length - 1];
  const latestYear = periodYear(latest.year);
  if(latestYear === null){
    const count = Math.max(1, Math.min(points.length, Number(years)));
    chartState.start = Math.max(0, points.length - count);
    chartState.end = points.length - 1;
    return;
  }
  const startYear = latestYear - Number(years);
  const first = present.find(point => periodYear(point.year) !== null && periodYear(point.year) > startYear) || present[0];
  chartState.start = first.index;
  chartState.end = latest.index;
}
function drawDetail(country, indicator){
  if(indicator.kind === 'rating'){
    detailTitle.textContent = `${country.code} credit rating`;
    detailValue.textContent = indicator.values[country.code] || 'NR';
    detailUnit.textContent = '';
    detailAsof.textContent = 'Current snapshot';
    detailCode.textContent = `${country.code}RATE`;
  detailSource.textContent = 'S&P';
    drawBarChart(country, indicator);
    drawRange(country, indicator);
    return;
  }
  const points = seriesFor(country, indicator);
  if(chartState.end <= 0){ chartState.start = Math.max(0, points.length - 10); chartState.end = points.length - 1; }
  const latest = latestPoint(country, indicator);
  detailTitle.textContent = `${country.code} ${indicatorSlug(indicator)}`;
  detailValue.textContent = valueText(latest.value, indicator, false);
  detailUnit.textContent = indicator.unit === '%' ? '%' : displayUnit(indicator);
  detailAsof.textContent = latest.year ? `As of ${latest.year} · ${indicator.frequency || 'All available history'}` : 'No data';
  detailCode.textContent = `${country.code}${indicator.short.toUpperCase()}`;
  detailSource.textContent = 'OECD / World Bank';
  drawBarChart(country, indicator);
  drawRange(country, indicator);
}
function renderDetail(country, indicator){
  homeView.style.display = 'none';
  detailView.style.display = 'block';
  detailFlag.textContent = countryFlag(country.code);
  document.getElementById('backLink').href = `economy.html?country=${encodeURIComponent(country.code)}`;
  chartState.start = 0;
  chartState.end = Math.max(0, seriesFor(country, indicator).length - 1);
  setRangeByYears('10', seriesFor(country, indicator));
  drawDetail(country, indicator);
  document.querySelectorAll('.range-btn').forEach(button => {
    button.onclick = () => {
      document.querySelectorAll('.range-btn').forEach(item => item.classList.remove('active'));
      button.classList.add('active');
      setRangeByYears(button.dataset.range, seriesFor(country, indicator));
      drawDetail(country, indicator);
    };
  });
}
function pointerIndex(canvas, event, points){
  const rect = canvas.getBoundingClientRect();
  const x = event.clientX - rect.left;
  const left = canvas === rangeCanvas ? 24 : 12;
  const right = canvas === rangeCanvas ? 24 : 82;
  const count = canvas === rangeCanvas ? points.length : chartState.end - chartState.start + 1;
  const slot = (rect.width - left - right) / Math.max(count, 1);
  return Math.max(0, Math.min(count - 1, Math.floor((x - left) / slot)));
}
function installChartEvents(country, indicator){
  const points = seriesFor(country, indicator);
  barCanvas.onpointermove = event => {
    if(!points.length) return;
    chartState.hover = chartState.start + pointerIndex(barCanvas, event, points);
    drawDetail(country, indicator);
  };
  barCanvas.onpointerleave = () => { chartState.hover = null; tooltip.style.display = 'none'; drawDetail(country, indicator); };
  rangeCanvas.onpointerdown = event => {
    if(!points.length) return;
    const rect = rangeCanvas.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const slot = (rect.width - 48) / Math.max(points.length, 1);
    const startX = 24 + slot * chartState.start;
    const endX = 24 + slot * (chartState.end + 1);
    chartState.drag = Math.abs(x - startX) < 18 ? 'start' : Math.abs(x - endX) < 18 ? 'end' : x > startX && x < endX ? 'move' : 'move';
    chartState.dragOffset = pointerIndex(rangeCanvas, event, points) - chartState.start;
    rangeCanvas.classList.add('dragging');
    rangeCanvas.setPointerCapture(event.pointerId);
  };
  rangeCanvas.onpointermove = event => {
    if(!chartState.drag || !points.length) return;
    let index = pointerIndex(rangeCanvas, event, points);
    const length = chartState.end - chartState.start;
    if(chartState.drag === 'start') chartState.start = Math.min(index, chartState.end);
    if(chartState.drag === 'end') chartState.end = Math.max(index, chartState.start);
    if(chartState.drag === 'move'){
      let nextStart = index - chartState.dragOffset;
      nextStart = Math.max(0, Math.min(points.length - length - 1, nextStart));
      chartState.start = nextStart;
      chartState.end = nextStart + length;
    }
    drawDetail(country, indicator);
  };
  rangeCanvas.onpointerup = event => {
    chartState.drag = null;
    rangeCanvas.classList.remove('dragging');
    try{ rangeCanvas.releasePointerCapture(event.pointerId); }catch(error){}
  };
}
function boot(){
  setupNavSearch();
  const country = countryByCode(params.get('country') || localStorage.getItem('economyCountry') || 'US');
  const indicatorParam = params.get('indicator');
  if(indicatorParam){
    const indicator = indicatorByKey(indicatorParam);
    renderDetail(country, indicator);
    installChartEvents(country, indicator);
  }else{
    renderHome(country);
    countrySelect.onchange = () => {
      const next = countryByCode(countrySelect.value);
      localStorage.setItem('economyCountry', next.code);
      history.replaceState(null, '', `economy.html?country=${encodeURIComponent(next.code)}`);
      renderHome(next);
    };
  }
}
window.addEventListener('resize', () => {
  const country = countryByCode(params.get('country') || countrySelect.value || 'US');
  const indicatorParam = params.get('indicator');
  if(indicatorParam) drawDetail(country, indicatorByKey(indicatorParam));
  else renderHome(country);
});
boot();
</script>
</body>
</html>
'''


def write_outputs(payload):
    data_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    Path("economic_data.json").write_text(data_json, encoding="utf-8")
    html = HTML_TEMPLATE.replace("__DATA__", data_json).replace("__UPDATED__", payload["updated"])
    Path("economy.html").write_text(html, encoding="utf-8")
    Path("economic.html").write_text(html, encoding="utf-8")


def main():
    payload = build_payload()
    write_outputs(payload)
    print(f"Generated economy.html with {len(payload['countries'])} countries")


if __name__ == "__main__":
    main()
