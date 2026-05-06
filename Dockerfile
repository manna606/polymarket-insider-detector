# Polymarket Insider Detector — Docker image for Railway
# Usage:
#   docker build -t polymarket-insider .
#   docker run --rm polymarket-insider

FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY *.py .

# Run the cross-sectional analysis by default
CMD ["python", "analysis.py"]
