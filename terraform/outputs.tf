output "api_endpoint" {
  description = "API Gateway endpoint URL for Slack events"
  value       = "${aws_apigatewayv2_stage.de_agent.invoke_url}/slack/events"
}

output "slack_listener_function_arn" {
  description = "ARN of the Slack listener Lambda function"
  value       = aws_lambda_function.slack_listener.arn
}

output "diagnostic_function_arn" {
  description = "ARN of the diagnostic Lambda function"
  value       = aws_lambda_function.diagnostic.arn
}

output "dlq_url" {
  description = "URL of the Dead Letter Queue"
  value       = aws_sqs_queue.diagnostic_dlq.url
}

output "sns_topic_arn" {
  description = "ARN of the SNS topic for alerts"
  value       = aws_sns_topic.alerts.arn
}

output "cloudwatch_dashboard_url" {
  description = "URL to the CloudWatch dashboard"
  value       = "https://console.aws.amazon.com/cloudwatch/home?region=${var.aws_region}#dashboards:name=${aws_cloudwatch_dashboard.de_agent.dashboard_name}"
}

output "slack_listener_log_group" {
  description = "CloudWatch log group for Slack listener function"
  value       = aws_cloudwatch_log_group.slack_listener.name
}

output "diagnostic_log_group" {
  description = "CloudWatch log group for diagnostic function"
  value       = aws_cloudwatch_log_group.diagnostic.name
}