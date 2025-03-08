"""Plugin source handling system."""

import importlib.util
import json
import logging
import re
import subprocess
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Type, cast

from typing_extensions import Protocol

from .base import Plugin

logger = logging.getLogger(__name__)


# Define a Protocol for Plugin classes
class PluginClass(Protocol):
    """A class that implements the Plugin interface."""

    namespace: str
    name: str


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

    @abstractmethod
    def _get_current_sha(self) -> str:
        """Get the current SHA for this plugin source.

        Returns:
            A string representation of the current SHA, or empty string if unavailable
        """

    def needs_update(self, lockfile_sha: str) -> bool:
        """Check if the plugin needs to be updated based on SHA.

        Args:
            lockfile_sha: SHA from the lockfile

        Returns:
            True if the plugin needs updating, False otherwise
        """
        # Get current SHA using subclass-specific implementation
        current_sha = self._get_current_sha()

        # If current SHA is empty, it could mean:
        # 1. The plugin directory doesn't exist
        # 2. We couldn't calculate a SHA for some reason
        if not current_sha:
            # If there's a SHA in the lockfile, but we can't get a current SHA,
            # we should update (may need reinstallation)
            return bool(lockfile_sha)

        # If lockfile SHA is empty, we should update
        if not lockfile_sha:
            return True

        # Compare SHAs - if different, we need to update
        return current_sha != lockfile_sha


@dataclass
class LocalPluginSource(PluginSource):
    """A plugin source from the local filesystem."""

    path: Path
    namespace: str = "local"  # Default namespace for local plugins
    name: str = ""  # Optional name override, defaults to directory name
    force_reinstall: bool = False  # Whether to force reinstallation

    def _get_current_sha(self) -> str:
        """Get the current SHA for this plugin source.

        Returns:
            SHA calculated from the plugin files
        """
        return self._calculate_plugin_sha()

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

        # Determine the plugin name if not provided
        plugin_name = self.name
        if not plugin_name:
            plugin_name = path.stem if path.is_file() else path.name

        # Check if we need to reinstall by comparing SHAs
        should_reinstall = self.force_reinstall

        # If not forcing reinstall, check if the SHA has changed
        if not should_reinstall:
            # Calculate the current SHA
            current_sha = self._calculate_plugin_sha()

            # Get the SHA from the lockfile if it exists
            lockfile_path = Path.cwd() / "agently.lockfile.json"
            if lockfile_path.exists():
                try:
                    with open(lockfile_path, "r") as f:
                        lockfile = json.load(f)

                    # Get the plugin key
                    plugin_key = f"{self.namespace}/{plugin_name}"

                    # Check if the plugin exists in the lockfile and get its SHA
                    if plugin_key in lockfile.get("plugins", {}):
                        lockfile_sha = lockfile["plugins"][plugin_key].get("sha", "")

                        # If the SHA has changed, we should reinstall
                        if lockfile_sha and lockfile_sha != current_sha:
                            logger.info(f"Plugin SHA has changed, reinstalling: {lockfile_sha} -> {current_sha}")
                            should_reinstall = True
                except Exception as e:
                    logger.warning(f"Failed to check SHA from lockfile: {e}")
                    # If we can't check the SHA, we'll continue with loading

        if should_reinstall:
            logger.info(f"Reinstalling local plugin (force={self.force_reinstall})")
            # For local plugins, reinstallation just means reloading the module
            # We don't need to do anything special here since we'll reload it anyway

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

        # Set the namespace and name on the plugin class
        plugin_class_with_attrs = cast(PluginClass, plugin_class)
        plugin_class_with_attrs.namespace = self.namespace
        plugin_class_with_attrs.name = plugin_name

        # Note: We no longer update the lockfile here, as it's handled by the _initialize_plugins function

        logger.info(f"Successfully loaded plugin class: {plugin_class.__name__} as {self.namespace}/{plugin_name}")
        return plugin_class

    def _calculate_plugin_sha(self) -> str:
        """Calculate a SHA for the plugin directory or file.

        For directories, this creates a SHA based on file contents and structure.
        For single files, it uses the file's content.

        Returns:
            A SHA string representing the plugin's current state
        """
        import hashlib

        path = Path(self.path)
        logger.debug(f"Calculating SHA for plugin at path: {path}")

        if not path.exists():
            logger.warning(f"Path does not exist, cannot calculate SHA: {path}")
            return ""

        if path.is_file():
            # For a single file, hash its contents
            try:
                with open(path, "rb") as f:
                    file_hash = hashlib.sha256(f.read()).hexdigest()
                logger.debug(f"Calculated SHA for file {path}: {file_hash[:8]}...")
                return file_hash
            except Exception as e:
                logger.warning(f"Failed to calculate SHA for file {path}: {e}")
                return ""
        else:
            # For a directory, create a composite hash of all Python files
            try:
                hasher = hashlib.sha256()

                # Get all Python files in the directory and subdirectories
                python_files = sorted(path.glob("**/*.py"))
                logger.debug(f"Found {len(python_files)} Python files in {path}")

                for py_file in python_files:
                    # Add the relative path to the hash
                    rel_path = py_file.relative_to(path)
                    hasher.update(str(rel_path).encode())

                    # Add the file content to the hash
                    with open(py_file, "rb") as f:
                        hasher.update(f.read())

                dir_hash = hasher.hexdigest()
                logger.debug(f"Calculated SHA for directory {path}: {dir_hash[:8]}...")
                return dir_hash
            except Exception as e:
                logger.warning(f"Failed to calculate SHA for directory {path}: {e}")
                return ""

    def _get_plugin_info(self, plugin_class: Type[Plugin]) -> Dict[str, Any]:
        """Get information about the plugin for the lockfile.

        Args:
            plugin_class: The loaded plugin class

        Returns:
            Dict with plugin information
        """
        # Calculate a SHA for the plugin directory/file
        plugin_sha = self._calculate_plugin_sha()

        # Get current timestamp in ISO format for consistency with GitHub plugins
        from datetime import datetime

        current_time = datetime.utcnow().isoformat()

        plugin_class_with_attrs = cast(PluginClass, plugin_class)
        return {
            "namespace": plugin_class_with_attrs.namespace,  # Store namespace
            "name": plugin_class_with_attrs.name,  # Store name without prefix for consistency
            "full_name": plugin_class_with_attrs.name,  # Store full name
            "version": "local",  # Local plugins don't have versions
            "source_type": "local",
            "source_path": str(self.path),
            "sha256": plugin_sha,  # Store SHA for change detection
            "installed_at": current_time,  # Use ISO format timestamp for consistency
        }


@dataclass
class GitHubPluginSource(PluginSource):
    """A plugin source from a GitHub repository."""

    repo_url: str
    version: str = "main"  # Default to main branch if not specified
    plugin_path: str = ""  # Path within repo to the plugin (empty for root)
    namespace: str = ""  # User or organization name (extracted from repo_url if empty)
    name: str = ""  # Repository name (extracted from repo_url if empty)
    cache_dir: Optional[Path] = None
    force_reinstall: bool = False  # Whether to force reinstallation

    # Plugin prefix standard
    PLUGIN_PREFIX = "agently-plugin-"

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
            # Parse GitHub URL: support multiple formats
            # 1. github.com/user/agently-plugin-name
            # 2. https://github.com/user/agently-plugin-name
            # 3. user/agently-plugin-name
            # 4. user/name (without prefix, will add prefix automatically)

            # Remove https:// prefix if present
            clean_url = re.sub(r"^https?://", "", self.repo_url)

            # Remove github.com/ prefix if present
            clean_url = re.sub(r"^github\.com/", "", clean_url)

            # Now we should have user/repo format
            match = re.match(r"([^/]+)/([^/]+)", clean_url)
            if match:
                if not self.namespace:
                    self.namespace = match.group(1)

                if not self.name:
                    repo_name = match.group(2)

                    # Store the full repo name (with or without prefix)
                    self.full_repo_name = repo_name

                    # If the name doesn't have the prefix, we'll add it for the actual repo URL
                    if not repo_name.startswith(self.PLUGIN_PREFIX):
                        self.full_repo_name = f"{self.PLUGIN_PREFIX}{repo_name}"
                        # The name for storage is just the original name
                        self.name = repo_name
                    else:
                        # If it already has the prefix, strip it for storage
                        self.name = repo_name[len(self.PLUGIN_PREFIX) :]

                # Update repo_url to ensure it has the correct format with prefix
                self.repo_url = f"github.com/{self.namespace}/{self.full_repo_name}"
            else:
                raise ValueError(
                    f"Invalid GitHub repository format: {self.repo_url}. Expected format: user/name or github.com/user/name"
                )

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

    def _get_current_sha(self) -> str:
        """Get the current SHA for this plugin source.

        Returns:
            SHA from the git repository, or empty string if unavailable
        """
        # Determine the plugin directory name
        plugin_dir = self.cache_dir / self.name

        # If directory doesn't exist, we can't get a SHA
        if not plugin_dir.exists():
            return ""

        # Get SHA from the repository
        return self._get_repo_sha(plugin_dir)

    def _get_plugin_info(self, plugin_class: Type[Plugin]) -> Dict[str, Any]:
        """Get information about the plugin for the lockfile.

        Args:
            plugin_class: The loaded plugin class

        Returns:
            Dict with plugin information
        """
        # Get the plugin directory
        plugin_dir = self.cache_dir / self.name

        # Get the commit SHA
        commit_sha = self._get_repo_sha(plugin_dir)

        # Get current timestamp in ISO format
        from datetime import datetime

        current_time = datetime.utcnow().isoformat()

        return {
            "namespace": plugin_class.namespace,
            "name": plugin_class.name,
            "full_name": f"{self.namespace}/{self.name}",
            "version": self.version,
            "source_type": "github",
            "repo_url": self.repo_url,
            "plugin_path": self.plugin_path,
            "commit_sha": commit_sha,
            "installed_at": current_time,
        }

    def _get_repo_sha(self, repo_path: Path) -> str:
        """Get the current commit SHA of the repository.

        Args:
            repo_path: Path to the repository

        Returns:
            The commit SHA as a string
        """
        try:
            # Run git command to get the current commit SHA
            result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo_path, capture_output=True, text=True, check=True)
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            logger.warning(f"Failed to get commit SHA: {e}")
            return ""

    def load(self) -> Type[Plugin]:
        """Load a plugin from a GitHub repository.

        This will:
        1. Clone the repository if it doesn't exist
        2. Update the repository if it already exists
        3. Import the plugin module
        4. Find and return the plugin class

        Returns:
            The plugin class

        Raises:
            ImportError: If the plugin cannot be imported
            ValueError: If the plugin is invalid
        """
        # Ensure the cache directory exists
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Determine the plugin directory name (repo name without prefix)
        plugin_dir_name = self.name

        # Full path to the plugin directory
        plugin_dir = self.cache_dir / plugin_dir_name

        # Check if we need to clone/update the repository
        if not plugin_dir.exists() or self.force_reinstall:
            # Clone or update the repository
            self._clone_or_update_repo(plugin_dir)
        else:
            # Check if we need to update based on SHA
            should_update = False

            try:
                # Get the current commit SHA
                current_sha = self._get_repo_sha(plugin_dir)

                # Check if the SHA has changed
                lockfile_path = Path.cwd() / "agently.lockfile.json"
                if lockfile_path.exists():
                    with open(lockfile_path, "r") as f:
                        lockfile = json.load(f)

                    # Get the plugin key
                    plugin_key = f"{self.namespace}/{self.name}"

                    # Check if the plugin exists in the lockfile and get its SHA
                    if plugin_key in lockfile.get("plugins", {}):
                        lockfile_sha = lockfile["plugins"][plugin_key].get("commit_sha", "")

                        # If the SHA has changed, we should update
                        if lockfile_sha and lockfile_sha != current_sha:
                            logger.info(f"Plugin SHA has changed, updating: {lockfile_sha} -> {current_sha}")
                            should_update = True
            except Exception as e:
                logger.warning(f"Failed to check SHA from lockfile: {e}")
                # If we can't check the SHA, we'll continue with loading

            if should_update:
                # Update the repository
                self._clone_or_update_repo(plugin_dir)

        # Determine the plugin module path
        if self.plugin_path:
            # Use the specified path within the repo
            module_path = plugin_dir / self.plugin_path
        else:
            # Use the repo root
            module_path = plugin_dir

        # Check if the module path exists
        if not module_path.exists():
            raise ImportError(f"Plugin path does not exist: {module_path}")

        # Import the plugin module
        if module_path.is_file() and module_path.suffix == ".py":
            # Single file plugin
            spec = importlib.util.spec_from_file_location(self.name, module_path)
            if not spec or not spec.loader:
                raise ImportError(f"Could not load plugin spec from: {module_path}")

            module = importlib.util.module_from_spec(spec)
            sys.modules[self.name] = module
            spec.loader.exec_module(module)
        elif module_path.is_dir() and (module_path / "__init__.py").exists():
            # Package plugin
            sys.path.insert(0, str(module_path.parent))
            try:
                module = importlib.import_module(module_path.name)
            finally:
                sys.path.pop(0)
        else:
            raise ImportError(f"Plugin path must be a .py file or directory with __init__.py: {module_path}")

        # Find the plugin class
        plugin_class = None
        for item_name in dir(module):
            item = getattr(module, item_name)

            # Check if it's a Plugin subclass
            if (
                isinstance(item, type)
                and item.__module__ == module.__name__
                and hasattr(item, "name")
                and hasattr(item, "description")
                and hasattr(item, "plugin_instructions")
                and hasattr(item, "get_kernel_functions")
                and callable(getattr(item, "get_kernel_functions"))
            ):
                plugin_class = item
                break

        if not plugin_class:
            raise ValueError(f"No Plugin class found in module: {module_path}")

        # Set the namespace and name on the plugin class
        plugin_class_with_attrs = cast(PluginClass, plugin_class)
        plugin_class_with_attrs.namespace = self.namespace
        plugin_class_with_attrs.name = self.name

        # Note: We no longer update the lockfile here, as it's handled by the _initialize_plugins function

        return plugin_class

    def _clone_or_update_repo(self, cache_path: Path) -> None:
        """Clone or update the repository to the cache directory."""
        try:
            # If force_reinstall is True, remove the directory if it exists
            if self.force_reinstall and cache_path.exists():
                import shutil

                logger.info(f"Force reinstall enabled, removing existing directory: {cache_path}")
                shutil.rmtree(cache_path)
            # Otherwise, remove directory only if it exists but isn't a git repository
            elif cache_path.exists() and not (cache_path / ".git").exists():
                import shutil

                logger.debug(f"Directory exists but is not a git repository, removing: {cache_path}")
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

    def remove_from_lockfile(self) -> None:
        """Remove this plugin from the lockfile."""
        lockfile_path = self._get_lockfile_path()

        if not lockfile_path.exists():
            logger.debug(f"No lockfile found at {lockfile_path}, nothing to remove")
            return

        try:
            with open(lockfile_path, "r") as f:
                lockfile = json.load(f)
        except json.JSONDecodeError:
            logger.warning(f"Invalid lockfile at {lockfile_path}, cannot remove plugin")
            return

        # Use consistent key format
        plugin_key = f"{self.namespace}/{self.name}"

        # Remove the plugin entry if it exists
        if plugin_key in lockfile.get("plugins", {}):
            logger.info(f"Removing plugin {plugin_key} from lockfile")
            lockfile["plugins"].pop(plugin_key)

            # Write updated lockfile
            with open(lockfile_path, "w") as f:
                json.dump(lockfile, f, indent=2)
        else:
            logger.debug(f"Plugin {plugin_key} not found in lockfile")
