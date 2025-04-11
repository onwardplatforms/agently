# Agently Versioning Guide

This document outlines the versioning strategy for the Agently project.

## Version Number Format

Agently follows [Semantic Versioning](https://semver.org/) (SemVer) with the format `MAJOR.MINOR.PATCH`:

- **MAJOR** version (e.g., 1.0.0): Incompatible API changes
- **MINOR** version (e.g., 0.2.0): Add functionality in a backward-compatible manner
- **PATCH** version (e.g., 0.1.1): Backward-compatible bug fixes

## Pre-release Versions

For pre-release versions, we use the following suffixes according to [PEP 440](https://www.python.org/dev/peps/pep-0440/):

- **Alpha releases**: `0.2.0a1`, `0.2.0a2`, etc.
- **Beta releases**: `0.2.0b1`, `0.2.0b2`, etc.
- **Release candidates**: `0.2.0rc1`, `0.2.0rc2`, etc.
- **Development releases**: `0.2.0.dev0`, `0.2.0.dev1`, etc.

## Version Lifecycle

1. **Development**: Work happens on the `develop` branch with version `X.Y.Z.devN`
2. **Beta**: When features are ready for testing, we release a beta version `X.Y.ZbN`
3. **Release Candidate**: When the beta is stable, we release a release candidate `X.Y.ZrcN`
4. **Final Release**: When ready for production, we release the final version `X.Y.Z`

## When to Increment Versions

- **MAJOR**: When making incompatible API changes
- **MINOR**: When adding functionality in a backward-compatible manner
- **PATCH**: When making backward-compatible bug fixes
- **Pre-release**: When making changes to a pre-release version

## Release Process

1. Update the version in `setup.py`
2. Update the CHANGELOG.md with the changes
3. Create a release branch: `git checkout -b release/X.Y.Z`
4. Build and test the package: `make clean-dist build test`
5. Create a GitHub release with the appropriate tag
6. Release to PyPI: `make release`
7. Merge the release branch back to `main` and `develop`

## Examples

- `0.1.0`: First stable release
- `0.1.1`: Bug fix release
- `0.2.0.dev0`: Development version for 0.2.0
- `0.2.0b1`: Beta version for 0.2.0
- `0.2.0rc1`: Release candidate for 0.2.0
- `0.2.0`: Final release of 0.2.0 