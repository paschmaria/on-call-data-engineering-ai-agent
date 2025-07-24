# Setup Guide: On-call Data Engineering AI Agent

## Prerequisites

Before setting up the DE-Agent, ensure you have:

1. **AWS Account** with appropriate permissions to create:
   - Lambda functions
   - API Gateway
   - Secrets Manager secrets
   - IAM roles and policies
   - CloudWatch log groups

2. **Slack Workspace** with admin privileges to install apps

3. **Google Cloud Account** for Gemini API access

4. **Development Tools**:
   ```bash
   # Required versions
   python >= 3.11
   aws-cli >= 2.0
   sam-cli >= 1.100
   ```

5. **MWAA Environment** already running with:
   - Web server access enabled
   - Proper VPC configuration

6. **Redshift Cluster** with:
   - Audit logging enabled
   - DBT audit schema configured

## Step 1: Clone the Repository

```bash
git clone https://github.com/paschmaria/on-call-data-engineering-ai-agent.git
cd on-call-data-engineering-ai-agent
```

## Step 2: Set Up Python Environment

```bash
# Create virtual environment
python -m venv venv

# Activate it
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

## Step 3: Configure Slack App

### 3.1 Create Slack App

1. Go to [api.slack.com/apps](https://api.slack.com/apps)
2. Click "Create New App"
3. Choose "From an app manifest"
4. Select your workspace
5. Paste the contents of `deployment/slack_manifest.yaml`
6. Review and create the app

### 3.2 Install App to Workspace

1. Go to "OAuth & Permissions"
2. Click "Install to Workspace"
3. Authorize the app
4. Save the following tokens:
   - Bot User OAuth Token (starts with `xoxb-`)
   - Signing Secret (from "Basic Information")
   - Verification Token (from "Basic Information")

### 3.3 Configure Event Subscriptions

**Note**: You'll need to deploy the Lambda function first to get the API Gateway URL.
Come back to this step after deployment.

1. Go to "Event Subscriptions"
2. Enable Events
3. Set Request URL: `https://[your-api-gateway-url]/slack/events`
4. Verify the URL (it should show "Verified")

## Step 4: Get Google Gemini API Key

1. Go to [makersuite.google.com](https://makersuite.google.com)
2. Create a new API key
3. Save it securely

## Step 5: Configure AWS Secrets

### 5.1 Create Slack Secrets

```bash
aws secretsmanager create-secret \
  --name de-agent/slack \
  --description "Slack credentials for DE-Agent" \
  --secret-string '{
    "bot_token":"xoxb-your-bot-token",
    "signing_secret":"your-signing-secret",
    "verification_token":"your-verification-token"
  }'
```

### 5.2 Create Gemini Secret

```bash
aws secretsmanager create-secret \
  --name de-agent/gemini \
  --description "Google Gemini API key" \
  --secret-string '{"api_key":"your-gemini-api-key"}'
```

### 5.3 Create Redshift Secret

First, create a secret in Secrets Manager for Redshift credentials:

```bash
aws secretsmanager create-secret \
  --name de-agent/redshift-creds \
  --description "Redshift credentials" \
  --secret-string '{
    "username":"your-redshift-user",
    "password":"your-redshift-password"
  }'
```

Then create the configuration secret:

```bash
aws secretsmanager create-secret \
  --name de-agent/redshift \
  --description "Redshift configuration" \
  --secret-string '{
    "cluster_id":"your-cluster-id",
    "database":"your-database",
    "secret_arn":"arn:aws:secretsmanager:region:account:secret:de-agent/redshift-creds-xxxxx"
  }'
```

## Step 6: Configure Deployment Parameters

Create a `samconfig.toml` file in the root directory:

```toml
version = 0.1

[default.deploy.parameters]
stack_name = "de-agent-stack"
resolve_s3 = true
s3_prefix = "de-agent"
region = "us-east-1"
confirm_changeset = true
capabilities = "CAPABILITY_IAM"
parameter_overrides = [
    "EnvironmentName=prod",
    "MWAAEnvironmentName=your-mwaa-env-name",
    "RedshiftClusterId=your-redshift-cluster",
    "SlackChannelId=C1234567890"
]

[test.deploy.parameters]
stack_name = "de-agent-stack-test"
parameter_overrides = [
    "EnvironmentName=test",
    "MWAAEnvironmentName=your-test-mwaa-env",
    "RedshiftClusterId=your-test-redshift",
    "SlackChannelId=C0987654321"
]
```

## Step 7: Deploy the Application

### 7.1 Build the Application

```bash
cd deployment
sam build
```

### 7.2 Deploy to Test Environment

```bash
# First deployment (guided)
sam deploy --guided --config-env test

# Follow the prompts and save the configuration
```

### 7.3 Note the Outputs

After deployment, note these outputs:
- `ApiEndpoint`: Use this for Slack Event Subscriptions
- `SlackListenerFunctionArn`: For monitoring
- `DiagnosticFunctionArn`: For monitoring

## Step 8: Complete Slack Configuration

1. Go back to your Slack app settings
2. Update Event Subscriptions with your API Gateway URL
3. Add the bot to your monitoring channel:
   ```
   /invite @DE-Bot
   ```

## Step 9: Test the Setup

### 9.1 Test Slack Connection

```bash
# Send a test event
aws lambda invoke \
  --function-name de-agent-slack-listener-test \
  --payload file://tests/sample_slack_event.json \
  response.json

# Check the response
cat response.json
```

### 9.2 Test Diagnostic Function

```bash
# Test with sample Airflow failure
aws lambda invoke \
  --function-name de-agent-diagnostic-test \
  --payload file://tests/sample_diagnostic_event.json \
  response.json
```

### 9.3 End-to-End Test

1. Post a test failure message in your Slack channel:
   ```
   ❌ Task has failed.
   DAG: test_dag
   Task: test_task
   Execution Time: 2024-01-01 00:00:00+00:00
   Exception: Test exception for DE-Bot
   Log URL: [https://test.url]
   ```

2. Watch for:
   - 👀 reaction added by DE-Bot
   - Diagnostic response in thread (within 30 seconds)

## Step 10: Production Deployment

### 10.1 Review Security

1. Ensure IAM roles follow least privilege
2. Review Secret rotation policy
3. Enable AWS GuardDuty for the account
4. Set up AWS Config rules

### 10.2 Deploy to Production

```bash
sam deploy --config-env prod
```

### 10.3 Set Up Monitoring

1. Create CloudWatch Dashboard:
   ```bash
   aws cloudwatch put-dashboard \
     --dashboard-name DE-Agent \
     --dashboard-body file://monitoring/dashboard.json
   ```

2. Configure SNS alerts for the CloudWatch alarms

3. Set up log aggregation and analysis

## Troubleshooting

### Common Issues

1. **Slack URL Verification Fails**
   - Check API Gateway logs
   - Ensure Lambda has proper permissions
   - Verify signing secret is correct

2. **No Response in Slack**
   - Check CloudWatch logs for both Lambda functions
   - Verify bot has channel access
   - Check DLQ for failed messages

3. **Timeout Errors**
   - Increase Lambda timeout
   - Check VPC configuration if accessing private resources
   - Optimize diagnostic queries

4. **Permission Errors**
   - Review IAM role policies
   - Check Secrets Manager permissions
   - Verify Redshift/MWAA access

### Debug Mode

Enable debug logging:

```bash
# Update Lambda environment variable
aws lambda update-function-configuration \
  --function-name de-agent-diagnostic-test \
  --environment Variables={LOG_LEVEL=DEBUG}
```

## Maintenance

### Regular Tasks

1. **Weekly**:
   - Review CloudWatch metrics
   - Check error rates
   - Monitor response times

2. **Monthly**:
   - Review and optimize LLM token usage
   - Update prompt templates based on feedback
   - Audit access logs

3. **Quarterly**:
   - Rotate secrets
   - Update dependencies
   - Review and update IAM policies

## Support

For issues or questions:
1. Check CloudWatch logs
2. Review error messages in DLQ
3. Create an issue in the GitHub repository
4. Contact the platform team

---

**Next Steps**: After successful setup, read `ARCHITECTURE.md` for deep technical details.