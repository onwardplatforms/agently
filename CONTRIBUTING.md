# Contributing to Agently

Thank you for your interest in contributing to Agently! This document outlines how to contribute to the project effectively.

## Development Environment Setup

1. **Fork and clone the repository**
   ```bash
   git clone https://github.com/onwardplatforms/agently.git
   cd agently
   ```

2. **Set up the development environment**
   ```bash
   make install-dev
   ```
   This installs all dependencies and sets up pre-commit hooks.

3. **Set up environment variables**
   Create a `.env` file based on `.env.example`:
   ```bash
   cp .env.example .env
   # Edit .env with your API keys
   ```

## Development Workflow

1. **Create a branch for your work**
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes**
   - Write code
   - Include appropriate tests
   - Update documentation as needed

3. **Run tests**
   ```bash
   make test
   ```

4. **Format and lint your code**
   ```bash
   make format
   make lint
   ```

5. **Check type hints**
   ```bash
   make check
   ```

6. **Run all checks**
   ```bash
   make all
   ```

7. **Commit your changes**
   ```bash
   git add .
   git commit -m "Description of your changes"
   ```

## Pull Request Process

1. **Push your branch to GitHub**
   ```bash
   git push origin feature/your-feature-name
   ```

2. **Create a pull request**
   - Go to the GitHub repository
   - Click "Pull Requests" and then "New Pull Request"
   - Choose your branch and create the PR

3. **PR Guidelines**
   - Provide a clear description
   - Reference any related issues
   - Ensure all tests pass
   - Follow the code style

## Code Style

We follow these conventions:
- Black for code formatting
- isort for import sorting
- flake8 for linting
- Google-style docstrings

## Adding New Features

1. **Plugin Development**
   - Follow the plugin template in `examples/`
   - Include proper type hints and docstrings
   - Write tests for your plugin

2. **Core Functionality**
   - Discuss major changes in an issue first
   - Ensure backward compatibility
   - Update documentation

## License

By contributing, you agree that your contributions will be licensed under the project's MIT License.
