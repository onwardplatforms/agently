# Agently Distribution Guide

This document covers how to distribute the Agently package using GitHub Actions.

## Local Development & Testing

For local development and testing:

```bash
# Install development dependencies
make install-dev

# Run tests
make test

# Build the package locally
make build

# Check the built package
make dist
```

## Release Process

1. **Update Version**: Update the version in `setup.py`

2. **Create a GitHub Release**: 
   - Go to the repository on GitHub
   - Navigate to "Releases"
   - Click "Draft a new release" 
   - Create a new tag (e.g., `v0.1.0`)
   - Add release notes
   - Publish the release

3. **Automated Publishing**: 
   - The GitHub Actions workflow will automatically:
     - Build the package
     - Run tests
     - Publish to PyPI

4. **Manual Publishing** (if needed):
   ```bash
   make release
   ```

## CI/CD Workflow

- **CI Workflow**: Runs tests on every push and pull request to main/develop branches
- **Publish Workflow**: Triggered when a new GitHub release is created

## PyPI Configuration

To set up PyPI publishing:

1. Create an API token on PyPI
2. Add these secrets to your GitHub repository:
   - `PYPI_USERNAME`: Use `__token__`
   - `PYPI_PASSWORD`: Your PyPI API token

## Installation for Users

Users can install the package with:

```bash
pip install agently-cli
```

After installation, users can create a new project:

```bash
# Create an agently.yaml file
# Run the CLI
agently init
agently run
```

Note: While the package name is `agently-cli`, the command to run is simply `agently`. 