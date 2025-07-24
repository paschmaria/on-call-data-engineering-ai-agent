#!/usr/bin/env python3
"""
Slack Listener for DE-Agent

This module sets up a Slack Bolt application that listens for Apache Airflow
failure notifications and triggers diagnostic analysis.
"""

import os
import re
import json
import logging
from typing import Dict, Optional

import boto3
from slack_bolt import App
from slack_bolt.adapter.aws_lambda import SlackRequestHandler

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize AWS clients
secrets_client = boto3.client('secretsmanager')
lambda_client = boto3.client('lambda')


def get_slack_credentials() -> Dict[str, str]:
    """Retrieve Slack credentials from AWS Secrets Manager."""
    try:
        response = secrets_client.get_secret_value(SecretId='de-agent/slack')
        return json.loads(response['SecretString'])
    except Exception as e:
        logger.error(f"Failed to retrieve Slack credentials: {e}")
        raise


# Initialize Slack app with credentials
credentials = get_slack_credentials()
app = App(
    token=credentials['bot_token'],
    signing_secret=credentials['signing_secret'],
    process_before_response=True  # Enable async processing
)


# Regex pattern to match Airflow failure messages
AIRFLOW_FAILURE_PATTERN = re.compile(
    r"❌ Task has failed\..*?DAG: (.*?)\n.*?Task: (.*?)\n.*?Execution Time: (.*?)\n.*?Exception: (.*?)\n.*?Log URL: \[(.*?)\]",
    re.DOTALL
)


@app.event("message")
def handle_message_events(event: Dict, say, client) -> None:
    """
    Handle incoming messages and filter for Airflow failure notifications.
    
    Args:
        event: Slack event data
        say: Function to send messages to the channel
        client: Slack WebClient instance
    """
    try:
        # Skip messages from the bot itself
        if event.get('bot_id'):
            return
            
        # Check if message is from Apache Airflow app
        if event.get('username') != 'Apache Airflow':
            return
            
        message_text = event.get('text', '')
        
        # Check for failure indicator
        if '❌ Task has failed' not in message_text:
            return
            
        logger.info(f"Processing Airflow failure notification")
        
        # Extract failure details
        match = AIRFLOW_FAILURE_PATTERN.search(message_text)
        if not match:
            logger.warning("Failed to parse Airflow failure message")
            return
            
        # Prepare diagnostic request
        diagnostic_request = {
            'channel': event['channel'],
            'thread_ts': event.get('thread_ts', event['ts']),
            'message_ts': event['ts'],
            'raw_message': message_text,
            'parsed_data': {
                'dag_id': match.group(1).strip(),
                'task_id': match.group(2).strip(),
                'execution_time': match.group(3).strip(),
                'exception': match.group(4).strip(),
                'log_url': match.group(5).strip()
            }
        }
        
        # Acknowledge receipt immediately
        client.reactions_add(
            channel=event['channel'],
            timestamp=event['ts'],
            name='eyes'  # 👀 emoji to show we're looking at it
        )
        
        # Invoke Lambda function for diagnostics
        invoke_diagnostic_lambda(diagnostic_request)
        
    except Exception as e:
        logger.error(f"Error handling message: {e}", exc_info=True)


def invoke_diagnostic_lambda(request_data: Dict) -> None:
    """
    Invoke the diagnostic Lambda function asynchronously.
    
    Args:
        request_data: Diagnostic request payload
    """
    try:
        response = lambda_client.invoke(
            FunctionName=os.environ.get('DIAGNOSTIC_LAMBDA_NAME', 'de-agent-diagnostic'),
            InvocationType='Event',  # Async invocation
            Payload=json.dumps(request_data)
        )
        
        logger.info(f"Diagnostic Lambda invoked: {response['StatusCode']}")
        
    except Exception as e:
        logger.error(f"Failed to invoke diagnostic Lambda: {e}")
        # Consider sending a fallback message to Slack here


@app.event("app_mention")
def handle_mention(event: Dict, say) -> None:
    """
    Handle direct mentions of the bot.
    
    Args:
        event: Slack event data
        say: Function to send messages
    """
    user = event['user']
    text = event['text']
    
    # Simple help response
    if 'help' in text.lower():
        say(
            text=f"Hi <@{user}>! I'm DE-Bot, your on-call data engineering assistant. 🤖\n\n"
                 "I automatically monitor this channel for Apache Airflow failures and provide diagnostic analysis.\n\n"
                 "**What I do:**\n"
                 "• Parse Airflow failure notifications\n"
                 "• Gather logs from MWAA, Redshift, and CloudWatch\n"
                 "• Analyze root causes using AI\n"
                 "• Post detailed diagnostics in threads\n\n"
                 "Just let me watch the channel and I'll help diagnose any failures that occur!",
            thread_ts=event.get('thread_ts', event['ts'])
        )
    else:
        say(
            text=f"Hi <@{user}>! I'm here to help diagnose Airflow failures. "
                 "Type `@DE-Bot help` for more information.",
            thread_ts=event.get('thread_ts', event['ts'])
        )


# Lambda handler for AWS deployment
def lambda_handler(event: Dict, context) -> Dict:
    """
    AWS Lambda handler for Slack events.
    
    Args:
        event: Lambda event data
        context: Lambda context
        
    Returns:
        Response dictionary
    """
    slack_handler = SlackRequestHandler(app=app)
    return slack_handler.handle(event, context)


# Local development server
if __name__ == "__main__":
    # For local testing, you'll need to set these environment variables
    app.start(port=int(os.environ.get("PORT", 3000)))
    logger.info("DE-Bot Slack listener started on port 3000")