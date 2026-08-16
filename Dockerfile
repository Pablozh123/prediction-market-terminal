# Prediction Market Terminal — production image (one image, two entry points)
#
# Build:  docker build -t market-terminal .
# Run:    docker compose up -d   (see docker-compose.yml)
#
# The same image runs both public faces of the project; compose picks the
# command per service:
#
#   control room (default public site, FastAPI + web/ + public/data):
#     python -m uvicorn api.server:app --host 0.0.0.0 --port 8787
#   Streamlit terminal (this file's CMD; secondary, on its own hostname):
#     python -m streamlit run prediction_terminal.py ...
#   alert scanner:
#     python scripts/run_alert_scanner.py
FROM python:3.13-slim

# Streamlit needs a writable home for its config/telemetry files.
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HOME=/app \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Streamlit terminal
COPY prediction_terminal.py ./
COPY src/ ./src/
COPY app/ ./app/
COPY scripts/run_alert_scanner.py ./scripts/run_alert_scanner.py
COPY .streamlit/ ./.streamlit/
# Control room: JSON bridge, static frontend, published research payloads.
COPY api/ ./api/
COPY web/ ./web/
COPY public/ ./public/

# Runtime state (settings, watchlists, copy-trading DB) lives in /app/data — mount it.
RUN useradd --create-home --uid 10001 terminal \
    && mkdir -p /app/data \
    && chown -R terminal:terminal /app
USER terminal

# 8501 Streamlit, 8787 control room. Neither is published by compose; Caddy is
# the only public entry point.
EXPOSE 8501 8787

# Both servers answer GET /healthz. HEALTHCHECK_PORT selects which one this
# container runs (compose sets 8787 for the control room; the scanner has no
# HTTP port and disables the check).
ENV HEALTHCHECK_PORT=8501
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import os, urllib.request as u; u.urlopen('http://127.0.0.1:' + os.environ.get('HEALTHCHECK_PORT', '8501') + '/healthz', timeout=4)" || exit 1

CMD ["python", "-m", "streamlit", "run", "prediction_terminal.py", \
     "--server.address", "0.0.0.0", \
     "--server.port", "8501", \
     "--server.headless", "true", \
     "--server.enableXsrfProtection", "true", \
     "--server.enableCORS", "false", \
     "--server.maxUploadSize", "1", \
     "--browser.gatherUsageStats", "false"]
