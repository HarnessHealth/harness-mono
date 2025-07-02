# Mac Mini M-Series Optimized Dockerfile for MedGemma Local Training
FROM python:3.11-slim

# Set environment variables for Mac compatibility
ENV PYTHONUNBUFFERED=1
ENV PYTORCH_ENABLE_MPS_FALLBACK=1
ENV TOKENIZERS_PARALLELISM=false

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    git \
    curl \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Install additional Mac-optimized packages
RUN pip install --no-cache-dir \
    torch torchvision torchaudio \
    transformers[torch] \
    peft \
    datasets \
    accelerate \
    bitsandbytes \
    boto3 \
    s3fs \
    aioboto3 \
    fastapi \
    uvicorn \
    wandb \
    mlflow \
    numpy \
    pandas \
    scikit-learn \
    tqdm \
    psutil

# Copy application code
COPY src/ ./src/
COPY scripts/ ./scripts/
COPY config/ ./config/

# Create cache directories
RUN mkdir -p /app/.cache/harness/models && \
    mkdir -p /app/.cache/harness/data && \
    mkdir -p /app/logs

# Set permissions
RUN chmod +x scripts/*.py

# Expose port for inference server
EXPOSE 8000

# Default command
CMD ["python", "src/inference_server.py"]