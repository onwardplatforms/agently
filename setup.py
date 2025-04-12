from setuptools import find_packages, setup
import os
import re
import subprocess

# Version configuration
version_args = {}

# If in CI/CD (GitHub Actions), use a fixed version
if os.environ.get("GITHUB_ACTIONS") == "true":
    # If this is a release with a tag, use the tag version
    if os.environ.get("GITHUB_REF", "").startswith("refs/tags/v"):
        tag = os.environ.get("GITHUB_REF", "").split("/")[-1]
        if tag.startswith("v"):
            version = tag[1:]  # Remove 'v' prefix
        print(f"CI/CD release build using tag version: {version}")
    else:
        # For non-release builds, use base version + git SHA
        try:
            git_sha = os.environ.get("GITHUB_SHA", "")
            if git_sha:
                short_sha = git_sha[:7]
                version = f"0.2.0.dev0+g{short_sha}"
            else:
                # Fallback if SHA isn't available
                version = "0.2.0.dev0"
            print(f"CI/CD build using version with git SHA: {version}")
        except Exception as e:
            print(f"Error getting git SHA: {e}, using fallback version")
            version = "0.2.0.dev0"
    
    version_args["version"] = version
else:
    # For local development, use setuptools_scm
    print("Local development using setuptools_scm")
    version_args["use_scm_version"] = {
        "fallback_version": "0.2.0.dev0"
    }

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
