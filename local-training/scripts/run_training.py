#!/usr/bin/env python3
"""
Script to run local MedGemma training on Mac Mini
"""
import os
import sys
import argparse
import json
from pathlib import Path

# Add src to path
sys.path.append(str(Path(__file__).parent.parent / 'src'))

from training.local_trainer import MacMiniOptimizedTrainer


def load_config(config_path: str) -> dict:
    """Load configuration from JSON file"""
    with open(config_path, 'r') as f:
        return json.load(f)


def main():
    parser = argparse.ArgumentParser(description='Run local MedGemma training')
    parser.add_argument('--config', type=str, default='config/training_config.json',
                       help='Path to training configuration file')
    parser.add_argument('--model-name', type=str,
                       help='Override model name from config')
    parser.add_argument('--s3-bucket', type=str,
                       help='Override S3 bucket from config')
    parser.add_argument('--output-dir', type=str,
                       help='Override output directory from config')
    parser.add_argument('--test-mode', action='store_true',
                       help='Run in test mode with reduced data and epochs')
    parser.add_argument('--dry-run', action='store_true',
                       help='Only setup datasets and model, do not train')
    
    args = parser.parse_args()
    
    # Load configuration
    if os.path.exists(args.config):
        config = load_config(args.config)
    else:
        print(f"Configuration file {args.config} not found. Using default config.")
        config = {}
    
    # Apply command line overrides
    if args.model_name:
        config['model_name'] = args.model_name
    if args.s3_bucket:
        config['s3_bucket'] = args.s3_bucket
    if args.output_dir:
        config['output_dir'] = args.output_dir
    
    # Test mode adjustments
    if args.test_mode:
        config.update({
            'num_epochs': 1,
            'train_batch_size': 1,
            'eval_batch_size': 1,
            'gradient_accumulation_steps': 2,
            'max_length': 128,
            'logging_steps': 5,
            'eval_steps': 10,
            'save_steps': 20,
        })
        print("Running in test mode with reduced parameters")
    
    print("Training configuration:")
    print(json.dumps(config, indent=2))
    
    # Initialize trainer
    print("\nInitializing trainer...")
    trainer = MacMiniOptimizedTrainer(config)
    
    # Load model and tokenizer
    print("Loading model and tokenizer...")
    model_name = config.get('model_name', 'microsoft/DialoGPT-medium')
    trainer.load_model_and_tokenizer(model_name)
    
    # Setup datasets
    print("Setting up datasets...")
    trainer.setup_datasets()
    
    if args.dry_run:
        print("Dry run completed. Model and datasets are ready.")
        return
    
    # Run training
    print("Starting training...")
    try:
        results = trainer.train()
        print(f"Training completed successfully!")
        print(f"Final training metrics: {results.metrics}")
        
        # Run evaluation
        print("Running final evaluation...")
        eval_results = trainer.evaluate()
        print(f"Final evaluation metrics: {eval_results}")
        
    except Exception as e:
        print(f"Training failed with error: {e}")
        raise


if __name__ == "__main__":
    main()