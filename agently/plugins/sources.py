"""Plugin source handling system."""

import importlib.util
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
                # Extract namespace (user/org)
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

                # Update repo_url to ensure it has the correct format
                if self.plugin_type == "mcp":
                    # For MCP servers, use the original repo name
                    self.repo_url = f"github.com/{self.namespace}/{original_repo_name}"
                else:
                    # For SK plugins, use full_repo_name which may have the plugin prefix added
                    self.repo_url = f"github.com/{self.namespace}/{self.full_repo_name}"
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

        return {
            "namespace": plugin_class.namespace,
            "name": plugin_class.name,
            "full_name": f"{self.namespace}/{self.name}",
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
        # Ensure the cache directory exists
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Determine the plugin directory name (repo name without prefix)
        plugin_dir_name = self.name

        # Full path to the plugin directory
        plugin_dir = self.cache_dir / plugin_dir_name

        # Clone or update the repository
        self._clone_or_update_repo(plugin_dir)

        # For MCP servers, we don't need to load a plugin class
        # We just return a special dummy class that satisfies the Plugin interface
        if self.plugin_type == "mcp":
            # Create a dynamic class that implements the Plugin interface
            # for MCP servers. This serves as a placeholder until actual
            # MCP server integration is handled by the agent.
            from agently.plugins.base import Plugin

            class MCPServerPlugin(Plugin):
                """Placeholder for MCP server plugin."""

                name = self.name
                description = "MCP Server plugin"
                namespace = self.namespace
                plugin_instructions = "This plugin provides access to an MCP server."

                @classmethod
                def get_kernel_functions(cls):
                    """Return an empty dictionary since the actual functions are provided by the MCP server."""
                    return {}

            return MCPServerPlugin

        # Determine plugin module path within the repository
        if self.plugin_path:
            # Specific plugin path provided (can be a file or directory)
            module_path = plugin_dir / self.plugin_path
        else:
            # Default: look for plugin code at the repository root
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

            # Check if the directory exists and is a git repository
            if cache_path.exists():
                if (cache_path / ".git").exists():
                    # It's a git repository, update it
                    logger.info(f"Repository already exists, updating from remote: {cache_path}")
                    # Fetch the latest changes
                    subprocess.run(["git", "fetch", "origin"], cwd=cache_path, check=True, capture_output=True)

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

            # First clone the repository
            subprocess.run(
                ["git", "clone", git_url, str(cache_path)],
                check=True,
                capture_output=True,
            )

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
