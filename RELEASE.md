# Release Process Guide

This document explains the versioning and release process for the agently project.

## Versioning Strategy

Agently follows [PEP 440](https://www.python.org/dev/peps/pep-0440/) for versioning:

- **Development versions**: Automatically generated using setuptools_scm based on git history
  - After a v0.2.1 tag: `0.2.1.dev1+g3a4b5c6`, `0.2.1.dev2+g7d8e9f0`, etc.
- **Release versions**: Tagged in git and published as GitHub Releases
  - Clean versions: `v0.2.1`, `v0.3.0`, `v1.0.0`

## Development Workflow

During normal development:

1. Work in feature branches
2. Create pull requests to merge into main/develop
3. The version will be automatically calculated by setuptools_scm
4. CI tests will run on pull requests

## Creating a Release

To create a new release:

1. Go to GitHub → Releases → "Create a new release"
2. Choose a tag following semantic versioning (e.g., `v0.2.1`, `v1.0.0-beta1`)
3. Write release notes documenting changes
4. Click "Publish release"

## What Happens When You Create a Release

When you publish a release on GitHub:

1. GitHub Actions workflow is triggered
2. Cross-platform packages are built using setuptools_scm
3. PyPI package is published with this version
4. Standalone executables are built for each platform
5. Executables are attached to the GitHub Release

## Release Types

- **Production releases**: Use standard version numbers (`v1.0.0`, `v1.1.0`)
- **Pre-releases**: Use suffixes like beta or rc (`v1.0.0-beta1`, `v1.0.0rc1`)

## Installing Released Versions

Users can install releases via:

```bash
# From PyPI
pip install agently-cli

# Download and use standalone executables from GitHub Releases
# (platform-specific instructions)
``` 