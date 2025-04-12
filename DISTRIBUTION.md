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

## Cross-Platform Building

You can build the package for different platforms locally:

```bash
# Build for all platforms (Linux, macOS, Windows)
make build-all

# Build for a specific platform
make build-linux
make build-macos
make build-windows

# Build for the current platform
make build-current
```

The builds will be placed in the `dist/<platform>` directory.

## Standalone Executables

You can also build standalone executables that don't require Python to be installed:

```bash
# Build executable for the current platform
make build-exe
```

The executable will be placed in `dist/executables/<platform>/` directory.

Note: To build executables for other platforms, you need to run the command on the respective platform, or use the GitHub Actions workflow.

## Release Process

1. **Update Version**: Update the version in `agently/version.py`

2. **Create a GitHub Release**: 
   - Go to the repository on GitHub
   - Navigate to "Releases"
   - Click "Draft a new release" 
   - Create a new tag (e.g., `v0.1.0`)
   - Add release notes
   - Publish the release

3. **Automated Publishing**: 
   - The GitHub Actions workflows will automatically:
     - Build the Python package for all platforms (Linux, macOS, Windows)
     - Build standalone executables for all platforms
     - Run tests
     - Publish the Python package to PyPI
     - Attach the executables to the GitHub release

4. **Manual Publishing** (if needed):
   - You can trigger a manual build and publish from GitHub by:
     - Go to Actions tab
     - Select "Manual Publish Python Package" or "Build Standalone Executables"
     - Click "Run workflow"
     - Enter version number
     - Start the workflow

## CI/CD Workflow

- **CI Workflow**: Runs tests on every push and pull request to main/develop branches
- **Build Workflow**: Builds the Python package for all platforms (Linux, macOS, Windows)
  - Runs on pushes to main/develop, pull requests, and when tags starting with 'v' are created
  - Publishes to PyPI automatically when a tag starting with 'v' is pushed
- **Build Executables Workflow**: Builds standalone executables for all platforms
  - Triggered when a GitHub release is created
  - Can also be run manually
  - Attaches executables to GitHub releases
- **Manual Publish Workflow**: Allows manual publication to PyPI
  - Useful for emergency deployments or when the automated process needs to be bypassed
  - Will be deprecated in the future

## Installation Options

### PyPI Installation

Users can install the package with:

```bash
pip install agently-cli
```

This requires Python to be installed on the user's system.

### Standalone Executable Installation

Users can download the standalone executable for their platform from the GitHub releases page. No Python installation is required.

1. Download the appropriate executable for your platform
2. Make it executable (Linux/macOS): `chmod +x agently`
3. Run it directly: `./agently` (Linux/macOS) or `agently.exe` (Windows)

## Usage

After installation, users can create a new project:

```bash
# Create an agently.yaml file
# Run the CLI
agently init
agently run
```

Note: While the package name is `agently-cli`, the command to run is simply `agently`. 