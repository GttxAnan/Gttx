FROM python:3.10-slim

# Install system dependencies
# ffmpeg might be needed for some audio operations, though edge-tts outputs mp3 directly.
# Keeping it minimal for now.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements first to leverage cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY . .

# Create necessary directories
RUN mkdir -p uploads output

# Expose port (Render sets PORT env var, but we expose 5000 as documentation)
EXPOSE 5000

# Run with Gunicorn
# Adjust workers based on free tier limits
CMD gunicorn --bind 0.0.0.0:$PORT pdfAudioConverter:app --workers 1 --threads 8 --timeout 0
