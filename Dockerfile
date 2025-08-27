# Production-Ready Python Application Container
# Optimized for security, performance, and maintainability

FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies with security updates
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    ca-certificates \
    && apt-get upgrade -y \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf /tmp/* \
    && rm -rf /var/tmp/*

# Upgrade pip and install Python dependencies with security optimizations
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# Copy requirements and install dependencies with version pinning verification
COPY requirements.txt .
RUN pip install --no-cache-dir --require-hashes --disable-pip-version-check -r requirements.txt || \
    pip install --no-cache-dir --disable-pip-version-check -r requirements.txt

# Copy application code
COPY . .

# Create non-root user
RUN useradd -m -u 1000 dealerscope && chown -R dealerscope:dealerscope /app
USER dealerscope

# Expose port (Cloud Run uses PORT env var, default 8080)
EXPOSE 8080

# Enhanced health check with meaningful error reporting
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f --connect-timeout 5 --max-time 8 http://localhost:${PORT:-8080}/healthz || \
        (echo "Health check failed at $(date)" && exit 1)

# Security and performance labels
LABEL maintainer="DealerScope Team" \
      version="4.9.0" \
      description="DealerScope Backend API" \
      security.scan="enabled" \
      org.opencontainers.image.source="https://github.com/pilsonandrew-hub/DealerScope"

# Run application with production optimizations
CMD ["sh", "-c", "uvicorn webapp.main:app --host 0.0.0.0 --port ${PORT:-8080} --workers 1 --log-level info --access-log --timeout-keep-alive 120 --timeout-graceful-shutdown 30"]