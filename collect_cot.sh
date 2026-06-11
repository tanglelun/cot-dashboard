#!/bin/bash
# CFTC COT Weekly Update Script
# Run this weekly to fetch latest data and regenerate HTML

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "========================================"
echo "CFTC COT Weekly Update - $(date)"
echo "========================================"

# Step 1: Update COT data
echo ""
echo "Step 1: Fetching latest COT data..."
python3 update_cot.py

# Step 2: Update price data
echo ""
echo "Step 2: Fetching latest price data..."
python3 fetch_prices.py

# Step 3: Regenerate HTML
echo ""
echo "Step 3: Regenerating HTML..."
python3 generate_history_html.py

# Step 4: Summary
echo ""
echo "========================================"
echo "Update Complete!"
echo "========================================"
echo "Files updated:"
echo "  - cot_noncommercial_history.csv (COT data)"
echo "  - price_history.csv (price data)"
echo "  - cot_noncommercial_history.html"
echo "  - charts/"
echo ""
echo "To set up weekly cron job (Fridays at 15:00 ET):"
echo "  crontab -e"
echo "  Then add: 0 20 * * 5 cd $SCRIPT_DIR && ./collect_cot.sh >> /tmp/cot_update.log 2>&1"
