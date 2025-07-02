#!/usr/bin/env python3
"""
Script to run local MedGemma inference server
"""
import os
import sys
import argparse
import json
from pathlib import Path

# Add src to path
sys.path.append(str(Path(__file__).parent.parent / 'src'))

import uvicorn


def main():
    parser = argparse.ArgumentParser(description='Run local MedGemma inference server')
    parser.add_argument('--host', type=str, default='0.0.0.0',
                       help='Host to bind to')
    parser.add_argument('--port', type=int, default=8000,
                       help='Port to bind to')
    parser.add_argument('--model-path', type=str,
                       help='Path to model (local or S3)')
    parser.add_argument('--base-model', type=str, default='microsoft/DialoGPT-medium',
                       help='Base model name')
    parser.add_argument('--reload', action='store_true',
                       help='Enable auto-reload for development')
    parser.add_argument('--workers', type=int, default=1,
                       help='Number of worker processes')
    
    args = parser.parse_args()
    
    # Set environment variables for the server
    if args.model_path:
        os.environ['MODEL_PATH'] = args.model_path
    os.environ['BASE_MODEL_NAME'] = args.base_model
    
    print(f"Starting inference server on {args.host}:{args.port}")
    print(f"Base model: {args.base_model}")
    if args.model_path:
        print(f"Model path: {args.model_path}")
    
    # Run the server
    uvicorn.run(
        "inference_server:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        workers=args.workers,
        log_level="info"
    )


if __name__ == "__main__":
    main()