import asyncio
import pytest
from unittest.mock import Mock, patch

from src.orchestrator import DiagnosticOrchestrator


def test_call_llm_success():
    orchestrator = DiagnosticOrchestrator()
    with patch('google.generativeai') as mock_genai:
        mock_model = Mock()
        mock_response = Mock(text='LLM result')
        mock_model.generate_content.return_value = mock_response
        mock_genai.GenerativeModel.return_value = mock_model

        result = asyncio.run(orchestrator._call_llm('test prompt'))

        assert result == 'LLM result'
        mock_genai.configure.assert_called_once()
        mock_genai.GenerativeModel.assert_called_once_with('gemini-pro')
        mock_model.generate_content.assert_called_once()


def test_call_llm_failure():
    orchestrator = DiagnosticOrchestrator()
    with patch('google.generativeai') as mock_genai:
        mock_genai.GenerativeModel.side_effect = Exception('boom')
        with pytest.raises(Exception):
            asyncio.run(orchestrator._call_llm('prompt'))
