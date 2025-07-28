# On-call Data Engineering AI Agent

A serverless AI agent that monitors Slack for Apache Airflow failures, diagnoses issues using AWS services (MWAA, Redshift, CloudWatch), and provides intelligent root cause analysis.

## 🏗️ High-Level Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐     ┌──────────────────┐
│   Slack     │────▶│ API Gateway  │────▶│   Lambda    │────▶│  AWS Services    │
│ Events API  │     │              │     │  Function   │     │ • MWAA           │
└─────────────┘     └──────────────┘     └──────┬──────┘     │ • Redshift       │
                                                 │            │ • CloudWatch     │
                                                 │            └──────────────────┘
                                                 │                      
                                                 ▼                      
┌─────────────┐     ┌──────────────┐     ┌─────────────┐              
│   Slack     │◀────│     LLM      │◀────│   Prompt    │              
│  Web API    │     │   (Gemini)   │     │ Engineering │              
└─────────────┘     └──────────────┘     └─────────────┘              
```

### Why This Architecture?

1. **Serverless**: No infrastructure to manage, automatic scaling, pay-per-use
2. **Event-driven**: Responds only when failures occur
3. **Secure**: All credentials stored in AWS Secrets Manager
4. **Maintainable**: Clear separation of concerns with modular code
5. **Cost-effective**: Lambda free tier covers thousands of monthly invocations

## 📋 Features

- **Automated Failure Detection**: Monitors Slack for Apache Airflow failure notifications
- **Multi-source Diagnostics**: Gathers context from MWAA logs, Redshift audit tables, and CloudWatch
- **Intelligent Analysis**: Uses LLM to reason about root causes and suggest fixes
- **Thread-aware Responses**: Posts formatted analysis back to the original Slack thread
- **Error Type Recognition**: Handles timeout errors, DBT failures, database errors, and more

## 🚀 Quick Start

### Prerequisites

- AWS Account with appropriate permissions
- Slack workspace with admin access
- Python 3.11+
- AWS CLI configured
- Terraform >= 1.0

### Installation

1. Clone this repository:
```bash
git clone https://github.com/paschmaria/on-call-data-engineering-ai-agent.git
cd on-call-data-engineering-ai-agent
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Configure AWS Secrets Manager with required credentials (see `docs/SETUP.md`)

4. Deploy using Terraform:
```bash
# Make deployment script executable
chmod +x deployment/deploy.sh

# Deploy to development environment
./deployment/deploy.sh deploy dev

# Or deploy to production
./deployment/deploy.sh deploy prod
```

## 📁 Project Structure

```
├── src/
│   ├── app.py                 # Slack listener
│   ├── lambda_handler.py      # Main Lambda function
│   ├── tools.py               # AWS diagnostic tools
│   ├── parser.py              # Message parsing logic
│   ├── orchestrator.py        # Workflow coordination
│   ├── prompt_engine.py       # LLM interactions
│   └── runtime_prompt.py      # LLM prompt template
├── tests/
│   ├── test_tools.py          # AWS tools unit tests
│   └── test_lambda_handler.py # Lambda handler tests
├── docs/
│   ├── SETUP.md               # Detailed setup guide
│   ├── ARCHITECTURE.md        # Architecture decisions
│   └── DEVELOPMENT_PLAN.md    # Step-by-step development guide
├── deployment/
│   ├── README.md              # Deployment documentation
│   ├── deploy.sh              # Deployment script
│   └── slack_manifest.yaml    # Slack app configuration
├── terraform/
│   ├── main.tf                # Main Terraform configuration
│   ├── variables.tf           # Variable definitions
│   └── outputs.tf             # Output definitions
├── requirements.txt
└── README.md
```

## 🔧 Configuration

The agent requires the following environment variables (managed through Terraform):

- `SLACK_BOT_TOKEN`: Bot user OAuth token
- `SLACK_SIGNING_SECRET`: For request verification
- `GEMINI_API_KEY`: Google Gemini API key
- `REDSHIFT_CLUSTER_ID`: Your Redshift cluster identifier
- `REDSHIFT_DATABASE`: Database name for audit logs
- `MWAA_ENVIRONMENT_NAME`: MWAA environment name
- `DIAGNOSTIC_LAMBDA_NAME`: Name of the diagnostic Lambda (set by Terraform)

## 🧪 Testing

Run unit tests:
```bash
python -m pytest tests/
```

Test end-to-end in development:
```bash
python src/app.py  # Starts local Slack listener
```

## 📊 Monitoring

The agent creates CloudWatch logs and metrics:
- `/aws/lambda/de-agent`: Function logs
- `DE-Agent/Diagnostics`: Custom metrics for response times and error rates

## 🚀 Deployment

### Development Environment
```bash
./deployment/deploy.sh deploy dev
```

### Production Environment
```bash
./deployment/deploy.sh deploy prod
```

### Other Commands
```bash
# Set up secrets
./deployment/deploy.sh secrets dev

# Validate deployment
./deployment/deploy.sh validate dev

# Package Lambda function only
./deployment/deploy.sh package

# Clean up infrastructure
./deployment/deploy.sh cleanup dev
```

## 🔒 Security

- All sensitive data stored in AWS Secrets Manager
- IAM policies follow principle of least privilege
- Slack webhook signature verification enabled
- API Gateway uses HTTPS only
- Lambda functions can run in VPC (optional)

## 💰 Cost Optimization

**Monthly Cost Estimates (1000 failures/month):**
- Lambda: ~$2.50
- API Gateway: ~$1.00
- CloudWatch: ~$5.00
- Secrets Manager: ~$2.00
- **Total: ~$10.50/month**

## 🤝 Contributing

Please read `CONTRIBUTING.md` for details on our code of conduct and the process for submitting pull requests.

## 📝 License

This project is licensed under the MIT License - see the `LICENSE` file for details.

## 🙏 Acknowledgments

- Apache Airflow community for webhook integrations
- AWS for comprehensive SDK documentation
- Slack for excellent developer tools
