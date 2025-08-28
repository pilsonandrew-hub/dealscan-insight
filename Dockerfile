# Production-Ready Python Application Container
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    ca-certificates \
    && apt-get upgrade -y \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf /tmp/* \
    && rm -rf /var/tmp/*

# Upgrade pip and install Python dependencies
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --disable-pip-version-check -r requirements.txt

# Copy application code
COPY . .

# Create non-root user
RUN useradd -m -u 1000 dealerscope && chown -R dealerscope:dealerscope /app
USER dealerscope

# Expose port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f --connect-timeout 5 --max-time 8 http://localhost:${PORT:-8080}/healthz || \
        (echo "Health check failed at $(date)" && exit 1)

# Security and performance labels
LABEL maintainer="DealerScope Team" \
      version="1.0.0" \
      description="DealerScope Backend API" \
      security.scan="enabled"

# Run application with fallback to simple mode
CMD ["sh", "-c", "uvicorn webapp.simple_main:app --host 0.0.0.0 --port ${PORT:-8080} --workers 1 --log-level info --access-log --timeout-keep-alive 120 --timeout-graceful-shutdown 30 || uvicorn webapp.main_minimal:app --host 0.0.0.0 --port ${PORT:-8080}"]