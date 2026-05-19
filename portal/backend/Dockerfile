FROM python:3.11-slim

# Install system dependencies.
# siril: provided by the Ubuntu/Debian main repo (works on x86_64 + Ubuntu 22.04 aarch64).
# The lock042 PPA has a broken ARM64 build as of early 2026 — do NOT use it.
# If apt install siril fails on the target Jetson, override at runtime:
#   docker run -e SIRIL_BIN="flatpak run --command=siril-cli org.siril.Siril" ...
# shlex.split() in the service handles multi-word commands natively — no wrapper script needed.
# Flatpak inside Docker requires --privileged and adds 200MB+, so we keep it as the override path only.
# OpenCV+sep also need libgl1/libglib2/gcc.
RUN apt-get update && apt-get install -y \
    curl \
    siril \
    libgl1 \
    libglib2.0-0 \
    libc6-dev \
    gcc \
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

# Copy the canonical clients/ package (same code Streamlit imports).
# Previously the backend imported from a stale snapshot at existing_codebase/clients/
# which silently drifted from portal/clients/ — see commit history (#39, #38, #41).
COPY clients /app/clients

# Copy shared utils so postprocessing_service can import utils.image_enhancement
COPY utils /app/utils

# Copy billing module so backend.main can import `from billing import webhook_handler`
COPY billing /app/billing

# Create data directories
RUN mkdir -p /app/data /app/captures /app/siril_workdir

# Expose backend port
EXPOSE 8503

# Run FastAPI backend
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8503"]
