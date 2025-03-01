"""Plugin source handling system."""

import importlib.util
import logging
import subprocess
import sys
import tempfile
import json
import re
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Type, Dict, Any, Tuple

from .base import Plugin

logger = logging.getLogger(__name__)


@dataclass
class PluginSource(ABC):
    """Base class for plugin sources."""

    @abstractmethod
    def load(self) -> Type[Plugin]:
        """Load the plugin class from this source.

        Returns:
            The plugin class

        Raises:
            ImportError: If the plugin cannot be imported
            ValueError: If the plugin is invalid
        """


@dataclass
class LocalPluginSource(PluginSource):
    """A plugin source from the local filesystem."""

    path: Path

    def load(self) -> Type[Plugin]:
        """Load a plugin from a local path.

        The path can point to either:
        1. A .py file containing the plugin class
        2. A directory containing an __init__.py with the plugin class

        Returns:
            The plugin class

        Raises:
            ImportError: If the plugin cannot be imported
            ValueError: If the plugin is invalid
        """
        path = Path(self.path)
        logger.info(f"Loading plugin from local path: {path}")

        if not path.exists():
            logger.error(f"Plugin path does not exist: {path}")
            raise ImportError(f"Plugin path does not exist: {path}")

        if path.is_file() and path.suffix == ".py":
            module_path = path
            module_name = path.stem
            logger.info(f"Loading plugin from Python file: {module_path}")
        elif path.is_dir() and (path / "__init__.py").exists():
            module_path = path / "__init__.py"
            module_name = path.name
            logger.info(f"Loading plugin from directory with __init__.py: {module_path}")
        else:
            logger.error(f"Plugin path must be a .py file or directory with __init__.py: {path}")
            raise ImportError(f"Plugin path must be a .py file or directory with __init__.py: {path}")

        # Import the module
        logger.debug(f"Creating module spec from file: {module_path}")
        spec = importlib.util.spec_from_file_location(module_name, module_path)
        if not spec or not spec.loader:
            logger.error(f"Could not load plugin spec from: {module_path}")
            raise ImportError(f"Could not load plugin spec from: {module_path}")

        logger.debug(f"Creating module from spec: {spec}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module

        logger.debug(f"Executing module: {module_name}")
        try:
            spec.loader.exec_module(module)
            logger.info(f"Module executed successfully: {module_name}")
        except Exception as e:
            logger.error(f"Error executing module {module_name}: {e}", exc_info=e)
            raise ImportError(f"Error executing module {module_name}: {e}") from e

        # Find the plugin class
        logger.debug(f"Searching for Plugin subclass in module: {module_name}")
        plugin_class = None
        for item_name in dir(module):
            item = getattr(module, item_name)
            logger.debug(f"Checking item: {item_name}, type: {type(item)}")

            # First try direct inheritance check
            if (
                isinstance(item, type)
                and hasattr(module, "Plugin")
                and issubclass(item, getattr(module, "Plugin"))
                and item != getattr(module, "Plugin")
            ):
                plugin_class = item
                logger.info(f"Found Plugin subclass via direct inheritance: {item_name}")
                break

            # If that fails, check for duck typing - does it have the required attributes of a Plugin?
            elif (
                isinstance(item, type)
                and hasattr(item, "name")
                and hasattr(item, "description")
                and hasattr(item, "plugin_instructions")
            ):
                # Check if it has the get_kernel_functions method
                if hasattr(item, "get_kernel_functions") and callable(getattr(item, "get_kernel_functions")):
                    plugin_class = item
                    logger.info(f"Found Plugin-compatible class via duck typing: {item_name}")
                    break

        if not plugin_class:
            logger.error(f"No Plugin subclass found in module: {module_path}")
            raise ValueError(f"No Plugin subclass found in module: {module_path}")

        logger.info(f"Successfully loaded plugin class: {plugin_class.__name__}")
        return plugin_class


@dataclass
class GitHubPluginSource(PluginSource):
    """A plugin source from a GitHub repository."""

    repo_url: str
    version: str = "main"  # Default to main branch if not specified
    plugin_path: str = ""  # Path within repo to the plugin (empty for root)
    namespace: str = ""  # User or organization name (extracted from repo_url if empty)
    name: str = ""  # Repository name (extracted from repo_url if empty)
    cache_dir: Optional[Path] = None

    def __post_init__(self):
        """Set up the cache directory and extract namespace/name if not provided."""
        # Set default cache directory to ./.agently/plugins if not specified
        if self.cache_dir is None:
            self.cache_dir = Path.cwd() / ".agently" / "plugins"

        # Ensure plugin_path is never None
        if self.plugin_path is None:
            self.plugin_path = ""

        # Extract namespace and name from repo_url if not provided
        if not self.namespace or not self.name:
            # Parse GitHub URL: user/org name and repo name
            match = re.match(r"github\.com/([^/]+)/([^/]+)", self.repo_url)
            if match:
                if not self.namespace:
                    self.namespace = match.group(1)
                if not self.name:
                    self.name = match.group(2)
            else:
                raise ValueError(f"Invalid GitHub repository URL: {self.repo_url}")

        # Normalize version string (handling tags with/without 'v' prefix)
        self._normalize_version()

    def _normalize_version(self):
        """Normalize version string for consistent handling."""
        # If version is specified with a 'v' prefix followed by a number, we'll store it
        # without the prefix for consistency, but we'll need to check both forms when checking out
        if re.match(r"^v\d+", self.version):
            logger.debug(f"Version specified with 'v' prefix: {self.version}")
            # Store the version without the 'v' prefix for cache path
            self._version_for_path = self.version[1:]
            # Keep the original version for checkout
            self._version_for_checkout = self.version
        elif re.match(r"^\d+", self.version):
            logger.debug(f"Version specified without 'v' prefix: {self.version}")
            # Store the version as is for cache path
            self._version_for_path = self.version
            # We'll try both with and without 'v' prefix during checkout
            self._version_for_checkout = self.version
        else:
            # For branch names or commit SHAs, use as is
            logger.debug(f"Version specified as branch or commit: {self.version}")
            self._version_for_path = self.version
            self._version_for_checkout = self.version

    def _get_cache_path(self) -> Path:
        """Get the path where this plugin version should be cached."""
        # Use normalized version for the cache path
        return self.cache_dir / self.namespace / self.name / self._version_for_path

    def _get_lockfile_path(self) -> Path:
        """Get the path to the lockfile for this plugin."""
        # Return the lockfile path at the same level as the .agently folder
        return Path.cwd() / "agently.lockfile.json"

    def _get_plugin_info(self) -> Dict[str, Any]:
        """Get information about this plugin for the lockfile."""
        return {
            "namespace": self.namespace,
            "name": self.name,
            "version": self.version,
            "repo_url": self.repo_url,
            "commit_sha": self._get_commit_sha(),
            "installed_at": self._get_current_timestamp(),
        }

    def _get_current_timestamp(self) -> str:
        """Get the current timestamp in ISO format."""
        from datetime import datetime

        return datetime.utcnow().isoformat()

    def _get_commit_sha(self, cache_path: Optional[Path] = None) -> str:
        """Get the full commit SHA for the currently checked out version."""
        if cache_path is None:
            cache_path = self._get_cache_path()

        if not cache_path.exists():
            return ""

        try:
            result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=cache_path, check=True, capture_output=True, text=True)
            return result.stdout.strip()
        except subprocess.CalledProcessError:
            logger.warning(f"Failed to get commit SHA for {cache_path}")
            return ""

    def _update_lockfile(self, plugin_info: Dict[str, Any]) -> None:
        """Update the lockfile with information about this plugin."""
        lockfile_path = self._get_lockfile_path()

        # Create lockfile directory if it doesn't exist
        lockfile_path.parent.mkdir(parents=True, exist_ok=True)

        # Read existing lockfile or create new one
        if lockfile_path.exists():
            try:
                with open(lockfile_path, "r") as f:
                    lockfile = json.load(f)
            except json.JSONDecodeError:
                logger.warning(f"Invalid lockfile at {lockfile_path}, creating new one")
                lockfile = {"plugins": {}}
        else:
            lockfile = {"plugins": {}}

        # Add or update plugin information
        plugin_key = f"{self.namespace}/{self.name}"
        lockfile["plugins"][plugin_key] = plugin_info

        # Write updated lockfile
        with open(lockfile_path, "w") as f:
            json.dump(lockfile, f, indent=2)

        logger.debug(f"Updated lockfile at {lockfile_path}")

    def load(self) -> Type[Plugin]:
        """Load a plugin from a GitHub repository.

        Returns:
            The plugin class

        Raises:
            ImportError: If the plugin cannot be imported
            ValueError: If the plugin is invalid
        """
        logger.info(f"Loading plugin from GitHub: {self.repo_url} at {self.version}")

        # Create cache directory structure
        cache_path = self._get_cache_path()
        cache_path.mkdir(parents=True, exist_ok=True)
        logger.debug(f"Using cache directory: {cache_path}")

        # Check if already cached and clone/update if needed
        if not (cache_path / ".git").exists():
            logger.info("Repository not cached, cloning from GitHub")
            self._clone_repository(cache_path)
        else:
            logger.info(f"Using cached repository at {cache_path}")
            # Optionally could add logic to update repo here if needed

        # Get the commit SHA and update lockfile
        commit_sha = self._get_commit_sha(cache_path)
        plugin_info = self._get_plugin_info()
        plugin_info["commit_sha"] = commit_sha
        self._update_lockfile(plugin_info)

        # Determine the path to the plugin within the repository
        if self.plugin_path:
            plugin_path = cache_path / self.plugin_path
        else:
            plugin_path = cache_path

        logger.info(f"Loading plugin from path: {plugin_path}")
        return LocalPluginSource(plugin_path).load()

    def _clone_repository(self, cache_path: Path) -> None:
        """Clone the repository to the cache directory."""
        try:
            # Remove directory if it exists but isn't a git repository
            if cache_path.exists():
                import shutil

                shutil.rmtree(cache_path)

            # Ensure directory exists
            cache_path.parent.mkdir(parents=True, exist_ok=True)

            # Clone the repository
            logger.debug(f"Running git clone for {self.repo_url}")
            git_url = f"https://{self.repo_url}"

            # First clone the repository
            subprocess.run(
                ["git", "clone", git_url, str(cache_path)],
                check=True,
                capture_output=True,
            )

            # Then checkout the specific version
            try:
                # First try with the original version string
                logger.debug(f"Attempting checkout with version: {self._version_for_checkout}")
                subprocess.run(
                    ["git", "checkout", self._version_for_checkout],
                    cwd=cache_path,
                    check=True,
                    capture_output=True,
                )
                logger.info(f"Successfully checked out {self._version_for_checkout}")
            except subprocess.CalledProcessError as e:
                # If version is numeric and checkout failed, try with 'v' prefix
                if re.match(r"^\d+", self.version) and not re.match(r"^v\d+", self.version):
                    try:
                        v_version = f"v{self.version}"
                        logger.debug(f"First attempt failed, trying with 'v' prefix: {v_version}")
                        subprocess.run(
                            ["git", "checkout", v_version],
                            cwd=cache_path,
                            check=True,
                            capture_output=True,
                        )
                        logger.info(f"Successfully checked out {v_version}")
                    except subprocess.CalledProcessError:
                        # Both attempts failed, raise the original error
                        raise e
                else:
                    # Rethrow the original error
                    raise e

            logger.info(f"Repository cloned successfully to {cache_path}")
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.decode()
            logger.error(f"Failed to clone or checkout repository: {error_msg}", exc_info=e)
            raise ImportError(f"Failed to clone repository {self.repo_url} at {self.version}: {error_msg}")
