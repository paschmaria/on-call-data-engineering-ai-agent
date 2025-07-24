# Troubleshooting Guide

This guide helps you diagnose and fix common issues with the DE-Agent.

## Common Issues

### 1. Slack Integration Issues

#### Bot Not Responding to Messages

**Symptoms:**
- Bot doesn't add 👀 reaction to failure messages
- No diagnostic response in threads

**Solutions:**

1. **Check Bot Permissions:**
   ```bash
   # Verify bot is in channel
   /invite @DE-Bot
   ```

2. **Verify Event Subscriptions:**
   - Go to api.slack.com → Your App → Event Subscriptions
   - Ensure URL is verified
   - Check that `message.channels` event is subscribed

3. **Check CloudWatch Logs:**
   ```bash
   aws logs tail /aws/lambda/de-agent-slack-listener-prod --follow
   ```

4. **Test Webhook Manually:**
   ```bash
   curl -X POST https://your-api-gateway-url/slack/events \
     -H "Content-Type: application/json" \
     -d @tests/sample_slack_event.json
   ```

#### URL Verification Failing

**Error:** "Your URL didn't respond with the value of the challenge parameter"

**Solution:**
```python
# Ensure Lambda returns challenge for verification
if event.get('type') == 'url_verification':
    return {
        'statusCode': 200,
        'body': event['challenge']
    }
```

### 2. AWS Permission Issues

#### SecretsManager Access Denied

**Error:** "An error occurred (AccessDeniedException) when calling the GetSecretValue operation"

**Solution:**
1. Check IAM role has permission:
   ```json
   {
     "Effect": "Allow",
     "Action": "secretsmanager:GetSecretValue",
     "Resource": "arn:aws:secretsmanager:*:*:secret:de-agent/*"
   }
   ```

2. Verify secret exists:
   ```bash
   aws secretsmanager describe-secret --secret-id de-agent/slack
   ```

#### MWAA Access Issues

**Error:** "Failed to access MWAA: ResourceNotFoundException"

**Solutions:**
1. Verify environment name:
   ```bash
   aws mwaa list-environments
   ```

2. Check VPC connectivity if MWAA is private

3. Ensure Lambda has VPC configuration if needed

### 3. Diagnostic Tool Failures

#### Redshift Query Timeout

**Symptoms:** Redshift queries never complete

**Solutions:**
1. Check cluster status:
   ```bash
   aws redshift describe-clusters --cluster-identifier your-cluster
   ```

2. Verify Redshift Data API is enabled

3. Test query directly:
   ```bash
   aws redshift-data execute-statement \
     --cluster-identifier your-cluster \
     --database your-db \
     --sql "SELECT 1"
   ```

#### CloudWatch Logs Not Found

**Error:** "Log group not found for function: xyz"

**Solution:**
1. Verify log group exists:
   ```bash
   aws logs describe-log-groups --log-group-name-prefix "/aws/lambda/"
   ```

2. Check Lambda function name matches expected pattern

### 4. LLM Integration Issues

#### Gemini API Errors

**Error:** "API key not valid"

**Solutions:**
1. Verify API key in Secrets Manager
2. Check API key hasn't expired
3. Test API key:
   ```python
   import google.generativeai as genai
   genai.configure(api_key='your-key')
   model = genai.GenerativeModel('gemini-pro')
   response = model.generate_content('Test')
   ```

#### Token Limit Exceeded

**Error:** "The input + output tokens must be less than..."

**Solution:**
Reduce context size in `runtime_prompt.py`:
```python
# Limit log content
log_content[:2000]  # Increase limit in code
```

### 5. Performance Issues

#### Lambda Timeouts

**Symptoms:** Function times out after 300 seconds

**Solutions:**
1. Increase timeout in SAM template
2. Add parallel processing:
   ```python
   import concurrent.futures
   
   with concurrent.futures.ThreadPoolExecutor() as executor:
       futures = [
           executor.submit(get_mwaa_logs, url),
           executor.submit(get_dag_status, dag_id)
       ]
   ```

3. Implement caching for frequently accessed data

#### High Costs

**Issue:** Unexpected AWS bills

**Solutions:**
1. Review CloudWatch metrics:
   ```bash
   # Check invocation count
   aws cloudwatch get-metric-statistics \
     --namespace AWS/Lambda \
     --metric-name Invocations \
     --dimensions Name=FunctionName,Value=de-agent-diagnostic-prod \
     --start-time 2024-01-01T00:00:00Z \
     --end-time 2024-01-31T23:59:59Z \
     --period 86400 \
     --statistics Sum
   ```

2. Implement caching for LLM responses
3. Set up billing alerts

## Debugging Steps

### 1. Enable Debug Logging

```bash
# Update Lambda environment variable
aws lambda update-function-configuration \
  --function-name de-agent-diagnostic-prod \
  --environment Variables={LOG_LEVEL=DEBUG}
```

### 2. Test Individual Components

```python
# Test tools locally
from src.tools import get_mwaa_task_logs

# Set up environment
import os
os.environ['AWS_PROFILE'] = 'your-profile'

# Test function
try:
    result = get_mwaa_task_logs('https://your-url')
    print(result)
except Exception as e:
    print(f"Error: {e}")
```

### 3. Check CloudWatch Insights

```
fields @timestamp, @message
| filter @message like /ERROR/
| sort @timestamp desc
| limit 50
```

### 4. Monitor Metrics

Create custom dashboard:
```json
{
  "MetricWidget": {
    "metrics": [
      ["DE-Agent", "DiagnosticTime"],
      [".", "ErrorRate"]
    ]
  }
}
```

## Emergency Procedures

### Service is Down

1. **Immediate Response:**
   ```bash
   # Check Lambda status
   aws lambda get-function --function-name de-agent-diagnostic-prod
   
   # Check recent errors
   aws logs filter-log-events \
     --log-group-name /aws/lambda/de-agent-diagnostic-prod \
     --filter-pattern ERROR \
     --start-time $(($(date +%s) - 3600))000
   ```

2. **Rollback if Needed:**
   ```bash
   # Deploy previous version
   sam deploy --parameter-overrides ParameterKey=LambdaVersion,ParameterValue=previous
   ```

### High Error Rate

1. **Identify Pattern:**
   - Check if errors are from specific DAGs
   - Look for infrastructure issues
   - Review recent deployments

2. **Temporary Mitigation:**
   - Increase Lambda memory/timeout
   - Disable problematic diagnostic tools
   - Switch to fallback responses

## Getting Help

### Logs to Collect

When reporting issues, include:
1. CloudWatch logs from both Lambda functions
2. Error messages and stack traces
3. Sample event that triggered the error
4. Time range when issue occurred

### Support Channels

1. **GitHub Issues:** For bugs and feature requests
2. **Slack #platform-support:** For urgent issues
3. **Email:** de-agent-support@company.com

### Useful Commands

```bash
# Get Lambda configuration
aws lambda get-function-configuration --function-name de-agent-diagnostic-prod

# List recent invocations
aws logs filter-log-events \
  --log-group-name /aws/lambda/de-agent-diagnostic-prod \
  --filter-pattern "[timestamp, request_id, event_type=REPORT*]"

# Check API Gateway logs
aws logs filter-log-events \
  --log-group-name API-Gateway-Execution-Logs_xxxxx/prod

# Get Secrets Manager values (be careful!)
aws secretsmanager get-secret-value --secret-id de-agent/slack --query SecretString
```

## Preventive Measures

1. **Set Up Monitoring:**
   - CloudWatch alarms for errors
   - Custom metrics dashboards
   - Weekly performance reviews

2. **Regular Testing:**
   - Automated integration tests
   - Monthly disaster recovery drills
   - Load testing before peak periods

3. **Documentation:**
   - Keep runbooks updated
   - Document all custom configurations
   - Maintain change log

---

**Remember:** Always test changes in the test environment first!