# Configure Terraform backend for state management
# Uncomment and configure for remote state storage

# terraform {
#   backend "s3" {
#     bucket         = "your-terraform-state-bucket"
#     key            = "de-agent/${var.environment}/terraform.tfstate"
#     region         = "us-east-1"
#     encrypt        = true
#     dynamodb_table = "terraform-state-lock"
#   }
# }