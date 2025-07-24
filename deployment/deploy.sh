#!/bin/bash

# Deployment script for On-call Data Engineering AI Agent
# This script orchestrates the deployment using Terraform

set -e  # Exit on any error

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
TERRAFORM_DIR="$PROJECT_ROOT/terraform"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_prerequisites() {
    log_info "Checking prerequisites..."
    
    # Check if Terraform is installed
    if ! command -v terraform &> /dev/null; then
        log_error "Terraform is not installed. Please install Terraform >= 1.0"
        exit 1
    fi
    
    # Check Terraform version
    TERRAFORM_VERSION=$(terraform version -json | jq -r '.terraform_version')
    log_info "Terraform version: $TERRAFORM_VERSION"
    
    # Check if AWS CLI is installed and configured
    if ! command -v aws &> /dev/null; then
        log_error "AWS CLI is not installed. Please install AWS CLI"
        exit 1
    fi
    
    # Check AWS credentials
    if ! aws sts get-caller-identity &> /dev/null; then
        log_error "AWS credentials not configured. Please run 'aws configure'"
        exit 1
    fi
    
    # Check if jq is available for JSON parsing
    if ! command -v jq &> /dev/null; then
        log_warning "jq is not installed. Some features may not work properly"
    fi
    
    log_success "Prerequisites check completed"
}

deploy_infrastructure() {
    local environment=${1:-dev}
    
    log_info "Deploying infrastructure to environment: $environment"
    
    cd "$TERRAFORM_DIR"
    
    # Initialize Terraform
    log_info "Initializing Terraform..."
    terraform init
    
    # Select or create workspace
    log_info "Setting up Terraform workspace: $environment"
    terraform workspace select "$environment" 2>/dev/null || terraform workspace new "$environment"
    
    # Plan the deployment
    log_info "Planning Terraform deployment..."
    terraform plan -var="environment=$environment" -out="tfplan-$environment"
    
    # Ask for confirmation
    echo
    read -p "Do you want to proceed with the deployment? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_warning "Deployment cancelled by user"
        exit 0
    fi
    
    # Apply the plan
    log_info "Applying Terraform plan..."
    terraform apply "tfplan-$environment"
    
    # Clean up plan file
    rm -f "tfplan-$environment"
    
    log_success "Infrastructure deployment completed"
}

setup_secrets() {
    local environment=${1:-dev}
    
    log_info "Setting up AWS Secrets Manager secrets for environment: $environment"
    
    # Define secret names with environment prefix
    SLACK_SECRET="de-agent-$environment/slack"
    GEMINI_SECRET="de-agent-$environment/gemini"
    REDSHIFT_SECRET="de-agent-$environment/redshift"
    
    # Function to create or update secret
    create_or_update_secret() {
        local secret_name=$1
        local secret_description=$2
        
        if aws secretsmanager describe-secret --secret-id "$secret_name" &>/dev/null; then
            log_info "Secret $secret_name already exists"
        else
            log_info "Creating secret: $secret_name"
            aws secretsmanager create-secret \
                --name "$secret_name" \
                --description "$secret_description" \
                --secret-string '{}' > /dev/null
            log_success "Created secret: $secret_name"
        fi
    }
    
    # Create secrets
    create_or_update_secret "$SLACK_SECRET" "Slack bot token and signing secret for DE Agent"
    create_or_update_secret "$GEMINI_SECRET" "Google Gemini API key for DE Agent"
    create_or_update_secret "$REDSHIFT_SECRET" "Redshift cluster credentials for DE Agent"
    
    log_warning "Please update the secret values manually in AWS Secrets Manager console:"
    echo "  - $SLACK_SECRET: {\"bot_token\": \"xoxb-...\", \"signing_secret\": \"...\"}"
    echo "  - $GEMINI_SECRET: {\"api_key\": \"...\"}"
    echo "  - $REDSHIFT_SECRET: {\"cluster_id\": \"...\", \"database\": \"...\", \"user\": \"...\"}"
}

package_lambda() {
    log_info "Packaging Lambda function..."
    
    cd "$PROJECT_ROOT"
    
    # Create deployment package
    PACKAGE_DIR="$PROJECT_ROOT/build"
    mkdir -p "$PACKAGE_DIR"
    
    # Copy source code
    cp -r src/* "$PACKAGE_DIR/"
    
    # Install dependencies
    log_info "Installing Python dependencies..."
    pip install -r requirements.txt -t "$PACKAGE_DIR"
    
    # Create ZIP package
    cd "$PACKAGE_DIR"
    zip -r "../lambda-deployment-package.zip" .
    
    cd "$PROJECT_ROOT"
    rm -rf "$PACKAGE_DIR"
    
    log_success "Lambda package created: lambda-deployment-package.zip"
}

validate_deployment() {
    local environment=${1:-dev}
    
    log_info "Validating deployment for environment: $environment"
    
    cd "$TERRAFORM_DIR"
    
    # Get outputs
    API_GATEWAY_URL=$(terraform output -raw api_gateway_url 2>/dev/null || echo "")
    LAMBDA_FUNCTION_NAME=$(terraform output -raw lambda_function_name 2>/dev/null || echo "")
    
    if [[ -n "$API_GATEWAY_URL" ]]; then
        log_info "API Gateway URL: $API_GATEWAY_URL"
        
        # Test API Gateway health
        if curl -s -o /dev/null -w "%{http_code}" "$API_GATEWAY_URL/health" | grep -q "200"; then
            log_success "API Gateway is responding"
        else
            log_warning "API Gateway health check failed"
        fi
    fi
    
    if [[ -n "$LAMBDA_FUNCTION_NAME" ]]; then
        log_info "Lambda Function: $LAMBDA_FUNCTION_NAME"
        
        # Test Lambda function
        if aws lambda get-function --function-name "$LAMBDA_FUNCTION_NAME" &>/dev/null; then
            log_success "Lambda function is deployed"
        else
            log_error "Lambda function not found"
        fi
    fi
}

cleanup() {
    local environment=${1:-dev}
    
    log_warning "This will destroy all infrastructure for environment: $environment"
    read -p "Are you sure you want to proceed? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_info "Cleanup cancelled"
        exit 0
    fi
    
    cd "$TERRAFORM_DIR"
    terraform workspace select "$environment"
    terraform destroy -var="environment=$environment"
    
    log_success "Infrastructure destroyed"
}

show_help() {
    cat << EOF
Usage: $0 [COMMAND] [ENVIRONMENT]

Commands:
    deploy      Deploy infrastructure (default: dev environment)
    secrets     Set up AWS Secrets Manager secrets
    package     Package Lambda function
    validate    Validate deployment
    cleanup     Destroy infrastructure
    help        Show this help message

Environments:
    dev         Development environment (default)
    prod        Production environment

Examples:
    $0 deploy dev           # Deploy to development
    $0 deploy prod          # Deploy to production
    $0 secrets prod         # Set up secrets for production
    $0 validate dev         # Validate development deployment
    $0 cleanup dev          # Destroy development infrastructure

Prerequisites:
    - Terraform >= 1.0
    - AWS CLI configured
    - Python 3.11+
    - jq (recommended)

EOF
}

# Main script
main() {
    local command=${1:-deploy}
    local environment=${2:-dev}
    
    case $command in
        deploy)
            check_prerequisites
            package_lambda
            deploy_infrastructure "$environment"
            validate_deployment "$environment"
            ;;
        secrets)
            check_prerequisites
            setup_secrets "$environment"
            ;;
        package)
            package_lambda
            ;;
        validate)
            check_prerequisites
            validate_deployment "$environment"
            ;;
        cleanup)
            check_prerequisites
            cleanup "$environment"
            ;;
        help|--help|-h)
            show_help
            ;;
        *)
            log_error "Unknown command: $command"
            show_help
            exit 1
            ;;
    esac
}

# Run main function with all arguments
main "$@"
