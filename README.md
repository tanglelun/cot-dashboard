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
union, not the top-100 ranking groups. Membership is refreshed from the S&P
500 CSV maintained by datasets and Wikipedia's Nasdaq-100 companies table;
`pattern_constituents.json` records source/read dates. A failed fetch may use
that source's cached list for at most seven calendar days. The homepage reports
constituent dates, coverage, and excluded symbols.

The price-only heuristic uses the last 252 completed daily bars, 3-bar confirmed
pivots, 20–120-session patterns, a preceding trend, and alternating five-pivot
geometry. The head must exceed both shoulders by at least 2% of head price and
15% of head-to-neckline height. Shoulders differ by at most 6% of head price and
50% of pattern height; their headward durations have a 0.4–2.5 ratio. Neckline
slope is capped at 60% of pattern height over the shoulder span. Both shoulders
must stand at least 20% of pattern height above the neckline (inverted for
bottoms). The previous 20-session move into the left shoulder must be at least
3% and 30% of pattern height. EMA/trend-candle colors are unrelated to this scan.

A close 0.5% beyond the extrapolated neckline confirms a price breakout;
intraday wicks alone do not. Confirmation cannot predate the three-bar right
shoulder confirmation. Candidates expire 20 sessions after the right shoulder;
confirmed breakouts expire after 10 sessions. All right shoulders must be within
25 sessions. A subsequent head breach or 0.5% neckline recross invalidates the
result. No volume confirmation, probability estimate, or performance claim is
made. These are mechanical candidates for chart review, not verified outcomes.

After successful stock updates, the market workflow generates and publishes
`patterns_data.json`. If fewer than 90% of constituent charts are current and
valid, generation fails without replacing the previous scan. Stale/missing
pattern output triggers the existing hourly recovery path. Run manually with
`python generate_patterns.py`; tests: `python -m unittest discover -s tests`.
