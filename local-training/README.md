# Harness Local MedGemma Training

Local training and inference setup for MedGemma models on Mac Mini M-series, with S3 streaming integration.

## Features

- **Mac Mini Optimized**: Designed for Apple Silicon M-series chips with unified memory
- **S3 Streaming**: Train on large datasets without local storage using S3 streaming
- **LoRA Fine-tuning**: Memory-efficient fine-tuning with Parameter-Efficient Fine-Tuning (PEFT)
- **Local Inference**: FastAPI server for testing models locally
- **Veterinary Focus**: Specialized for veterinary medical AI applications

## Quick Start

### 1. Setup Environment

```bash
# Build Docker container
docker build -t harness-local-training .

# Or run locally with Python
pip install -r requirements.txt
```

### 2. Configure AWS Access

```bash
# Set up AWS credentials
aws configure

# Or use environment variables
export AWS_ACCESS_KEY_ID=your_key
export AWS_SECRET_ACCESS_KEY=your_secret
export AWS_DEFAULT_REGION=us-east-1
```

### 3. Test S3 Connection

```bash
# Test connection to your training data bucket
python scripts/test_s3_connection.py --bucket harness-training-data-development

# Test with specific prefix
python scripts/test_s3_connection.py --bucket harness-training-data-development --prefix veterinary_qa_v1/
```

### 4. Run Training

```bash
# Quick test training (1 epoch, small batch)
python scripts/run_training.py --test-mode

# Full training with custom config
python scripts/run_training.py --config config/training_config.json

# Override specific parameters
python scripts/run_training.py --s3-bucket your-bucket --output-dir ./my-models
```

### 5. Start Inference Server

```bash
# Start server with trained model
python scripts/run_inference_server.py --model-path ./models/medgemma-local-v1

# Start with S3 model
python scripts/run_inference_server.py --model-path s3://harness-model-artifacts-development/local-experiments/medgemma-local-v1

# Development mode with auto-reload
python scripts/run_inference_server.py --reload
```

## Architecture

### Training Pipeline

```
S3 Training Data → Streaming Dataset → LoRA Fine-tuning → Model Artifacts → S3
                                    ↓
                           Mac Mini Unified Memory
                           (32-96GB shared CPU/GPU)
```

### Inference Pipeline

```
S3 Model Artifacts → Local Cache → FastAPI Server → Veterinary Q&A
                                        ↓
                               RAG with S3 Corpus
```

## Configuration

### Training Configuration (`config/training_config.json`)

```json
{
  "model_name": "microsoft/DialoGPT-medium",
  "max_length": 512,
  
  "lora_r": 16,
  "lora_alpha": 32,
  "lora_dropout": 0.1,
  
  "num_epochs": 3,
  "train_batch_size": 1,
  "gradient_accumulation_steps": 32,
  "learning_rate": 2e-5,
  
  "s3_bucket": "harness-training-data-development",
  "training_prefix": "veterinary_qa_v1/train/",
  "validation_prefix": "veterinary_qa_v1/val/",
  
  "output_dir": "./models/medgemma-local-v1",
  "s3_model_output": "local-experiments/medgemma-local-v1"
}
```

### Environment Variables

```bash
# Model configuration
MODEL_PATH=./models/medgemma-local-v1
BASE_MODEL_NAME=microsoft/DialoGPT-medium

# AWS configuration
AWS_PROFILE=default
AWS_DEFAULT_REGION=us-east-1

# Training configuration
PYTORCH_ENABLE_MPS_FALLBACK=1
TOKENIZERS_PARALLELISM=false
```

## API Endpoints

### Health Check
```bash
curl http://localhost:8000/health
```

### Model Information
```bash
curl http://localhost:8000/model/info
```

### Chat (OpenAI-compatible)
```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": "What causes kennel cough in dogs?"}
    ],
    "max_tokens": 500
  }'
```

### Veterinary Query with RAG
```bash
curl -X POST http://localhost:8000/veterinary/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "How to treat feline diabetes?",
    "include_citations": true,
    "max_tokens": 500
  }'
```

### Load Different Model
```bash
curl -X POST "http://localhost:8000/model/load" \
  -H "Content-Type: application/json" \
  -d '{
    "model_path": "s3://bucket/path/to/model",
    "is_s3_path": true
  }'
```

## Data Format

### Training Data Structure

Training data should be in JSON or JSONL format with the following structure:

```json
{
  "question": "What are the symptoms of kennel cough?",
  "answer": "Kennel cough symptoms include persistent dry cough, retching, and mild fever...",
  "context": "Kennel cough is a highly contagious respiratory disease affecting dogs...",
  "citations": ["Smith et al. 2023", "Veterinary Medicine Journal"]
}
```

### S3 Bucket Structure

```
harness-training-data-development/
├── veterinary_qa_v1/
│   ├── train/
│   │   ├── batch_001.jsonl
│   │   ├── batch_002.jsonl
│   │   └── ...
│   └── val/
│       ├── val_001.jsonl
│       └── ...
└── preprocessed/
    └── embeddings/
```

## Mac Mini Optimizations

### Memory Management
- Uses unified memory architecture (shared CPU/GPU memory)
- Optimized batch sizes for 32-96GB configurations
- Gradient accumulation for effective large batch training
- Smart caching for frequently accessed S3 objects

### Apple Silicon Features
- Metal Performance Shaders (MPS) acceleration
- Optimized for M2/M3 Max chips
- Power-efficient training for long sessions
- Native PyTorch optimizations

### Performance Tips
- Use `gradient_accumulation_steps=32` for effective batch size of 32
- Enable `gradient_checkpointing=True` to trade compute for memory
- Set `dataloader_num_workers=0` to avoid multiprocessing issues
- Use `fp16=False` on MPS (not supported)

## Testing

### Run Tests
```bash
# Run all tests
python -m pytest tests/

# Run specific test file
python -m pytest tests/test_s3_streaming.py

# Run with coverage
python -m pytest tests/ --cov=src --cov-report=html
```

### Integration Tests
```bash
# Test S3 connectivity
python scripts/test_s3_connection.py --bucket your-bucket

# Test training pipeline (dry run)
python scripts/run_training.py --dry-run --test-mode

# Test inference server
python scripts/run_inference_server.py &
curl http://localhost:8000/health
```

## Troubleshooting

### Common Issues

#### S3 Access Denied
```bash
# Check AWS credentials
aws sts get-caller-identity

# Verify bucket access
aws s3 ls s3://harness-training-data-development/
```

#### Memory Issues on Mac Mini
```python
# Reduce batch size and increase gradient accumulation
{
  "train_batch_size": 1,
  "gradient_accumulation_steps": 64,
  "max_length": 256
}
```

#### MPS Device Issues
```bash
# Enable fallback to CPU
export PYTORCH_ENABLE_MPS_FALLBACK=1

# Check MPS availability
python -c "import torch; print(torch.backends.mps.is_available())"
```

### Performance Monitoring

#### System Resources
```bash
# Monitor memory usage
htop

# Monitor GPU usage (if applicable)
nvidia-smi  # For CUDA
```

#### Training Metrics
- Loss curves in logs
- Memory usage tracking
- Training speed (tokens/second)
- Gradient norms

## Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Run the test suite
5. Submit a pull request

## License

This project is part of the Harness platform and follows the same licensing terms.