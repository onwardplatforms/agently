"""Agently: Declarative AI Agent Framework."""

try:
    # If installed normally, _version.py will be generated by setuptools_scm
    from ._version import version as __version__
except ImportError:
    # For development or when running from source without installation
    try:
        from .version import __version__
    except ImportError:
        __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
