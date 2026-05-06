# Polymarket + Kalshi Data Pipeline — Docker image for Railway
# Usage:
#   docker build -t polymarket-fetcher .
#   docker run --rm -e DATABASE_URL=... polymarket-fetcher

FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY *.py .
COPY *.sh .
COPY schema.sql .
RUN chmod +x *.sh

# Default: run the daily data fetcher
CMD ["python", "fetcher.py"]
