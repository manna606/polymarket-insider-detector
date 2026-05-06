#!/bin/bash
# Start the Streamlit dashboard on Railway
# Railway sets $PORT automatically

PORT=${PORT:-8501}

echo "Starting Streamlit dashboard on port $PORT..."
exec streamlit run dashboard.py --server.port=$PORT --server.address=0.0.0.0
