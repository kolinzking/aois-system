# Stage 1 — build: install dependencies into a clean layer
FROM python:3.11-slim AS builder

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# Stage 2 — runtime: copy only what is needed to run
FROM python:3.11-slim AS runtime

# Non-root user — running as root inside a container is a security risk
RUN useradd --create-home --shell /bin/bash aois
WORKDIR /home/aois/app

# Copy installed packages from builder stage
COPY --from=builder /install /usr/local

# Remove build tools — not needed at runtime, and carry known CVEs
RUN pip uninstall -y setuptools wheel 2>/dev/null || true

# Copy application code
COPY main.py .

# Switch to non-root user before the process starts
USER aois

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
