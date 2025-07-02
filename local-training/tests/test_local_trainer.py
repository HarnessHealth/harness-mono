"""
Tests for local training functionality
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
import torch
import tempfile
import os
from pathlib import Path

from src.training.local_trainer import MacMiniOptimizedTrainer


class TestMacMiniOptimizedTrainer:
    """Test Mac Mini optimized trainer"""
    
    @pytest.fixture
    def trainer_config(self):
        """Training configuration for testing"""
        return {
            'model_name': 'microsoft/DialoGPT-medium',
            'max_length': 256,
            'lora_r': 8,
            'lora_alpha': 16,
            'lora_dropout': 0.1,
            'lora_target_modules': ['c_attn', 'c_proj'],
            'num_epochs': 1,
            'train_batch_size': 1,
            'eval_batch_size': 1,
            'gradient_accumulation_steps': 4,
            'learning_rate': 2e-5,
            's3_bucket': 'test-bucket',
            'training_prefix': 'train/',
            'validation_prefix': 'val/',
            'output_dir': './test_output',
            'use_wandb': False,
            'use_mlflow': False,
        }
    
    def test_trainer_initialization(self, trainer_config):
        """Test trainer initialization"""
        trainer = MacMiniOptimizedTrainer(trainer_config)
        
        assert trainer.config == trainer_config
        assert trainer.model is None
        assert trainer.tokenizer is None
        assert trainer.device.type in ['mps', 'cuda', 'cpu']
    
    def test_device_setup(self, trainer_config):
        """Test device setup for different platforms"""
        trainer = MacMiniOptimizedTrainer(trainer_config)
        device = trainer._setup_device()
        
        # Should detect the appropriate device
        assert isinstance(device, torch.device)
    
    @patch('src.training.local_trainer.psutil')
    def test_log_system_info(self, mock_psutil, trainer_config):
        """Test system information logging"""
        # Mock system info
        mock_memory = Mock()
        mock_memory.total = 32 * 1024**3  # 32GB
        mock_memory.available = 16 * 1024**3  # 16GB
        mock_psutil.virtual_memory.return_value = mock_memory
        mock_psutil.cpu_count.return_value = 8
        
        trainer = MacMiniOptimizedTrainer(trainer_config)
        # Should not raise any exceptions
        trainer._log_system_info()
    
    @patch('src.training.local_trainer.wandb')
    def test_setup_tracking_wandb(self, mock_wandb, trainer_config):
        """Test experiment tracking setup with wandb"""
        trainer_config['use_wandb'] = True
        trainer = MacMiniOptimizedTrainer(trainer_config)
        
        mock_wandb.init.assert_called_once()
    
    @patch('src.training.local_trainer.mlflow')
    def test_setup_tracking_mlflow(self, mock_mlflow, trainer_config):
        """Test experiment tracking setup with mlflow"""
        trainer_config['use_mlflow'] = True
        trainer = MacMiniOptimizedTrainer(trainer_config)
        
        mock_mlflow.set_experiment.assert_called_once()
    
    @patch('src.training.local_trainer.AutoModelForCausalLM')
    @patch('src.training.local_trainer.AutoTokenizer')
    @patch('src.training.local_trainer.get_peft_model')
    def test_load_model_and_tokenizer(self, mock_get_peft_model, mock_model_class, mock_tokenizer_class, trainer_config):
        """Test model and tokenizer loading"""
        # Mock tokenizer
        mock_tokenizer = Mock()
        mock_tokenizer.pad_token = None
        mock_tokenizer.eos_token = '<eos>'
        mock_tokenizer_class.from_pretrained.return_value = mock_tokenizer
        
        # Mock model
        mock_model = Mock()
        mock_model_class.from_pretrained.return_value = mock_model
        
        # Mock PEFT model
        mock_peft_model = Mock()
        mock_peft_model.print_trainable_parameters.return_value = None
        mock_get_peft_model.return_value = mock_peft_model
        
        trainer = MacMiniOptimizedTrainer(trainer_config)
        trainer.load_model_and_tokenizer()
        
        assert trainer.tokenizer is not None
        assert trainer.model is not None
        assert trainer.tokenizer.pad_token == '<eos>'  # Should be set to eos_token
        mock_peft_model.print_trainable_parameters.assert_called_once()
    
    @patch('src.training.local_trainer.S3VeterinaryDataProcessor')
    def test_setup_datasets(self, mock_processor_class, trainer_config):
        """Test dataset setup"""
        # Mock processor and datasets
        mock_processor = Mock()
        mock_train_dataset = Mock()
        mock_eval_dataset = Mock()
        mock_processor.create_training_dataset.return_value = (mock_train_dataset, mock_eval_dataset)
        mock_processor_class.return_value = mock_processor
        
        trainer = MacMiniOptimizedTrainer(trainer_config)
        trainer.tokenizer = Mock()  # Mock tokenizer
        
        trainer.setup_datasets()
        
        assert trainer.train_dataset == mock_train_dataset
        assert trainer.eval_dataset == mock_eval_dataset
        mock_processor_class.assert_called_once_with(
            bucket_name='test-bucket',
            tokenizer=trainer.tokenizer
        )
    
    @patch('src.training.local_trainer.Trainer')
    @patch('os.makedirs')
    def test_train_method(self, mock_makedirs, mock_trainer_class, trainer_config):
        """Test training method"""
        # Create temporary output directory
        with tempfile.TemporaryDirectory() as temp_dir:
            trainer_config['output_dir'] = temp_dir
            
            # Mock trainer
            mock_trainer = Mock()
            mock_train_result = Mock()
            mock_train_result.metrics = {'train_loss': 0.5, 'eval_loss': 0.4}
            mock_trainer.train.return_value = mock_train_result
            mock_trainer.save_model.return_value = None
            mock_trainer_class.return_value = mock_trainer
            
            # Setup trainer with mocked components
            trainer = MacMiniOptimizedTrainer(trainer_config)
            trainer.model = Mock()
            trainer.tokenizer = Mock()
            trainer.tokenizer.save_pretrained = Mock()
            trainer.train_dataset = Mock()
            trainer.eval_dataset = Mock()
            
            result = trainer.train()
            
            assert result == mock_train_result
            mock_trainer.train.assert_called_once()
            mock_trainer.save_model.assert_called_once()
            
            # Check that metrics file was created
            metrics_file = Path(temp_dir) / 'training_metrics.json'
            assert metrics_file.exists()
    
    @patch('src.training.local_trainer.boto3')
    def test_upload_model_to_s3(self, mock_boto3, trainer_config):
        """Test model upload to S3"""
        with tempfile.TemporaryDirectory() as temp_dir:
            trainer_config['output_dir'] = temp_dir
            trainer_config['s3_model_output'] = 'test-models/experiment-1'
            
            # Create test files
            test_file = Path(temp_dir) / 'model.bin'
            test_file.write_text('test model data')
            
            # Mock S3 client
            mock_s3_client = Mock()
            mock_boto3.client.return_value = mock_s3_client
            
            trainer = MacMiniOptimizedTrainer(trainer_config)
            trainer._upload_model_to_s3()
            
            mock_s3_client.upload_file.assert_called_once()
    
    @patch('src.training.local_trainer.Trainer')
    def test_evaluate_method(self, mock_trainer_class, trainer_config):
        """Test evaluation method"""
        # Mock trainer
        mock_trainer = Mock()
        mock_eval_result = {'eval_loss': 0.3, 'eval_accuracy': 0.85}
        mock_trainer.evaluate.return_value = mock_eval_result
        mock_trainer_class.return_value = mock_trainer
        
        trainer = MacMiniOptimizedTrainer(trainer_config)
        trainer.model = Mock()
        trainer.tokenizer = Mock()
        trainer.eval_dataset = Mock()
        
        result = trainer.evaluate()
        
        assert result == mock_eval_result
        mock_trainer.evaluate.assert_called_once()
    
    def test_lora_config_creation(self, trainer_config):
        """Test LoRA configuration setup"""
        trainer = MacMiniOptimizedTrainer(trainer_config)
        
        # Mock model for LoRA setup
        mock_model = Mock()
        trainer.model = mock_model
        
        with patch('src.training.local_trainer.LoraConfig') as mock_lora_config:
            with patch('src.training.local_trainer.get_peft_model') as mock_get_peft_model:
                mock_peft_model = Mock()
                mock_peft_model.print_trainable_parameters = Mock()
                mock_get_peft_model.return_value = mock_peft_model
                
                trainer._setup_lora()
                
                # Check LoRA config was created with correct parameters
                mock_lora_config.assert_called_once()
                call_kwargs = mock_lora_config.call_args[1]
                assert call_kwargs['r'] == trainer_config['lora_r']
                assert call_kwargs['lora_alpha'] == trainer_config['lora_alpha']
                assert call_kwargs['lora_dropout'] == trainer_config['lora_dropout']
                assert call_kwargs['target_modules'] == trainer_config['lora_target_modules']


class TestTrainingConfiguration:
    """Test training configuration and arguments"""
    
    def test_training_args_generation(self):
        """Test TrainingArguments generation"""
        from transformers import TrainingArguments
        
        config = {
            'output_dir': './test_output',
            'num_epochs': 2,
            'train_batch_size': 2,
            'eval_batch_size': 2,
            'gradient_accumulation_steps': 8,
            'learning_rate': 1e-5,
        }
        
        # This would be similar to what's done in the trainer
        training_args = TrainingArguments(
            output_dir=config['output_dir'],
            num_train_epochs=config['num_epochs'],
            per_device_train_batch_size=config['train_batch_size'],
            per_device_eval_batch_size=config['eval_batch_size'],
            gradient_accumulation_steps=config['gradient_accumulation_steps'],
            learning_rate=config['learning_rate'],
            logging_steps=10,
            evaluation_strategy="steps",
            eval_steps=100,
            save_strategy="steps",
            save_steps=500,
        )
        
        assert training_args.output_dir == config['output_dir']
        assert training_args.num_train_epochs == config['num_epochs']
        assert training_args.per_device_train_batch_size == config['train_batch_size']


@pytest.mark.integration
class TestTrainingIntegration:
    """Integration tests for training pipeline"""
    
    @pytest.mark.skip(reason="Requires actual model and data")
    def test_full_training_pipeline(self):
        """Test complete training pipeline"""
        # This would test the entire pipeline:
        # 1. Load small model
        # 2. Create small dataset
        # 3. Run training for 1 step
        # 4. Verify outputs
        pass
    
    @pytest.mark.skip(reason="Requires S3 access")
    def test_s3_model_upload(self):
        """Test actual S3 model upload"""
        # This would test real S3 upload functionality
        pass


if __name__ == "__main__":
    pytest.main([__file__])