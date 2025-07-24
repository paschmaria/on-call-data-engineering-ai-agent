# Dead Letter Queue for failed Lambda invocations
resource "aws_sqs_queue" "diagnostic_dlq" {
  name                      = "de-agent-dlq-${var.environment}"
  message_retention_seconds = 1209600  # 14 days
  visibility_timeout_seconds = 300
  
  tags = local.common_tags
}

# Dead letter queue policy
resource "aws_sqs_queue_policy" "diagnostic_dlq_policy" {
  queue_url = aws_sqs_queue.diagnostic_dlq.id
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "lambda.amazonaws.com"
      }
      Action = [
        "sqs:SendMessage",
        "sqs:GetQueueAttributes"
      ]
      Resource = aws_sqs_queue.diagnostic_dlq.arn
      Condition = {
        ArnEquals = {
          "aws:SourceArn" = aws_lambda_function.diagnostic.arn
        }
      }
    }]
  })
}

# Configure Lambda to use DLQ
resource "aws_lambda_function_event_invoke_config" "diagnostic_dlq" {
  function_name = aws_lambda_function.diagnostic.function_name
  
  destination_config {
    on_failure {
      destination = aws_sqs_queue.diagnostic_dlq.arn
    }
  }
  
  maximum_retry_attempts = 2
}