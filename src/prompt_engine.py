"""
Prompt engineering module for LLM interactions.

This module manages the construction of prompts for different types of
diagnostic scenarios and handles LLM API interactions with proper
error handling and response formatting.
"""

import json
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from dataclasses import dataclass

import google.generativeai as genai

logger = logging.getLogger(__name__)

@dataclass
class PromptTemplate:
    """Template for constructing diagnostic prompts."""
    system_prompt: str
    context_sections: List[str]
    output_format: str
    max_tokens: int = 2000

class PromptEngine:
    """
    Manages LLM interactions and prompt engineering for diagnostic analysis.
    
    Handles different failure types with specialized prompts and manages
    token limits and response formatting.
    """
    
    SYSTEM_PROMPTS = {
        'general': """You are DE-Bot, an expert data engineering AI assistant specializing in Apache Airflow failure diagnosis. 
You have deep knowledge of:
- Apache Airflow architecture and common failure patterns
- AWS services (MWAA, Redshift, Lambda, CloudWatch)
- DBT models and SQL debugging
- Python error analysis
- Infrastructure and connectivity issues

Your role is to analyze failure information from multiple sources and provide:
1. Root cause analysis with confidence level
2. Specific remediation steps
3. Prevention recommendations
4. Escalation guidance when needed

Be concise but thorough. Use technical language appropriate for data engineers.""",

        'sql': """You are DE-Bot, an expert SQL and data warehouse troubleshooting assistant.
Focus on:
- SQL syntax and logic errors
- Database connection and permission issues
- Table/column existence problems
- Data quality and integrity issues
- Performance and timeout problems
- DBT compilation and execution errors

Provide specific SQL debugging steps and query optimization recommendations.""",

        'timeout': """You are DE-Bot, specializing in performance and timeout issue diagnosis.
Focus on:
- Resource allocation problems
- Query performance issues
- Network connectivity problems
- Service limits and throttling
- Memory and CPU constraints
- Concurrent execution conflicts

Provide performance optimization and resource scaling recommendations.""",

        'dbt': """You are DE-Bot, an expert in DBT (data build tool) troubleshooting.
Focus on:
- DBT model compilation errors
- Dependency resolution issues
- Macro and jinja templating problems
- Source and seed issues
- Test failures and data quality
- Incremental model problems

Provide DBT-specific debugging steps and best practices."""
    }
    
    OUTPUT_FORMAT = """
Respond in the following structured format:

## 🔍 Root Cause Analysis
[Brief summary of the most likely cause]

## 📊 Confidence Level
[High/Medium/Low] - [Justification]

## 🛠️ Immediate Actions
1. [First step to take]
2. [Second step to take]
3. [Additional steps...]

## 🔧 Detailed Investigation
[Specific commands, queries, or checks to perform]

## 🚀 Prevention Recommendations
[How to prevent this issue in the future]

## ⚠️ Escalation Triggers
[When to escalate and to whom]
"""

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the prompt engine.
        
        Args:
            api_key: Google Gemini API key (if not set in environment)
        """
        if api_key:
            genai.configure(api_key=api_key)
        
        self.model = genai.GenerativeModel('gemini-pro')
        self.templates = self._build_templates()
    
    def _build_templates(self) -> Dict[str, PromptTemplate]:
        """Build prompt templates for different failure types."""
        templates = {}
        
        for failure_type, system_prompt in self.SYSTEM_PROMPTS.items():
            templates[failure_type] = PromptTemplate(
                system_prompt=system_prompt,
                context_sections=[
                    "failure_details",
                    "logs_and_errors",
                    "system_state",
                    "historical_context"
                ],
                output_format=self.OUTPUT_FORMAT,
                max_tokens=2000
            )
        
        return templates
    
    async def generate_analysis(self, 
                              failure_type: str,
                              failure_details: Dict[str, Any],
                              diagnostic_context: Dict[str, Any]) -> Optional[str]:
        """
        Generate diagnostic analysis using LLM.
        
        Args:
            failure_type: Type of failure (sql, timeout, dbt, etc.)
            failure_details: Parsed failure information
            diagnostic_context: Collected diagnostic data
            
        Returns:
            Formatted analysis or None if generation failed
        """
        try:
            # Select appropriate template
            template = self.templates.get(failure_type, self.templates['general'])
            
            # Build the prompt
            prompt = self._build_prompt(template, failure_details, diagnostic_context)
            
            # Call LLM API
            response = await self._call_gemini(prompt, template.max_tokens)
            
            # Format and validate response
            formatted_response = self._format_response(response)
            
            logger.info(f"Generated analysis for failure type: {failure_type}")
            return formatted_response
            
        except Exception as e:
            logger.error(f"Failed to generate analysis: {e}")
            return self._generate_fallback_response(failure_details)
    
    def _build_prompt(self, 
                     template: PromptTemplate,
                     failure_details: Dict[str, Any],
                     diagnostic_context: Dict[str, Any]) -> str:
        """Build the complete prompt from template and context."""
        
        prompt_parts = [
            template.system_prompt,
            "\n\n## Context Information\n"
        ]
        
        # Add failure details section
        prompt_parts.append("### Failure Details")
        prompt_parts.append(self._format_failure_details(failure_details))
        
        # Add diagnostic context sections
        if diagnostic_context.get('mwaa_logs'):
            prompt_parts.append("### MWAA Task Logs")
            prompt_parts.append(f"```\n{diagnostic_context['mwaa_logs'][:2000]}\n```")
        
        if diagnostic_context.get('redshift_audit'):
            prompt_parts.append("### Redshift Audit Logs")
            prompt_parts.append(self._format_redshift_audit(diagnostic_context['redshift_audit']))
        
        if diagnostic_context.get('cloudwatch_errors'):
            prompt_parts.append("### CloudWatch Errors")
            prompt_parts.append(self._format_cloudwatch_errors(diagnostic_context['cloudwatch_errors']))
        
        if diagnostic_context.get('dag_state'):
            prompt_parts.append("### DAG State Information")
            prompt_parts.append(json.dumps(diagnostic_context['dag_state'], indent=2))
        
        # Add output format instructions
        prompt_parts.append("\n\n## Required Output Format")
        prompt_parts.append(template.output_format)
        
        return "\n\n".join(prompt_parts)
    
    def _format_failure_details(self, failure_details: Dict[str, Any]) -> str:
        """Format failure details for the prompt."""
        details = []
        
        details.append(f"**DAG ID**: {failure_details.get('dag_id', 'Unknown')}")
        
        if failure_details.get('task_id'):
            details.append(f"**Task ID**: {failure_details['task_id']}")
        
        if failure_details.get('execution_date'):
            details.append(f"**Execution Date**: {failure_details['execution_date']}")
        
        details.append(f"**Error Type**: {failure_details.get('error_type', 'general')}")
        details.append(f"**Error Message**: {failure_details.get('error_message', 'No message available')}")
        
        if failure_details.get('log_url'):
            details.append(f"**Log URL**: {failure_details['log_url']}")
        
        return "\n".join(details)
    
    def _format_redshift_audit(self, audit_logs: List[Dict]) -> str:
        """Format Redshift audit logs for the prompt."""
        if not audit_logs:
            return "No Redshift audit logs available."
        
        formatted = []
        for i, log in enumerate(audit_logs[:5]):  # Limit to first 5 entries
            formatted.append(f"**Entry {i+1}**:")
            formatted.append(f"- Query: {log.get('query', 'N/A')[:200]}...")
            formatted.append(f"- Status: {log.get('status', 'N/A')}")
            formatted.append(f"- Error: {log.get('error_message', 'N/A')}")
            formatted.append(f"- Timestamp: {log.get('timestamp', 'N/A')}")
            formatted.append("")
        
        return "\n".join(formatted)
    
    def _format_cloudwatch_errors(self, errors: List[str]) -> str:
        """Format CloudWatch errors for the prompt."""
        if not errors:
            return "No CloudWatch errors available."
        
        formatted = []
        for i, error in enumerate(errors[:10]):  # Limit to first 10 errors
            formatted.append(f"**Error {i+1}**: {error[:300]}...")
        
        return "\n".join(formatted)
    
    async def _call_gemini(self, prompt: str, max_tokens: int) -> str:
        """
        Call the Gemini API with proper error handling.
        
        Args:
            prompt: The complete prompt to send
            max_tokens: Maximum tokens to generate
            
        Returns:
            Generated response text
        """
        try:
            # Configure generation parameters
            generation_config = genai.types.GenerationConfig(
                max_output_tokens=max_tokens,
                temperature=0.1,  # Low temperature for consistent, factual responses
                top_p=0.8,
                top_k=40
            )
            
            # Generate response
            response = self.model.generate_content(
                prompt,
                generation_config=generation_config
            )
            
            if response.text:
                return response.text
            else:
                logger.warning("Empty response from Gemini API")
                return "Unable to generate analysis - empty response from LLM."
            
        except Exception as e:
            logger.error(f"Gemini API call failed: {e}")
            raise
    
    def _format_response(self, response: str) -> str:
        """Format and validate the LLM response."""
        # Clean up the response
        response = response.strip()
        
        # Ensure it's not too long for Slack
        if len(response) > 4000:  # Slack has message limits
            # Truncate and add note
            response = response[:3900] + "\n\n*[Response truncated due to length]*"
        
        # Add metadata
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        response += f"\n\n---\n*Analysis generated at {timestamp} by DE-Bot*"
        
        return response
    
    def _generate_fallback_response(self, failure_details: Dict[str, Any]) -> str:
        """Generate a basic fallback response when LLM fails."""
        dag_id = failure_details.get('dag_id', 'Unknown DAG')
        error_type = failure_details.get('error_type', 'general')
        
        fallback = f"""## ⚠️ Analysis Failed - Basic Troubleshooting Guide

**DAG**: {dag_id}
**Error Type**: {error_type}

## 🛠️ General Troubleshooting Steps

1. **Check MWAA Logs**: Review the task logs in the Airflow UI for detailed error messages
2. **Verify Connections**: Ensure all required connections are properly configured
3. **Check Resources**: Verify sufficient memory and CPU allocation
4. **Review Dependencies**: Check if upstream tasks completed successfully
5. **Validate Data Sources**: Ensure all required tables/files are available

## 📞 Escalation
Contact the data engineering team if the issue persists after basic troubleshooting.

---
*Fallback response generated due to LLM analysis failure*
"""
        return fallback
    
    def estimate_token_count(self, text: str) -> int:
        """Estimate token count for prompt planning."""
        # Rough estimation: 1 token ≈ 4 characters for English text
        return len(text) // 4
    
    def truncate_context(self, context: str, max_tokens: int) -> str:
        """Truncate context to fit within token limits."""
        max_chars = max_tokens * 4  # Rough conversion
        if len(context) <= max_chars:
            return context
        
        # Truncate with ellipsis
        return context[:max_chars-10] + "\n...[truncated]"

# Factory function
def create_prompt_engine(api_key: Optional[str] = None) -> PromptEngine:
    """Create a PromptEngine instance."""
    return PromptEngine(api_key=api_key)

# Utility function for backward compatibility
def build_diagnostic_prompt(failure: Any, **kwargs) -> str:
    """Build a diagnostic prompt from failure info and context."""
    engine = create_prompt_engine()
    template = engine.templates['general']
    
    failure_details = {
        'dag_id': getattr(failure, 'dag_id', 'Unknown'),
        'task_id': getattr(failure, 'task_id', None),
        'error_type': getattr(failure, 'error_type', 'general'),
        'error_message': getattr(failure, 'error_message', ''),
        'log_url': getattr(failure, 'log_url', None),
        'execution_date': getattr(failure, 'execution_date', None)
    }
    
    diagnostic_context = {
        'mwaa_logs': kwargs.get('mwaa_logs'),
        'redshift_audit': kwargs.get('redshift_audit'),
        'cloudwatch_errors': kwargs.get('cloudwatch_errors'),
        'dag_state': kwargs.get('dag_state')
    }
    
    return engine._build_prompt(template, failure_details, diagnostic_context)
