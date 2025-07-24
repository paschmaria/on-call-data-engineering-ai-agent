.PHONY: help install install-dev test test-cov lint format type-check clean build deploy tf-init tf-plan tf-apply tf-destroy

# Default target
.DEFAULT_GOAL := help

# Python interpreter
PYTHON := python3

# Terraform command
TERRAFORM := terraform

# Help target
help:
	@echo "Available commands:"
	@echo "  install       Install production dependencies"
	@echo "  install-dev   Install development dependencies"
	@echo "  test          Run tests"
	@echo "  test-cov      Run tests with coverage"
	@echo "  lint          Run linting"
	@echo "  format        Format code"
	@echo "  type-check    Run type checking"
	@echo "  clean         Clean build artifacts"
	@echo "  tf-init       Initialize Terraform"
	@echo "  tf-plan       Plan Terraform deployment"
	@echo "  tf-apply      Apply Terraform configuration"
	@echo "  tf-destroy    Destroy Terraform resources"

# Install production dependencies
install:
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -r requirements.txt

# Install development dependencies
install-dev: install
	$(PYTHON) -m pip install -r requirements-dev.txt
	pre-commit install

# Run tests
test:
	$(PYTHON) -m pytest tests/ -v

# Run tests with coverage
test-cov:
	$(PYTHON) -m pytest tests/ -v --cov=src --cov-report=term --cov-report=html

# Run linting
lint:
	flake8 src/ tests/

# Format code
format:
	black src/ tests/
	isort src/ tests/

# Run type checking
type-check:
	mypy src/

# Clean build artifacts
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name "*.coverage" -delete
	rm -rf .coverage
	rm -rf htmlcov/
	rm -rf .pytest_cache/
	rm -rf .mypy_cache/
	rm -rf dist/
	rm -rf build/
	rm -rf *.egg-info
	rm -rf .terraform/
	rm -f terraform/*.zip

# Terraform commands
TF_DIR := terraform

# Initialize Terraform
tf-init:
	cd $(TF_DIR) && $(TERRAFORM) init

# Format Terraform files
tf-fmt:
	cd $(TF_DIR) && $(TERRAFORM) fmt -recursive

# Validate Terraform configuration
tf-validate:
	cd $(TF_DIR) && $(TERRAFORM) validate

# Plan Terraform deployment
tf-plan: tf-fmt tf-validate
	cd $(TF_DIR) && $(TERRAFORM) plan

# Apply Terraform configuration
tf-apply: tf-fmt tf-validate
	cd $(TF_DIR) && $(TERRAFORM) apply

# Apply Terraform configuration with auto-approve (use with caution)
tf-apply-auto: tf-fmt tf-validate
	cd $(TF_DIR) && $(TERRAFORM) apply -auto-approve

# Destroy Terraform resources
tf-destroy:
	cd $(TF_DIR) && $(TERRAFORM) destroy

# Show Terraform outputs
tf-output:
	cd $(TF_DIR) && $(TERRAFORM) output

# Deploy to specific environment
deploy-dev: tf-init
	cd $(TF_DIR) && $(TERRAFORM) workspace select dev || $(TERRAFORM) workspace new dev
	cd $(TF_DIR) && $(TERRAFORM) apply -var="environment=dev"

deploy-test: tf-init
	cd $(TF_DIR) && $(TERRAFORM) workspace select test || $(TERRAFORM) workspace new test
	cd $(TF_DIR) && $(TERRAFORM) apply -var="environment=test"

deploy-prod: tf-init
	cd $(TF_DIR) && $(TERRAFORM) workspace select prod || $(TERRAFORM) workspace new prod
	cd $(TF_DIR) && $(TERRAFORM) apply -var="environment=prod"

# Run all checks before commit
check: format lint type-check test

# Create a new release
release:
	@echo "Creating a new release..."
	@read -p "Enter version number (current: $$(grep version pyproject.toml | cut -d'"' -f2)): " VERSION; \
	sed -i "s/version = \".*\"/version = \"$$VERSION\"/" pyproject.toml; \
	sed -i "s/__version__ = \".*\"/__version__ = \"$$VERSION\"/" src/__init__.py; \
	git add pyproject.toml src/__init__.py; \
	git commit -m "chore: bump version to $$VERSION"; \
	git tag -a "v$$VERSION" -m "Release version $$VERSION"; \
	echo "Release v$$VERSION created. Push with: git push && git push --tags"