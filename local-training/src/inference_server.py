"""
Local MedGemma Inference Server with S3 Integration
FastAPI server for testing fine-tuned models locally on Mac Mini
"""
import os
import json
import logging
from typing import Dict, List, Optional, Union
from pathlib import Path
import asyncio
from contextlib import asynccontextmanager

import torch
from transformers import AutoTokenizer, AutoModelForCausalLM
from peft import PeftModel
import boto3
from botocore.exceptions import NoCredentialsError
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn

from .data.s3_streaming import S3StreamingDataset

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ChatMessage(BaseModel):
    role: str = Field(..., description="Role of the message sender (user/assistant/system)")
    content: str = Field(..., description="Content of the message")


class ChatRequest(BaseModel):
    messages: List[ChatMessage] = Field(..., description="List of chat messages")
    max_tokens: int = Field(default=500, description="Maximum tokens to generate")
    temperature: float = Field(default=0.7, description="Sampling temperature")
    top_p: float = Field(default=0.9, description="Top-p sampling parameter")
    stream: bool = Field(default=False, description="Whether to stream the response")


class ChatResponse(BaseModel):
    response: str = Field(..., description="Generated response")
    citations: List[str] = Field(default=[], description="Citations for the response")
    metadata: Dict = Field(default={}, description="Additional metadata")


class VeterinaryQueryRequest(BaseModel):
    query: str = Field(..., description="Veterinary question or query")
    context: Optional[str] = Field(None, description="Additional context")
    include_citations: bool = Field(default=True, description="Whether to include citations")
    max_tokens: int = Field(default=500, description="Maximum tokens to generate")


class ModelInfo(BaseModel):
    model_name: str
    model_path: str
    is_loaded: bool
    parameters: Dict
    device: str


class LocalMedGemmaServer:
    """Local inference server for MedGemma models"""
    
    def __init__(self, config: Dict):
        self.config = config
        self.device = self._setup_device()
        self.base_model = None
        self.model = None
        self.tokenizer = None
        self.s3_client = None
        
        # Model cache
        self.model_cache = {}
        
        # Setup S3 client
        self._setup_s3_client()
    
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
    
    def _setup_s3_client(self):
        """Setup S3 client for model and data access"""
        try:
            self.s3_client = boto3.client('s3')
            logger.info("S3 client initialized successfully")
        except NoCredentialsError:
            logger.warning("AWS credentials not found. S3 features will be disabled.")
            self.s3_client = None
    
    async def load_model(self, model_path: str, is_s3_path: bool = False):
        """Load model from local path or S3"""
        logger.info(f"Loading model from: {model_path}")
        
        if is_s3_path and self.s3_client:
            model_path = await self._download_model_from_s3(model_path)
        
        # Load base model
        base_model_name = self.config.get('base_model_name', 'microsoft/DialoGPT-medium')
        
        logger.info(f"Loading base model: {base_model_name}")
        self.tokenizer = AutoTokenizer.from_pretrained(base_model_name)
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token
        
        self.base_model = AutoModelForCausalLM.from_pretrained(
            base_model_name,
            torch_dtype=torch.float16 if self.device.type != "cpu" else torch.float32,
            device_map="auto" if self.device.type != "mps" else None,
            trust_remote_code=True,
            low_cpu_mem_usage=True,
        )
        
        # Move to device if needed
        if self.device.type == "mps":
            self.base_model = self.base_model.to(self.device)
        
        # Load LoRA adapters if available
        if Path(model_path).exists() and any(Path(model_path).glob("adapter_*")):
            logger.info("Loading LoRA adapters...")
            self.model = PeftModel.from_pretrained(self.base_model, model_path)
        else:
            logger.info("No LoRA adapters found, using base model")
            self.model = self.base_model
        
        self.model.eval()
        logger.info("Model loaded successfully")
    
    async def _download_model_from_s3(self, s3_path: str) -> str:
        """Download model from S3 to local cache"""
        # Parse S3 path
        if s3_path.startswith('s3://'):
            s3_path = s3_path[5:]
        
        bucket, key_prefix = s3_path.split('/', 1)
        
        # Local cache directory
        cache_dir = Path.home() / '.cache' / 'harness' / 'models' / key_prefix
        cache_dir.mkdir(parents=True, exist_ok=True)
        
        # List and download all model files
        paginator = self.s3_client.get_paginator('list_objects_v2')
        
        for page in paginator.paginate(Bucket=bucket, Prefix=key_prefix):
            if 'Contents' in page:
                for obj in page['Contents']:
                    s3_key = obj['Key']
                    local_file = cache_dir / Path(s3_key).relative_to(key_prefix)
                    local_file.parent.mkdir(parents=True, exist_ok=True)
                    
                    # Download if not exists or newer
                    if not local_file.exists():
                        logger.info(f"Downloading {s3_key} to {local_file}")
                        self.s3_client.download_file(bucket, s3_key, str(local_file))
        
        return str(cache_dir)
    
    def format_veterinary_prompt(self, query: str, context: str = "") -> str:
        """Format prompt for veterinary Q&A"""
        prompt = f"""<|system|>
You are a veterinary clinical AI assistant. Provide evidence-based answers with citations when possible.
<|user|>
{query}

{f"Context: {context}" if context else ""}
<|assistant|>
"""
        return prompt
    
    async def generate_response(
        self,
        prompt: str,
        max_tokens: int = 500,
        temperature: float = 0.7,
        top_p: float = 0.9
    ) -> Dict:
        """Generate response using the loaded model"""
        if self.model is None:
            raise ValueError("Model not loaded. Call load_model() first.")
        
        # Tokenize input
        inputs = self.tokenizer.encode(prompt, return_tensors="pt")
        
        # Move to device
        if self.device.type == "mps":
            inputs = inputs.to(self.device)
        
        # Generate response
        with torch.no_grad():
            outputs = self.model.generate(
                inputs,
                max_new_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
                do_sample=True,
                pad_token_id=self.tokenizer.eos_token_id,
                attention_mask=torch.ones_like(inputs)
            )
        
        # Decode response
        full_response = self.tokenizer.decode(outputs[0], skip_special_tokens=True)
        
        # Extract just the generated part
        response = full_response[len(prompt):].strip()
        
        # Parse citations if present
        citations = self._extract_citations(response)
        
        return {
            "response": response,
            "citations": citations,
            "metadata": {
                "prompt_length": len(prompt),
                "response_length": len(response),
                "total_tokens": len(outputs[0])
            }
        }
    
    def _extract_citations(self, text: str) -> List[str]:
        """Extract citations from generated text"""
        citations = []
        
        # Look for citation patterns
        import re
        
        # Pattern for "Citations: ..."
        citation_match = re.search(r'Citations?:\s*(.+?)(?:\n|$)', text, re.IGNORECASE)
        if citation_match:
            citation_text = citation_match.group(1)
            citations = [c.strip() for c in citation_text.split(',') if c.strip()]
        
        return citations
    
    async def search_veterinary_corpus(self, query: str, max_results: int = 5) -> List[Dict]:
        """Search veterinary corpus for relevant papers"""
        if not self.s3_client:
            return []
        
        # This is a simplified implementation
        # In practice, you'd use vector embeddings or Elasticsearch
        try:
            # Use the embeddings bucket for similarity search
            # For now, return mock results
            return [
                {
                    "title": f"Veterinary Paper {i+1}",
                    "authors": f"Author {i+1} et al.",
                    "abstract": f"Abstract for paper {i+1} related to: {query}",
                    "source": f"Journal {i+1}",
                    "relevance_score": 0.9 - (i * 0.1)
                }
                for i in range(min(max_results, 3))
            ]
        except Exception as e:
            logger.error(f"Error searching corpus: {e}")
            return []
    
    def get_model_info(self) -> ModelInfo:
        """Get information about the loaded model"""
        if self.model is None:
            return ModelInfo(
                model_name="None",
                model_path="None",
                is_loaded=False,
                parameters={},
                device=str(self.device)
            )
        
        total_params = sum(p.numel() for p in self.model.parameters())
        trainable_params = sum(p.numel() for p in self.model.parameters() if p.requires_grad)
        
        return ModelInfo(
            model_name=self.config.get('model_name', 'Unknown'),
            model_path=self.config.get('model_path', 'Unknown'),
            is_loaded=True,
            parameters={
                "total_parameters": total_params,
                "trainable_parameters": trainable_params,
                "trainable_percentage": trainable_params / total_params * 100 if total_params > 0 else 0
            },
            device=str(self.device)
        )


# Global server instance
server = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    global server
    
    # Startup
    config = {
        'base_model_name': os.getenv('BASE_MODEL_NAME', 'microsoft/DialoGPT-medium'),
        'model_path': os.getenv('MODEL_PATH', './models/medgemma-local-v1'),
        'model_name': 'MedGemma Local'
    }
    
    server = LocalMedGemmaServer(config)
    
    # Load model if path exists
    model_path = config['model_path']
    if Path(model_path).exists() or model_path.startswith('s3://'):
        try:
            await server.load_model(model_path, is_s3_path=model_path.startswith('s3://'))
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
    
    yield
    
    # Shutdown
    logger.info("Shutting down inference server")


# FastAPI app
app = FastAPI(
    title="Harness Local MedGemma Inference Server",
    description="Local inference server for fine-tuned MedGemma models",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "model_loaded": server.model is not None if server else False}


@app.get("/model/info")
async def get_model_info():
    """Get information about the loaded model"""
    if not server:
        raise HTTPException(status_code=500, detail="Server not initialized")
    
    return server.get_model_info()


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Chat endpoint compatible with OpenAI format"""
    if not server or not server.model:
        raise HTTPException(status_code=503, detail="Model not loaded")
    
    try:
        # Convert messages to prompt
        prompt = ""
        for message in request.messages:
            if message.role == "system":
                prompt += f"<|system|>\n{message.content}\n"
            elif message.role == "user":
                prompt += f"<|user|>\n{message.content}\n"
            elif message.role == "assistant":
                prompt += f"<|assistant|>\n{message.content}\n"
        
        prompt += "<|assistant|>\n"
        
        # Generate response
        result = await server.generate_response(
            prompt=prompt,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            top_p=request.top_p
        )
        
        return ChatResponse(
            response=result["response"],
            citations=result["citations"],
            metadata=result["metadata"]
        )
        
    except Exception as e:
        logger.error(f"Error in chat endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/veterinary/query")
async def veterinary_query(request: VeterinaryQueryRequest):
    """Veterinary-specific query endpoint with RAG"""
    if not server or not server.model:
        raise HTTPException(status_code=503, detail="Model not loaded")
    
    try:
        # Search corpus for relevant context if enabled
        relevant_papers = []
        if request.include_citations:
            relevant_papers = await server.search_veterinary_corpus(request.query)
        
        # Build context from relevant papers
        context = request.context or ""
        if relevant_papers:
            context += "\n\nRelevant research:\n"
            for paper in relevant_papers:
                context += f"- {paper['title']}: {paper['abstract'][:200]}...\n"
        
        # Format prompt
        prompt = server.format_veterinary_prompt(request.query, context)
        
        # Generate response
        result = await server.generate_response(
            prompt=prompt,
            max_tokens=request.max_tokens
        )
        
        return {
            "query": request.query,
            "response": result["response"],
            "citations": result["citations"],
            "relevant_papers": relevant_papers,
            "metadata": result["metadata"]
        }
        
    except Exception as e:
        logger.error(f"Error in veterinary query: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/model/load")
async def load_model(model_path: str, is_s3_path: bool = False):
    """Load a model from local path or S3"""
    if not server:
        raise HTTPException(status_code=500, detail="Server not initialized")
    
    try:
        await server.load_model(model_path, is_s3_path)
        return {"message": f"Model loaded successfully from {model_path}"}
    except Exception as e:
        logger.error(f"Error loading model: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to load model: {str(e)}")


@app.get("/corpus/search")
async def search_corpus(query: str, max_results: int = 5):
    """Search veterinary corpus"""
    if not server:
        raise HTTPException(status_code=500, detail="Server not initialized")
    
    try:
        results = await server.search_veterinary_corpus(query, max_results)
        return {"query": query, "results": results}
    except Exception as e:
        logger.error(f"Error searching corpus: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    uvicorn.run(
        "src.inference_server:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )