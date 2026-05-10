FROM python:3.11-slim

# Install system dependencies (siril for stacking; libgl1/libglib2/gcc for OpenCV+sep)
RUN apt-get update && apt-get install -y \
    curl \
    siril \
    libgl1 \
    libglib2.0-0 \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first (for caching)
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code (preserving backend/ directory structure)
COPY backend /app/backend

# Copy existing_codebase for client imports
COPY existing_codebase /app/existing_codebase

# Copy shared utils so postprocessing_service can import utils.image_enhancement
COPY utils /app/utils

# Create data directories
RUN mkdir -p /app/data /app/captures /app/siril_workdir

# Expose backend port
EXPOSE 8503

# Run FastAPI backend
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8503"]
