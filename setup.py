from setuptools import find_packages, setup
import os
import re

# Read version from version.py without importing the package
def read_version():
    version_file = os.path.join(os.path.dirname(__file__), "agently", "version.py")
    with open(version_file, "r") as f:
        version_line = f.read()
    version_match = re.search(r"^__version__ = ['\"]([^'\"]*)['\"]", version_line, re.M)
    if version_match:
        return version_match.group(1)
    raise RuntimeError("Unable to find version string.")

setup(
    name="agently-cli",
    version=read_version(),
    description="Declarative AI Agent Framework",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    author="Onward Platforms",
    author_email="info@onwardplatforms.com",
    url="https://github.com/onwardplatforms/agently",
    license="MIT",
    packages=find_packages(),
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
