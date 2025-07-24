# Contributing to On-call Data Engineering AI Agent

We love your input! We want to make contributing to this project as easy and transparent as possible, whether it's:

- Reporting a bug
- Discussing the current state of the code
- Submitting a fix
- Proposing new features
- Becoming a maintainer

## We Develop with GitHub

We use GitHub to host code, to track issues and feature requests, as well as accept pull requests.

## We Use [GitHub Flow](https://guides.github.com/introduction/flow/index.html)

All code changes happen through pull requests:

1. Fork the repo and create your branch from `main`
2. If you've added code that should be tested, add tests
3. If you've changed APIs, update the documentation
4. Ensure the test suite passes
5. Make sure your code lints
6. Issue that pull request!

## Any contributions you make will be under the MIT Software License

In short, when you submit code changes, your submissions are understood to be under the same [MIT License](LICENSE) that covers the project.

## Report bugs using GitHub's [issues](https://github.com/paschmaria/on-call-data-engineering-ai-agent/issues)

We use GitHub issues to track public bugs. Report a bug by [opening a new issue](https://github.com/paschmaria/on-call-data-engineering-ai-agent/issues/new).

**Great Bug Reports** tend to have:

- A quick summary and/or background
- Steps to reproduce
  - Be specific!
  - Give sample code if you can
- What you expected would happen
- What actually happens
- Notes (possibly including why you think this might be happening, or stuff you tried that didn't work)

## Development Process

### Setting Up Development Environment

1. Clone your fork:
   ```bash
   git clone https://github.com/your-username/on-call-data-engineering-ai-agent.git
   cd on-call-data-engineering-ai-agent
   ```

2. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   pip install -r requirements-dev.txt
   ```

4. Set up pre-commit hooks:
   ```bash
   pre-commit install
   ```

### Code Style

We use several tools to maintain code quality:

- **Black** for code formatting
- **isort** for import sorting
- **flake8** for linting
- **mypy** for type checking

Run all checks:
```bash
# Format code
black src/ tests/
isort src/ tests/

# Lint
flake8 src/ tests/

# Type check
mypy src/
```

### Testing

We maintain high test coverage. Please write tests for new code:

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Run specific test file
pytest tests/test_tools.py -v
```

### Documentation

- Update docstrings for any new functions/classes
- Update README.md if adding new features
- Update SETUP.md if changing setup process
- Add inline comments for complex logic

## Pull Request Process

1. Update the README.md with details of changes to the interface
2. Update the docs/ with any new environment variables, dependencies, or deployment changes
3. Increase version numbers in any examples files and the README.md to the new version that this PR would represent
4. Ensure all tests pass and coverage remains high
5. The PR will be merged once you have the sign-off of at least one maintainer

### PR Title Convention

We follow conventional commits. PR titles should be:

- `feat:` New feature
- `fix:` Bug fix
- `docs:` Documentation only changes
- `style:` Changes that don't affect code meaning
- `refactor:` Code change that neither fixes a bug nor adds a feature
- `perf:` Performance improvement
- `test:` Adding missing tests
- `chore:` Changes to build process or auxiliary tools

Example: `feat: add support for BigQuery diagnostics`

## Feature Requests

We love feature requests! Please:

1. Check if the feature has already been requested
2. Open an issue with the `enhancement` label
3. Describe the feature and why it would be useful
4. Consider submitting a PR if you can implement it!

## Code Review Process

The core team looks at Pull Requests on a regular basis. We will provide feedback and may request changes. We appreciate your patience during the review process.

### What we look for:

- **Correctness**: Does the code do what it's supposed to?
- **Testing**: Are there adequate tests?
- **Documentation**: Is the code well-documented?
- **Performance**: Are there any performance concerns?
- **Security**: Are there any security implications?
- **Style**: Does it follow our coding standards?

## Community

Discussions about the project take place on:
- GitHub Issues for bugs and features
- GitHub Discussions for general questions
- Pull Request comments for code-specific discussions

## License

By contributing, you agree that your contributions will be licensed under its MIT License.

## Recognition

Contributors who submit accepted PRs will be added to our [Contributors list](README.md#contributors).

Thank you for contributing! 🎉