#!/bin/bash
# One-click deploy dashboard to Railway
# This script creates a PostgreSQL DB and deploys the Streamlit dashboard

echo "=================================================="
echo "  Deploy Polymarket Dashboard to Railway"
echo "=================================================="
echo ""

# Check if railway CLI is installed
if ! command -v railway &> /dev/null; then
    echo "❌ Railway CLI not found. Installing..."
    npm install -g @railway/cli
fi

# Login check
railway whoami || railway login

echo ""
echo "Step 1: Linking to your Railway project..."
railway link

echo ""
echo "Step 2: Adding PostgreSQL database..."
railway add --database postgres

echo ""
echo "Step 3: Waiting for PostgreSQL to be ready..."
sleep 10

echo ""
echo "Step 4: Getting DATABASE_URL..."
DB_URL=$(railway variables --service postgresql | grep DATABASE_URL | head -1 || echo "")

if [ -z "$DB_URL" ]; then
    echo "⚠️  Could not auto-fetch DATABASE_URL."
    echo "Please go to Railway Dashboard → your PostgreSQL service → Variables"
    echo "Copy DATABASE_URL and add it to your main service as an environment variable."
else
    echo "✅ Found DATABASE_URL"
fi

echo ""
echo "Step 5: Deploying Dashboard service..."
railway up

echo ""
echo "=================================================="
echo "  ✅ Deployment complete!"
echo "=================================================="
echo ""
echo "Next steps:"
echo "1. Go to Railway Dashboard → your service"
echo "2. If DATABASE_URL wasn't set automatically, add it manually in Variables"
echo "3. Click the 🌐 domain link at the top of your service"
echo "4. Your dashboard will be live at: https://xxx.up.railway.app"
echo ""
echo "To populate data, run: python3 fetcher.py (locally or set up a Railway Cron)"
