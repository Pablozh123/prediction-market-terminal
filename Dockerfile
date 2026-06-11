# Prediction Market Terminal — production image
# Build:  docker build -t market-terminal .
# Run:    docker compose up -d   (see docker-compose.yml)
FROM python:3.13-slim

# Streamlit needs a writable home for its config/telemetry files.
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HOME=/app \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY prediction_terminal.py ./
COPY src/ ./src/
COPY app/ ./app/
COPY scripts/run_alert_scanner.py ./scripts/run_alert_scanner.py
COPY .streamlit/ ./.streamlit/

# Runtime state (settings, watchlists, copy-trading DB) lives in /app/data — mount it.
RUN useradd --create-home --uid 10001 terminal \
    && mkdir -p /app/data \
    && chown -R terminal:terminal /app
USER terminal

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8501/healthz', timeout=4)" || exit 1

CMD ["python", "-m", "streamlit", "run", "prediction_terminal.py", \
     "--server.address", "0.0.0.0", \
     "--server.port", "8501", \
     "--server.headless", "true", \
     "--server.enableXsrfProtection", "true", \
     "--server.enableCORS", "false", \
     "--server.maxUploadSize", "1", \
     "--browser.gatherUsageStats", "false"]
