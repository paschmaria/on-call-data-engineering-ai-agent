#!/usr/bin/env python3
"""
Diagnostic Tools for DE-Agent

This module provides functions to gather diagnostic information from various
AWS services including MWAA, Redshift, and CloudWatch.
"""

import re
import json
import time
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from urllib.parse import urlparse, parse_qs

import boto3
import requests
from botocore.exceptions import ClientError

# Configure logging
logger = logging.getLogger(__name__)

# Initialize AWS clients
mwaa_client = boto3.client('mwaa')
redshift_data_client = boto3.client('redshift-data')
logs_client = boto3.client('logs')
secrets_client = boto3.client('secretsmanager')


class DiagnosticError(Exception):
    """Custom exception for diagnostic tool errors."""
    pass


def get_mwaa_task_logs(log_url: str) -> str:
    """
    Fetch detailed task logs from MWAA using the provided log URL.
    
    Args:
        log_url: URL to the MWAA task logs
        
    Returns:
        str: Full log text content
        
    Raises:
        DiagnosticError: If logs cannot be retrieved
    """
    try:
        # Parse the log URL to extract environment and log details
        parsed_url = urlparse(log_url)
        path_parts = parsed_url.path.split('/')
        
        # Extract environment name from URL
        # Format: https://[env-name].[region].airflow.amazonaws.com/...
        env_name = parsed_url.hostname.split('.')[0]
        
        # Get MWAA environment details for authentication
        response = mwaa_client.get_environment(Name=env_name)
        
        if response['Environment']['Status'] != 'AVAILABLE':
            raise DiagnosticError(f"MWAA environment {env_name} is not available")
        
        # Create a web login token for accessing the UI
        token_response = mwaa_client.create_web_login_token(
            Name=env_name
        )
        
        # Use the token to fetch logs
        headers = {
            'Authorization': f"Bearer {token_response['WebToken']}",
            'Content-Type': 'application/json'
        }
        
        # Construct the API endpoint for log retrieval
        log_api_url = f"{token_response['WebServerHostname']}/api/v1/logs/get"
        
        # Make request to fetch logs
        log_response = requests.get(
            log_url,
            headers=headers,
            timeout=30
        )
        
        if log_response.status_code != 200:
            raise DiagnosticError(
                f"Failed to fetch logs: HTTP {log_response.status_code}"
            )
        
        # Extract log content (handling both HTML and API responses)
        log_content = log_response.text
        
        # If HTML response, extract log content from pre tags
        if '<pre>' in log_content:
            match = re.search(r'<pre[^>]*>([\s\S]*?)</pre>', log_content)
            if match:
                log_content = match.group(1)
                
        # Clean up HTML entities
        log_content = log_content.replace('&lt;', '<').replace('&gt;', '>')
        log_content = log_content.replace('&amp;', '&').replace('&quot;', '"')
        
        # Limit log size to prevent token overflow
        max_log_size = 50000  # ~50KB
        if len(log_content) > max_log_size:
            log_content = (
                f"[Log truncated - showing last {max_log_size} characters]\n\n"
                f"{log_content[-max_log_size:]}"
            )
            
        return log_content
        
    except ClientError as e:
        logger.error(f"AWS API error fetching MWAA logs: {e}")
        raise DiagnosticError(f"Failed to access MWAA: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error fetching MWAA logs: {e}")
        raise DiagnosticError(f"Failed to fetch task logs: {str(e)}")


def get_dag_run_status(dag_id: str, execution_date: str) -> Dict[str, Any]:
    """
    Get the status of all tasks in a DAG run to identify cascading failures.
    
    Args:
        dag_id: The DAG identifier
        execution_date: Execution timestamp
        
    Returns:
        dict: DAG run status including task states
    """
    try:
        # Get environment name from config
        env_name = os.environ.get('MWAA_ENVIRONMENT_NAME')
        if not env_name:
            raise DiagnosticError("MWAA_ENVIRONMENT_NAME not configured")
        
        # Create CLI token for API access
        token_response = mwaa_client.create_cli_token(Name=env_name)
        
        # Prepare Airflow CLI command
        cli_command = [
            'dags', 'state',
            dag_id,
            execution_date,
            '--json'
        ]
        
        # Execute CLI command
        response = requests.post(
            token_response['CliToken'],
            json={'cmd': cli_command},
            headers={'Authorization': f"Bearer {token_response['CliToken']}"},
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            
            # Parse task states
            task_states = {}
            for line in result.get('stdout', '').split('\n'):
                if line.strip():
                    try:
                        task_data = json.loads(line)
                        task_states.update(task_data)
                    except json.JSONDecodeError:
                        continue
                        
            return {
                'dag_id': dag_id,
                'execution_date': execution_date,
                'task_states': task_states,
                'summary': {
                    'total_tasks': len(task_states),
                    'failed': sum(1 for s in task_states.values() if s == 'failed'),
                    'success': sum(1 for s in task_states.values() if s == 'success'),
                    'running': sum(1 for s in task_states.values() if s == 'running'),
                    'upstream_failed': sum(1 for s in task_states.values() if s == 'upstream_failed')
                }
            }
        else:
            logger.warning(f"Failed to get DAG run status: {response.status_code}")
            return {
                'dag_id': dag_id,
                'execution_date': execution_date,
                'error': 'Unable to retrieve DAG run status'
            }
            
    except Exception as e:
        logger.error(f"Error getting DAG run status: {e}")
        return {
            'dag_id': dag_id,
            'execution_date': execution_date,
            'error': str(e)
        }


def query_redshift_audit_logs(
    dbt_model_name: Optional[str] = None,
    time_window_hours: int = 24
) -> List[Dict[str, Any]]:
    """
    Query Redshift audit logs for dbt model errors or general database errors.
    
    Args:
        dbt_model_name: Optional dbt model name to filter by
        time_window_hours: Hours to look back (default: 24)
        
    Returns:
        list: Audit log entries
    """
    try:
        # Get Redshift credentials
        secrets = secrets_client.get_secret_value(SecretId='de-agent/redshift')
        config = json.loads(secrets['SecretString'])
        
        # Construct query based on whether we have a model name
        if dbt_model_name:
            # Clean model name (remove schema prefix if present)
            model_name = dbt_model_name.split('.')[-1]
            
            query = f"""
            SELECT 
                event_timestamp,
                model_name,
                status,
                error_message,
                execution_time_seconds,
                rows_affected,
                database_name,
                schema_name,
                user_name
            FROM dbt_audit.run_results
            WHERE model_name = :model_name
                AND status IN ('error', 'fail')
                AND event_timestamp > DATEADD(hour, -{time_window_hours}, GETDATE())
            ORDER BY event_timestamp DESC
            LIMIT 10;
            """
            parameters = [{'name': 'model_name', 'value': model_name}]
        else:
            # General query for recent errors
            query = f"""
            SELECT 
                starttime AS event_timestamp,
                database AS database_name,
                username AS user_name,
                query_text,
                error_message,
                elapsed_time_seconds
            FROM stl_query_errors
            WHERE starttime > DATEADD(hour, -{time_window_hours}, GETDATE())
            ORDER BY starttime DESC
            LIMIT 20;
            """
            parameters = []
        
        # Execute query
        response = redshift_data_client.execute_statement(
            ClusterIdentifier=config['cluster_id'],
            Database=config['database'],
            SecretArn=config['secret_arn'],
            Sql=query,
            Parameters=parameters if parameters else None
        )
        
        statement_id = response['Id']
        
        # Wait for query completion (with timeout)
        max_wait = 30  # seconds
        wait_time = 0
        while wait_time < max_wait:
            desc_response = redshift_data_client.describe_statement(Id=statement_id)
            status = desc_response['Status']
            
            if status == 'FINISHED':
                break
            elif status in ['FAILED', 'ABORTED']:
                raise DiagnosticError(f"Query failed: {desc_response.get('Error', 'Unknown error')}")
                
            time.sleep(1)
            wait_time += 1
            
        # Get results
        result = redshift_data_client.get_statement_result(Id=statement_id)
        
        # Parse results into list of dicts
        columns = [col['label'] for col in result['ColumnMetadata']]
        records = []
        
        for row in result.get('Records', []):
            record = {}
            for i, col in enumerate(columns):
                value = list(row[i].values())[0] if row[i] else None
                record[col] = value
            records.append(record)
            
        return records
        
    except ClientError as e:
        logger.error(f"AWS API error querying Redshift: {e}")
        return [{'error': f"Failed to query Redshift: {str(e)}"}]
    except Exception as e:
        logger.error(f"Unexpected error querying Redshift: {e}")
        return [{'error': f"Failed to query audit logs: {str(e)}"}]


def get_cloudwatch_lambda_errors(
    function_name: str,
    time_window_minutes: int = 60
) -> List[str]:
    """
    Retrieve recent error logs from CloudWatch for a Lambda function.
    
    Args:
        function_name: Lambda function name
        time_window_minutes: Minutes to look back (default: 60)
        
    Returns:
        list: Error log messages
    """
    try:
        log_group = f"/aws/lambda/{function_name}"
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(minutes=time_window_minutes)
        
        # Use CloudWatch Insights for efficient querying
        query = """
        fields @timestamp, @message
        | filter @message like /ERROR/
            or @message like /Exception/
            or @message like /Failed/
        | sort @timestamp desc
        | limit 20
        """
        
        response = logs_client.start_query(
            logGroupName=log_group,
            startTime=int(start_time.timestamp()),
            endTime=int(end_time.timestamp()),
            queryString=query
        )
        
        query_id = response['queryId']
        
        # Wait for query completion
        max_wait = 10  # seconds
        wait_time = 0
        results = None
        
        while wait_time < max_wait:
            response = logs_client.get_query_results(queryId=query_id)
            status = response['status']
            
            if status == 'Complete':
                results = response['results']
                break
            elif status == 'Failed':
                raise DiagnosticError("CloudWatch Insights query failed")
                
            time.sleep(1)
            wait_time += 1
            
        if not results:
            return ["No error logs found in the specified time window"]
            
        # Extract messages
        error_messages = []
        for result in results:
            message = next(
                (field['value'] for field in result if field['field'] == '@message'),
                None
            )
            if message:
                # Truncate very long messages
                if len(message) > 500:
                    message = message[:500] + "... [truncated]"
                error_messages.append(message)
                
        return error_messages if error_messages else ["No error logs found"]
        
    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceNotFoundException':
            return [f"Log group not found for function: {function_name}"]
        logger.error(f"AWS API error getting CloudWatch logs: {e}")
        return [f"Failed to retrieve CloudWatch logs: {str(e)}"]
    except Exception as e:
        logger.error(f"Unexpected error getting CloudWatch logs: {e}")
        return [f"Failed to retrieve logs: {str(e)}"]


# Utility function for testing
if __name__ == "__main__":
    # Example usage
    import os
    
    # Test MWAA logs
    test_url = "https://my-env.us-east-1.airflow.amazonaws.com/log?dag_id=test&task_id=test&execution_date=2024-01-01"
    try:
        logs = get_mwaa_task_logs(test_url)
        print(f"MWAA Logs (first 500 chars): {logs[:500]}")
    except Exception as e:
        print(f"MWAA test failed: {e}")
    
    # Test Redshift query
    try:
        audit_logs = query_redshift_audit_logs("dim_providers")
        print(f"Redshift audit logs: {audit_logs[:2]}")
    except Exception as e:
        print(f"Redshift test failed: {e}")
    
    # Test CloudWatch logs
    try:
        cw_logs = get_cloudwatch_lambda_errors("my-function")
        print(f"CloudWatch errors: {cw_logs[:2]}")
    except Exception as e:
        print(f"CloudWatch test failed: {e}")