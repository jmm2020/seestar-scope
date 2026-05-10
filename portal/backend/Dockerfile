FROM python:3.11-slim

# Install system dependencies.
# siril: provided by the Ubuntu/Debian main repo (works on x86_64 + Ubuntu 22.04 aarch64).
# The lock042 PPA has a broken ARM64 build as of early 2026 — do NOT use it.
# If apt install siril fails on the target Jetson, override at runtime:
#   docker run -e SIRIL_BIN="/usr/local/bin/siril-cli" ...
# where /usr/local/bin/siril-cli is a host-side wrapper for `flatpak run --command=siril-cli org.siril.Siril`.
# Flatpak inside Docker requires --privileged and adds 200MB+, so we keep it as the override path only.
RUN apt-get update && apt-get install -y \
    curl \
    siril \
    && rm -rf /var/lib/apt/lists/*

# Default Siril CLI binary; override with SIRIL_BIN env var for ARM64/Flatpak.
ENV SIRIL_BIN=siril-cli

# Set working directory
WORKDIR /app

# Copy requirements first (for caching)
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code (preserving backend/ directory structure)
COPY backend /app/backend

# Copy existing_codebase for client imports
COPY existing_codebase /app/existing_codebase

# Create data directories
RUN mkdir -p /app/data /app/captures /app/siril_workdir

# Expose backend port
EXPOSE 8503

# Run FastAPI backend
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8503"]
