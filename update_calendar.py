import json
import re
import time
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path

import requests


OUTPUT_FILE = Path("calendar_data.json")
WINDOW_PAST_DAYS = 7
WINDOW_FUTURE_DAYS = 190
IMPORTANCE = 3
EASTERN_OFFSET = "-04:00"

BEA_JSON_URL = "https://apps.bea.gov/API/signup/release_dates.json"
FED_FOMC_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
NAGER_HOLIDAYS_URL = "https://date.nager.at/api/v3/PublicHolidays/{year}/{code}"
ECB_TARGET_HOLIDAYS_URL = "https://www.ecb.europa.eu/paym/target/target_services/profuse/html/index.en.html"
PUBLIC_HOLIDAY_RULES_URL = "https://date.nager.at/"

CATEGORY_ORDER = [
    "Interest Rate",
    "Prices & Inflation",
    "Labour Market",
    "GDP Growth",
    "Foreign Trade",
    "Government",
    "Business Confidence",
    "Consumer Sentiment",
    "Housing Market",
    "Bond Auctions",
    "Energy",
    "Holidays",
    "Earnings",
]

G20_COUNTRIES = [
    {"code": "AR", "name": "Argentina"},
    {"code": "AU", "name": "Australia"},
    {"code": "BR", "name": "Brazil"},
    {"code": "CA", "name": "Canada"},
    {"code": "CN", "name": "China"},
    {"code": "EU", "name": "European Union"},
    {"code": "FR", "name": "France"},
    {"code": "DE", "name": "Germany"},
    {"code": "IN", "name": "India"},
    {"code": "ID", "name": "Indonesia"},
    {"code": "IT", "name": "Italy"},
    {"code": "JP", "name": "Japan"},
    {"code": "MX", "name": "Mexico"},
    {"code": "RU", "name": "Russia"},
    {"code": "SA", "name": "Saudi Arabia"},
    {"code": "ZA", "name": "South Africa"},
    {"code": "KR", "name": "South Korea"},
    {"code": "TR", "name": "Turkiye"},
    {"code": "GB", "name": "United Kingdom"},
    {"code": "US", "name": "United States"},
]
COUNTRY_CODE_BY_NAME = {country["name"]: country["code"] for country in G20_COUNTRIES}

FIXED_PUBLIC_HOLIDAYS = {
    "India": [
        (1, 26, "Republic Day"),
        (8, 15, "Independence Day"),
        (10, 2, "Gandhi Jayanti"),
        (12, 25, "Christmas Day"),
    ],
    "Saudi Arabia": [
        (2, 22, "Founding Day"),
        (9, 23, "Saudi National Day"),
    ],
}

HIGH_IMPACT_KEYWORDS = {
    "employment situation": ("Labour Market", "Employment Situation"),
    "consumer price index": ("Prices & Inflation", "Consumer Price Index"),
    "producer price index": ("Prices & Inflation", "Producer Price Index"),
    "job openings and labor turnover": ("Labour Market", "JOLTS"),
    "employment cost index": ("Labour Market", "Employment Cost Index"),
    "productivity and costs": ("Productivity", "Productivity and Costs"),
    "u.s. export and import price indexes": ("Prices & Inflation", "Import/Export Prices"),
    "gdp (advance estimate)": ("GDP Growth", "GDP Advance Estimate"),
    "gdp (second estimate)": ("GDP Growth", "GDP Second Estimate"),
    "gdp (third estimate)": ("GDP Growth", "GDP Third Estimate"),
    "personal income and outlays": ("Consumer Sentiment", "Personal Income and Outlays"),
    "u.s. international trade in goods and services": ("Foreign Trade", "U.S. Trade Balance"),
    "fomc": ("Interest Rate", "FOMC Decision"),
}


class FomcParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.text = []

    def handle_data(self, data):
        text = " ".join(data.split())
        if text:
            self.text.append(text)


def utc_now():
    return datetime.now(timezone.utc)


def request_text(url):
    last_error = None
    headers = {"User-Agent": "NetDataCalendar/1.0"}
    for attempt in range(3):
        try:
            response = requests.get(url, headers=headers, timeout=45)
            if response.status_code in (429, 500, 502, 503, 504) and attempt < 2:
                time.sleep(2 + attempt * 2)
                continue
            response.raise_for_status()
            return response.text
        except requests.RequestException as error:
            last_error = error
            if attempt < 2:
                time.sleep(1 + attempt * 2)
    raise RuntimeError(f"Unable to fetch {url}: {last_error}")


def normalize_space(value):
    return " ".join(str(value or "").replace("\\n", " ").replace("\\,", ",").split())


def parse_ics_datetime(value):
    value = value.strip()
    if not value:
        return None
    if value.endswith("Z"):
        dt = datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        return dt.isoformat().replace("+00:00", "Z")
    if "T" in value:
        dt = datetime.strptime(value, "%Y%m%dT%H%M%S")
    else:
        dt = datetime.strptime(value, "%Y%m%d")
    return dt.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


def parse_ics_events(text):
    events = []
    current = None
    last_key = None
    for raw_line in text.splitlines():
        if raw_line.startswith((" ", "\t")) and current is not None and last_key:
            current[last_key] += raw_line[1:]
            continue
        line = raw_line.strip()
        if line == "BEGIN:VEVENT":
            current = {}
            last_key = None
            continue
        if line == "END:VEVENT" and current is not None:
            events.append(current)
            current = None
            last_key = None
            continue
        if current is None or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.split(";", 1)[0].upper()
        current[key] = value
        last_key = key
    return events


def high_impact_meta(title):
    normalized = normalize_space(title).lower()
    for keyword, meta in HIGH_IMPACT_KEYWORDS.items():
        if keyword in normalized:
            return meta
    return None


def event_id(source, date_value, title):
    compact = re.sub(r"[^a-z0-9]+", "-", f"{source}-{date_value}-{title}".lower()).strip("-")
    return compact[:140]


def build_event(source, source_url, date_value, title, category, reference="", country="United States"):
    country_code = COUNTRY_CODE_BY_NAME.get(country, country[:2].upper())
    return {
        "id": event_id(source, date_value, title),
        "date": date_value,
        "country": country,
        "countryCode": country_code,
        "category": category,
        "event": title,
        "reference": reference,
        "actual": "",
        "previous": "",
        "consensus": "",
        "forecast": "",
        "revised": "",
        "importance": IMPORTANCE,
        "lastUpdate": "",
        "unit": "",
        "currency": "",
        "url": source_url,
        "source": source,
    }


def easter_date(year):
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return datetime(year, month, day, tzinfo=timezone.utc).date()


def target_holidays_for_year(year):
    easter = easter_date(year)
    days = [
        (datetime(year, 1, 1, tzinfo=timezone.utc).date(), "New Year's Day"),
        (easter - timedelta(days=2), "Good Friday"),
        (easter + timedelta(days=1), "Easter Monday"),
        (datetime(year, 5, 1, tzinfo=timezone.utc).date(), "Labour Day"),
        (datetime(year, 12, 25, tzinfo=timezone.utc).date(), "Christmas Day"),
        (datetime(year, 12, 26, tzinfo=timezone.utc).date(), "Boxing Day"),
    ]
    return [
        build_event(
            "European Central Bank",
            ECB_TARGET_HOLIDAYS_URL,
            f"{day.isoformat()}T00:00:00Z",
            name,
            "Holidays",
            "TARGET closing day",
            "European Union",
        )
        for day, name in days
    ]


def fetch_holiday_events():
    result = []
    now = utc_now()
    years = sorted({now.year, (now + timedelta(days=WINDOW_FUTURE_DAYS)).year})
    for country in G20_COUNTRIES:
        code = country["code"]
        if code == "EU":
            for year in years:
                result.extend(target_holidays_for_year(year))
            continue
        for year in years:
            url = NAGER_HOLIDAYS_URL.format(year=year, code=code)
            try:
                response = requests.get(url, headers={"User-Agent": "NetDataCalendar/1.0"}, timeout=45)
                if not response.ok:
                    continue
                rows = response.json()
            except (requests.RequestException, ValueError):
                continue
            if not isinstance(rows, list):
                continue
            for row in rows:
                date_value = normalize_space(row.get("date"))
                name = normalize_space(row.get("name") or row.get("localName"))
                if not date_value or not name:
                    continue
                result.append(
                    build_event(
                        "Nager.Date Public Holidays",
                        url,
                        f"{date_value}T00:00:00Z",
                        name,
                        "Holidays",
                        row.get("localName") or "Public holiday",
                        country["name"],
                    )
                )
    for country_name, days in FIXED_PUBLIC_HOLIDAYS.items():
        for year in years:
            for month, day, name in days:
                result.append(
                    build_event(
                        "Public holiday rules",
                        PUBLIC_HOLIDAY_RULES_URL,
                        f"{year:04d}-{month:02d}-{day:02d}T00:00:00Z",
                        name,
                        "Holidays",
                        "Fixed-date public holiday",
                        country_name,
                    )
                )
    return result


def parse_bea_date(date_text, time_text, year):
    date_text = normalize_space(date_text)
    time_text = normalize_space(time_text)
    if not date_text or "to be announced" in date_text.lower():
        return None
    candidates = [f"{date_text} {year} {time_text}", f"{date_text} {time_text}"]
    for candidate in candidates:
        for fmt in ("%B %d %Y %I:%M %p", "%B %d, %Y %I:%M %p", "%Y-%m-%d %I:%M %p"):
            try:
                return datetime.strptime(candidate, fmt).replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
            except ValueError:
                continue
    return None


def fetch_bea_events():
    rows = requests.get(BEA_JSON_URL, headers={"User-Agent": "NetDataCalendar/1.0"}, timeout=45).json()
    result = []
    if isinstance(rows, list):
        iterable = [(normalize_space(row.get("ReleaseName") or row.get("Title") or row.get("name")), row) for row in rows]
    else:
        iterable = [(normalize_space(title), data) for title, data in rows.items() if isinstance(data, dict)]
    for title, row in iterable:
        meta = high_impact_meta(title)
        if not meta:
            continue
        category, short_title = meta
        release_dates = row.get("release_dates") or []
        if not release_dates:
            raw_date = row.get("ReleaseDate") or row.get("date") or row.get("Date")
            raw_time = row.get("ReleaseTime") or row.get("time") or row.get("Time") or "8:30 AM"
            parsed = parse_bea_date(str(raw_date), str(raw_time), utc_now().year)
            release_dates = [parsed] if parsed else []
        for date_value in release_dates:
            if date_value:
                result.append(build_event("U.S. Bureau of Economic Analysis", BEA_JSON_URL, date_value, short_title, category, title))
    return result


def fetch_fomc_events():
    text = request_text(FED_FOMC_URL)
    pattern = re.compile(
        r'<h4><a id="[^"]+">(20\d{2}) FOMC Meetings</a></h4>.*?(?=<h4><a id="[^"]+">20\d{2} FOMC Meetings</a></h4>|</div>\s*<div class="panel panel-default"|$)',
        re.S,
    )
    row_pattern = re.compile(
        r'fomc-meeting__month[^>]*>\s*<strong>([^<]+)</strong>.*?fomc-meeting__date[^>]*>([^<]+)</div>',
        re.S,
    )
    result = []
    for section in pattern.finditer(text):
        year = int(section.group(1))
        if year < utc_now().year:
            continue
        for row in row_pattern.finditer(section.group(0)):
            month = normalize_space(row.group(1))
            day_text = normalize_space(row.group(2))
            day = day_text.split("-")[-1].strip()
            try:
                dt = datetime.strptime(f"{month} {day} {year} 2:00 PM", "%B %d %Y %I:%M %p").replace(tzinfo=timezone.utc)
            except ValueError:
                continue
            result.append(build_event("Federal Reserve", FED_FOMC_URL, dt.isoformat().replace("+00:00", "Z"), "FOMC Decision", "Interest Rate", "FOMC meeting"))
    dedup = {}
    for item in result:
        dedup[item["date"][:10]] = item
    return list(dedup.values())


def in_window(event, start, end):
    try:
        day = datetime.fromisoformat(event["date"].replace("Z", "+00:00")).date()
    except ValueError:
        return False
    return start <= day <= end


def build_payload(events, generated_at):
    start = generated_at.date() - timedelta(days=WINDOW_PAST_DAYS)
    end = generated_at.date() + timedelta(days=WINDOW_FUTURE_DAYS)
    filtered = [event for event in events if in_window(event, start, end)]
    dedup = {}
    for event in filtered:
        dedup[event["id"]] = event
    filtered = sorted(dedup.values(), key=lambda item: (item["date"], item["country"], item["event"]))
    return {
        "updated": generated_at.isoformat().replace("+00:00", "Z"),
        "source": "Official public release calendars",
        "sourceUrl": BEA_JSON_URL,
        "importance": IMPORTANCE,
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "sources": [
            {"name": "U.S. Bureau of Economic Analysis", "url": BEA_JSON_URL},
            {"name": "Federal Reserve", "url": FED_FOMC_URL},
            {"name": "Nager.Date Public Holidays", "url": "https://date.nager.at/"},
            {"name": "European Central Bank", "url": ECB_TARGET_HOLIDAYS_URL},
            {"name": "Public holiday rules", "url": PUBLIC_HOLIDAY_RULES_URL},
        ],
        "countries": G20_COUNTRIES,
        "coverage": {
            "scope": "G20 countries",
            "activeSources": sorted({event["countryCode"] for event in filtered}),
            "note": "Events are included only when an official or free public source is connected; no third-party calendar tables are copied.",
        },
        "categories": CATEGORY_ORDER,
        "events": filtered,
    }


def load_existing():
    try:
        return json.loads(OUTPUT_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def write_payload(payload):
    OUTPUT_FILE.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def main():
    now = utc_now()
    events = []
    errors = []
    for fetcher in (fetch_bea_events, fetch_fomc_events, fetch_holiday_events):
        try:
            events.extend(fetcher())
        except Exception as error:
            errors.append(str(error))
    if not events:
        existing = load_existing()
        if existing and existing.get("events"):
            existing["updateError"] = "; ".join(errors)
            existing["lastAttempt"] = now.isoformat().replace("+00:00", "Z")
            write_payload(existing)
            print(f"Kept existing {OUTPUT_FILE}: {'; '.join(errors)}")
            return
        raise RuntimeError("; ".join(errors) or "No calendar events found")
    payload = build_payload(events, now)
    if errors:
        payload["updateWarnings"] = errors
    write_payload(payload)
    print(f"Updated {OUTPUT_FILE} with {len(payload['events'])} high-impact public events")


if __name__ == "__main__":
    main()
