# Package Lambda functions
data "archive_file" "lambda_package" {
  type        = "zip"
  source_dir  = "${path.module}/../src"
  output_path = "${path.module}/../.terraform/lambda-package.zip"
  excludes    = ["__pycache__", "*.pyc", ".pytest_cache"]
}

# Slack Listener Lambda Function
resource "aws_lambda_function" "slack_listener" {
  filename         = data.archive_file.lambda_package.output_path
  function_name    = "de-agent-slack-listener-${var.environment}"
  role            = aws_iam_role.lambda_execution_role.arn
  handler         = "app.lambda_handler"
  source_code_hash = data.archive_file.lambda_package.output_base64sha256
  runtime         = "python3.11"
  timeout         = 60
  memory_size     = 512
  
  environment {
    variables = {
      DIAGNOSTIC_LAMBDA_NAME = aws_lambda_function.diagnostic.function_name
      ENVIRONMENT_NAME       = var.environment
      LOG_LEVEL             = "INFO"
    }
  }
  
  depends_on = [
    aws_iam_role_policy_attachment.lambda_logs,
    aws_cloudwatch_log_group.slack_listener,
  ]
  
  tags = local.common_tags
}

# Diagnostic Lambda Function
resource "aws_lambda_function" "diagnostic" {
  filename         = data.archive_file.lambda_package.output_path
  function_name    = "de-agent-diagnostic-${var.environment}"
  role            = aws_iam_role.diagnostic_role.arn
  handler         = "lambda_handler.lambda_handler"
  source_code_hash = data.archive_file.lambda_package.output_base64sha256
  runtime         = "python3.11"
  timeout         = var.lambda_timeout
  memory_size     = var.lambda_memory
  reserved_concurrent_executions = 100
  
  environment {
    variables = {
      MWAA_ENVIRONMENT_NAME = var.mwaa_environment_name
      REDSHIFT_CLUSTER_ID   = var.redshift_cluster_id
      ENVIRONMENT_NAME      = var.environment
      LOG_LEVEL            = "INFO"
    }
  }
  
  depends_on = [
    aws_iam_role_policy_attachment.diagnostic_policy,
    aws_cloudwatch_log_group.diagnostic,
  ]
  
  tags = local.common_tags
}

# Lambda Layers for dependencies (optional, for better package management)
resource "aws_lambda_layer_version" "dependencies" {
  filename   = "${path.module}/../.terraform/layer.zip"
  layer_name = "de-agent-dependencies-${var.environment}"
  
  compatible_runtimes = ["python3.11"]
  
  lifecycle {
    create_before_destroy = true
  }
}