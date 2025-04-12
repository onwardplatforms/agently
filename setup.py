from setuptools import find_packages, setup
import os
import re
import subprocess

# Version configuration
version_args = {}

# If in CI/CD (GitHub Actions) and this is a release (tag)
if os.environ.get("GITHUB_ACTIONS") == "true" and os.environ.get("GITHUB_REF", "").startswith("refs/tags/"):
    # Extract version from the tag (v0.2.0 -> 0.2.0)
    version = os.environ.get("GITHUB_REF_NAME", "").lstrip("v")
    print(f"Building release version: {version}")
    version_args["version"] = version
else:
    # For local development and non-release CI builds, use setuptools_scm
    print("Using setuptools_scm for development versioning")
    version_args["use_scm_version"] = True

setup(
    name="agently-cli",
    **version_args,
    description="Declarative AI Agent Framework",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    author="Onward Platforms",
    author_email="info@onwardplatforms.com",
    url="https://github.com/onwardplatforms/agently",
    license="MIT",
    packages=find_packages(include=['agently', 'agently.*']),
    package_data={
        'agently': ['config/*.json'],
    },
    install_requires=[
        "click",
        "semantic-kernel",
        "semantic-kernel[mcp]",
        "python-dotenv",
        "aiohttp",
        "jsonschema",
        "pyyaml",
        "requests",
        "typing-extensions",
        "agently-sdk",
        "azure-identity",
        "ollama",
        "mcp",
        "prompt_toolkit",
    ],
    extras_require={
        "test": [
            "pytest",
            "pytest-asyncio",
            "pytest-cov",
            "pytest-mock",
            "pytest-timeout",
        ],
        "dev": [
            "black",
            "flake8",
            "flake8-docstrings",
            "isort",
            "mypy",
            "pre-commit",
            "pydantic",
            "types-requests",
            "autoflake",
            "types-jsonschema",
            "types-PyYAML",
        ],
    },
    entry_points={
        "console_scripts": [
            "agently=agently.cli.commands:cli",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    python_requires=">=3.8",
    include_package_data=True,
)
