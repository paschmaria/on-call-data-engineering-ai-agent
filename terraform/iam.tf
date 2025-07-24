# IAM role for Slack Listener Lambda
resource "aws_iam_role" "lambda_execution_role" {
  name = "de-agent-slack-listener-role-${var.environment}"
  
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "lambda.amazonaws.com"
      }
    }]
  })
  
  tags = local.common_tags
}

# IAM role for Diagnostic Lambda
resource "aws_iam_role" "diagnostic_role" {
  name = "de-agent-diagnostic-role-${var.environment}"
  
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "lambda.amazonaws.com"
      }
    }]
  })
  
  tags = local.common_tags
}

# Basic Lambda execution policy
resource "aws_iam_role_policy_attachment" "lambda_logs" {
  role       = aws_iam_role.lambda_execution_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Policy for Slack Listener
resource "aws_iam_role_policy" "slack_listener_policy" {
  name = "de-agent-slack-listener-policy"
  role = aws_iam_role.lambda_execution_role.id
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue"
        ]
        Resource = [
          "arn:aws:secretsmanager:${var.aws_region}:*:secret:de-agent/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "lambda:InvokeFunction"
        ]
        Resource = [
          aws_lambda_function.diagnostic.arn
        ]
      }
    ]
  })
}

# Comprehensive policy for Diagnostic Lambda
resource "aws_iam_policy" "diagnostic_policy" {
  name        = "de-agent-diagnostic-policy-${var.environment}"
  description = "IAM policy for DE Agent diagnostic Lambda"
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "SecretsManagerAccess"
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue",
          "secretsmanager:DescribeSecret"
        ]
        Resource = [
          "arn:aws:secretsmanager:*:*:secret:de-agent/*"
        ]
      },
      {
        Sid    = "MWAAAccess"
        Effect = "Allow"
        Action = [
          "airflow:GetEnvironment",
          "airflow:CreateCliToken",
          "airflow:CreateWebLoginToken"
        ]
        Resource = [
          "arn:aws:airflow:*:*:environment/*"
        ]
      },
      {
        Sid    = "RedshiftDataAPIAccess"
        Effect = "Allow"
        Action = [
          "redshift-data:ExecuteStatement",
          "redshift-data:DescribeStatement",
          "redshift-data:GetStatementResult",
          "redshift-data:ListStatements",
          "redshift-data:CancelStatement"
        ]
        Resource = "*"
      },
      {
        Sid    = "CloudWatchLogsAccess"
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents",
          "logs:StartQuery",
          "logs:GetQueryResults",
          "logs:DescribeLogGroups",
          "logs:DescribeLogStreams",
          "logs:GetLogEvents",
          "logs:FilterLogEvents"
        ]
        Resource = [
          "arn:aws:logs:*:*:log-group:/aws/lambda/*",
          "arn:aws:logs:*:*:log-group:/aws/airflow/*"
        ]
      },
      {
        Sid    = "CloudWatchMetricsAccess"
        Effect = "Allow"
        Action = [
          "cloudwatch:PutMetricData"
        ]
        Resource = "*"
        Condition = {
          StringEquals = {
            "cloudwatch:namespace" = "DE-Agent"
          }
        }
      },
      {
        Sid    = "XRayAccess"
        Effect = "Allow"
        Action = [
          "xray:PutTraceSegments",
          "xray:PutTelemetryRecords"
        ]
        Resource = "*"
      }
    ]
  })
}

# Attach diagnostic policy to role
resource "aws_iam_role_policy_attachment" "diagnostic_policy" {
  role       = aws_iam_role.diagnostic_role.name
  policy_arn = aws_iam_policy.diagnostic_policy.arn
}

# Attach basic execution policy to diagnostic role
resource "aws_iam_role_policy_attachment" "diagnostic_logs" {
  role       = aws_iam_role.diagnostic_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}