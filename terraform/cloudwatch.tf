# CloudWatch Log Groups
resource "aws_cloudwatch_log_group" "slack_listener" {
  name              = "/aws/lambda/de-agent-slack-listener-${var.environment}"
  retention_in_days = var.log_retention_days
  
  tags = local.common_tags
}

resource "aws_cloudwatch_log_group" "diagnostic" {
  name              = "/aws/lambda/de-agent-diagnostic-${var.environment}"
  retention_in_days = var.log_retention_days
  
  tags = local.common_tags
}

resource "aws_cloudwatch_log_group" "api_gateway" {
  name              = "/aws/apigateway/de-agent-${var.environment}"
  retention_in_days = var.log_retention_days
  
  tags = local.common_tags
}

# CloudWatch Alarms
resource "aws_cloudwatch_metric_alarm" "diagnostic_errors" {
  alarm_name          = "de-agent-diagnostic-errors-${var.environment}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "1"
  metric_name        = "Errors"
  namespace          = "AWS/Lambda"
  period             = "300"
  statistic          = "Sum"
  threshold          = "5"
  alarm_description  = "DE Agent diagnostic function errors"
  treat_missing_data = "notBreaching"
  
  dimensions = {
    FunctionName = aws_lambda_function.diagnostic.function_name
  }
  
  alarm_actions = [aws_sns_topic.alerts.arn]
  
  tags = local.common_tags
}

resource "aws_cloudwatch_metric_alarm" "diagnostic_duration" {
  alarm_name          = "de-agent-diagnostic-duration-${var.environment}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name        = "Duration"
  namespace          = "AWS/Lambda"
  period             = "300"
  statistic          = "Average"
  threshold          = "60000"  # 60 seconds
  alarm_description  = "DE Agent diagnostic function taking too long"
  treat_missing_data = "notBreaching"
  
  dimensions = {
    FunctionName = aws_lambda_function.diagnostic.function_name
  }
  
  alarm_actions = [aws_sns_topic.alerts.arn]
  
  tags = local.common_tags
}

# CloudWatch Dashboard
resource "aws_cloudwatch_dashboard" "de_agent" {
  dashboard_name = "DE-Agent-${var.environment}"
  
  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "metric"
        x      = 0
        y      = 0
        width  = 12
        height = 6
        
        properties = {
          metrics = [
            ["AWS/Lambda", "Invocations", { stat = "Sum" }],
            [".", "Errors", { stat = "Sum" }],
            [".", "Duration", { stat = "Average" }]
          ]
          view    = "timeSeries"
          stacked = false
          region  = var.aws_region
          title   = "Lambda Performance"
          period  = 300
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 0
        width  = 12
        height = 6
        
        properties = {
          metrics = [
            ["DE-Agent", "DiagnosticTime", { stat = "Average" }],
            [".", "MWAALogsFetched", { stat = "Sum" }],
            [".", "RedshiftAuditFetched", { stat = "Sum" }],
            [".", "CloudWatchLogsFetched", { stat = "Sum" }]
          ]
          view    = "timeSeries"
          stacked = false
          region  = var.aws_region
          title   = "Diagnostic Operations"
          period  = 300
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 6
        width  = 12
        height = 6
        
        properties = {
          metrics = [
            ["DE-Agent", "Success", { stat = "Sum" }],
            [".", "Failure", { stat = "Sum" }]
          ]
          view   = "singleValue"
          region = var.aws_region
          title  = "Success/Failure Count"
          period = 3600
        }
      },
      {
        type   = "log"
        x      = 0
        y      = 12
        width  = 24
        height = 6
        
        properties = {
          query   = "SOURCE '${aws_cloudwatch_log_group.diagnostic.name}'\n| fields @timestamp, @message\n| filter @message like /ERROR/\n| sort @timestamp desc\n| limit 20"
          region  = var.aws_region
          title   = "Recent Errors"
          queryType = "Logs"
        }
      }
    ]
  })
}