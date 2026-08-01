FROM python:3.12-slim

# ── uv — fast Python package installer (Rust) ────────────────────────────────
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Pre-compile .pyc files for faster interpreter startup
ENV UV_COMPILE_BYTECODE=1

# ── System dependencies ──────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# ── Application ──────────────────────────────────────────────────────────────
WORKDIR /app

# Install Python dependencies with uv (reads pip-format requirements.txt)
COPY requirements.txt .
RUN uv venv && uv pip install --no-cache -r requirements.txt

# Ensure the venv's binaries are on PATH
ENV PATH="/app/.venv/bin:$PATH"

# Copy application code (mounted as volume in dev, but included for prod builds)
COPY . .

# Run Alembic migrations then start the server
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
