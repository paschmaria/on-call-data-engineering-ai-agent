# Terraform Infrastructure for DE-Agent

This directory contains the Terraform configuration for deploying the On-call Data Engineering AI Agent infrastructure on AWS.

## Prerequisites

1. **Terraform** >= 1.0
2. **AWS CLI** configured with appropriate credentials
3. **AWS Account** with permissions to create:
   - Lambda functions
   - API Gateway
   - IAM roles and policies
   - CloudWatch resources
   - SQS queues
   - SNS topics

## Directory Structure

```
terraform/
├── main.tf                 # Main Terraform configuration
├── variables.tf           # Variable definitions
├── lambda.tf             # Lambda function resources
├── api_gateway.tf        # API Gateway configuration
├── iam.tf               # IAM roles and policies
├── cloudwatch.tf        # CloudWatch logs, alarms, and dashboard
├── sqs.tf              # SQS Dead Letter Queue
├── sns.tf              # SNS topic for alerts
├── outputs.tf          # Output values
├── backend.tf          # Backend configuration (optional)
├── terraform.tfvars.example  # Example variables file
└── README.md           # This file
```

## Quick Start

1. **Clone the repository and navigate to terraform directory:**
   ```bash
   cd terraform
   ```

2. **Copy and configure the variables file:**
   ```bash
   cp terraform.tfvars.example terraform.tfvars
   # Edit terraform.tfvars with your values
   ```

3. **Initialize Terraform:**
   ```bash
   terraform init
   ```

4. **Plan the deployment:**
   ```bash
   terraform plan
   ```

5. **Apply the configuration:**
   ```bash
   terraform apply
   ```

## Configuration

### Required Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `environment` | Environment name (dev/test/prod) | `"dev"` |
| `mwaa_environment_name` | MWAA environment to monitor | `"my-airflow-env"` |
| `redshift_cluster_id` | Redshift cluster identifier | `"my-redshift-cluster"` |
| `slack_channel_id` | Slack channel ID | `"C1234567890"` |

### Optional Variables

| Variable | Description | Default |
|----------|-------------|----------|
| `aws_region` | AWS region | `"us-east-1"` |
| `lambda_timeout` | Lambda timeout in seconds | `300` |
| `lambda_memory` | Lambda memory in MB | `1024` |
| `log_retention_days` | CloudWatch log retention | `30` |

## Deployment Environments

### Development
```bash
terraform workspace new dev
terraform workspace select dev
terraform apply -var="environment=dev"
```

### Testing
```bash
terraform workspace new test
terraform workspace select test
terraform apply -var="environment=test"
```

### Production
```bash
terraform workspace new prod
terraform workspace select prod
terraform apply -var="environment=prod"
```

## Remote State Management

For team collaboration, configure remote state in `backend.tf`:

```hcl
terraform {
  backend "s3" {
    bucket         = "your-terraform-state-bucket"
    key            = "de-agent/terraform.tfstate"
    region         = "us-east-1"
    encrypt        = true
    dynamodb_table = "terraform-state-lock"
  }
}
```

## Outputs

After successful deployment, Terraform will output:

- `api_endpoint` - API Gateway URL for Slack webhook configuration
- `slack_listener_function_arn` - ARN of the Slack listener Lambda
- `diagnostic_function_arn` - ARN of the diagnostic Lambda
- `dlq_url` - Dead Letter Queue URL
- `sns_topic_arn` - SNS topic ARN for alerts
- `cloudwatch_dashboard_url` - Direct link to CloudWatch dashboard

## Managing Dependencies

The Lambda deployment package is automatically created from the `src/` directory. To update dependencies:

1. Update `requirements.txt` in the project root
2. Re-run `terraform apply` to update the Lambda functions

## Monitoring

- **CloudWatch Dashboard**: Access via the output URL or AWS Console
- **Alarms**: Configure SNS subscriptions for email/Slack notifications
- **Logs**: Check CloudWatch log groups for debugging

## Cleanup

To destroy all resources:

```bash
terraform destroy
```

## Troubleshooting

### Common Issues

1. **Lambda package too large**: Consider using Lambda layers for dependencies
2. **API Gateway timeout**: Increase Lambda timeout or optimize code
3. **Permission errors**: Check IAM policies in `iam.tf`

### Debug Commands

```bash
# Show current state
terraform show

# List resources
terraform state list

# Refresh state
terraform refresh

# Import existing resources
terraform import <resource_type>.<resource_name> <resource_id>
```

## Security Best Practices

1. Never commit `terraform.tfvars` with sensitive data
2. Use AWS Secrets Manager for credentials (already configured)
3. Enable state file encryption
4. Regularly review IAM policies for least privilege
5. Use separate AWS accounts for different environments

## Contributing

When modifying infrastructure:

1. Test changes in dev environment first
2. Run `terraform fmt` to format code
3. Run `terraform validate` to check syntax
4. Update documentation if adding new resources