# Production Playwright Scraper Image
FROM mcr.microsoft.com/playwright/python:v1.49.1-noble

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt requirements-dev.txt ./
RUN pip install --upgrade pip && \
    pip install -r requirements.txt -r requirements-dev.txt

# Ensure Chromium browser binaries are installed
RUN playwright install chromium

# Copy application codebase
COPY . .

# Set up persistence and log directories
RUN mkdir -p data data/exports snapshots data/browser_context

ENTRYPOINT ["python", "-m", "src.cli"]
CMD ["--help"]
