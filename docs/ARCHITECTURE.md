# Architecture Document: On-call Data Engineering AI Agent

## System Overview

The On-call Data Engineering AI Agent is a serverless, event-driven system that automatically diagnoses Apache Airflow failures by combining multiple data sources with LLM-powered analysis.

## Architecture Diagram

```mermaid
graph TB
    subgraph "Slack Integration"
        A[Slack Events API] -->|HTTP POST| B[API Gateway]
        H[Slack Web API] -->|Thread Reply| I[Data Engineers]
    end
    
    subgraph "AWS Lambda"
        B --> C[Lambda Handler]
        C --> D[Message Parser]
        D --> E[Orchestration Engine]
    end
    
    subgraph "Diagnostic Tools"
        E --> F1[MWAA Client]
        E --> F2[Redshift Data API]
        E --> F3[CloudWatch Logs]
        F1 --> G1[Task Logs]
        F2 --> G2[Audit Tables]
        F3 --> G3[Error Logs]
    end
    
    subgraph "AI Analysis"
        E --> J[Context Assembler]
        J --> K[LLM Client<br/>(Gemini)]
        K --> L[Response Formatter]
        L --> H
    end
    
    subgraph "Security & Config"
        M[Secrets Manager] -.->|Credentials| C
        N[IAM Roles] -.->|Permissions| C
        O[Environment Vars] -.->|Config| C
    end
```

## Component Details

### 1. Slack Integration Layer

**Purpose**: Handle incoming failure notifications and post diagnostic responses

**Components**:
- **Events API Listener**: Receives real-time messages from Slack channels
- **Message Filter**: Identifies Apache Airflow failure messages
- **Thread Manager**: Maintains conversation context for replies

**Key Design Decisions**:
- Use Slack Bolt framework for robust event handling
- Implement request signing verification for security
- Async processing to avoid 3-second Slack timeout

### 2. API Gateway

**Purpose**: Secure, scalable entry point for Slack webhooks

**Configuration**:
```yaml
Type: AWS::ApiGatewayV2::Api
Properties:
  Name: de-agent-api
  ProtocolType: HTTP
  CorsConfiguration:
    AllowOrigins: ['https://slack.com']
    AllowMethods: ['POST']
    AllowHeaders: ['Content-Type', 'X-Slack-Signature']
```

**Features**:
- Request validation
- Rate limiting (100 req/second)
- Custom domain with SSL
- Request/response logging

### 3. Lambda Function

**Purpose**: Core processing engine for failure diagnosis

**Specifications**:
- Runtime: Python 3.11
- Memory: 1024 MB
- Timeout: 300 seconds
- Concurrent executions: 100

**Environment Structure**:
```
/var/task/
├── lambda_handler.py     # Entry point
├── tools.py             # AWS service integrations
├── parser.py            # Message parsing logic
├── orchestrator.py      # Workflow coordination
└── prompt_engine.py     # LLM interaction
```

### 4. Diagnostic Tools

**4.1 MWAA Integration**
```python
def get_mwaa_task_logs(log_url: str) -> str:
    """
    Fetches detailed task logs from MWAA web UI.
    Uses presigned URLs for secure access.
    """
```

**4.2 Redshift Data API**
```python
def query_redshift_audit_logs(model_name: str) -> List[Dict]:
    """
    Queries dbt audit tables for model-specific errors.
    Uses asynchronous execution for large result sets.
    """
```

**4.3 CloudWatch Logs Insights**
```python
def get_cloudwatch_lambda_errors(function_name: str) -> List[str]:
    """
    Retrieves recent error logs using Insights queries.
    Implements intelligent log filtering.
    """
```

### 5. Security Architecture

**Secrets Management**:
```
de-agent/
├── slack/              # Bot token, signing secret
├── gemini/             # API key
├── redshift/           # Cluster credentials
└── mwaa/               # Environment details
```

**IAM Role Policy**:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue",
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents",
        "redshift-data:ExecuteStatement",
        "redshift-data:GetStatementResult",
        "airflow:GetEnvironment",
        "cloudwatch:GetMetricStatistics"
      ],
      "Resource": "*"
    }
  ]
}
```

### 6. LLM Integration

**Prompt Engineering Strategy**:
1. Structured context assembly
2. Role-based prompting (DE-Bot persona)
3. Few-shot examples for consistency
4. Output format enforcement

**Token Optimization**:
- Max input tokens: 8,000
- Max output tokens: 2,000
- Context window management
- Response caching for similar errors

## Data Flow

1. **Event Reception** (< 100ms)
   - Slack sends POST to API Gateway
   - Gateway validates signature
   - Triggers Lambda async

2. **Message Parsing** (< 500ms)
   - Extract DAG, task, exception details
   - Identify error category
   - Determine diagnostic strategy

3. **Diagnostic Collection** (5-15s)
   - Parallel API calls to AWS services
   - Timeout handling with partial results
   - Error resilience with fallbacks

4. **LLM Analysis** (3-8s)
   - Context assembly and compression
   - API call with retry logic
   - Response parsing and validation

5. **Slack Response** (< 1s)
   - Format markdown response
   - Post to correct thread
   - Update monitoring metrics

**Total Response Time**: 10-25 seconds

## Scalability Considerations

### Current Limits
- 100 concurrent Lambda executions
- 1,000 requests/second via API Gateway
- 10,000 Slack API calls/minute

### Scaling Strategy
1. **Horizontal**: Add Lambda concurrency
2. **Vertical**: Increase memory/timeout
3. **Caching**: Redis for frequent queries
4. **Queueing**: SQS for burst handling

## Monitoring & Observability

### CloudWatch Metrics
- Custom namespace: `DE-Agent`
- Key metrics:
  - `DiagnosticTime`: End-to-end latency
  - `ErrorRate`: Failed diagnoses
  - `LLMTokenUsage`: Cost tracking
  - `ServiceCallFailures`: By service

### Logging Strategy
```python
logger.info("diagnostic_complete", extra={
    "dag_id": dag_id,
    "error_type": error_type,
    "diagnostic_time_ms": elapsed_ms,
    "llm_tokens_used": token_count,
    "services_called": services_list
})
```

### Distributed Tracing
- AWS X-Ray for request tracing
- Correlation IDs for cross-service tracking
- Performance bottleneck identification

## Disaster Recovery

### Backup Strategy
- Lambda deployment packages in S3
- Configuration versioning in Git
- Secrets rotation every 90 days

### Failure Modes
1. **Slack API Down**: Queue messages in SQS
2. **LLM API Down**: Fallback to template responses
3. **AWS Service Errors**: Graceful degradation
4. **Lambda Timeout**: Partial response with available data

## Cost Analysis

### Monthly Estimates (1000 failures/month)
- Lambda: $2.50 (compute + requests)
- API Gateway: $1.00
- CloudWatch: $5.00 (logs + metrics)
- Secrets Manager: $2.00
- LLM API: $30.00 (@ $0.03/diagnosis)

**Total: ~$40.50/month**

## Future Enhancements

1. **Machine Learning**
   - Pattern recognition for recurring errors
   - Predictive failure detection
   - Automated remediation triggers

2. **Integration Expansion**
   - PagerDuty integration
   - Jira ticket creation
   - Datadog metrics correlation

3. **Advanced Features**
   - Multi-channel support
   - Custom alert routing
   - Scheduled diagnostics
   - Performance optimization suggestions