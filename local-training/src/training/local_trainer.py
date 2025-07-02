"""
Local MedGemma Training Script for Mac Mini M-Series
Optimized for unified memory architecture with S3 streaming
"""
import os
import json
import logging
from datetime import datetime
from typing import Dict, Optional, Union
from pathlib import Path

import torch
import torch.backends.mps
from transformers import (
    AutoTokenizer,
    AutoModelForCausalLM,
    TrainingArguments,
    Trainer,
    DataCollatorForLanguageModeling,
    EarlyStoppingCallback,
)
from peft import (
    LoraConfig,
    get_peft_model,
    TaskType,
    prepare_model_for_kbit_training,
)
from torch.utils.data import DataLoader
import wandb
import mlflow
from accelerate import Accelerator
import psutil

from ..data.s3_streaming import S3StreamingDataset, S3VeterinaryDataProcessor

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MacMiniOptimizedTrainer:
    """
    Trainer optimized for Mac Mini M-series with unified memory
    """
    
    def __init__(self, config: Dict):
        self.config = config
        self.device = self._setup_device()
        self.model = None
        self.tokenizer = None
        self.train_dataset = None
        self.eval_dataset = None
        
        # Setup experiment tracking
        self._setup_tracking()
        
        # Monitor system resources
        self._log_system_info()
    
    def _setup_device(self) -> torch.device:
        """Setup optimal device for Mac Mini"""
        if torch.backends.mps.is_available():
            device = torch.device("mps")
            logger.info("Using Apple Metal Performance Shaders (MPS)")
        elif torch.cuda.is_available():
            device = torch.device("cuda")
            logger.info("Using CUDA")
        else:
            device = torch.device("cpu")
            logger.info("Using CPU")
        
        return device
    
    def _log_system_info(self):
        """Log system information for optimization"""
        memory_info = psutil.virtual_memory()
        logger.info(f"Total RAM: {memory_info.total / (1024**3):.1f} GB")
        logger.info(f"Available RAM: {memory_info.available / (1024**3):.1f} GB")
        logger.info(f"CPU cores: {psutil.cpu_count()}")
        
        if torch.backends.mps.is_available():
            logger.info("Mac unified memory architecture detected")
    
    def _setup_tracking(self):
        """Setup experiment tracking"""
        if self.config.get('use_wandb', False):
            wandb.init(
                project=self.config.get('wandb_project', 'harness-local-training'),
                name=f"local-medgemma-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
                config=self.config
            )
        
        if self.config.get('use_mlflow', False):
            mlflow.set_experiment(self.config.get('mlflow_experiment', 'local-medgemma'))
    
    def load_model_and_tokenizer(self, model_name: str = "microsoft/DialoGPT-medium"):
        """
        Load model and tokenizer optimized for Mac Mini
        Using smaller model for local testing
        """
        logger.info(f"Loading model: {model_name}")
        
        # Load tokenizer
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token
        
        # Load model with optimizations for Mac Mini
        self.model = AutoModelForCausalLM.from_pretrained(
            model_name,
            torch_dtype=torch.float16 if self.device.type != "cpu" else torch.float32,
            device_map="auto" if self.device.type != "mps" else None,
            trust_remote_code=True,
            low_cpu_mem_usage=True,
        )
        
        # Move to device if not using device_map
        if self.device.type == "mps":
            self.model = self.model.to(self.device)
        
        # Setup LoRA for efficient fine-tuning
        self._setup_lora()
        
        logger.info(f"Model loaded successfully on {self.device}")
        
        # Log model parameters
        total_params = sum(p.numel() for p in self.model.parameters())
        trainable_params = sum(p.numel() for p in self.model.parameters() if p.requires_grad)
        logger.info(f"Total parameters: {total_params:,}")
        logger.info(f"Trainable parameters: {trainable_params:,} ({trainable_params/total_params:.2%})")
    
    def _setup_lora(self):
        """Setup LoRA configuration optimized for Mac Mini"""
        lora_config = LoraConfig(
            r=self.config.get('lora_r', 16),  # Smaller rank for memory efficiency
            lora_alpha=self.config.get('lora_alpha', 32),
            target_modules=self.config.get('lora_target_modules', [
                "c_attn",  # For GPT-2 style models
                "c_proj",
            ]),
            lora_dropout=self.config.get('lora_dropout', 0.1),
            bias="none",
            task_type=TaskType.CAUSAL_LM,
        )
        
        # Apply LoRA
        self.model = get_peft_model(self.model, lora_config)
        self.model.print_trainable_parameters()
    
    def setup_datasets(self):
        """Setup streaming datasets from S3"""
        logger.info("Setting up S3 streaming datasets...")
        
        processor = S3VeterinaryDataProcessor(
            bucket_name=self.config['s3_bucket'],
            tokenizer=self.tokenizer
        )
        
        self.train_dataset, self.eval_dataset = processor.create_training_dataset(
            training_prefix=self.config.get('training_prefix', 'training/'),
            validation_prefix=self.config.get('validation_prefix', 'validation/'),
            max_length=self.config.get('max_length', 512),
            streaming_batch_size=self.config.get('streaming_batch_size', 50)
        )
        
        logger.info("Datasets setup complete")
    
    def train(self):
        """Run training with Mac Mini optimizations"""
        logger.info("Starting training...")
        
        # Training arguments optimized for Mac Mini
        training_args = TrainingArguments(
            output_dir=self.config['output_dir'],
            num_train_epochs=self.config.get('num_epochs', 3),
            per_device_train_batch_size=self.config.get('train_batch_size', 1),
            per_device_eval_batch_size=self.config.get('eval_batch_size', 1),
            gradient_accumulation_steps=self.config.get('gradient_accumulation_steps', 32),
            warmup_steps=self.config.get('warmup_steps', 100),
            learning_rate=self.config.get('learning_rate', 2e-5),
            fp16=self.device.type == "cuda",  # Use fp16 only on CUDA
            bf16=self.device.type == "cuda",  # Use bf16 only on CUDA
            logging_steps=self.config.get('logging_steps', 10),
            evaluation_strategy="steps",
            eval_steps=self.config.get('eval_steps', 100),
            save_strategy="steps",
            save_steps=self.config.get('save_steps', 500),
            save_total_limit=3,
            load_best_model_at_end=True,
            metric_for_best_model="eval_loss",
            greater_is_better=False,
            report_to=["wandb"] if self.config.get('use_wandb', False) else [],
            gradient_checkpointing=True,
            dataloader_num_workers=0,  # Avoid multiprocessing issues on Mac
            dataloader_pin_memory=False,  # Not needed with unified memory
            optim="adamw_torch",  # Use torch optimizer
            max_grad_norm=1.0,
            remove_unused_columns=False,
        )
        
        # Data collator
        data_collator = DataCollatorForLanguageModeling(
            tokenizer=self.tokenizer,
            mlm=False,
        )
        
        # Early stopping callback
        early_stopping = EarlyStoppingCallback(
            early_stopping_patience=self.config.get('early_stopping_patience', 3),
            early_stopping_threshold=self.config.get('early_stopping_threshold', 0.01)
        )
        
        # Initialize trainer
        trainer = Trainer(
            model=self.model,
            args=training_args,
            train_dataset=self.train_dataset,
            eval_dataset=self.eval_dataset,
            data_collator=data_collator,
            tokenizer=self.tokenizer,
            callbacks=[early_stopping],
        )
        
        # Train model
        train_result = trainer.train()
        
        # Save final model
        logger.info(f"Saving model to {self.config['output_dir']}")
        trainer.save_model()
        self.tokenizer.save_pretrained(self.config['output_dir'])
        
        # Save training metrics
        with open(os.path.join(self.config['output_dir'], 'training_metrics.json'), 'w') as f:
            json.dump(train_result.metrics, f, indent=2)
        
        # Upload to S3 if configured
        if self.config.get('s3_model_output'):
            self._upload_model_to_s3()
        
        return train_result
    
    def _upload_model_to_s3(self):
        """Upload trained model to S3"""
        import boto3
        
        s3_client = boto3.client('s3')
        bucket = self.config['s3_bucket']
        s3_prefix = self.config['s3_model_output']
        
        local_dir = Path(self.config['output_dir'])
        
        for file_path in local_dir.rglob('*'):
            if file_path.is_file():
                relative_path = file_path.relative_to(local_dir)
                s3_key = f"{s3_prefix}/{relative_path}"
                
                logger.info(f"Uploading {file_path} to s3://{bucket}/{s3_key}")
                s3_client.upload_file(str(file_path), bucket, s3_key)
        
        logger.info(f"Model uploaded to s3://{bucket}/{s3_prefix}")
    
    def evaluate(self, eval_dataset=None):
        """Evaluate model performance"""
        if eval_dataset is None:
            eval_dataset = self.eval_dataset
        
        # Create a simple trainer for evaluation
        training_args = TrainingArguments(
            output_dir=self.config['output_dir'],
            per_device_eval_batch_size=self.config.get('eval_batch_size', 1),
            dataloader_num_workers=0,
            remove_unused_columns=False,
        )
        
        data_collator = DataCollatorForLanguageModeling(
            tokenizer=self.tokenizer,
            mlm=False,
        )
        
        trainer = Trainer(
            model=self.model,
            args=training_args,
            eval_dataset=eval_dataset,
            data_collator=data_collator,
            tokenizer=self.tokenizer,
        )
        
        eval_results = trainer.evaluate()
        logger.info(f"Evaluation results: {eval_results}")
        
        return eval_results


def main():
    """Main training function"""
    # Configuration for Mac Mini local training
    config = {
        # Model configuration
        'model_name': 'microsoft/DialoGPT-medium',  # Smaller model for local testing
        'max_length': 512,
        
        # LoRA configuration
        'lora_r': 16,
        'lora_alpha': 32,
        'lora_dropout': 0.1,
        'lora_target_modules': ['c_attn', 'c_proj'],
        
        # Training configuration
        'num_epochs': 3,
        'train_batch_size': 1,
        'eval_batch_size': 1,
        'gradient_accumulation_steps': 32,
        'learning_rate': 2e-5,
        'warmup_steps': 100,
        'logging_steps': 10,
        'eval_steps': 100,
        'save_steps': 500,
        'early_stopping_patience': 3,
        
        # Data configuration
        's3_bucket': 'harness-training-data-development',
        'training_prefix': 'veterinary_qa_v1/train/',
        'validation_prefix': 'veterinary_qa_v1/val/',
        'streaming_batch_size': 50,
        
        # Output configuration
        'output_dir': './models/medgemma-local-v1',
        's3_model_output': 'local-experiments/medgemma-local-v1',
        
        # Experiment tracking
        'use_wandb': False,  # Set to True if you want to use Weights & Biases
        'use_mlflow': False,  # Set to True if you want to use MLflow
        'wandb_project': 'harness-local-training',
        'mlflow_experiment': 'local-medgemma',
    }
    
    # Initialize trainer
    trainer = MacMiniOptimizedTrainer(config)
    
    # Load model and tokenizer
    trainer.load_model_and_tokenizer(config['model_name'])
    
    # Setup datasets
    trainer.setup_datasets()
    
    # Train model
    results = trainer.train()
    
    # Evaluate model
    eval_results = trainer.evaluate()
    
    logger.info("Training completed successfully!")
    logger.info(f"Final evaluation: {eval_results}")


if __name__ == "__main__":
    main()