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

The workflow in `.github/workflows/update-economic.yml` refreshes the G20
Economy dashboard weekly from the World Bank API and updates:

- `economy.html`
- `economic.html`
- `economic_data.json`

You can also run it manually in GitHub:

`Actions` -> `Update COT data` -> `Run workflow`
