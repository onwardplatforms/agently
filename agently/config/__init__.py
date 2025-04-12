"""Configuration package for agently."""

from pathlib import Path

# Define the path to the schema file for easy access
SCHEMA_PATH = Path(__file__).parent / "schema.json"

__all__ = ["SCHEMA_PATH"]
