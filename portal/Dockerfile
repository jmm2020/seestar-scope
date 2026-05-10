FROM python:3.11-slim

WORKDIR /app

# System deps for OpenCV (libgl1, libglib2) and sep (gcc to compile C ext)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libgl1 \
    libglib2.0-0 \
    libc6-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8502

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8502/_stcore/health || exit 1

ENTRYPOINT ["streamlit", "run", "app.py", \
    "--server.port=8502", \
    "--server.address=0.0.0.0", \
    "--server.headless=true", \
    "--theme.base=dark", \
    "--theme.primaryColor=#00ff88"]
