"""
Harness - MedGemma Veterinary Fine-tuning Script
Fine-tunes MedGemma models on veterinary corpus using LoRA
"""
import os
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional

import torch
import transformers
from transformers import (
    AutoTokenizer,
    AutoModelForCausalLM,
    TrainingArguments,
    Trainer,
    DataCollatorForLanguageModeling,
)
from peft import (
    LoraConfig,
    get_peft_model,
    TaskType,
    prepare_model_for_kbit_training,
)
from datasets import Dataset, load_from_disk
import wandb
import mlflow
from accelerate import Accelerator
from bitsandbytes import BitsAndBytesConfig

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class VeterinaryDataProcessor:
    """Process veterinary training data for MedGemma fine-tuning"""
    
    def __init__(self, tokenizer, max_length=512):
        self.tokenizer = tokenizer
        self.max_length = max_length
    
    def format_instruction_data(self, example: Dict) -> Dict:
        """Format data for instruction tuning"""
        instruction = example.get('question', '')
        context = example.get('context', '')
        answer = example.get('answer', '')
        citations = example.get('citations', [])
        
        # Create prompt in MedGemma format
        prompt = f"""<|system|>
You are a veterinary clinical AI assistant. Provide evidence-based answers with citations.
<|user|>
{instruction}

Context: {context}
<|assistant|>
{answer}

Citations: {', '.join(citations)}
"""
        
        # Tokenize
        encodings = self.tokenizer(
            prompt,
            truncation=True,
            max_length=self.max_length,
            padding='max_length',
            return_tensors='pt'
        )
        
        return {
            'input_ids': encodings['input_ids'].squeeze(),
            'attention_mask': encodings['attention_mask'].squeeze(),
            'labels': encodings['input_ids'].squeeze()
        }


def setup_model_for_training(model_name: str = "medgemma-27b"):
    """Set up MedGemma model with LoRA for efficient fine-tuning"""
    
    # Quantization config for efficient training
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_use_double_quant=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16
    )
    
    # Load model
    logger.info(f"Loading {model_name} model...")
    model = AutoModelForCausalLM.from_pretrained(
        model_name,
        quantization_config=bnb_config,
        device_map="auto",
        trust_remote_code=True,
    )
    
    # Load tokenizer
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    tokenizer.pad_token = tokenizer.eos_token
    
    # Prepare model for k-bit training
    model = prepare_model_for_kbit_training(model)
    
    # LoRA configuration
    lora_config = LoraConfig(
        r=64,
        lora_alpha=128,
        target_modules=[
            "q_proj",
            "k_proj",
            "v_proj",
            "o_proj",
            "gate_proj",
            "up_proj",
            "down_proj",
        ],
        lora_dropout=0.1,
        bias="none",
        task_type=TaskType.CAUSAL_LM,
    )
    
    # Apply LoRA
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()
    
    return model, tokenizer


def load_veterinary_dataset(data_path: str) -> Dataset:
    """Load veterinary training dataset"""
    logger.info(f"Loading dataset from {data_path}")
    
    # Load from S3 or local path
    if data_path.startswith('s3://'):
        import boto3
        s3 = boto3.client('s3')
        # Download and load dataset
        # Implementation depends on data format
    else:
        dataset = load_from_disk(data_path)
    
    return dataset


def train_model(
    model,
    tokenizer,
    train_dataset: Dataset,
    eval_dataset: Dataset,
    output_dir: str,
    num_epochs: int = 3,
):
    """Train MedGemma on veterinary data"""
    
    # Training arguments
    training_args = TrainingArguments(
        output_dir=output_dir,
        num_train_epochs=num_epochs,
        per_device_train_batch_size=4,
        per_device_eval_batch_size=4,
        gradient_accumulation_steps=8,
        warmup_steps=1000,
        learning_rate=2e-5,
        fp16=True,
        logging_steps=10,
        evaluation_strategy="steps",
        eval_steps=500,
        save_strategy="steps",
        save_steps=1000,
        save_total_limit=3,
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
        greater_is_better=False,
        report_to=["wandb", "mlflow"],
        push_to_hub=False,
        gradient_checkpointing=True,
        optim="paged_adamw_8bit",
    )
    
    # Data collator
    data_collator = DataCollatorForLanguageModeling(
        tokenizer=tokenizer,
        mlm=False,
    )
    
    # Initialize trainer
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        data_collator=data_collator,
        tokenizer=tokenizer,
    )
    
    # Start training
    logger.info("Starting training...")
    trainer.train()
    
    # Save final model
    logger.info(f"Saving model to {output_dir}")
    trainer.save_model()
    tokenizer.save_pretrained(output_dir)
    
    return trainer


def evaluate_veterinary_performance(model, tokenizer, test_dataset):
    """Evaluate model on veterinary benchmarks"""
    logger.info("Evaluating model performance...")
    
    metrics = {
        'accuracy': 0.0,
        'citation_accuracy': 0.0,
        'clinical_relevance': 0.0,
    }
    
    # Implement evaluation logic
    # This would test on veterinary QA pairs, clinical cases, etc.
    
    return metrics


def main():
    """Main training pipeline"""
    # Configuration
    config = {
        'model_name': 'medgemma-27b',
        'data_path': 's3://harness-training-data-development/veterinary_qa_v1',
        'output_dir': 's3://harness-model-artifacts-development/medgemma-27b-vet-it-v0.1',
        'num_epochs': 3,
        'experiment_name': 'medgemma-vet-finetuning',
    }
    
    # Initialize tracking
    wandb.init(project="harness-medgemma", name=f"vet-finetune-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
    mlflow.set_experiment(config['experiment_name'])
    
    with mlflow.start_run():
        # Log parameters
        mlflow.log_params(config)
        
        # Setup model
        model, tokenizer = setup_model_for_training(config['model_name'])
        
        # Load and process data
        dataset = load_veterinary_dataset(config['data_path'])
        processor = VeterinaryDataProcessor(tokenizer)
        
        # Split dataset
        train_test_split = dataset.train_test_split(test_size=0.1)
        train_dataset = train_test_split['train']
        eval_dataset = train_test_split['test']
        
        # Process datasets
        train_dataset = train_dataset.map(processor.format_instruction_data)
        eval_dataset = eval_dataset.map(processor.format_instruction_data)
        
        # Train model
        trainer = train_model(
            model,
            tokenizer,
            train_dataset,
            eval_dataset,
            config['output_dir'],
            config['num_epochs']
        )
        
        # Evaluate
        metrics = evaluate_veterinary_performance(model, tokenizer, eval_dataset)
        mlflow.log_metrics(metrics)
        
        logger.info("Training completed successfully!")


if __name__ == "__main__":
    main()