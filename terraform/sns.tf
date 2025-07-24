# SNS Topic for alerts
resource "aws_sns_topic" "alerts" {
  name = "de-agent-alerts-${var.environment}"
  
  tags = local.common_tags
}

# SNS Topic Policy
resource "aws_sns_topic_policy" "alerts" {
  arn = aws_sns_topic.alerts.arn
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "cloudwatch.amazonaws.com"
      }
      Action = "SNS:Publish"
      Resource = aws_sns_topic.alerts.arn
    }]
  })
}

# You can add SNS subscriptions here for email/Slack notifications
# resource "aws_sns_topic_subscription" "alerts_email" {
#   topic_arn = aws_sns_topic.alerts.arn
#   protocol  = "email"
#   endpoint  = "your-email@example.com"
# }