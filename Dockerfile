FROM python:3.10-slim

# Install system dependencies required by typical OCR, image processing, and PDF tools
RUN apt-get update && apt-get install -y \
    build-essential \
    ffmpeg \
    libsm6 \
    libxext6 \
    poppler-utils \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements and install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install the actual marker tool
RUN pip install --no-cache-dir marker-pdf

# Copy the API source
COPY api.py .

# Setup environment defaults targeted towards Docker contexts
ENV MARKER_OUTPUT_DIR=/app/output
ENV MARKER_API_PORT=8335
ENV MARKER_API_TOKEN=my-secret-token

# Use host.docker.internal to interface with the local LLM running on the host machine
ENV OPENAI_BASE_URL=http://host.docker.internal:8020/v1

# Ensure the output dir permissions are set to accept mounted volumes well
RUN mkdir -p /app/output && chmod 777 /app/output

EXPOSE 8335

CMD ["python", "api.py"]
