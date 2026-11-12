# COT Dashboard

Static CFTC COT dashboard with weekly GitHub Actions updates.

## Publish with GitHub Pages

1. Create a new GitHub repository.
2. Push this local repository:

   ```bash
   git remote add origin https://github.com/YOUR_USER/YOUR_REPO.git
   git push -u origin main
   ```

3. In GitHub, open the repository settings:

   `Settings` -> `Pages` -> `Build and deployment`

4. Choose:

   - Source: `Deploy from a branch`
   - Branch: `main`
   - Folder: `/ (root)`

5. Your dashboard will be available at:

   `https://YOUR_USER.github.io/YOUR_REPO/`

## Automatic Updates

The workflow in `.github/workflows/update-data.yml` runs every Saturday at 02:30 UTC.

It updates:

- `cot_noncommercial_history.csv`
- `price_history.csv`
- `cot_noncommercial_history.html`
- `index.html`
- `charts/*.html`

The workflow in `.github/workflows/update-market.yml` runs after the regular US
market close on weekdays and updates:

- `russell2000_top100.html`
- `market_data/*.json`
- `commodities_data.json`
- `commodities_data/*.json`
- `indexes_data.json`
- `indexes_data/*.json`

Market updates run at 22:30 UTC Monday–Friday, with a second pass at 04:30
UTC Tuesday–Saturday (06:30 and 12:30 Beijing time Tuesday–Saturday; GitHub
may delay scheduled runs). Stock downloads are checked against the most recent
completed NYSE session, including holidays and early closes. Missing or stale
symbols are retried twice using recent history and merged into the full history.
Publishing stops if fewer than 95% of chart stocks or 90% of the full stock
universe have that session's close. Individual chart files keep their actual
last-candle date, including suspended stocks. Failed runs remain visible in
GitHub Actions instead of reporting a stale refresh as successful.

The workflow in `.github/workflows/update-economic.yml` refreshes the G20
Economy dashboard weekly from OECD SDMX and World Bank WDI APIs and updates:

- `economy.html`
- `economic.html`
- `economic_data.json`

The workflow in `.github/workflows/update-calendar.yml` refreshes the high-impact
economic Calendar daily from official public release calendars and updates:

- `calendar_data.json`

The Calendar intentionally uses official public sources rather than third-party
calendar tables. Current sources include BEA's machine-readable release schedule
and the Federal Reserve FOMC calendar.

You can also run it manually in GitHub:

`Actions` -> `Update COT data` -> `Run workflow`

CNN Fear & Greed also refreshes independently every two hours through
`.github/workflows/update-cnn.yml`. This lightweight job uses the current CNN
endpoint, preserves the official source timestamp and existing history, and
does not advance timestamps for other Insight indicators. Failed or older
responses preserve the saved data and fail the job. The CNN and full Insight workflows share
a concurrency group to prevent simultaneous writes to the same JSON files.

The full Insight page (S&P 500 index/breadth, liquidity, and valuation) refreshes
independently through `update-insight.yml` at 22:45 UTC Monday–Friday and 04:45
UTC Tuesday–Saturday. It does not depend on the all-stock update succeeding.
S&P 500 index and MA50/MA200 breadth must reach the last completed session;
breadth requires at least 90% of the constituent universe with valid averages.
Stale constituents are retried with one year of adjusted prices, keeping history.
The full Insight and CNN-only workflows share their write lock; market data has
a separate lock because it writes different files.

Stock, commodity, and index steps publish successful updates even if another
source fails. The overall run still fails visibly when any source fails; crossover
signals are only regenerated after a successful stock refresh.

All current US stock charts refresh by default (`GENERATE_ALL_STOCK_CHARTS=1`).
Top-stock charts keep full-history downloads. Other charts merge the validated
one-year universe download into their saved candles, retaining older history up
to `MARKET_CHART_MAX_ROWS`. The previous default refreshed only top-stock charts,
leaving other saved chart files unchanged even when their summary prices updated.

Hourly recovery checks supplement the regular daily schedules: market at minute
11 and Insight at minute 26 UTC. Recovery only downloads when the published
stock/chart, benchmark, or breadth data is behind the latest completed US market
session (including holidays). Up-to-date recovery runs skip data downloads.
Manual runs and both regular daily runs still refresh unconditionally. GitHub
scheduled execution is best-effort and may be delayed; these checks provide more
recovery opportunities, not a guaranteed wall-clock deadline.

Publishing uses `publish_data.sh`, which supplies the bot identity explicitly for
rebases and autostashes on fresh runners. Failed publishes retain the generated
commit as a downloadable Git bundle artifact for seven days, so data can be
recovered without downloading every market again.

### Homepage head-and-shoulders scanner

`generate_patterns.py` scans the complete S&P 500 and Nasdaq 100 constituent
union plus listed equity holdings of IWM as a public Russell 2000 proxy, not
the top-100 ranking groups. IWM holdings are explicitly labeled approximate
and are not represented as exact licensed FTSE Russell index membership. Membership is refreshed from the S&P
500 CSV maintained by datasets, Wikipedia's Nasdaq-100 companies table, and
iShares' official `latest-holdings.csv` for IWM;
`pattern_constituents.json` records source/read dates. A failed fetch may use
that source's cached list for at most seven calendar days. The homepage reports
constituent dates, coverage, and excluded symbols. IWM's embedded holdings date
must be within seven days of retrieval, including when cached; refreshing the
HTTP request cannot make old holdings fresh. Cash, derivatives, unlisted and
invalid-ticker holdings are excluded. Space-separated share classes normalize
to Yahoo hyphens (MOG A → MOG-A). Source size bounds are 1,800–2,200 listed
IWM equities, and symbol overlap is deduplicated across all three groups.

Version 2 uses the same closing-price curve for detection and previews so all five
pivots lie on the displayed curve. It requires three distinct peaks/troughs,
two substantial intervening reversals, a prior trend, and a real right-shoulder
recovery. References: StockCharts ChartSchool [bottom](https://chartschool.stockcharts.com/table-of-contents/chart-analysis/chart-patterns/head-and-shoulders-bottom)
and [top](https://chartschool.stockcharts.com/table-of-contents/chart-analysis/chart-patterns/head-and-shoulders-top).

These conservative numeric choices are implementation parameters, not universal
textbook definitions: use 252 completed bars, 3-bar confirmed pivots, 20–120-day
shoulder span, at least 3 days per structural leg and max/min leg ratio 3.
Head width cannot exceed 2.5 times the combined inner shoulder legs. Left/right
headward durations must have ratio 0.5–2. The head must exceed shoulders by
1.5% of its price, 20% of pattern height and one mean true range. Each shoulder
reversal must be at least 35% of pattern height and 1.5 mean true ranges;
the recovery after the right shoulder must be at least 20% and one mean true
range. Mean true range is measured from 14 bars before the left shoulder through
the right shoulder. Shoulder height differences are capped at 4% of head price
and 30% of pattern height; neckline slope over the shoulder span at 35% of height.

Status `candidate` is unbroken structure. `breakout` requires a close 0.5%
beyond the neckline. `confirmed` additionally requires breakout-day volume
at least 1.2 times the preceding 20-session mean; missing volume never confirms.
This is called volume expansion in the UI, not a guarantee of trend reversal.
Candidates expire after 20 sessions, breakouts after 10, all right shoulders
after 25. A head breach or a subsequent 0.5% neckline recross invalidates the
result. Zero matches are valid and must not trigger looser thresholds.

`tests/fixtures/rounding_bottoms_2026_11_11.json` freezes four former false
positives from the repository daily OHLCV history (FE, USB, EXC, SLB). Tests
retain clear synthetic positive examples for both orientations, including
price-only versus volume-confirmed breakouts, while rejecting these broad
rounding-bottom examples. The mini-chart marks both real neckline anchors and
extends the line only to the right, not across the unrelated preceding trend.

After successful stock updates, the market workflow generates and publishes
`patterns_data.json`. If fewer than 90% of charts in any constituent group are current and
valid, generation fails without replacing the previous scan. Stale/missing
pattern output triggers the existing hourly recovery path. Run manually with
`python generate_patterns.py`; tests: `python -m unittest discover -s tests`.
