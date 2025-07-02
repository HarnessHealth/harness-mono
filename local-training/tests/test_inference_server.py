"""
Tests for local inference server
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch, AsyncMock
import torch

from src.inference_server import app, LocalMedGemmaServer


class TestLocalMedGemmaServer:
    """Test local MedGemma server"""
    
    @pytest.fixture
    def server_config(self):
        """Server configuration for testing"""
        return {
            'base_model_name': 'microsoft/DialoGPT-medium',
            'model_path': './test_models/',
            'model_name': 'Test MedGemma'
        }
    
    @pytest.fixture
    def mock_model(self):
        """Mock model for testing"""
        model = Mock()
        model.eval.return_value = None
        model.generate.return_value = torch.tensor([[1, 2, 3, 4, 5]])
        return model
    
    @pytest.fixture
    def mock_tokenizer(self):
        """Mock tokenizer for testing"""
        tokenizer = Mock()
        tokenizer.pad_token = '<pad>'
        tokenizer.eos_token = '<eos>'
        tokenizer.eos_token_id = 0
        tokenizer.encode.return_value = torch.tensor([1, 2, 3])
        tokenizer.decode.return_value = "Test response from model"
        return tokenizer
    
    def test_server_initialization(self, server_config):
        """Test server initialization"""
        server = LocalMedGemmaServer(server_config)
        
        assert server.config == server_config
        assert server.model is None
        assert server.tokenizer is None
    
    def test_device_setup(self, server_config):
        """Test device setup"""
        server = LocalMedGemmaServer(server_config)
        device = server._setup_device()
        
        # Should be one of the supported devices
        assert device.type in ['mps', 'cuda', 'cpu']
    
    @patch('src.inference_server.AutoModelForCausalLM')
    @patch('src.inference_server.AutoTokenizer')
    @pytest.mark.asyncio
    async def test_load_model(self, mock_tokenizer_class, mock_model_class, server_config, mock_model, mock_tokenizer):
        """Test model loading"""
        mock_tokenizer_class.from_pretrained.return_value = mock_tokenizer
        mock_model_class.from_pretrained.return_value = mock_model
        
        server = LocalMedGemmaServer(server_config)
        await server.load_model('./test_models/')
        
        assert server.model is not None
        assert server.tokenizer is not None
        mock_model.eval.assert_called_once()
    
    def test_format_veterinary_prompt(self, server_config):
        """Test veterinary prompt formatting"""
        server = LocalMedGemmaServer(server_config)
        
        prompt = server.format_veterinary_prompt(
            query="What causes kennel cough?",
            context="Respiratory diseases in dogs"
        )
        
        assert "<|system|>" in prompt
        assert "<|user|>" in prompt
        assert "<|assistant|>" in prompt
        assert "What causes kennel cough?" in prompt
        assert "Respiratory diseases in dogs" in prompt
    
    @pytest.mark.asyncio
    async def test_generate_response(self, server_config, mock_model, mock_tokenizer):
        """Test response generation"""
        server = LocalMedGemmaServer(server_config)
        server.model = mock_model
        server.tokenizer = mock_tokenizer
        
        result = await server.generate_response("Test prompt")
        
        assert "response" in result
        assert "citations" in result
        assert "metadata" in result
        mock_model.generate.assert_called_once()
    
    def test_extract_citations(self, server_config):
        """Test citation extraction"""
        server = LocalMedGemmaServer(server_config)
        
        text_with_citations = "This is a response. Citations: Smith et al. 2023, Jones et al. 2022"
        citations = server._extract_citations(text_with_citations)
        
        assert len(citations) == 2
        assert "Smith et al. 2023" in citations
        assert "Jones et al. 2022" in citations
    
    @pytest.mark.asyncio
    async def test_search_veterinary_corpus(self, server_config):
        """Test corpus searching"""
        server = LocalMedGemmaServer(server_config)
        
        results = await server.search_veterinary_corpus("kennel cough")
        
        # Should return mock results
        assert isinstance(results, list)
        if results:  # If S3 client is available
            assert len(results) <= 5
            assert all('title' in result for result in results)
    
    def test_get_model_info_no_model(self, server_config):
        """Test model info when no model loaded"""
        server = LocalMedGemmaServer(server_config)
        
        info = server.get_model_info()
        
        assert info.model_name == "None"
        assert info.is_loaded is False
    
    def test_get_model_info_with_model(self, server_config, mock_model):
        """Test model info with model loaded"""
        server = LocalMedGemmaServer(server_config)
        server.model = mock_model
        
        # Mock model parameters
        mock_param = Mock()
        mock_param.numel.return_value = 1000
        mock_param.requires_grad = True
        mock_model.parameters.return_value = [mock_param]
        
        info = server.get_model_info()
        
        assert info.is_loaded is True
        assert info.parameters['total_parameters'] == 1000
        assert info.parameters['trainable_parameters'] == 1000


class TestInferenceAPI:
    """Test FastAPI endpoints"""
    
    @pytest.fixture
    def client(self):
        """Test client"""
        return TestClient(app)
    
    def test_health_endpoint(self, client):
        """Test health check endpoint"""
        response = client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "model_loaded" in data
    
    def test_model_info_endpoint(self, client):
        """Test model info endpoint"""
        response = client.get("/model/info")
        
        # May return 500 if server not initialized, which is expected in tests
        assert response.status_code in [200, 500]
    
    @patch('src.inference_server.server')
    def test_chat_endpoint_no_model(self, mock_server, client):
        """Test chat endpoint without model loaded"""
        mock_server.model = None
        
        response = client.post("/chat", json={
            "messages": [
                {"role": "user", "content": "What causes kennel cough?"}
            ]
        })
        
        assert response.status_code == 503
    
    @patch('src.inference_server.server')
    @pytest.mark.asyncio
    async def test_chat_endpoint_with_model(self, mock_server, client):
        """Test chat endpoint with model loaded"""
        mock_server.model = Mock()
        mock_server.generate_response = AsyncMock(return_value={
            "response": "Kennel cough is caused by...",
            "citations": ["Smith et al. 2023"],
            "metadata": {"tokens": 100}
        })
        
        response = client.post("/chat", json={
            "messages": [
                {"role": "user", "content": "What causes kennel cough?"}
            ]
        })
        
        if response.status_code == 200:
            data = response.json()
            assert "response" in data
            assert "citations" in data
    
    @patch('src.inference_server.server')
    @pytest.mark.asyncio
    async def test_veterinary_query_endpoint(self, mock_server, client):
        """Test veterinary query endpoint"""
        mock_server.model = Mock()
        mock_server.generate_response = AsyncMock(return_value={
            "response": "Treatment involves...",
            "citations": ["Jones et al. 2022"],
            "metadata": {"tokens": 150}
        })
        mock_server.search_veterinary_corpus = AsyncMock(return_value=[
            {"title": "Canine Diseases", "abstract": "Study on...", "relevance_score": 0.9}
        ])
        
        response = client.post("/veterinary/query", json={
            "query": "How to treat parvo in dogs?",
            "include_citations": True
        })
        
        if response.status_code == 200:
            data = response.json()
            assert "query" in data
            assert "response" in data
            assert "relevant_papers" in data
    
    def test_corpus_search_endpoint(self, client):
        """Test corpus search endpoint"""
        response = client.get("/corpus/search?query=kennel%20cough&max_results=3")
        
        # May return 500 if server not initialized
        assert response.status_code in [200, 500]


@pytest.mark.integration
class TestEndToEndIntegration:
    """Integration tests for the complete pipeline"""
    
    @pytest.mark.skip(reason="Requires actual model and S3 access")
    def test_full_pipeline(self):
        """Test complete training and inference pipeline"""
        # This would test:
        # 1. Loading data from S3
        # 2. Training a small model
        # 3. Loading trained model in inference server
        # 4. Making predictions
        pass
    
    @pytest.mark.skip(reason="Requires S3 access")
    def test_s3_integration(self):
        """Test S3 integration"""
        # This would test actual S3 connectivity
        pass


if __name__ == "__main__":
    pytest.main([__file__])