#!/usr/bin/env python3
"""
Main Lambda Handler for DE-Agent

This module orchestrates the diagnostic process: parsing Slack messages,
gathering diagnostic data, invoking the LLM, and posting responses.
"""

import os
import re
import json
import time
import logging
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime

import boto3
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
import google.generativeai as genai

from tools import (
    get_mwaa_task_logs,
    get_dag_run_status,
    query_redshift_audit_logs,
    get_cloudwatch_lambda_errors,
    DiagnosticError
)
from runtime_prompt import get_diagnostic_prompt

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize AWS clients
secrets_client = boto3.client('secretsmanager')

# Initialize metrics client for monitoring
cloudwatch = boto3.client('cloudwatch')


class MessageParser:
    """Parse Airflow failure messages to extract structured data."""
    
    # Regex patterns for different error types
    PATTERNS = {
        'timeout': re.compile(r'AirflowSensorTimeout.*?run duration of ([\d.]+) seconds.*?timeout of ([\d.]+)'),
        'dbt_error': re.compile(r'CosmosDbtRunError.*?Database Error in model (\w+)'),
        'connection': re.compile(r'(Connection.*?failed|could not connect|connection refused)', re.I),
        'permission': re.compile(r'(permission denied|access denied|unauthorized)', re.I),
        'syntax': re.compile(r'(syntax error|SyntaxError|invalid syntax)', re.I),
        'resource': re.compile(r'(out of memory|disk full|no space left|resource exhausted)', re.I)
    }
    
    @classmethod
    def parse(cls, message: str) -> Dict[str, Any]:
        """Parse message and return structured data with error classification."""
        result = {
            'error_type': 'unknown',
            'details': {},
            'keywords': []
        }
        
        # Check each pattern
        for error_type, pattern in cls.PATTERNS.items():
            match = pattern.search(message)
            if match:
                result['error_type'] = error_type
                result['details'] = {f'group_{i}': g for i, g in enumerate(match.groups(), 1)}
                break
        
        # Extract keywords for better context
        keywords = []
        if 'timeout' in message.lower():
            keywords.append('timeout')
        if 'dbt' in message.lower():
            keywords.append('dbt')
        if 'database' in message.lower():
            keywords.append('database')
        if 'connection' in message.lower():
            keywords.append('connection')
            
        result['keywords'] = keywords
        return result


class DiagnosticOrchestrator:
    """Orchestrate the diagnostic process across multiple data sources."""
    
    def __init__(self):
        self.metrics = []
        
    def add_metric(self, name: str, value: float, unit: str = 'Count'):
        """Add a metric for CloudWatch reporting."""
        self.metrics.append({
            'MetricName': name,
            'Value': value,
            'Unit': unit,
            'Timestamp': datetime.utcnow()
        })
    
    def gather_diagnostics(self, parsed_data: Dict[str, Any]) -> Dict[str, Any]:
        """Gather diagnostic data from all relevant sources."""
        start_time = time.time()
        diagnostics = {
            'mwaa_logs': None,
            'dag_status': None,
            'redshift_audit': None,
            'cloudwatch_errors': None,
            'errors': []
        }
        
        # 1. Always try to get MWAA task logs
        try:
            logger.info("Fetching MWAA task logs...")
            diagnostics['mwaa_logs'] = get_mwaa_task_logs(parsed_data['log_url'])
            self.add_metric('MWAALogsFetched', 1)
        except DiagnosticError as e:
            logger.error(f"Failed to get MWAA logs: {e}")
            diagnostics['errors'].append(f"MWAA logs: {str(e)}")
            self.add_metric('MWAALogsFailed', 1)
        
        # 2. Get DAG run status to check for cascading failures
        try:
            logger.info("Checking DAG run status...")
            diagnostics['dag_status'] = get_dag_run_status(
                parsed_data['dag_id'],
                parsed_data['execution_time']
            )
            self.add_metric('DAGStatusFetched', 1)
        except Exception as e:
            logger.error(f"Failed to get DAG status: {e}")
            diagnostics['errors'].append(f"DAG status: {str(e)}")
        
        # 3. For DBT errors, query Redshift audit logs
        if 'dbt' in parsed_data['exception'].lower():
            try:
                logger.info("Querying Redshift audit logs for DBT errors...")
                # Extract model name if available
                model_match = re.search(r'model (\w+)', parsed_data['exception'])
                model_name = model_match.group(1) if model_match else None
                
                diagnostics['redshift_audit'] = query_redshift_audit_logs(
                    dbt_model_name=model_name
                )
                self.add_metric('RedshiftAuditFetched', 1)
            except Exception as e:
                logger.error(f"Failed to query Redshift: {e}")
                diagnostics['errors'].append(f"Redshift audit: {str(e)}")
        
        # 4. Check for related Lambda errors if applicable
        if 'lambda' in parsed_data['task_id'].lower():
            try:
                logger.info("Checking CloudWatch for Lambda errors...")
                # Extract function name from task ID
                function_name = parsed_data['task_id'].split('.')[-1]
                diagnostics['cloudwatch_errors'] = get_cloudwatch_lambda_errors(
                    function_name
                )
                self.add_metric('CloudWatchLogsFetched', 1)
            except Exception as e:
                logger.error(f"Failed to get CloudWatch logs: {e}")
                diagnostics['errors'].append(f"CloudWatch: {str(e)}")
        
        # Record diagnostic time
        elapsed_time = time.time() - start_time
        self.add_metric('DiagnosticTime', elapsed_time * 1000, 'Milliseconds')
        logger.info(f"Diagnostics gathered in {elapsed_time:.2f} seconds")
        
        return diagnostics
    
    def publish_metrics(self):
        """Publish collected metrics to CloudWatch."""
        if self.metrics:
            try:
                cloudwatch.put_metric_data(
                    Namespace='DE-Agent',
                    MetricData=self.metrics
                )
            except Exception as e:
                logger.error(f"Failed to publish metrics: {e}")


def get_credentials() -> Tuple[str, str]:
    """Retrieve Slack and Gemini credentials from Secrets Manager."""
    try:
        # Get Slack credentials
        slack_response = secrets_client.get_secret_value(SecretId='de-agent/slack')
        slack_creds = json.loads(slack_response['SecretString'])
        
        # Get Gemini credentials
        gemini_response = secrets_client.get_secret_value(SecretId='de-agent/gemini')
        gemini_creds = json.loads(gemini_response['SecretString'])
        
        return slack_creds['bot_token'], gemini_creds['api_key']
    except Exception as e:
        logger.error(f"Failed to retrieve credentials: {e}")
        raise


def invoke_llm(context: Dict[str, Any], api_key: str) -> str:
    """
    Invoke Gemini to analyze the diagnostic data.
    
    Args:
        context: All gathered diagnostic information
        api_key: Gemini API key
        
    Returns:
        str: LLM response with root cause analysis
    """
    try:
        # Configure Gemini
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-pro')
        
        # Get the prompt template and format with context
        prompt = get_diagnostic_prompt(context)
        
        # Generate response with safety settings
        response = model.generate_content(
            prompt,
            generation_config={
                'temperature': 0.7,
                'top_p': 0.9,
                'top_k': 40,
                'max_output_tokens': 2000,
            },
            safety_settings=[
                {
                    "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                    "threshold": "BLOCK_NONE"
                }
            ]
        )
        
        return response.text
        
    except Exception as e:
        logger.error(f"LLM invocation failed: {e}")
        # Return a fallback response
        return (
            "🤖 **Diagnostic Analysis**\n\n"
            "I encountered an error while analyzing the failure. "
            "Here's what I was able to gather:\n\n"
            f"**Error Type**: {context.get('error_type', 'Unknown')}\n"
            f"**DAG**: {context.get('dag_id', 'Unknown')}\n"
            f"**Task**: {context.get('task_id', 'Unknown')}\n\n"
            "Please check the logs manually for more details."
        )


def post_to_slack(client: WebClient, channel: str, thread_ts: str, message: str) -> bool:
    """
    Post the diagnostic response to Slack.
    
    Args:
        client: Slack WebClient
        channel: Channel ID
        thread_ts: Thread timestamp to reply to
        message: Formatted message to post
        
    Returns:
        bool: Success status
    """
    try:
        response = client.chat_postMessage(
            channel=channel,
            thread_ts=thread_ts,
            text=message,
            mrkdwn=True
        )
        logger.info(f"Posted response to Slack: {response['ts']}")
        return True
    except SlackApiError as e:
        logger.error(f"Slack API error: {e.response['error']}")
        return False
    except Exception as e:
        logger.error(f"Failed to post to Slack: {e}")
        return False


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Main Lambda handler function.
    
    Args:
        event: Lambda event containing Slack message data
        context: Lambda context
        
    Returns:
        dict: Response status
    """
    start_time = time.time()
    logger.info(f"Processing diagnostic request: {event.get('message_ts', 'unknown')}")
    
    try:
        # Extract data from event
        channel = event['channel']
        thread_ts = event['thread_ts']
        parsed_data = event['parsed_data']
        raw_message = event['raw_message']
        
        # Get credentials
        slack_token, gemini_api_key = get_credentials()
        slack_client = WebClient(token=slack_token)
        
        # Parse the message for error classification
        parser_result = MessageParser.parse(raw_message)
        
        # Initialize orchestrator
        orchestrator = DiagnosticOrchestrator()
        
        # Gather diagnostics from all sources
        diagnostics = orchestrator.gather_diagnostics(parsed_data)
        
        # Prepare context for LLM
        llm_context = {
            **parsed_data,
            **parser_result,
            'diagnostics': diagnostics,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        # Get LLM analysis
        logger.info("Invoking LLM for analysis...")
        analysis = invoke_llm(llm_context, gemini_api_key)
        
        # Post response to Slack
        success = post_to_slack(slack_client, channel, thread_ts, analysis)
        
        # Update reaction based on success
        try:
            slack_client.reactions_add(
                channel=channel,
                timestamp=event['message_ts'],
                name='white_check_mark' if success else 'x'
            )
        except:
            pass  # Don't fail if reaction fails
        
        # Publish metrics
        orchestrator.add_metric('ProcessingTime', (time.time() - start_time) * 1000, 'Milliseconds')
        orchestrator.add_metric('Success' if success else 'Failure', 1)
        orchestrator.publish_metrics()
        
        return {
            'statusCode': 200 if success else 500,
            'body': json.dumps({
                'success': success,
                'processing_time': time.time() - start_time,
                'error_type': parser_result['error_type']
            })
        }
        
    except Exception as e:
        logger.error(f"Lambda handler error: {e}", exc_info=True)
        
        # Try to post an error message to Slack
        try:
            if 'channel' in event and 'thread_ts' in event:
                slack_token, _ = get_credentials()
                slack_client = WebClient(token=slack_token)
                post_to_slack(
                    slack_client,
                    event['channel'],
                    event['thread_ts'],
                    "❌ I encountered an error while diagnosing this failure. "
                    "Please check the logs manually or contact the platform team."
                )
        except:
            pass
        
        return {
            'statusCode': 500,
            'body': json.dumps({
                'success': False,
                'error': str(e)
            })
        }


# For local testing
if __name__ == "__main__":
    # Test event
    test_event = {
        'channel': 'C1234567890',
        'thread_ts': '1234567890.123456',
        'message_ts': '1234567890.123456',
        'raw_message': '❌ Task has failed....',
        'parsed_data': {
            'dag_id': 'test_dag',
            'task_id': 'test_task',
            'execution_time': '2024-01-01T00:00:00',
            'exception': 'Test exception',
            'log_url': 'https://test.com/logs'
        }
    }
    
    result = lambda_handler(test_event, None)
    print(json.dumps(result, indent=2))