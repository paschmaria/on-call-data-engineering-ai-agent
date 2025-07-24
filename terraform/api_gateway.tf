# API Gateway for Slack Events
resource "aws_apigatewayv2_api" "de_agent" {
  name          = "de-agent-api-${var.environment}"
  protocol_type = "HTTP"
  description   = "API Gateway for DE Agent Slack integration"
  
  cors_configuration {
    allow_origins     = ["https://slack.com"]
    allow_methods     = ["POST"]
    allow_headers     = ["Content-Type", "X-Slack-Signature", "X-Slack-Request-Timestamp"]
    expose_headers    = ["*"]
    max_age          = 300
  }
  
  tags = local.common_tags
}

# API Gateway Stage
resource "aws_apigatewayv2_stage" "de_agent" {
  api_id = aws_apigatewayv2_api.de_agent.id
  name   = var.environment
  
  auto_deploy = true
  
  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api_gateway.arn
    format = jsonencode({
      requestId      = "$context.requestId"
      sourceIp       = "$context.identity.sourceIp"
      requestTime    = "$context.requestTime"
      protocol       = "$context.protocol"
      httpMethod     = "$context.httpMethod"
      resourcePath   = "$context.resourcePath"
      routeKey       = "$context.routeKey"
      status         = "$context.status"
      responseLength = "$context.responseLength"
      error          = "$context.error.message"
    })
  }
  
  tags = local.common_tags
}

# API Gateway Integration
resource "aws_apigatewayv2_integration" "slack_events" {
  api_id = aws_apigatewayv2_api.de_agent.id
  
  integration_uri    = aws_lambda_function.slack_listener.invoke_arn
  integration_type   = "AWS_PROXY"
  integration_method = "POST"
}

# API Gateway Route
resource "aws_apigatewayv2_route" "slack_events" {
  api_id = aws_apigatewayv2_api.de_agent.id
  
  route_key = "POST /slack/events"
  target    = "integrations/${aws_apigatewayv2_integration.slack_events.id}"
}

# Lambda permission for API Gateway
resource "aws_lambda_permission" "api_gateway" {
  statement_id  = "AllowExecutionFromAPIGateway"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.slack_listener.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.de_agent.execution_arn}/*/*"
}

# Lambda permission for Slack Listener to invoke Diagnostic
resource "aws_lambda_permission" "slack_to_diagnostic" {
  statement_id  = "AllowExecutionFromSlackListener"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.diagnostic.function_name
  principal     = "lambda.amazonaws.com"
  source_arn    = aws_lambda_function.slack_listener.arn
}