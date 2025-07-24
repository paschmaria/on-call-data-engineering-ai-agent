"""
Unit tests for AWS diagnostic tools and helper functions.

Tests the AWS service integration functions with mocking to ensure
proper error handling and response formatting.
"""

import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.tools import (
    get_mwaa_task_logs,
    query_redshift_audit_logs,
    get_cloudwatch_lambda_errors,
    get_redshift_recent_errors,
    check_mwaa_dag_state,
    get_secrets_manager_value,
    format_slack_response
)

class TestSecretsManager:
    """Test cases for Secrets Manager interactions."""
    
    @patch('src.tools.boto3.client')
    def test_get_secrets_manager_value_success(self, mock_boto_client):
        """Test successful secret retrieval."""
        mock_client = Mock()
        mock_boto_client.return_value = mock_client
        mock_client.get_secret_value.return_value = {
            'SecretString': json.dumps({'api_key': 'test-key-123'})
        }
        
        result = get_secrets_manager_value('de-agent/gemini')
        
        assert result == {'api_key': 'test-key-123'}
        mock_client.get_secret_value.assert_called_once_with(SecretId='de-agent/gemini')
    
    @patch('src.tools.boto3.client')
    def test_get_secrets_manager_value_not_found(self, mock_boto_client):
        """Test secret not found scenario."""
        mock_client = Mock()
        mock_boto_client.return_value = mock_client
        mock_client.get_secret_value.side_effect = Exception("ResourceNotFoundException")
        
        result = get_secrets_manager_value('nonexistent-secret')
        
        assert result is None
    
    @patch('src.tools.boto3.client')
    def test_get_secrets_manager_value_invalid_json(self, mock_boto_client):
        """Test invalid JSON in secret."""
        mock_client = Mock()
        mock_boto_client.return_value = mock_client
        mock_client.get_secret_value.return_value = {
            'SecretString': 'invalid-json'
        }
        
        result = get_secrets_manager_value('de-agent/gemini')
        
        assert result is None

class TestMWAAIntegration:
    """Test cases for MWAA service integration."""
    
    @patch('src.tools.requests.get')
    def test_get_mwaa_task_logs_success(self, mock_get):
        """Test successful MWAA log retrieval."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = "Task execution log content here"
        mock_get.return_value = mock_response
        
        log_url = "https://mwaa-env.us-east-1.amazonaws.com/log/dag/task"
        result = get_mwaa_task_logs(log_url)
        
        assert result == "Task execution log content here"
        mock_get.assert_called_once_with(log_url, timeout=30)
    
    @patch('src.tools.requests.get')
    def test_get_mwaa_task_logs_failure(self, mock_get):
        """Test MWAA log retrieval failure."""
        mock_get.side_effect = Exception("Connection timeout")
        
        log_url = "https://mwaa-env.us-east-1.amazonaws.com/log/dag/task"
        result = get_mwaa_task_logs(log_url)
        
        assert result is None
    
    @patch('src.tools.requests.get')
    def test_get_mwaa_task_logs_http_error(self, mock_get):
        """Test MWAA log retrieval with HTTP error."""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = Exception("404 Not Found")
        mock_get.return_value = mock_response
        
        log_url = "https://mwaa-env.us-east-1.amazonaws.com/log/dag/task"
        result = get_mwaa_task_logs(log_url)
        
        assert result is None
    
    @patch('src.tools.boto3.client')
    def test_check_mwaa_dag_state_success(self, mock_boto_client):
        """Test successful DAG state check."""
        mock_client = Mock()
        mock_boto_client.return_value = mock_client
        mock_client.get_environment.return_value = {
            'Environment': {
                'Name': 'test-environment',
                'Status': 'AVAILABLE',
                'WebserverUrl': 'https://test-env.com'
            }
        }
        
        result = check_mwaa_dag_state('test_dag')
        
        assert result['environment_status'] == 'AVAILABLE'
        assert 'environment_name' in result
    
    @patch('src.tools.boto3.client')
    def test_check_mwaa_dag_state_failure(self, mock_boto_client):
        """Test DAG state check failure."""
        mock_client = Mock()
        mock_boto_client.return_value = mock_client
        mock_client.get_environment.side_effect = Exception("Environment not found")
        
        result = check_mwaa_dag_state('nonexistent_dag')
        
        assert result is None

class TestRedshiftIntegration:
    """Test cases for Redshift service integration."""
    
    @patch('src.tools.boto3.client')
    def test_query_redshift_audit_logs_success(self, mock_boto_client):
        """Test successful Redshift audit log query."""
        mock_client = Mock()
        mock_boto_client.return_value = mock_client
        
        # Mock execute_statement
        mock_client.execute_statement.return_value = {
            'Id': 'query-123'
        }
        
        # Mock get_statement_result
        mock_client.get_statement_result.return_value = {
            'Records': [
                [
                    {'stringValue': 'model_name'},
                    {'stringValue': 'FAILED'},
                    {'stringValue': 'Database error: relation does not exist'},
                    {'timestampValue': datetime.utcnow()}
                ]
            ],
            'ColumnMetadata': [
                {'name': 'model_name'},
                {'name': 'status'},
                {'name': 'error_message'},
                {'name': 'timestamp'}
            ]
        }
        
        result = query_redshift_audit_logs('test_model')
        
        assert len(result) == 1
        assert result[0]['model_name'] == 'model_name'
        assert result[0]['status'] == 'FAILED'
    
    @patch('src.tools.boto3.client')
    def test_query_redshift_audit_logs_no_results(self, mock_boto_client):
        """Test Redshift audit log query with no results."""
        mock_client = Mock()
        mock_boto_client.return_value = mock_client
        
        mock_client.execute_statement.return_value = {'Id': 'query-123'}
        mock_client.get_statement_result.return_value = {
            'Records': [],
            'ColumnMetadata': []
        }
        
        result = query_redshift_audit_logs('test_model')
        
        assert result == []
    
    @patch('src.tools.boto3.client')
    def test_query_redshift_audit_logs_failure(self, mock_boto_client):
        """Test Redshift audit log query failure."""
        mock_client = Mock()
        mock_boto_client.return_value = mock_client
        mock_client.execute_statement.side_effect = Exception("Query execution failed")
        
        result = query_redshift_audit_logs('test_model')
        
        assert result == []
    
    @patch('src.tools.boto3.client')
    def test_get_redshift_recent_errors_success(self, mock_boto_client):
        """Test successful recent errors retrieval."""
        mock_client = Mock()
        mock_boto_client.return_value = mock_client
        
        mock_client.execute_statement.return_value = {'Id': 'query-456'}
        mock_client.get_statement_result.return_value = {
            'Records': [
                [
                    {'stringValue': 'Connection failed'},
                    {'timestampValue': datetime.utcnow()},
                    {'stringValue': 'user_query'}
                ]
            ],
            'ColumnMetadata': [
                {'name': 'error_message'},
                {'name': 'timestamp'},
                {'name': 'query_text'}
            ]
        }
        
        result = get_redshift_recent_errors(24)
        
        assert len(result) == 1
        assert 'error_message' in result[0]

class TestCloudWatchIntegration:
    """Test cases for CloudWatch service integration."""
    
    @patch('src.tools.boto3.client')
    def test_get_cloudwatch_lambda_errors_success(self, mock_boto_client):
        """Test successful CloudWatch error retrieval."""
        mock_client = Mock()
        mock_boto_client.return_value = mock_client
        
        mock_client.start_query.return_value = {'queryId': 'query-789'}
        mock_client.get_query_results.return_value = {
            'status': 'Complete',
            'results': [
                [
                    {'field': '@timestamp', 'value': '2024-01-01T12:00:00Z'},
                    {'field': '@message', 'value': 'ERROR: Task failed with exception'}
                ]
            ]
        }
        
        result = get_cloudwatch_lambda_errors('test_dag')
        
        assert len(result) == 1
        assert 'ERROR: Task failed with exception' in result[0]
    
    @patch('src.tools.boto3.client')
    def test_get_cloudwatch_lambda_errors_timeout(self, mock_boto_client):
        """Test CloudWatch query timeout."""
        mock_client = Mock()
        mock_boto_client.return_value = mock_client
        
        mock_client.start_query.return_value = {'queryId': 'query-789'}
        mock_client.get_query_results.side_effect = [
            {'status': 'Running'},
            {'status': 'Running'},
            {'status': 'Running'}
        ]
        
        result = get_cloudwatch_lambda_errors('test_dag')
        
        assert result == []
    
    @patch('src.tools.boto3.client')
    def test_get_cloudwatch_lambda_errors_failure(self, mock_boto_client):
        """Test CloudWatch query failure."""
        mock_client = Mock()
        mock_boto_client.return_value = mock_client
        mock_client.start_query.side_effect = Exception("CloudWatch unavailable")
        
        result = get_cloudwatch_lambda_errors('test_dag')
        
        assert result == []

class TestSlackFormatting:
    """Test cases for Slack response formatting."""
    
    def test_format_slack_response_basic(self):
        """Test basic Slack response formatting."""
        analysis = """## Root Cause Analysis
Database connection timeout

## Immediate Actions
1. Check connection settings
2. Restart the service"""
        
        result = format_slack_response(analysis, 'test_dag', 'Medium')
        
        assert '🔍 *Root Cause Analysis*' in result
        assert 'Database connection timeout' in result
        assert '1. Check connection settings' in result
    
    def test_format_slack_response_with_confidence(self):
        """Test Slack response formatting with confidence score."""
        analysis = "Basic analysis text"
        
        result = format_slack_response(analysis, 'test_dag', 'High')
        
        assert 'Confidence: High' in result
        assert 'DAG: `test_dag`' in result
    
    def test_format_slack_response_long_text(self):
        """Test Slack response formatting with text truncation."""
        long_analysis = "Analysis text " * 1000  # Very long text
        
        result = format_slack_response(long_analysis, 'test_dag')
        
        # Should be truncated for Slack limits
        assert len(result) < 4000
        assert 'truncated' in result.lower()
    
    def test_format_slack_response_markdown_conversion(self):
        """Test conversion of markdown to Slack format."""
        analysis = """## Section Title
**Bold text** and *italic text*
- List item 1
- List item 2"""
        
        result = format_slack_response(analysis, 'test_dag')
        
        assert '*Section Title*' in result
        assert '*Bold text*' in result
        assert '_italic text_' in result
        assert '• List item 1' in result

class TestErrorHandling:
    """Test cases for error handling across all functions."""
    
    @patch('src.tools.boto3.client')
    def test_boto3_client_creation_failure(self, mock_boto_client):
        """Test handling of boto3 client creation failure."""
        mock_boto_client.side_effect = Exception("AWS credentials not found")
        
        result = get_secrets_manager_value('test-secret')
        
        assert result is None
    
    def test_invalid_log_url(self):
        """Test handling of invalid log URLs."""
        result = get_mwaa_task_logs('not-a-valid-url')
        
        assert result is None
    
    def test_empty_model_name(self):
        """Test handling of empty model name in Redshift query."""
        result = query_redshift_audit_logs('')
        
        assert result == []
    
    def test_none_inputs(self):
        """Test handling of None inputs."""
        assert get_mwaa_task_logs(None) is None
        assert query_redshift_audit_logs(None) == []
        assert check_mwaa_dag_state(None) is None

# Fixtures for test data
@pytest.fixture
def sample_redshift_response():
    """Sample Redshift query response."""
    return {
        'Records': [
            [
                {'stringValue': 'test_model'},
                {'stringValue': 'FAILED'},
                {'stringValue': 'relation "test_table" does not exist'},
                {'timestampValue': datetime.utcnow()}
            ]
        ],
        'ColumnMetadata': [
            {'name': 'model_name'},
            {'name': 'status'},
            {'name': 'error_message'},
            {'name': 'timestamp'}
        ]
    }

@pytest.fixture
def sample_cloudwatch_response():
    """Sample CloudWatch Logs Insights response."""
    return {
        'status': 'Complete',
        'results': [
            [
                {'field': '@timestamp', 'value': '2024-01-01T12:00:00Z'},
                {'field': '@message', 'value': 'ERROR: Connection timeout after 30 seconds'}
            ],
            [
                {'field': '@timestamp', 'value': '2024-01-01T12:01:00Z'},
                {'field': '@message', 'value': 'WARN: Retrying connection attempt 2/3'}
            ]
        ]
    }

if __name__ == '__main__':
    pytest.main([__file__])
