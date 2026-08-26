# SoroScan webhook simulator — local development image
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY webhook_simulator ./webhook_simulator
COPY examples ./examples

RUN pip install --no-cache-dir . \
    && useradd --create-home --uid 1000 simulator \
    && chown -R simulator:simulator /app

USER simulator

ENTRYPOINT ["webhook-simulator"]
CMD ["--help"]
