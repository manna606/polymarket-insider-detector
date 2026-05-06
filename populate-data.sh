#!/bin/bash
# One-click populate real data into Railway PostgreSQL

echo "=================================================="
echo "  Populate Real Data to Railway"
echo "=================================================="
echo ""
echo "Step 1: Go to Railway Dashboard → PostgreSQL → Variables"
echo "Step 2: Copy DATABASE_URL (starts with postgresql://)"
echo ""
read -p "Paste your DATABASE_URL here: " DB_URL

if [ -z "$DB_URL" ]; then
    echo "❌ No URL provided. Exiting."
    exit 1
fi

echo ""
echo "⏳ Fetching real data from Polymarket + Kalshi..."
DATABASE_URL="$DB_URL" python3 fetcher.py

echo ""
echo "✅ Done! Refresh your Dashboard to see real data."
