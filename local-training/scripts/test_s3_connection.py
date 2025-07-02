#!/usr/bin/env python3
"""
Script to test S3 connection and data access
"""
import os
import sys
import argparse
import asyncio
from pathlib import Path

# Add src to path
sys.path.append(str(Path(__file__).parent.parent / 'src'))

from data.s3_streaming import S3StreamingDataset, S3VeterinaryDataProcessor
from transformers import AutoTokenizer


async def test_s3_connection(bucket_name: str, prefix: str = ""):
    """Test basic S3 connection and object listing"""
    print(f"Testing S3 connection to bucket: {bucket_name}")
    print(f"Prefix: {prefix}")
    
    try:
        # Create dataset without tokenizer first
        dataset = S3StreamingDataset(
            bucket_name=bucket_name,
            prefix=prefix,
            tokenizer=None,
            max_length=256
        )
        
        print(f"✓ Successfully connected to S3")
        print(f"✓ Found {len(dataset.object_keys)} objects")
        
        if dataset.object_keys:
            print("\nFirst 5 objects:")
            for obj in dataset.object_keys[:5]:
                print(f"  - {obj}")
        
        return True
        
    except Exception as e:
        print(f"✗ S3 connection failed: {e}")
        return False


async def test_data_loading(bucket_name: str, prefix: str = "", max_samples: int = 3):
    """Test data loading and processing"""
    print(f"\nTesting data loading from {bucket_name}/{prefix}")
    
    try:
        # Load tokenizer
        print("Loading tokenizer...")
        tokenizer = AutoTokenizer.from_pretrained("microsoft/DialoGPT-medium")
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token
        
        # Create dataset
        dataset = S3StreamingDataset(
            bucket_name=bucket_name,
            prefix=prefix,
            tokenizer=tokenizer,
            max_length=256,
            streaming_batch_size=10
        )
        
        print("✓ Dataset created successfully")
        
        # Try to load a few samples
        print(f"Loading {max_samples} samples...")
        samples = []
        for i, sample in enumerate(dataset):
            if i >= max_samples:
                break
            samples.append(sample)
        
        print(f"✓ Successfully loaded {len(samples)} samples")
        
        # Display sample information
        for i, sample in enumerate(samples):
            print(f"\nSample {i+1}:")
            if 'original_sample' in sample:
                orig = sample['original_sample']
                print(f"  Question: {orig.get('question', 'N/A')[:100]}...")
                print(f"  Answer: {orig.get('answer', 'N/A')[:100]}...")
                print(f"  Citations: {orig.get('citations', [])}")
            print(f"  Input IDs shape: {sample['input_ids'].shape}")
            print(f"  Attention mask shape: {sample['attention_mask'].shape}")
        
        return True
        
    except Exception as e:
        print(f"✗ Data loading failed: {e}")
        return False


async def test_veterinary_processor(bucket_name: str):
    """Test veterinary data processor"""
    print(f"\nTesting veterinary data processor")
    
    try:
        # Load tokenizer
        tokenizer = AutoTokenizer.from_pretrained("microsoft/DialoGPT-medium")
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token
        
        # Create processor
        processor = S3VeterinaryDataProcessor(
            bucket_name=bucket_name,
            tokenizer=tokenizer
        )
        
        print("✓ Processor created successfully")
        
        # Test dataset creation
        print("Creating training and validation datasets...")
        train_dataset, val_dataset = processor.create_training_dataset(
            training_prefix="training/",
            validation_prefix="validation/",
            max_length=256
        )
        
        print("✓ Datasets created successfully")
        print(f"  Training dataset: {len(train_dataset.object_keys)} objects")
        print(f"  Validation dataset: {len(val_dataset.object_keys)} objects")
        
        return True
        
    except Exception as e:
        print(f"✗ Processor test failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description='Test S3 connection and data access')
    parser.add_argument('--bucket', type=str, required=True,
                       help='S3 bucket name')
    parser.add_argument('--prefix', type=str, default='',
                       help='S3 prefix/folder')
    parser.add_argument('--max-samples', type=int, default=3,
                       help='Maximum samples to load for testing')
    parser.add_argument('--skip-data-loading', action='store_true',
                       help='Skip data loading test')
    parser.add_argument('--skip-processor', action='store_true',
                       help='Skip processor test')
    
    args = parser.parse_args()
    
    async def run_tests():
        # Test S3 connection
        connection_ok = await test_s3_connection(args.bucket, args.prefix)
        if not connection_ok:
            print("\n❌ S3 connection test failed. Check your AWS credentials and bucket access.")
            return False
        
        # Test data loading
        if not args.skip_data_loading:
            data_ok = await test_data_loading(args.bucket, args.prefix, args.max_samples)
            if not data_ok:
                print("\n❌ Data loading test failed.")
                return False
        
        # Test processor
        if not args.skip_processor:
            processor_ok = await test_veterinary_processor(args.bucket)
            if not processor_ok:
                print("\n❌ Processor test failed.")
                return False
        
        print("\n✅ All tests passed successfully!")
        return True
    
    # Run tests
    success = asyncio.run(run_tests())
    
    if success:
        print("\n🎉 S3 setup is working correctly!")
        print("You can now run training with:")
        print(f"  python scripts/run_training.py --s3-bucket {args.bucket}")
    else:
        print("\n💥 Some tests failed. Please check the errors above.")
        sys.exit(1)


if __name__ == "__main__":
    main()