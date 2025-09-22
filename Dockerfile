FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

COPY pm_arb_bot ./pm_arb_bot
COPY config.example.yaml ./
COPY .env.example ./
COPY pm_arb_bot/data/sample_books.ndjson ./pm_arb_bot/data/sample_books.ndjson

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir \
    "aiosqlite>=0.19" \
    "httpx[http2]>=0.25" \
    "pydantic>=2.4" \
    "pyyaml>=6.0" \
    "structlog>=23.1" \
    "tenacity>=8.2" \
    "typer>=0.9" \
    "prometheus-client>=0.17" \
    "websockets>=11.0"

RUN useradd --create-home botuser
USER botuser

EXPOSE 9308

HEALTHCHECK CMD curl -f http://localhost:9308/metrics || exit 1

ENTRYPOINT ["python", "-m", "pm_arb_bot.cli", "run", "--config", "config.example.yaml", "--dry-run"]
