#!/usr/bin/env python3
"""
Unit tests for Lambda handler
"""

import json
import pytest
from unittest.mock import Mock, patch, MagicMock

from src.lambda_handler import (
    MessageParser,
    DiagnosticOrchestrator,
    get_credentials,
    invoke_llm,
    post_to_slack,
    lambda_handler
)


class TestMessageParser:
    """Test cases for MessageParser class."""
    
    def test_parse_timeout_error(self):
        """Test parsing of timeout error messages."""
        message = """
        Exception: airflow.exceptions.AirflowSensorTimeout: 
        Sensor has timed out; run duration of 2452.710339 seconds 
        exceeds the specified timeout of 2400.0.
        """
        
        result = MessageParser.parse(message)
        
        assert result['error_type'] == 'timeout'
        assert 'timeout' in result['keywords']
        assert result['details']['group_1'] == '2452.710339'
        assert result['details']['group_2'] == '2400.0'
    
    def test_parse_dbt_error(self):
        """Test parsing of DBT error messages."""
        message = """
        Exception: cosmos.exceptions.CosmosDbtRunError: 
        dbt invocation completed with errors: Database Error in model dim_providers
        """
        
        result = MessageParser.parse(message)
        
        assert result['error_type'] == 'dbt_error'
        assert 'dbt' in result['keywords']
        assert 'database' in result['keywords']
        assert result['details']['group_1'] == 'dim_providers'
    
    def test_parse_connection_error(self):
        """Test parsing of connection error messages."""
        message = "Connection to database failed: timeout expired"
        
        result = MessageParser.parse(message)
        
        assert result['error_type'] == 'connection'
        assert 'connection' in result['keywords']
    
    def test_parse_unknown_error(self):
        """Test parsing of unknown error types."""
        message = "Some random error occurred"
        
        result = MessageParser.parse(message)
        
        assert result['error_type'] == 'unknown'
        assert result['keywords'] == []


class TestDiagnosticOrchestrator:
    """Test cases for DiagnosticOrchestrator class."""
    
    @patch('src.lambda_handler.get_mwaa_task_logs')
    @patch('src.lambda_handler.get_dag_run_status')
    def test_gather_diagnostics_success(self, mock_dag_status, mock_mwaa_logs):
        """Test successful diagnostic gathering."""
        # Setup mocks
        mock_mwaa_logs.return_value = "Test log content"
        mock_dag_status.return_value = {
            'summary': {'total_tasks': 5, 'failed': 1}
        }
        
        orchestrator = DiagnosticOrchestrator()
        parsed_data = {
            'log_url': 'https://test.url',
            'dag_id': 'test_dag',
            'execution_time': '2024-01-01',
            'exception': 'Test exception',
            'task_id': 'test_task'
        }
        
        result = orchestrator.gather_diagnostics(parsed_data)
        
        assert result['mwaa_logs'] == "Test log content"
        assert result['dag_status']['summary']['total_tasks'] == 5
        assert len(result['errors']) == 0
        mock_mwaa_logs.assert_called_once_with('https://test.url')
    
    @patch('src.lambda_handler.get_mwaa_task_logs')
    @patch('src.lambda_handler.query_redshift_audit_logs')
    def test_gather_diagnostics_with_dbt_error(self, mock_redshift, mock_mwaa_logs):
        """Test diagnostic gathering for DBT errors."""
        mock_mwaa_logs.return_value = "DBT error logs"
        mock_redshift.return_value = [{'error': 'Column not found'}]
        
        orchestrator = DiagnosticOrchestrator()
        parsed_data = {
            'log_url': 'https://test.url',
            'dag_id': 'test_dag',
            'execution_time': '2024-01-01',
            'exception': 'CosmosDbtRunError in model test_model',
            'task_id': 'run_dbt'
        }
        
        result = orchestrator.gather_diagnostics(parsed_data)
        
        assert result['redshift_audit'] is not None
        mock_redshift.assert_called_once()
    
    @patch('src.lambda_handler.cloudwatch')
    def test_publish_metrics(self, mock_cloudwatch):
        """Test CloudWatch metrics publishing."""
        orchestrator = DiagnosticOrchestrator()
        orchestrator.add_metric('TestMetric', 1.0)
        orchestrator.add_metric('TestTimer', 100.0, 'Milliseconds')
        
        orchestrator.publish_metrics()
        
        mock_cloudwatch.put_metric_data.assert_called_once()
        call_args = mock_cloudwatch.put_metric_data.call_args
        assert call_args[1]['Namespace'] == 'DE-Agent'
        assert len(call_args[1]['MetricData']) == 2


class TestCredentials:
    """Test cases for credential management."""
    
    @patch('src.lambda_handler.secrets_client')
    def test_get_credentials_success(self, mock_secrets):
        """Test successful credential retrieval."""
        mock_secrets.get_secret_value.side_effect = [
            {'SecretString': '{"bot_token": "xoxb-test", "signing_secret": "test"}'},
            {'SecretString': '{"api_key": "test-gemini-key"}'}
        ]
        
        slack_token, gemini_key = get_credentials()
        
        assert slack_token == 'xoxb-test'
        assert gemini_key == 'test-gemini-key'
        assert mock_secrets.get_secret_value.call_count == 2
    
    @patch('src.lambda_handler.secrets_client')
    def test_get_credentials_failure(self, mock_secrets):
        """Test credential retrieval failure."""
        mock_secrets.get_secret_value.side_effect = Exception("Access denied")
        
        with pytest.raises(Exception):
            get_credentials()


class TestLLMIntegration:
    """Test cases for LLM integration."""
    
    @patch('src.lambda_handler.genai')
    def test_invoke_llm_success(self, mock_genai):
        """Test successful LLM invocation."""
        # Setup mock
        mock_model = Mock()
        mock_response = Mock()
        mock_response.text = "## Root Cause Analysis\n\nTest analysis"
        mock_model.generate_content.return_value = mock_response
        mock_genai.GenerativeModel.return_value = mock_model
        
        context = {
            'dag_id': 'test_dag',
            'task_id': 'test_task',
            'error_type': 'timeout',
            'diagnostics': {'mwaa_logs': 'Test logs'}
        }
        
        result = invoke_llm(context, 'test-api-key')
        
        assert 'Root Cause Analysis' in result
        assert 'Test analysis' in result
        mock_genai.configure.assert_called_once_with(api_key='test-api-key')
    
    @patch('src.lambda_handler.genai')
    def test_invoke_llm_failure(self, mock_genai):
        """Test LLM invocation failure with fallback."""
        mock_genai.GenerativeModel.side_effect = Exception("API error")
        
        context = {
            'dag_id': 'test_dag',
            'task_id': 'test_task',
            'error_type': 'unknown'
        }
        
        result = invoke_llm(context, 'test-api-key')
        
        assert '🤖 **Diagnostic Analysis**' in result
        assert 'encountered an error' in result
        assert 'test_dag' in result


class TestSlackIntegration:
    """Test cases for Slack integration."""
    
    @patch('src.lambda_handler.WebClient')
    def test_post_to_slack_success(self, mock_webclient_class):
        """Test successful Slack message posting."""
        mock_client = Mock()
        mock_webclient_class.return_value = mock_client
        mock_client.chat_postMessage.return_value = {'ts': '1234567890.123456'}
        
        result = post_to_slack(
            mock_client,
            'C1234567890',
            '1234567890.000000',
            'Test message'
        )
        
        assert result is True
        mock_client.chat_postMessage.assert_called_once_with(
            channel='C1234567890',
            thread_ts='1234567890.000000',
            text='Test message',
            mrkdwn=True
        )
    
    @patch('src.lambda_handler.WebClient')
    def test_post_to_slack_api_error(self, mock_webclient_class):
        """Test Slack API error handling."""
        from slack_sdk.errors import SlackApiError
        
        mock_client = Mock()
        mock_webclient_class.return_value = mock_client
        mock_client.chat_postMessage.side_effect = SlackApiError(
            "Error",
            {'error': 'channel_not_found'}
        )
        
        result = post_to_slack(
            mock_client,
            'C1234567890',
            '1234567890.000000',
            'Test message'
        )
        
        assert result is False


class TestLambdaHandler:
    """Test cases for main Lambda handler."""
    
    @patch('src.lambda_handler.get_credentials')
    @patch('src.lambda_handler.WebClient')
    @patch('src.lambda_handler.DiagnosticOrchestrator')
    @patch('src.lambda_handler.invoke_llm')
    def test_lambda_handler_success(
        self,
        mock_llm,
        mock_orchestrator_class,
        mock_webclient_class,
        mock_get_creds
    ):
        """Test successful Lambda execution."""
        # Setup mocks
        mock_get_creds.return_value = ('slack-token', 'gemini-key')
        
        mock_client = Mock()
        mock_webclient_class.return_value = mock_client
        mock_client.chat_postMessage.return_value = {'ts': '123'}
        mock_client.reactions_add.return_value = {'ok': True}
        
        mock_orchestrator = Mock()
        mock_orchestrator_class.return_value = mock_orchestrator
        mock_orchestrator.gather_diagnostics.return_value = {
            'mwaa_logs': 'Test logs'
        }
        
        mock_llm.return_value = "Test analysis"
        
        # Test event
        event = {
            'channel': 'C123',
            'thread_ts': '123.456',
            'message_ts': '123.456',
            'raw_message': 'Test failure message',
            'parsed_data': {
                'dag_id': 'test_dag',
                'task_id': 'test_task',
                'execution_time': '2024-01-01',
                'exception': 'Test error',
                'log_url': 'https://test.url'
            }
        }
        
        result = lambda_handler(event, None)
        
        assert result['statusCode'] == 200
        assert json.loads(result['body'])['success'] is True
        mock_orchestrator.gather_diagnostics.assert_called_once()
        mock_llm.assert_called_once()
        mock_client.chat_postMessage.assert_called_once()
    
    @patch('src.lambda_handler.get_credentials')
    def test_lambda_handler_exception(self, mock_get_creds):
        """Test Lambda handler exception handling."""
        mock_get_creds.side_effect = Exception("Credentials error")
        
        event = {
            'channel': 'C123',
            'thread_ts': '123.456',
            'message_ts': '123.456',
            'raw_message': 'Test',
            'parsed_data': {}
        }
        
        result = lambda_handler(event, None)
        
        assert result['statusCode'] == 500
        assert json.loads(result['body'])['success'] is False
        assert 'Credentials error' in json.loads(result['body'])['error']
    
    @patch('src.lambda_handler.get_credentials')
    @patch('src.lambda_handler.WebClient')
    @patch('src.lambda_handler.DiagnosticOrchestrator')
    @patch('src.lambda_handler.invoke_llm')
    def test_lambda_handler_partial_failure(
        self,
        mock_llm,
        mock_orchestrator_class,
        mock_webclient_class,
        mock_get_creds
    ):
        """Test Lambda handler with partial failures in diagnostics."""
        # Setup mocks
        mock_get_creds.return_value = ('slack-token', 'gemini-key')
        
        mock_client = Mock()
        mock_webclient_class.return_value = mock_client
        mock_client.chat_postMessage.return_value = {'ts': '123'}
        
        mock_orchestrator = Mock()
        mock_orchestrator_class.return_value = mock_orchestrator
        mock_orchestrator.gather_diagnostics.return_value = {
            'mwaa_logs': None,
            'errors': ['Failed to get MWAA logs']
        }
        
        mock_llm.return_value = "Analysis with partial data"
        
        event = {
            'channel': 'C123',
            'thread_ts': '123.456',
            'message_ts': '123.456',
            'raw_message': 'Test failure',
            'parsed_data': {
                'dag_id': 'test_dag',
                'task_id': 'test_task',
                'execution_time': '2024-01-01',
                'exception': 'Test error',
                'log_url': 'https://test.url'
            }
        }
        
        result = lambda_handler(event, None)
        
        # Should still succeed even with partial diagnostic failures
        assert result['statusCode'] == 200
        assert json.loads(result['body'])['success'] is True


if __name__ == '__main__':
    pytest.main([__file__, '-v'])