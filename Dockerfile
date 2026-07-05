# ============================================================
# SignAI — Hugging Face Spaces Dockerfile
# Free tier: 2 vCPU, 16 GB RAM — enough for TensorFlow + MediaPipe.
# ============================================================
FROM python:3.11-slim

# System deps required by OpenCV, MediaPipe, TensorFlow, psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libgl1 \
        libglib2.0-0 \
        libsm6 \
        libxext6 \
        libxrender1 \
        libpq-dev \
        ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (better layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Hugging Face Spaces injects PORT=7860 automatically.
# Expose 7860 to match the platform expectation.
ENV PORT=7860
ENV FLASK_ENV=production
EXPOSE 7860

# Run with gunicorn; 2 workers fit comfortably in 16GB RAM.
CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:7860", "--timeout", "120", "app:app"]
