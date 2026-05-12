#!/bin/bash
# Start the Streamlit dashboard on Railway
# Railway sets $PORT automatically

PORT=${PORT:-8501}

echo "Ensuring tracked events are in database..."
python3 add_market.py who-will-trump-speak-to-in-may || true
python3 add_market.py starmer-out-in-2025 || true
python3 add_market.py next-uk-prime-minister-in-2026-122 || true

echo "Starting Streamlit dashboard on port $PORT..."
exec streamlit run dashboard.py --server.port=$PORT --server.address=0.0.0.0
