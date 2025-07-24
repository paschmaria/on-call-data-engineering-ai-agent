# Deployment Configuration

This directory contains deployment configuration files for the On-call Data Engineering AI Agent.

## Migration Notice

**⚠️ This project has been migrated from AWS SAM to Terraform for infrastructure management.**

All infrastructure is now managed through Terraform configurations located in the `/terraform` directory.

## What Changed

### Removed Files
- `template.yaml` - Replaced by Terraform configurations
- `iam_policy.json` - IAM policies now defined in Terraform
- `slack_manifest.yaml` - Moved to documentation for reference

### Current Deployment Structure
```
├── terraform/           # Terraform infrastructure code
│   ├── main.tf         # Main Terraform configuration
│   ├── variables.tf    # Variable definitions
│   ├── outputs.tf      # Output definitions
│   └── modules/        # Reusable Terraform modules
└── deployment/         # Deployment documentation and scripts
    ├── README.md       # This file
    └── slack_manifest.yaml # Slack app configuration reference
```

## Deployment Process

### Prerequisites
1. AWS CLI configured with appropriate permissions
2. Terraform >= 1.0 installed
3. Slack workspace admin access

### Infrastructure Deployment
```bash
# Navigate to terraform directory
cd terraform

# Initialize Terraform
terraform init

# Plan the deployment
terraform plan

# Apply the infrastructure
terraform apply
```

### Manual Steps Required
1. **Create Slack App**: Use the manifest in `slack_manifest.yaml` as reference
2. **Configure Secrets**: Set up AWS Secrets Manager values as documented
3. **Update Environment Variables**: Configure Lambda environment variables through Terraform

## Environment Management

### Development
- Use `terraform workspace select dev`
- Deploy to development AWS account
- Use separate Slack workspace for testing

### Production
- Use `terraform workspace select prod`
- Deploy to production AWS account
- Use production Slack workspace

## Monitoring and Troubleshooting

### CloudWatch Logs
- Lambda function logs: `/aws/lambda/de-agent-function`
- API Gateway logs: `/aws/apigateway/de-agent-api`

### Custom Metrics
- Namespace: `DE-Agent`
- Key metrics: DiagnosticTime, ErrorRate, LLMTokenUsage

### Common Issues
1. **IAM Permissions**: Ensure Terraform has sufficient permissions to create resources
2. **Secrets Manager**: Verify all required secrets are created with correct names
3. **Slack Integration**: Check that the Slack app has proper permissions and scopes

## Security Considerations

### Secrets Management
All sensitive data is stored in AWS Secrets Manager:
- `de-agent/slack` - Slack bot token and signing secret
- `de-agent/gemini` - Google Gemini API key
- `de-agent/redshift` - Redshift cluster credentials

### IAM Policies
IAM policies follow the principle of least privilege:
- Lambda execution role has minimal required permissions
- API Gateway has restricted access
- Secrets Manager access is scoped to specific secret paths

### Network Security
- Lambda functions run in VPC (optional)
- API Gateway uses HTTPS only
- Slack webhook signature verification enabled

## Cost Optimization

### Resource Sizing
- Lambda: 1024 MB memory allocation
- API Gateway: Pay-per-request pricing
- CloudWatch: Log retention set to 30 days

### Monthly Cost Estimates
- Lambda: ~$2.50 (1000 invocations)
- API Gateway: ~$1.00
- CloudWatch: ~$5.00
- Secrets Manager: ~$2.00
- **Total: ~$10.50/month**

## Support and Maintenance

### Updates
1. Update Terraform configurations for infrastructure changes
2. Update Lambda code through CI/CD pipeline
3. Monitor CloudWatch dashboards for performance metrics

### Backup and Recovery
1. Terraform state is stored in S3 with versioning
2. Lambda code is versioned in GitHub
3. Secrets can be restored from secure backups

### Contact
For deployment issues or questions:
- Check the troubleshooting guide in `/docs/TROUBLESHOOTING.md`
- Review CloudWatch logs for error details
- Contact the data engineering team for escalation
