"""
Tests for S3 streaming dataset functionality
"""
import pytest
import asyncio
from unittest.mock import Mock, patch, MagicMock
import json

from src.data.s3_streaming import S3StreamingDataset, S3VeterinaryDataProcessor


class TestS3StreamingDataset:
    """Test S3 streaming dataset"""
    
    @pytest.fixture
    def mock_s3_client(self):
        """Mock S3 client"""
        client = Mock()
        
        # Mock list_objects_v2
        client.get_paginator.return_value.paginate.return_value = [
            {
                'Contents': [
                    {'Key': 'training/sample1.json'},
                    {'Key': 'training/sample2.jsonl'},
                ]
            }
        ]
        
        # Mock get_object
        def mock_get_object(Bucket, Key):
            if Key == 'training/sample1.json':
                return {
                    'Body': Mock(read=lambda: json.dumps({
                        'question': 'What causes kennel cough in dogs?',
                        'answer': 'Kennel cough is typically caused by Bordetella bronchiseptica...',
                        'context': 'Respiratory diseases in dogs...',
                        'citations': ['Smith et al. 2023']
                    }).encode())
                }
            elif Key == 'training/sample2.jsonl':
                return {
                    'Body': Mock(read=lambda: '\n'.join([
                        json.dumps({
                            'question': 'How to treat feline diabetes?',
                            'answer': 'Feline diabetes is managed with insulin therapy...',
                            'context': 'Endocrine disorders in cats...',
                            'citations': ['Jones et al. 2022']
                        }),
                        json.dumps({
                            'question': 'What is equine colic?',
                            'answer': 'Equine colic refers to abdominal pain in horses...',
                            'context': 'Gastrointestinal issues in horses...',
                            'citations': ['Brown et al. 2021']
                        })
                    ]).encode())
                }
        
        client.get_object.side_effect = mock_get_object
        return client
    
    @pytest.fixture
    def mock_tokenizer(self):
        """Mock tokenizer"""
        tokenizer = Mock()
        tokenizer.pad_token = '<pad>'
        tokenizer.eos_token = '<eos>'
        
        def mock_tokenize(text, **kwargs):
            # Simple mock tokenization
            tokens = text.split()[:kwargs.get('max_length', 512)]
            input_ids = [i for i in range(len(tokens))]
            attention_mask = [1] * len(tokens)
            
            # Pad to max_length if needed
            max_length = kwargs.get('max_length', 512)
            if kwargs.get('padding') == 'max_length':
                while len(input_ids) < max_length:
                    input_ids.append(0)
                    attention_mask.append(0)
            
            import torch
            return {
                'input_ids': torch.tensor([input_ids]),
                'attention_mask': torch.tensor([attention_mask])
            }
        
        tokenizer.side_effect = mock_tokenize
        return tokenizer
    
    @patch('src.data.s3_streaming.boto3')
    def test_dataset_initialization(self, mock_boto3, mock_s3_client):
        """Test dataset initialization"""
        mock_boto3.Session.return_value.client.return_value = mock_s3_client
        
        dataset = S3StreamingDataset(
            bucket_name='test-bucket',
            prefix='training/',
            max_length=256
        )
        
        assert dataset.bucket_name == 'test-bucket'
        assert dataset.prefix == 'training/'
        assert dataset.max_length == 256
        assert len(dataset.object_keys) == 2
    
    @patch('src.data.s3_streaming.boto3')
    def test_dataset_iteration(self, mock_boto3, mock_s3_client, mock_tokenizer):
        """Test dataset iteration"""
        mock_boto3.Session.return_value.client.return_value = mock_s3_client
        
        dataset = S3StreamingDataset(
            bucket_name='test-bucket',
            prefix='training/',
            tokenizer=mock_tokenizer,
            max_length=256
        )
        
        samples = list(dataset)
        
        # Should have 3 samples total (1 from sample1.json, 2 from sample2.jsonl)
        assert len(samples) == 3
        
        # Check first sample
        assert 'input_ids' in samples[0]
        assert 'attention_mask' in samples[0]
        assert 'original_sample' in samples[0]
        assert samples[0]['original_sample']['question'] == 'What causes kennel cough in dogs?'
    
    @patch('src.data.s3_streaming.boto3')
    def test_cache_functionality(self, mock_boto3, mock_s3_client):
        """Test LRU cache functionality"""
        mock_boto3.Session.return_value.client.return_value = mock_s3_client
        
        dataset = S3StreamingDataset(
            bucket_name='test-bucket',
            prefix='training/',
            cache_size=1  # Small cache for testing
        )
        
        # Load first object
        data1 = dataset._load_s3_object('training/sample1.json')
        assert len(dataset._cache) == 1
        
        # Load second object (should evict first)
        data2 = dataset._load_s3_object('training/sample2.jsonl')
        assert len(dataset._cache) == 1
        assert 'training/sample1.json' not in dataset._cache
        assert 'training/sample2.jsonl' in dataset._cache
    
    def test_format_veterinary_sample(self):
        """Test veterinary sample formatting"""
        dataset = S3StreamingDataset('test-bucket', 'test/')
        
        sample = {
            'question': 'What is the treatment for parvo?',
            'answer': 'Supportive care including IV fluids...',
            'context': 'Canine parvovirus...',
            'citations': ['Veterinary Journal 2023']
        }
        
        formatted = dataset._format_veterinary_sample(sample)
        
        assert 'text' in formatted
        assert '<|system|>' in formatted['text']
        assert '<|user|>' in formatted['text']
        assert '<|assistant|>' in formatted['text']
        assert 'What is the treatment for parvo?' in formatted['text']
        assert 'Supportive care including IV fluids...' in formatted['text']


class TestS3VeterinaryDataProcessor:
    """Test S3 veterinary data processor"""
    
    @pytest.fixture
    def mock_tokenizer(self):
        """Mock tokenizer"""
        tokenizer = Mock()
        tokenizer.pad_token = '<pad>'
        return tokenizer
    
    def test_processor_initialization(self, mock_tokenizer):
        """Test processor initialization"""
        processor = S3VeterinaryDataProcessor(
            bucket_name='test-bucket',
            tokenizer=mock_tokenizer
        )
        
        assert processor.bucket_name == 'test-bucket'
        assert processor.tokenizer == mock_tokenizer
    
    @patch('src.data.s3_streaming.S3StreamingDataset')
    def test_create_training_dataset(self, mock_dataset_class, mock_tokenizer):
        """Test training dataset creation"""
        # Mock dataset instances
        mock_train_dataset = Mock()
        mock_val_dataset = Mock()
        mock_dataset_class.side_effect = [mock_train_dataset, mock_val_dataset]
        
        processor = S3VeterinaryDataProcessor(
            bucket_name='test-bucket',
            tokenizer=mock_tokenizer
        )
        
        train_ds, val_ds = processor.create_training_dataset()
        
        assert train_ds == mock_train_dataset
        assert val_ds == mock_val_dataset
        assert mock_dataset_class.call_count == 2


@pytest.mark.asyncio
async def test_async_streaming():
    """Test async functionality"""
    # This would test actual async streaming if implemented
    # For now, just a placeholder
    pass


if __name__ == "__main__":
    pytest.main([__file__])