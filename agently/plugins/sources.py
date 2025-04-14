"""Plugin source handling system."""

import importlib.util
import inspect
import json
import logging
import re
import subprocess
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
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

    name: str = field(default="")
    force_reinstall: bool = field(default=False)

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

    @abstractmethod
    def _get_cache_path(self) -> Path:
        """Get the path where this plugin should be cached.

        Returns:
            Path to the cache directory for this plugin
        """

    @abstractmethod
    def _calculate_plugin_sha(self) -> str:
        """Calculate a SHA for the plugin.

        Returns:
            A SHA string representing the plugin's current state
        """

    def needs_update(self, lockfile_sha: str) -> bool:
        """Check if the plugin needs to be updated based on lockfile SHA.

        Args:
            lockfile_sha: SHA hash from lockfile

        Returns:
            True if plugin needs update, False otherwise
        """
        try:
            logger.info(f"Checking if plugin {self.name} needs update (lockfile_sha: {lockfile_sha})")
            logger.info(f"Plugin type: {getattr(self, 'plugin_type', 'unknown')}")
            logger.info(f"Path: {getattr(self, 'path', 'unknown')}")

            # If force_reinstall is True, always update
            if self.force_reinstall:
                logger.debug(f"Force reinstall enabled for {self.name}")
                return True

            # Get the plugin directory - use _get_cache_path instead of _get_plugin_dir
            plugin_dir = self._get_cache_path()
            logger.info(f"Plugin directory: {plugin_dir}, exists: {plugin_dir.exists()}")

            # If plugin_dir doesn't exist, it needs to be installed
            if not plugin_dir.exists():
                logger.debug(f"Plugin directory does not exist: {plugin_dir}")
                return True

            # For Git repositories, check commit SHA
            git_dir = plugin_dir / ".git"
            logger.info(f"Git directory: {git_dir}, exists: {git_dir.exists()}")

            if git_dir.exists():
                current_sha = self._get_current_sha()
                logger.info(f"Current SHA: {current_sha}")

                if not current_sha:
                    logger.warning(f"Could not get commit SHA for {self.name}")
                    return True

                if not lockfile_sha:
                    logger.debug(f"No lockfile SHA for {self.name}, assuming update needed")
                    return True

                if current_sha != lockfile_sha:
                    logger.debug(f"SHA mismatch for {self.name}: {current_sha} != {lockfile_sha}")
                    return True

                logger.info(f"SHAs match, no update needed for {self.name}")
                return False
            else:
                # For local plugins, check file hash if lockfile has a SHA
                logger.info("Not a git repository, treating as local plugin")
                if lockfile_sha:
                    current_sha = self._calculate_plugin_sha()
                    logger.info(f"Calculated SHA: {current_sha}")
                    logger.info(f"Lockfile SHA: {lockfile_sha}")
                    logger.info(f"SHA match? {current_sha == lockfile_sha}")

                    if not current_sha:
                        logger.debug(f"Failed to calculate SHA for {self.name}")
                        return True
                    if current_sha != lockfile_sha:
                        logger.debug(f"Local SHA mismatch for {self.name}: {current_sha} != {lockfile_sha}")
                        return True
                    # If SHA matches, no update needed
                    logger.info(f"Local plugin SHA matches, no update needed for {self.name}")
                    return False
                else:
                    # If no lockfile SHA is provided, we need to update to generate one
                    logger.debug(f"No lockfile SHA for local plugin {self.name}, updating to generate one")
                    return True

            # Default fallback - no update needed if we get to this point
            logger.info(f"No update criteria matched, assuming no update needed for {self.name}")
            return False
        except Exception as e:
            logger.warning(f"Error checking if plugin needs update: {e}")
            # If we can't determine, assume update is needed
            return True


class LocalPluginSource(PluginSource):
    """A plugin source from the local filesystem."""

    def __init__(
        self,
        path: Path,
        name: str = "",
        force_reinstall: bool = False,
        namespace: str = "local",
        plugin_type: str = "sk",
        cache_dir: Optional[Path] = None,
    ):
        """Initialize a local plugin source."""
        super().__init__(name=name, force_reinstall=force_reinstall)
        self.path = path
        self.namespace = namespace
        self.plugin_type = plugin_type
        self.cache_dir = cache_dir

        # Set default cache directory based on plugin type
        if self.cache_dir is None:
            self.cache_dir = Path.cwd() / ".agently" / "plugins" / self.plugin_type

    def _get_current_sha(self) -> str:
        """Get the current SHA for this plugin source.

        Returns:
            SHA calculated from the plugin files
        """
        return self._calculate_plugin_sha()

    def _get_cache_path(self) -> Path:
        """Get the path where this plugin should be cached.

        Returns:
            Path to the cache directory for this plugin
        """
        # For local plugins, the cache path is the actual plugin path, not a cache directory
        return self.path

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

                    # Determine where to check based on plugin type
                    target_section = "mcp" if self.plugin_type == "mcp" else "sk"

                    # Check if the plugin exists in the lockfile and get its SHA
                    if plugin_key in lockfile.get("plugins", {}).get(target_section, {}):
                        lockfile_sha = lockfile["plugins"][target_section][plugin_key].get("sha", "")

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

        # Add logging to debug plugin type issues
        logger.debug(f"Plugin type specified in source: {self.plugin_type}")
        if hasattr(plugin_class, "get_plugin_type"):
            logger.debug(f"Plugin class has get_plugin_type: {plugin_class.get_plugin_type()}")
        else:
            logger.debug("Plugin class does not have get_plugin_type method")

        # Log all relevant attributes to diagnose 'agently' issue
        logger.debug(f"Plugin class attributes: {dir(plugin_class)}")
        logger.debug(f"Plugin class bases: {plugin_class.__bases__}")
        if hasattr(plugin_class, "__module__"):
            logger.debug(f"Plugin class module: {plugin_class.__module__}")

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
            "plugin_type": self.plugin_type,  # Store plugin type (sk or mcp)
            "source_path": str(self.path),
            "sha": plugin_sha,  # Store SHA for change detection
            "installed_at": current_time,  # Use ISO format timestamp for consistency
        }


class GitHubPluginSource(PluginSource):
    """A plugin source from a GitHub repository."""

    # Plugin prefix standard
    PLUGIN_PREFIX = "agently-plugin-"
    # MCP prefix standard
    MCP_PREFIX = "agently-mcp-"

    def __init__(
        self,
        repo_url: str,
        name: str = "",
        force_reinstall: bool = False,
        plugin_path: str = "",
        namespace: str = "",
        version: str = "main",
        cache_dir: Optional[Path] = None,
        plugin_type: str = "sk",
    ):
        """Initialize a GitHub plugin source."""
        super().__init__(name=name, force_reinstall=force_reinstall)
        self.repo_url = repo_url
        self.plugin_path = plugin_path
        self.namespace = namespace
        self.version = version
        self.cache_dir = cache_dir
        self.plugin_type = plugin_type

        # Initialize full_repo_name to ensure it always exists
        self.full_repo_name = ""
        # Store the original owner for URL construction
        self.repo_owner = ""

        # Set default cache directory based on plugin type
        if self.cache_dir is None:
            self.cache_dir = Path.cwd() / ".agently" / "plugins" / self.plugin_type

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
                # Extract owner (user/org)
                self.repo_owner = match.group(1)

                # Set namespace if not provided
                if not self.namespace:
                    self.namespace = match.group(1)

                # Extract repo name
                repo_name = match.group(2)

                # Store original repo name
                original_repo_name = repo_name

                if not self.name:
                    # Handle repository name based on plugin type
                    if self.plugin_type == "mcp":
                        # For MCP servers, use the repo name as-is for full_repo_name
                        self.full_repo_name = repo_name

                        # Remove MCP prefix if present for storage name
                        if repo_name.startswith(self.MCP_PREFIX):
                            self.name = repo_name[len(self.MCP_PREFIX) :]
                        else:
                            self.name = repo_name
                    else:
                        # For SK plugins, handle the plugin prefix
                        # If the name doesn't have the prefix, we'll add it for the actual repo URL
                        if not repo_name.startswith(self.PLUGIN_PREFIX):
                            self.full_repo_name = f"{self.PLUGIN_PREFIX}{repo_name}"
                            # The name for storage is just the original name
                            self.name = repo_name
                        else:
                            # If it already has the prefix, strip it for storage
                            self.name = repo_name[len(self.PLUGIN_PREFIX) :]
                            self.full_repo_name = repo_name

                # IMPORTANT: Update repo_url to preserve the original owner
                # instead of using namespace which might be different
                if self.plugin_type == "mcp":
                    # For MCP servers, use the original repo name and owner
                    self.repo_url = f"github.com/{self.repo_owner}/{original_repo_name}"
                else:
                    # For SK plugins, use full_repo_name which may have the plugin prefix added
                    # but keep the original owner
                    self.repo_url = f"github.com/{self.repo_owner}/{self.full_repo_name}"
            else:
                raise ValueError(
                    f"Invalid GitHub repository format: {self.repo_url}. Expected format: user/name or github.com/user/name"
                )

        # Normalize the version string to the format Git expects.
        self._version_normalized = True

    def _get_cache_path(self) -> Path:
        """Get the path where this plugin version should be cached."""
        # The actual clone location is just the plugin name under the cache directory
        return self.cache_dir / self.name

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

        # For MCP plugins, ensure we use the correct namespace from the repository URL
        if self.plugin_type == "mcp":
            # Extract the namespace from repo_url to ensure consistency
            clean_url = re.sub(r"^https?://", "", self.repo_url)
            clean_url = re.sub(r"^github\.com/", "", clean_url)
            match = re.match(r"([^/]+)/([^/]+)", clean_url)
            if match:
                namespace = match.group(1)
                repo_name = match.group(2)
                full_name = f"{namespace}/{repo_name}"
            else:
                namespace = self.namespace
                full_name = f"{self.namespace}/{self.name}"
        else:
            # For other plugin types, use the standard namespace and name
            namespace = plugin_class.namespace
            full_name = f"{self.namespace}/{self.name}"

        return {
            "namespace": namespace,
            "name": plugin_class.name,
            "full_name": full_name,
            "version": self.version,
            "source_type": "github",
            "plugin_type": self.plugin_type,  # Store plugin type (sk or mcp)
            "repo_url": self.repo_url,
            "plugin_path": self.plugin_path,
            "sha": commit_sha,
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
        try:
            # Ensure the cache directory exists
            self.cache_dir.mkdir(parents=True, exist_ok=True)

            logger.debug(f"Loading GitHub plugin: {self.name} from {self.repo_url}")
            logger.debug(f"Cache directory: {self.cache_dir}")
            logger.debug(f"Plugin type: {self.plugin_type}")

            # Get the plugin directory - use _get_cache_path
            cache_path = self._get_cache_path()
            logger.debug(f"Cache path: {cache_path}")

            # Clone or update the repository
            logger.debug(f"Cloning or updating repository to {cache_path}")
            self._clone_or_update_repo(cache_path)
            logger.debug("Repository cloned/updated")

            # For MCP plugin type, create a placeholder plugin class
            if self.plugin_type == "mcp":
                logger.debug(f"Creating MCP server plugin class for {self.name}")

                # Create a new class for this MCP server plugin
                class MCPServerPlugin(Plugin):
                    """Placeholder for MCP server plugin."""

                    name = self.name
                    description = "MCP Server plugin"
                    namespace = self.namespace
                    plugin_instructions = "This plugin provides access to an MCP server."

                    @classmethod
                    def get_kernel_functions(cls):
                        """Return an empty dictionary for MCP server plugins."""
                        return {}

                    @classmethod
                    def get_mcp_command(cls, repo_path=None, **kwargs):
                        """Return the MCP command for this plugin."""
                        # Base command data
                        command_data = {}

                        # Get the command from the plugin configuration
                        if hasattr(cls, "mcp_command"):
                            command_data["command"] = cls.mcp_command
                        else:
                            # Use the default command: python -m mcp_server_git.main
                            command_data["command"] = "python"
                            command_data["args"] = ["-m", "mcp_server_git.main"]

                        # Update with kwargs if provided
                        if kwargs:
                            command_data.update(kwargs)

                        return command_data

                # Fix name clashes
                MCPServerPlugin.__name__ = f"MCPServerPlugin_{self.name}"
                MCPServerPlugin.__qualname__ = f"MCPServerPlugin_{self.name}"

                logger.debug(f"Created MCP Server Plugin class: {MCPServerPlugin.__name__}")
                return MCPServerPlugin

            # For other plugin types, try to import from the repository
            logger.debug(f"Importing plugin module from {cache_path}")

            # Handle plugin path
            if self.plugin_path:
                plugin_dir = cache_path / self.plugin_path
                logger.debug(f"Using plugin path: {plugin_dir}")
            else:
                plugin_dir = cache_path
                logger.debug(f"Using repository root as plugin path: {plugin_dir}")

            sys.path.insert(0, str(plugin_dir.parent))
            plugin_dir_name = plugin_dir.name

            try:
                logger.debug(f"Attempting to import plugin module: {plugin_dir_name}")
                plugin_module = importlib.import_module(plugin_dir_name)
                logger.debug(f"Plugin module imported: {plugin_module}")

                # Find the plugin class - look for both regular Plugin inheritance
                # and Agently SDK Plugin classes
                plugin_class = None
                for attr_name in dir(plugin_module):
                    attr = getattr(plugin_module, attr_name)

                    # Check if it's a class
                    if not inspect.isclass(attr):
                        continue

                    # Option 1: Check if it's a subclass of our Plugin class
                    if issubclass(attr, Plugin) and attr != Plugin:
                        plugin_class = attr
                        logger.debug(f"Found plugin class via inheritance: {plugin_class}")
                        break

                    # Option 2: Check if it's an Agently SDK Plugin class
                    # Look for the commonly used naming pattern and required attributes
                    if "Plugin" in attr_name and hasattr(attr, "name") and hasattr(attr, "description"):
                        logger.debug(f"Found Agently SDK plugin class: {attr}")

                        # Create a wrapper Plugin class
                        plugin_class = self._create_sdk_plugin_wrapper(attr)
                        logger.debug(f"Created wrapper for SDK plugin: {plugin_class.__name__}")
                        break

                if plugin_class is None:
                    # Try to find a module named "plugin.py" or similar
                    logger.debug("No plugin class found in module, checking for plugin.py")
                    for search_path in [
                        plugin_dir / "plugin.py",
                        plugin_dir / "plugins.py",
                        plugin_dir / "sk_plugin.py",
                        plugin_dir / "sk_plugins.py",
                    ]:
                        if search_path.exists():
                            logger.debug(f"Found potential plugin file: {search_path}")
                            module_name = f"{plugin_dir_name}.{search_path.stem}"
                            try:
                                logger.debug(f"Attempting to import: {module_name}")
                                plugin_submodule = importlib.import_module(module_name)
                                logger.debug(f"Plugin submodule imported: {plugin_submodule}")

                                # Find the plugin class in the submodule - both types
                                for attr_name in dir(plugin_submodule):
                                    attr = getattr(plugin_submodule, attr_name)

                                    # Check if it's a class
                                    if not inspect.isclass(attr):
                                        continue

                                    # Option 1: Check if it's a subclass of our Plugin class
                                    if issubclass(attr, Plugin) and attr != Plugin:
                                        plugin_class = attr
                                        logger.debug(f"Found plugin class via inheritance in submodule: {plugin_class}")
                                        break

                                    # Option 2: Check if it's an Agently SDK Plugin class
                                    if "Plugin" in attr_name and hasattr(attr, "name") and hasattr(attr, "description"):
                                        logger.debug(f"Found Agently SDK plugin class in submodule: {attr}")

                                        # Create a wrapper Plugin class
                                        plugin_class = self._create_sdk_plugin_wrapper(attr)
                                        logger.debug(f"Created wrapper for SDK plugin in submodule: {plugin_class.__name__}")
                                        break

                                if plugin_class:
                                    break
                            except ImportError as e:
                                logger.debug(f"Failed to import {module_name}: {e}")

                if plugin_class:
                    logger.debug(f"Successfully found plugin class: {plugin_class}")
                    return plugin_class
                else:
                    error_msg = f"No plugin class found in {plugin_dir_name}"
                    logger.error(error_msg)
                    raise ValueError(error_msg)

            except ImportError as e:
                error_msg = f"Failed to import plugin: {e}"
                logger.error(error_msg)
                raise ImportError(error_msg)
            finally:
                # Remove the plugin directory from sys.path
                try:
                    sys.path.remove(str(plugin_dir.parent))
                except ValueError:
                    pass

        except Exception as e:
            logger.exception(f"Error loading GitHub plugin: {e}")
            raise

    def _clone_or_update_repo(self, cache_path: Path) -> None:
        """Clone or update the repository to the cache directory."""
        try:
            # If force_reinstall is True, remove the directory if it exists
            if self.force_reinstall and cache_path.exists():
                import shutil

                logger.info(f"Force reinstall enabled, removing existing directory: {cache_path}")
                shutil.rmtree(cache_path)

            # Check if the directory exists and is a git repository
            if cache_path.exists():
                if (cache_path / ".git").exists():
                    # It's a git repository, update it
                    logger.info(f"Repository already exists, updating from remote: {cache_path}")
                    # Fetch the latest changes
                    try:
                        fetch_result = subprocess.run(
                            ["git", "fetch", "origin"], cwd=cache_path, check=True, capture_output=True, text=True
                        )
                        logger.debug(f"Git fetch output: {fetch_result.stdout}")
                    except subprocess.CalledProcessError as fetch_error:
                        logger.error(f"Git fetch failed: {fetch_error}")
                        logger.error(f"Fetch output: {fetch_error.stdout}")
                        logger.error(f"Fetch errors: {fetch_error.stderr}")
                        raise RuntimeError(f"Failed to fetch updates for repository {self.repo_url}: {fetch_error.stderr}")

                    # Check out the specified version/branch/tag
                    self._checkout_version(cache_path)
                    return
                elif self.force_reinstall:
                    # Directory exists but is not a git repository and force_reinstall is True
                    # It was already removed above
                    pass
                else:
                    # Directory exists but is not a git repository, remove it and clone
                    import shutil

                    logger.debug(f"Directory exists but is not a git repository, removing: {cache_path}")
                    shutil.rmtree(cache_path)

            # Ensure parent directory exists
            cache_path.parent.mkdir(parents=True, exist_ok=True)

            # Clone the repository
            logger.debug(f"Cloning repository: {self.repo_url}")
            git_url = f"https://{self.repo_url}"
            logger.debug(f"Git URL: {git_url}")

            # First clone the repository
            try:
                clone_result = subprocess.run(
                    ["git", "clone", git_url, str(cache_path)], check=True, capture_output=True, text=True
                )
                logger.debug(f"Git clone output: {clone_result.stdout}")
            except subprocess.CalledProcessError as clone_error:
                logger.error(f"Git clone failed: {clone_error}")
                logger.error(f"Clone command: git clone {git_url} {str(cache_path)}")
                logger.error(f"Clone output: {clone_error.stdout}")
                logger.error(f"Clone errors: {clone_error.stderr}")
                raise RuntimeError(f"Failed to clone repository {self.repo_url}: {clone_error.stderr}")

            # Check out the specified version/branch/tag
            self._checkout_version(cache_path)

            logger.info(f"Repository cloned successfully to {cache_path}")

        except subprocess.CalledProcessError as e:
            error_msg = (
                f"Failed to clone or checkout repository: {e.stderr.decode('utf-8') if hasattr(e, 'stderr') else str(e)}"
            )
            logger.error(error_msg)
            raise RuntimeError(f"Failed to clone repository {self.repo_url} at {self.version}: {error_msg}")
        except Exception as e:
            logger.error(f"Error during repository clone or update: {e}")
            if hasattr(e, "__traceback__"):
                import traceback

                logger.error(f"Stack trace:\n{traceback.format_exc()}")
            raise RuntimeError(f"Failed to clone repository {self.repo_url} at {self.version}: {e}")

    def _checkout_version(self, repo_path: Path) -> None:
        """Check out the specified version (branch, tag, or commit)."""
        try:
            # Try to check out the version as-is
            result = subprocess.run(
                ["git", "checkout", self.version],
                cwd=repo_path,
                capture_output=True,
                text=True,
            )

            # If the checkout failed and the version doesn't start with 'v',
            # try adding 'v' prefix (common for version tags)
            if result.returncode != 0 and not self.version.startswith("v"):
                versioned_tag = f"v{self.version}"
                logger.info(f"Failed to checkout {self.version}, trying {versioned_tag}")
                result = subprocess.run(
                    ["git", "checkout", versioned_tag],
                    cwd=repo_path,
                    capture_output=True,
                    text=True,
                )

            # If both checkout attempts failed, try to pull the latest changes
            if result.returncode != 0:
                logger.warning(f"Failed to checkout {self.version}, pulling latest changes")
                subprocess.run(
                    ["git", "pull", "origin", self.version],
                    cwd=repo_path,
                    check=True,
                    capture_output=True,
                )

            # Log success if it worked
            if result.returncode == 0:
                logger.info(f"Successfully checked out {self.version}")

        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to checkout version: {e}")
            raise RuntimeError(f"Failed to checkout version {self.version}: {e}")
        except Exception as e:
            logger.error(f"Error during version checkout: {e}")
            raise RuntimeError(f"Failed to checkout version {self.version}: {e}")

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

    def _calculate_plugin_sha(self) -> str:
        """Calculate a SHA for the plugin directory or file.

        For GitHub plugins, we use the repository SHA.

        Returns:
            A SHA string representing the plugin's current state
        """
        return self._get_current_sha()

    def _create_sdk_plugin_wrapper(self, attr: Any) -> Type[Plugin]:
        """Create a wrapper for an Agently SDK Plugin class.

        Args:
            attr: The original plugin class to wrap

        Returns:
            A wrapper class that inherits from Plugin
        """

        class AgentlySdkPluginWrapper(Plugin):
            """Wrapper for Agently SDK Plugin classes."""

            # Copy over key attributes
            name = getattr(attr, "name", self.name)
            description = getattr(attr, "description", "")
            namespace = self.namespace
            plugin_instructions = getattr(attr, "plugin_instructions", "")

            # Keep reference to original class
            _original_class = attr

            @classmethod
            def get_kernel_functions(cls):
                """Return kernel functions from the SDK plugin."""
                # For compatibility with semantic_kernel plugins
                return {}

            def __init__(self, **kwargs):
                """Initialize the wrapper and the original plugin class.

                This forwards kwargs to the original plugin class.
                """
                # Initialize the Plugin base class
                super().__init__()

                # Create an instance of the original plugin class with the provided kwargs
                self._original_instance = self._original_class(**kwargs)

                # Copy any other attributes from the original instance
                for attr_name in dir(self._original_instance):
                    if not attr_name.startswith("__") and not hasattr(self, attr_name):
                        setattr(self, attr_name, getattr(self._original_instance, attr_name))

        # Copy over any variables from the original class for proper initialization
        for attr_name in dir(attr):
            # Look for PluginVariable attributes from the SDK
            if hasattr(attr, attr_name) and attr_name != "name" and not attr_name.startswith("__"):
                var_attr = getattr(attr, attr_name)
                if hasattr(var_attr, "type") and hasattr(var_attr, "description"):
                    # This looks like a PluginVariable - add it to the wrapper class
                    logger.debug(f"Adding plugin variable from SDK class: {attr_name}")
                    setattr(AgentlySdkPluginWrapper, attr_name, None)  # Create the attribute

        # Set class name
        AgentlySdkPluginWrapper.__name__ = attr.__name__ + "Wrapper"
        return AgentlySdkPluginWrapper
