"""
Message parsing logic for Slack events and Airflow failure notifications.

This module handles the extraction and parsing of DAG failures, task errors,
and other relevant information from Slack messages and event payloads.
"""

import re
import logging
from typing import Dict, Optional, List, Tuple
from datetime import datetime
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class ParsedFailure:
    """Structured representation of a parsed Airflow failure."""
    dag_id: str
    task_id: Optional[str]
    execution_date: Optional[str]
    error_type: str
    error_message: str
    log_url: Optional[str]
    channel: str
    thread_ts: Optional[str]
    original_text: str

class MessageParser:
    """Parser for Slack messages containing Airflow failure notifications."""
    
    # Regex patterns for different failure types
    AIRFLOW_PATTERNS = {
        'dag_failure': r'DAG\s+([a-zA-Z_][a-zA-Z0-9_]*)\s+(?:failed|error)',
        'task_failure': r'Task\s+([a-zA-Z_][a-zA-Z0-9_\.]*)\s+in\s+DAG\s+([a-zA-Z_][a-zA-Z0-9_]*)',
        'execution_date': r'(?:execution_date|run_id):\s*([0-9T:\-\+Z]+)',
        'log_url': r'(https?://[^\s]+(?:log|airflow)[^\s]*)',
        'exception': r'(?:Exception|Error):\s*([^\n]+)',
    }
    
    ERROR_TYPE_PATTERNS = {
        'timeout': r'(?i)timeout|timed?\s*out',
        'connection': r'(?i)connection|network|unreachable',
        'memory': r'(?i)memory|oom|out\s*of\s*memory',
        'permission': r'(?i)permission|access\s*denied|unauthorized',
        'sql': r'(?i)sql|query|database|relation.*does.*not.*exist',
        'dbt': r'(?i)dbt|compilation|model.*failed',
        'python': r'(?i)python|import|module|syntax',
        'resource': r'(?i)disk|space|resource|quota',
    }
    
    def __init__(self):
        """Initialize the message parser."""
        self.compiled_patterns = {
            name: re.compile(pattern, re.IGNORECASE | re.MULTILINE)
            for name, pattern in self.AIRFLOW_PATTERNS.items()
        }
        self.error_patterns = {
            name: re.compile(pattern, re.IGNORECASE)
            for name, pattern in self.ERROR_TYPE_PATTERNS.items()
        }
    
    def parse_slack_event(self, event: dict) -> Optional[ParsedFailure]:
        """
        Parse a Slack event for Airflow failure information.
        
        Args:
            event: Slack event payload
            
        Returns:
            ParsedFailure object if parsing successful, None otherwise
        """
        try:
            # Extract message details
            if 'event' not in event:
                logger.debug("No event field in payload")
                return None
                
            message_event = event['event']
            text = message_event.get('text', '')
            channel = message_event.get('channel', '')
            thread_ts = message_event.get('thread_ts')
            
            # Skip bot messages or empty text
            if message_event.get('bot_id') or not text:
                logger.debug("Skipping bot message or empty text")
                return None
            
            # Check if this looks like an Airflow failure
            if not self._is_airflow_failure(text):
                logger.debug("Message doesn't appear to be an Airflow failure")
                return None
            
            return self._parse_failure_details(text, channel, thread_ts)
            
        except Exception as e:
            logger.error(f"Error parsing Slack event: {e}")
            return None
    
    def parse_failure_message(self, text: str, channel: str = "", 
                            thread_ts: str = None) -> Optional[ParsedFailure]:
        """
        Parse a failure message text directly.
        
        Args:
            text: Message text to parse
            channel: Slack channel ID
            thread_ts: Thread timestamp if applicable
            
        Returns:
            ParsedFailure object if parsing successful, None otherwise
        """
        if not self._is_airflow_failure(text):
            return None
            
        return self._parse_failure_details(text, channel, thread_ts)
    
    def _is_airflow_failure(self, text: str) -> bool:
        """Check if the message appears to be an Airflow failure notification."""
        failure_indicators = [
            'dag', 'task', 'airflow', 'failed', 'error', 'exception',
            'workflow', 'pipeline', 'etl'
        ]
        
        text_lower = text.lower()
        return any(indicator in text_lower for indicator in failure_indicators)
    
    def _parse_failure_details(self, text: str, channel: str, 
                             thread_ts: Optional[str]) -> ParsedFailure:
        """Parse detailed failure information from message text."""
        
        # Extract DAG ID
        dag_id = self._extract_dag_id(text)
        
        # Extract task ID
        task_id = self._extract_task_id(text)
        
        # Extract execution date
        execution_date = self._extract_execution_date(text)
        
        # Extract log URL
        log_url = self._extract_log_url(text)
        
        # Extract error message
        error_message = self._extract_error_message(text)
        
        # Classify error type
        error_type = self._classify_error_type(text)
        
        return ParsedFailure(
            dag_id=dag_id,
            task_id=task_id,
            execution_date=execution_date,
            error_type=error_type,
            error_message=error_message,
            log_url=log_url,
            channel=channel,
            thread_ts=thread_ts,
            original_text=text
        )
    
    def _extract_dag_id(self, text: str) -> str:
        """Extract DAG ID from the message text."""
        # Try specific DAG patterns first
        match = self.compiled_patterns['dag_failure'].search(text)
        if match:
            return match.group(1)
        
        # Try task failure pattern (includes DAG)
        match = self.compiled_patterns['task_failure'].search(text)
        if match:
            return match.group(2)
        
        # Fallback: look for any identifier after "dag"
        dag_pattern = re.compile(r'dag[:\s]+([a-zA-Z_][a-zA-Z0-9_]*)', re.IGNORECASE)
        match = dag_pattern.search(text)
        if match:
            return match.group(1)
        
        return "unknown_dag"
    
    def _extract_task_id(self, text: str) -> Optional[str]:
        """Extract task ID from the message text."""
        match = self.compiled_patterns['task_failure'].search(text)
        if match:
            return match.group(1)
        
        # Fallback: look for task patterns
        task_pattern = re.compile(r'task[:\s]+([a-zA-Z_][a-zA-Z0-9_\.]*)', re.IGNORECASE)
        match = task_pattern.search(text)
        if match:
            return match.group(1)
        
        return None
    
    def _extract_execution_date(self, text: str) -> Optional[str]:
        """Extract execution date from the message text."""
        match = self.compiled_patterns['execution_date'].search(text)
        if match:
            return match.group(1)
        
        # Try to find any ISO date format
        date_pattern = re.compile(r'20\d{2}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2}')
        match = date_pattern.search(text)
        if match:
            return match.group(0)
        
        return None
    
    def _extract_log_url(self, text: str) -> Optional[str]:
        """Extract log URL from the message text."""
        match = self.compiled_patterns['log_url'].search(text)
        if match:
            return match.group(1)
        
        return None
    
    def _extract_error_message(self, text: str) -> str:
        """Extract the error message from the text."""
        # Try to find exception messages
        match = self.compiled_patterns['exception'].search(text)
        if match:
            return match.group(1).strip()
        
        # Look for lines containing "error" or "failed"
        lines = text.split('\n')
        for line in lines:
            if any(word in line.lower() for word in ['error', 'failed', 'exception']):
                return line.strip()
        
        # Fallback: return first few words of the message
        words = text.split()[:20]
        return ' '.join(words) + ('...' if len(text.split()) > 20 else '')
    
    def _classify_error_type(self, text: str) -> str:
        """Classify the type of error based on message content."""
        for error_type, pattern in self.error_patterns.items():
            if pattern.search(text):
                return error_type
        
        return "general"
    
    def extract_context_clues(self, text: str) -> Dict[str, List[str]]:
        """
        Extract additional context clues that might help with diagnosis.
        
        Args:
            text: Message text to analyze
            
        Returns:
            Dictionary with different types of context clues
        """
        clues = {
            'table_names': [],
            'model_names': [],
            'sql_keywords': [],
            'file_paths': [],
            'timestamps': [],
        }
        
        # Extract table/model names (common patterns)
        table_pattern = re.compile(r'\b(?:table|model|view)\s+["`\']*([a-zA-Z_][a-zA-Z0-9_\.]*)["`\']*', re.IGNORECASE)
        clues['table_names'] = [match.group(1) for match in table_pattern.finditer(text)]
        
        # Extract dbt model names
        dbt_pattern = re.compile(r'\bmodel\s+["`\']*([a-zA-Z_][a-zA-Z0-9_]*)["`\']*', re.IGNORECASE)
        clues['model_names'] = [match.group(1) for match in dbt_pattern.finditer(text)]
        
        # Extract SQL keywords that might indicate the issue
        sql_keywords = ['select', 'insert', 'update', 'delete', 'create', 'drop', 'alter', 'truncate']
        for keyword in sql_keywords:
            if re.search(rf'\b{keyword}\b', text, re.IGNORECASE):
                clues['sql_keywords'].append(keyword.upper())
        
        # Extract file paths
        path_pattern = re.compile(r'[/\\][\w/\\.-]+\.\w+')
        clues['file_paths'] = [match.group(0) for match in path_pattern.finditer(text)]
        
        # Extract timestamps
        timestamp_pattern = re.compile(r'\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[+-]\d{2}:?\d{2}|Z)?')
        clues['timestamps'] = [match.group(0) for match in timestamp_pattern.finditer(text)]
        
        return clues

def create_parser() -> MessageParser:
    """Factory function to create a MessageParser instance."""
    return MessageParser()

# Utility functions for backward compatibility
def parse_slack_message(event: dict) -> Optional[ParsedFailure]:
    """Parse a Slack event for failure information."""
    parser = create_parser()
    return parser.parse_slack_event(event)

def extract_dag_info(text: str) -> Tuple[str, Optional[str]]:
    """Extract DAG and task information from text."""
    parser = create_parser()
    failure = parser.parse_failure_message(text)
    if failure:
        return failure.dag_id, failure.task_id
    return "unknown", None
