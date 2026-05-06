FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    siril \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first (for caching)
COPY backend/requirements.txt ./backend/
RUN pip install --no-cache-dir -r backend/requirements.txt

# Copy backend code
COPY backend /app/backend

# Copy existing client code (needed by backend/clients.py)
COPY clients /app/clients
COPY config_loader.py /app/
COPY config.toml /app/

# Create data directories
RUN mkdir -p /app/data /app/captures

# Expose backend port
EXPOSE 8503

# Run FastAPI backend
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8503"]
