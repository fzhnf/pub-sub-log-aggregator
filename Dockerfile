# Multi-stage build for minimal final image
FROM python:3.13-slim AS builder

# Set working directory
WORKDIR /app

# Install uv for faster dependency installation
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files
COPY pyproject.toml ./

# Install dependencies (no dev dependencies)
RUN uv pip install --system --no-cache-dir -e .

# ============================================
# Final stage - minimal runtime image
# ============================================
FROM python:3.13-slim

# Set working directory
WORKDIR /app

# Create non-root user for security
RUN adduser --disabled-password --gecos '' --uid 1000 appuser && \
    chown -R appuser:appuser /app

# Copy installed dependencies from builder
COPY --from=builder /usr/local/lib/python3.13/site-packages \
                    /usr/local/lib/python3.13/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY models.py dedup_store.py main.py ./

# Create data directory with proper permissions
RUN mkdir -p /app/data && chown -R appuser:appuser /app/data

RUN touch /app/__init__.py

# Install curl while we are still root for health check
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*


# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8080/health || exit 1

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV DEDUP_DB_PATH=/app/data/dedup.db

# Run application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
