from setuptools import find_packages, setup
import os
import re

# Use setuptools_scm to get version from git tags
# SETUPTOOLS_SCM_PRETEND_VERSION environment variable will override in GitHub Actions

setup(
    name="agently-cli",
    use_scm_version={
        "version_scheme": "no-guess-dev",
        "local_scheme": "no-local-version",
        "fallback_version": "0.2.0",
    },
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
