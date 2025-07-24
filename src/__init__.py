"""
On-call Data Engineering AI Agent

A serverless application for diagnosing Apache Airflow failures
using AWS services and LLM-powered analysis.
"""

__version__ = "1.0.0"
__author__ = "DE-Agent Contributors"
__email__ = "support@example.com"

# Public API
__all__ = [
    "DiagnosticError",
    "get_mwaa_task_logs",
    "get_dag_run_status",
    "query_redshift_audit_logs",
    "get_cloudwatch_lambda_errors",
    "lambda_handler"
]

from .tools import (
    DiagnosticError,
    get_mwaa_task_logs,
    get_dag_run_status,
    query_redshift_audit_logs,
    get_cloudwatch_lambda_errors
)
from .lambda_handler import lambda_handler