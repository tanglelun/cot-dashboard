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
