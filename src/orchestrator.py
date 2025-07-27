"""
Orchestration engine for coordinating diagnostic workflows.

This module manages the overall flow of failure diagnosis, from initial
message parsing through data collection to LLM analysis and response formatting.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timedelta

from .parser import ParsedFailure, MessageParser
from .tools import (
    get_mwaa_task_logs, query_redshift_audit_logs, get_cloudwatch_lambda_errors,
    get_redshift_recent_errors, check_mwaa_dag_state
)
from .prompt_engine import build_diagnostic_prompt

logger = logging.getLogger(__name__)

@dataclass
class DiagnosticContext:
    """Container for all diagnostic information gathered."""
    failure: ParsedFailure
    mwaa_logs: Optional[str] = None
    redshift_audit: Optional[List[Dict]] = None
    cloudwatch_errors: Optional[List[str]] = None
    dag_state: Optional[Dict] = None
    context_metadata: Dict = None
    
    def __post_init__(self):
        if self.context_metadata is None:
            self.context_metadata = {}

@dataclass
class DiagnosticResult:
    """Results of the diagnostic process."""
    context: DiagnosticContext
    analysis: Optional[str] = None
    confidence_score: float = 0.0
    processing_time_ms: int = 0
    services_called: List[str] = None
    errors_encountered: List[str] = None
    
    def __post_init__(self):
        if self.services_called is None:
            self.services_called = []
        if self.errors_encountered is None:
            self.errors_encountered = []

class DiagnosticOrchestrator:
    """
    Coordinates the entire diagnostic workflow.
    
    Manages parallel data collection from various AWS services,
    handles failures gracefully, and orchestrates LLM analysis.
    """
    
    def __init__(self, max_workers: int = 5, timeout_seconds: int = 240):
        """
        Initialize the orchestrator.
        
        Args:
            max_workers: Maximum number of concurrent workers for data collection
            timeout_seconds: Maximum time to spend on diagnostic collection
        """
        self.max_workers = max_workers
        self.timeout_seconds = timeout_seconds
        self.parser = MessageParser()
        
    async def diagnose_failure(self, slack_event: dict) -> Optional[DiagnosticResult]:
        """
        Main entry point for failure diagnosis.
        
        Args:
            slack_event: Slack event payload containing failure message
            
        Returns:
            DiagnosticResult with analysis and context, or None if parsing failed
        """
        start_time = datetime.utcnow()
        
        try:
            # Parse the incoming message
            failure = self.parser.parse_slack_event(slack_event)
            if not failure:
                logger.warning("Failed to parse Slack event for failure information")
                return None
            
            logger.info(f"Parsed failure for DAG: {failure.dag_id}, Task: {failure.task_id}")
            
            # Collect diagnostic context
            context = await self._collect_diagnostic_context(failure)
            
            # Generate LLM analysis
            analysis = await self._generate_analysis(context)
            
            # Calculate processing time
            processing_time = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            
            result = DiagnosticResult(
                context=context,
                analysis=analysis,
                processing_time_ms=processing_time,
                confidence_score=self._calculate_confidence_score(context)
            )
            
            logger.info(f"Diagnostic completed in {processing_time}ms for DAG {failure.dag_id}")
            return result
            
        except Exception as e:
            logger.error(f"Error in failure diagnosis: {e}", exc_info=True)
            return None
    
    async def _collect_diagnostic_context(self, failure: ParsedFailure) -> DiagnosticContext:
        """
        Collect diagnostic information from multiple sources in parallel.
        
        Args:
            failure: Parsed failure information
            
        Returns:
            DiagnosticContext with collected information
        """
        context = DiagnosticContext(failure=failure)
        
        # Define diagnostic tasks based on failure type and available information
        tasks = self._plan_diagnostic_tasks(failure)
        
        # Execute tasks in parallel with timeout
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all tasks
            future_to_task = {
                executor.submit(task['function'], *task['args']): task['name']
                for task in tasks
            }
            
            # Collect results with timeout
            completed_tasks = []
            for future in as_completed(future_to_task, timeout=self.timeout_seconds):
                task_name = future_to_task[future]
                try:
                    result = future.result(timeout=30)  # Individual task timeout
                    self._apply_diagnostic_result(context, task_name, result)
                    completed_tasks.append(task_name)
                    logger.debug(f"Completed diagnostic task: {task_name}")
                except Exception as e:
                    logger.warning(f"Diagnostic task {task_name} failed: {e}")
                    context.context_metadata[f"{task_name}_error"] = str(e)
        
        context.context_metadata['completed_tasks'] = completed_tasks
        context.context_metadata['total_tasks'] = len(tasks)
        
        return context
    
    def _plan_diagnostic_tasks(self, failure: ParsedFailure) -> List[Dict[str, Any]]:
        """
        Plan which diagnostic tasks to execute based on failure information.
        
        Args:
            failure: Parsed failure information
            
        Returns:
            List of task definitions
        """
        tasks = []
        
        # Always try to get DAG state
        tasks.append({
            'name': 'dag_state',
            'function': check_mwaa_dag_state,
            'args': (failure.dag_id,)
        })
        
        # Try to get MWAA logs if we have a log URL or task info
        if failure.log_url or failure.task_id:
            if failure.log_url:
                tasks.append({
                    'name': 'mwaa_logs',
                    'function': get_mwaa_task_logs,
                    'args': (failure.log_url,)
                })
            elif failure.task_id:
                # Try to construct log URL or get recent logs
                tasks.append({
                    'name': 'mwaa_logs',
                    'function': self._get_recent_task_logs,
                    'args': (failure.dag_id, failure.task_id, failure.execution_date)
                })
        
        # Query Redshift audit logs for SQL/DBT related errors
        if failure.error_type in ['sql', 'dbt'] or 'dbt' in failure.error_message.lower():
            # Extract potential model name from error message
            model_name = self._extract_model_name(failure.error_message)
            tasks.append({
                'name': 'redshift_audit',
                'function': query_redshift_audit_logs,
                'args': (model_name or failure.dag_id,)
            })
            
            # Also get recent Redshift errors
            tasks.append({
                'name': 'redshift_errors',
                'function': get_redshift_recent_errors,
                'args': (24,)  # Last 24 hours
            })
        
        # Get CloudWatch errors for connection/timeout issues
        if failure.error_type in ['timeout', 'connection', 'python']:
            tasks.append({
                'name': 'cloudwatch_errors',
                'function': get_cloudwatch_lambda_errors,
                'args': (failure.dag_id,)
            })
        
        return tasks
    
    def _apply_diagnostic_result(self, context: DiagnosticContext, 
                               task_name: str, result: Any) -> None:
        """Apply the result of a diagnostic task to the context."""
        if task_name == 'dag_state':
            context.dag_state = result
        elif task_name == 'mwaa_logs':
            context.mwaa_logs = result
        elif task_name == 'redshift_audit':
            context.redshift_audit = result
        elif task_name == 'redshift_errors':
            if not context.redshift_audit:
                context.redshift_audit = []
            if isinstance(result, list):
                context.redshift_audit.extend(result)
        elif task_name == 'cloudwatch_errors':
            context.cloudwatch_errors = result
    
    def _get_recent_task_logs(self, dag_id: str, task_id: str, 
                            execution_date: Optional[str] = None) -> Optional[str]:
        """Get recent task logs when no direct URL is available."""
        try:
            # This is a placeholder - in practice, you'd need to construct
            # the MWAA log URL or use an alternative method
            logger.debug(f"Getting recent logs for {dag_id}.{task_id}")
            return None  # Implement based on your MWAA setup
        except Exception as e:
            logger.warning(f"Failed to get recent task logs: {e}")
            return None
    
    def _extract_model_name(self, error_message: str) -> Optional[str]:
        """Extract DBT model name from error message."""
        import re
        
        # Common patterns for DBT model names in error messages
        patterns = [
            r'model\s+["`\']*([a-zA-Z_][a-zA-Z0-9_]*)["`\']*',
            r'relation\s+["`\']*([a-zA-Z_][a-zA-Z0-9_\.]*)["`\']*',
            r'table\s+["`\']*([a-zA-Z_][a-zA-Z0-9_\.]*)["`\']*'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, error_message, re.IGNORECASE)
            if match:
                return match.group(1)
        
        return None
    
    async def _generate_analysis(self, context: DiagnosticContext) -> Optional[str]:
        """
        Generate LLM-powered analysis of the diagnostic context.
        
        Args:
            context: Collected diagnostic information
            
        Returns:
            Analysis text or None if generation failed
        """
        try:
            # Build the diagnostic prompt
            prompt = build_diagnostic_prompt(
                failure=context.failure,
                mwaa_logs=context.mwaa_logs,
                redshift_audit=context.redshift_audit,
                cloudwatch_errors=context.cloudwatch_errors,
                dag_state=context.dag_state
            )
            
            logger.info("Generated diagnostic prompt, calling LLM...")

            analysis = await self._call_llm(prompt)
            
            return analysis
            
        except Exception as e:
            logger.error(f"Failed to generate analysis: {e}")
            return None
    
    async def _call_llm(self, prompt: str) -> str:
        """
        Call the LLM API for analysis generation.
        """
        import os
        import google.generativeai as genai

        def _invoke() -> str:
            genai.configure(api_key=os.environ.get("GEMINI_API_KEY", ""))
            model = genai.GenerativeModel("gemini-pro")
            response = model.generate_content(
                prompt,
                generation_config={
                    "temperature": 0.7,
                    "top_p": 0.9,
                    "top_k": 40,
                    "max_output_tokens": 2000,
                },
                safety_settings=[
                    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
                ],
            )
            return response.text

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _invoke)
    
    def _calculate_confidence_score(self, context: DiagnosticContext) -> float:
        """
        Calculate a confidence score based on available diagnostic data.
        
        Args:
            context: Diagnostic context
            
        Returns:
            Confidence score between 0.0 and 1.0
        """
        score = 0.0
        max_score = 0.0
        
        # Base score for having parsed failure info
        max_score += 0.2
        if context.failure.dag_id != "unknown_dag":
            score += 0.2
        
        # Score for MWAA logs
        max_score += 0.3
        if context.mwaa_logs:
            score += 0.3
        elif context.dag_state:
            score += 0.15  # Partial credit for DAG state
        
        # Score for Redshift data
        max_score += 0.2
        if context.redshift_audit:
            score += 0.2
        
        # Score for CloudWatch data
        max_score += 0.2
        if context.cloudwatch_errors:
            score += 0.2
        
        # Score for successful task completion
        max_score += 0.1
        completed_tasks = context.context_metadata.get('completed_tasks', [])
        total_tasks = context.context_metadata.get('total_tasks', 1)
        if total_tasks > 0:
            completion_ratio = len(completed_tasks) / total_tasks
            score += 0.1 * completion_ratio
        
        return min(score / max_score, 1.0) if max_score > 0 else 0.0

# Factory function
def create_orchestrator(max_workers: int = 5, timeout_seconds: int = 240) -> DiagnosticOrchestrator:
    """Create a DiagnosticOrchestrator instance."""
    return DiagnosticOrchestrator(max_workers=max_workers, timeout_seconds=timeout_seconds)

# Convenience function for backward compatibility
async def orchestrate_diagnosis(slack_event: dict) -> Optional[DiagnosticResult]:
    """Orchestrate a complete failure diagnosis."""
    orchestrator = create_orchestrator()
    return await orchestrator.diagnose_failure(slack_event)
