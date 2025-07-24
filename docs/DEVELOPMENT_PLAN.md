# Development Plan: On-call Data Engineering AI Agent

## Overview

This document provides a complete step-by-step guide for building the On-call Data Engineering AI Agent from scratch to production deployment.

## Phase 1: Setup and Configuration (Day 1)

### 1. Set up Slack App & Get Credentials

1. Go to [api.slack.com](https://api.slack.com)
2. Create a new app "DE-Agent" using the manifest in `deployment/slack_manifest.yaml`
3. Configure OAuth scopes:
   - `channels:history` - Read channel messages
   - `chat:write` - Post messages
   - `chat:write.public` - Post to public channels
4. Install app to workspace and save:
   - Bot User OAuth Token
   - Signing Secret
   - Verification Token

### 2. Set up AWS Secrets Manager

```bash
# Create secrets for Slack credentials
aws secretsmanager create-secret \
  --name de-agent/slack \
  --secret-string '{
    "bot_token":"xoxb-...",
    "signing_secret":"...",
    "verification_token":"..."
  }'

# Create secrets for Gemini
aws secretsmanager create-secret \
  --name de-agent/gemini \
  --secret-string '{"api_key":"..."}}'

# Create secrets for Redshift
aws secretsmanager create-secret \
  --name de-agent/redshift \
  --secret-string '{
    "cluster_id":"...",
    "database":"...",
    "secret_arn":"..."
  }'
```

## Phase 2: Core Development (Days 2-4)

### 3. Code the `tools.py` Functions

Implement and unit test each diagnostic function:

- `get_mwaa_task_logs()`
- `get_dag_run_status()`
- `query_redshift_audit_logs()`
- `get_cloudwatch_lambda_errors()`

Run tests after each function:
```bash
python -m pytest tests/test_tools.py::test_get_mwaa_task_logs -v
```

### 4. Code the `lambda_handler.py`

1. Implement message parser with regex
2. Add orchestration logic
3. Integrate with tools
4. Add error handling and retries
5. Implement structured logging

### 5. Integrate LLM and Prompt Engineering

1. Test prompt with sample data
2. Optimize for token usage
3. Add response formatting
4. Implement fallback responses

## Phase 3: Local Testing (Day 5)

### 6. Set up Local Development Environment

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Set environment variables
export SLACK_BOT_TOKEN="xoxb-test-token"
export SLACK_SIGNING_SECRET="test-secret"
# ... other variables
```

### 7. Run Integration Tests

1. Create test Slack channel #de-agent-test
2. Trigger test messages
3. Verify end-to-end flow
4. Check CloudWatch logs

## Phase 4: Deployment (Days 6-7)

### 8. Deploy Test Version

```bash
# Build and deploy to test environment
sam build
sam deploy --config-env test

# Test the deployed function
aws lambda invoke \
  --function-name de-agent-test \
  --payload file://tests/sample_event.json \
  response.json
```

### 9. Production Deployment Checklist

- [ ] All unit tests passing
- [ ] Integration tests completed
- [ ] Security review completed
- [ ] IAM permissions minimized
- [ ] Monitoring dashboards created
- [ ] Runbook documented
- [ ] Rollback plan prepared

### 10. Deploy to Production

```bash
# Deploy to production
sam deploy --config-env prod

# Configure Slack Event Subscriptions
# Point to: https://[api-gateway-url]/slack/events

# Verify webhook
curl -X POST https://[api-gateway-url]/slack/events \
  -H "Content-Type: application/json" \
  -d @tests/verification_challenge.json
```

## Phase 5: Post-Deployment (Day 8)

### 11. Monitor and Optimize

1. Set up CloudWatch alarms:
   - Lambda errors > 1% threshold
   - Response time > 30s
   - Concurrent executions > 80% of limit

2. Create CloudWatch dashboard with:
   - Invocation count
   - Error rate
   - Duration metrics
   - Cost tracking

3. Implement feedback loop:
   - Add Slack reactions for feedback
   - Log successful/failed diagnoses
   - Track most common error patterns

### 12. Documentation and Training

1. Create user guide for data team
2. Document common troubleshooting steps
3. Schedule team training session
4. Create video walkthrough

## Timeline Summary

| Phase | Duration | Key Deliverables |
|-------|----------|------------------|
| Setup | 1 day | Slack app configured, AWS secrets created |
| Development | 3 days | Core functions coded and tested |
| Testing | 1 day | End-to-end testing completed |
| Deployment | 2 days | Test and production deployments |
| Post-Deploy | 1 day | Monitoring, documentation, training |

**Total: 8 days from concept to production**

## Risk Mitigation

1. **API Rate Limits**: Implement exponential backoff
2. **Large Log Files**: Add pagination and size limits
3. **LLM Costs**: Set token limits and implement caching
4. **Security**: Use least-privilege IAM, encrypt in transit
5. **Availability**: Deploy to multiple AZs, add DLQ

## Success Metrics

- Response time < 30 seconds
- Accuracy of root cause identification > 80%
- Reduction in MTTR by 50%
- Developer satisfaction score > 4/5