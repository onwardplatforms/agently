import logging
import os
import hashlib
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List, Optional, Dict, Any, Union, Literal, Tuple
import time
import shutil
from datetime import datetime
import subprocess
import tempfile

# Import agently_sdk styles for consistent formatting
from agently_sdk import styles
from agently_sdk.plugins import agently_function
from agently.plugins.base import Plugin

# Keep backward compatibility with kernel_function if needed
try:
    from semantic_kernel.functions.kernel_function_decorator import kernel_function
except ImportError:
    # Fallback if not running inside Semantic Kernel
    def kernel_function(description: str = ""):
        def decorator(func):
            return func

        return decorator


logger = logging.getLogger(__name__)


def print_action(message: str) -> None:
    """Print an agent action message with clear formatting."""
    print(f"\n{styles.blue.bold('Action:')} {message}")


def print_subaction(message: str) -> None:
    """Print a sub-action with indentation."""
    print(f"{styles.dim('├─')} {message}")


def print_result(message: str, success: bool = True) -> None:
    """Print a result message with appropriate coloring."""
    if success:
        print(f"{styles.success(message)}")
    else:
        print(f"{styles.error(message)}")


def print_file_header(
    path: str, start_line: Optional[int] = None, end_line: Optional[int] = None
) -> None:
    """Print a file header with optional line range."""
    header = styles.cyan.bold(f"● {path}")
    if start_line and end_line:
        header += styles.dim(f" (lines {start_line}-{end_line})")
    print(f"\n{header}")


class ChangeType(Enum):
    """Types of code changes that can be made."""

    UPDATE = "update"
    DELETE = "delete"
    INSERT = "insert"


@dataclass
class CodeSnippet:
    """Represents a snippet of code with context for reliable matching."""

    content: str
    start_line: int  # 1-based
    end_line: int  # 1-based, inclusive
    context_before: List[str]  # Lines before the snippet
    context_after: List[str]  # Lines after the snippet
    hash: Optional[str] = None  # Hash of normalized content

    def __post_init__(self):
        """Validate and normalize the snippet after creation."""
        if self.start_line < 1:
            raise ValueError("start_line must be >= 1")
        if self.end_line < self.start_line:
            raise ValueError("end_line must be >= start_line")
        if self.hash is None:
            self.hash = self._compute_hash()

    def _compute_hash(self) -> str:
        """Compute hash of normalized content."""
        normalized = self._normalize_content(self.content)
        return hashlib.sha256(normalized.encode()).hexdigest()

    def matches(
        self, other: "CodeSnippet", fuzzy: bool = False
    ) -> tuple[bool, Optional[str]]:
        """
        Check if this snippet matches another.

        Args:
            other: Another CodeSnippet to compare with
            fuzzy: If True, use fuzzy matching (ignoring whitespace differences)

        Returns:
            tuple[bool, Optional[str]]: (matched, match_type) where match_type is 'exact', 'fuzzy', or None
        """
        # Try exact match first
        if self.hash == other.hash:
            return True, "exact"

        # Try fuzzy match if enabled
        if fuzzy:
            # Remove all whitespace for comparison
            this_stripped = "".join(self.content.split())
            other_stripped = "".join(other.content.split())

            if this_stripped == other_stripped:
                return True, "fuzzy"

        return False, None

    def _normalize_content(self, content: str) -> str:
        """
        Normalize content for comparison by preserving indentation and empty lines.

        Args:
            content (str): The content to normalize

        Returns:
            str: Normalized content
        """
        lines = []
        for line in content.splitlines():
            # Replace tabs with four spaces (for instance)
            line = line.replace("\t", "    ")
            # Strip only trailing whitespace
            line = line.rstrip()
            # Keep leading spaces as-is
            lines.append(line)
        return "\n".join(lines)


@dataclass
class CodeChange:
    """Represents a change to be made to a file."""

    file_path: str
    change_type: ChangeType
    target_snippet: CodeSnippet
    new_content: Optional[str] = None
    position: Optional[Literal["before", "after"]] = None

    def __post_init__(self):
        """Validate the change after creation."""
        if self.change_type == ChangeType.UPDATE and self.new_content is None:
            raise ValueError("new_content required for UPDATE changes")
        if self.change_type == ChangeType.INSERT:
            if self.new_content is None:
                raise ValueError("new_content required for INSERT changes")
            if self.position not in ["before", "after"]:
                raise ValueError(
                    "position must be 'before' or 'after' for INSERT changes"
                )


@dataclass
class MatchResult:
    """Result of attempting to match a snippet in a file."""

    matched: bool
    start_line: Optional[int] = None  # 1-based
    end_line: Optional[int] = None  # 1-based, inclusive
    match_type: Optional[Literal["exact", "fuzzy"]] = None
    context_matches: bool = False
    error_message: Optional[str] = None


@dataclass
class ProcessResult:
    """Result of a process execution."""

    command: str
    return_code: int
    stdout: str
    stderr: str
    duration: float
    killed: bool = False
    error: Optional[str] = None

    def format_output(self) -> str:
        """Format the process result for display."""
        parts = []
        parts.append(f"Command: {self.command}")

        if self.stdout:
            parts.extend(["", "Output:", self.stdout.strip()])
        if self.stderr:
            parts.extend(["", "Errors:", self.stderr.strip()])

        parts.append(f"Duration: {self.duration:.2f}s")

        if self.killed:
            parts.append("Status: Killed")
        elif self.error:
            parts.append(f"Status: Error - {self.error}")
        else:
            parts.append(f"Exit Code: {self.return_code}")

        return "\n".join(parts)


class GitBackedCodeEditor:
    """Git-based code editor for reliable change tracking."""

    def __init__(self, workspace_root: Path):
        """Initialize with workspace root directory."""
        self.workspace_root = workspace_root.resolve()
        self.temp_dir = Path(tempfile.mkdtemp()).resolve()

        # Initialize Git repository
        subprocess.run(
            ["git", "init"], cwd=self.temp_dir, check=True, capture_output=True
        )

        # Configure Git
        subprocess.run(
            ["git", "config", "user.name", "Code Editor"],
            cwd=self.temp_dir,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "code.editor@local"],
            cwd=self.temp_dir,
            check=True,
            capture_output=True,
        )

        # Create .gitignore to exclude temporary files
        (self.temp_dir / ".gitignore").write_text("*.pyc\n__pycache__\n.DS_Store\n")

        # Stage .gitignore
        subprocess.run(
            ["git", "add", ".gitignore"],
            cwd=self.temp_dir,
            check=True,
            capture_output=True,
        )

        # Initial commit
        subprocess.run(
            ["git", "commit", "-m", "Initial repository setup"],
            cwd=self.temp_dir,
            check=True,
            capture_output=True,
        )

    def _stage_file_for_edit(self, file_path: Union[str, Path]) -> Path:
        """
        Stage a file for editing by copying it to the temporary Git repository.

        Args:
            file_path: Path to the file to stage

        Returns:
            Path: Path to the staged file in the temporary repository
        """
        try:
            # Convert to Path and resolve
            file_path = Path(file_path)
            if not file_path.is_absolute():
                file_path = (self.workspace_root / file_path).resolve()
            else:
                file_path = file_path.resolve()

            # Get relative path from workspace root
            rel_path = file_path.relative_to(self.workspace_root)
            temp_path = (self.temp_dir / rel_path).resolve()

            # Create parent directories if they don't exist
            temp_path.parent.mkdir(parents=True, exist_ok=True)

            # Copy the file to the temp directory if it exists
            if file_path.exists():
                shutil.copy2(file_path, temp_path)
            else:
                # Create an empty file
                temp_path.touch()

            # Stage the file in Git
            subprocess.run(
                ["git", "add", str(rel_path)],
                cwd=self.temp_dir,
                check=True,
                capture_output=True,
            )

            # Check if file is already tracked
            status = subprocess.run(
                ["git", "status", "--porcelain", str(rel_path)],
                cwd=self.temp_dir,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()

            # Only commit if the file is not already tracked
            if status.startswith("??") or status.startswith("A"):
                try:
                    subprocess.run(
                        ["git", "commit", "-m", f"Initial state for {rel_path}"],
                        cwd=self.temp_dir,
                        check=True,
                        capture_output=True,
                    )
                except subprocess.CalledProcessError:
                    # If commit fails (e.g., no changes), that's okay
                    pass

            return temp_path
        except ValueError as e:
            raise ValueError(f"Invalid path {file_path}: {str(e)}")

    def apply_changes(self, file_path: Union[str, Path]):
        """
        Apply changes to a file by committing them in Git and copying back to workspace.

        Args:
            file_path: Path to the file to apply changes to
        """
        try:
            # Convert to Path and resolve
            file_path = Path(file_path)
            if not file_path.is_absolute():
                file_path = (self.workspace_root / file_path).resolve()
            else:
                file_path = file_path.resolve()

            # Get relative path from workspace root
            rel_path = file_path.relative_to(self.workspace_root)
            temp_path = (self.temp_dir / rel_path).resolve()

            # Stage any changes
            subprocess.run(
                ["git", "add", str(rel_path)],
                cwd=self.temp_dir,
                check=True,
                capture_output=True,
            )

            # Commit changes
            subprocess.run(
                ["git", "commit", "-m", f"Update {rel_path}"],
                cwd=self.temp_dir,
                check=True,
                capture_output=True,
            )

            # Copy the file back to the workspace
            shutil.copy2(temp_path, file_path)
        except ValueError as e:
            raise ValueError(f"Invalid path {file_path}: {str(e)}")

    def revert_changes(self, file_path: Union[str, Path], num_changes: int = 1) -> str:
        """
        Revert changes to a file using Git.

        Args:
            file_path: Path to the file to revert
            num_changes: Number of changes to revert

        Returns:
            str: Success message or error
        """
        try:
            # Convert to Path and resolve
            file_path = Path(file_path)
            if not file_path.is_absolute():
                file_path = (self.workspace_root / file_path).resolve()
            else:
                file_path = file_path.resolve()

            # Get relative path from workspace root
            rel_path = file_path.relative_to(self.workspace_root)
            temp_path = (self.temp_dir / rel_path).resolve()

            # Get the current commit hash
            current = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self.temp_dir,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()

            # Get the target commit hash
            target = subprocess.run(
                ["git", "rev-parse", f"HEAD~{num_changes}"],
                cwd=self.temp_dir,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()

            # Checkout the file from the target commit
            subprocess.run(
                ["git", "checkout", target, "--", str(rel_path)],
                cwd=self.temp_dir,
                check=True,
                capture_output=True,
            )

            # Stage and commit the revert
            subprocess.run(
                ["git", "add", str(rel_path)],
                cwd=self.temp_dir,
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "commit", "-m", f"Revert {rel_path} to {target[:7]}"],
                cwd=self.temp_dir,
                check=True,
                capture_output=True,
            )

            # Copy the file back to the workspace
            shutil.copy2(temp_path, file_path)

            return f"Successfully reverted {num_changes} change(s) to {rel_path}"
        except Exception as e:
            return f"Error reverting changes: {str(e)}"

    def get_change_history(self, file_path: Union[str, Path]) -> str:
        """
        Get the Git history for a file.

        Args:
            file_path: Path to the file to get history for

        Returns:
            str: Git log with patches
        """
        try:
            # Convert to Path and resolve
            file_path = Path(file_path)
            if not file_path.is_absolute():
                file_path = (self.workspace_root / file_path).resolve()
            else:
                file_path = file_path.resolve()

            # Get relative path from workspace root
            rel_path = file_path.relative_to(self.workspace_root)

            # Get the Git log with patches
            result = subprocess.run(
                ["git", "log", "-p", "--", str(rel_path)],
                cwd=self.temp_dir,
                check=True,
                capture_output=True,
                text=True,
            )

            return result.stdout
        except Exception as e:
            return f"Error getting change history: {str(e)}"

    def __del__(self):
        """Clean up temporary directory when the object is destroyed."""
        try:
            if hasattr(self, 'git_editor') and self.git_editor and hasattr(self.git_editor, 'temp_dir'):
                shutil.rmtree(self.git_editor.temp_dir)
        except Exception as e:
            logger.error(f"Error cleaning up temporary directory: {str(e)}")


class CodeEditorPlugin(Plugin):
    """
    CodeEditorPlugin: A reliable and consistent code editing plugin
    built around snippet matching and Git-based change tracking.

    Groups of functionality:
    1. Core Code Modification - snippet-based code changes
    2. File Operations - basic file system operations
    3. Change Management - Git-based change tracking and control
    4. Search and Discovery - code searching capabilities
    5. System Operations - shell and system interaction
    """
    
    name = "coder"
    description = "A plugin for editing and managing code files"
    plugin_instructions = """
    HOW I WORK:
    I am a proactive coding assistant that handles code changes with careful consideration of dependencies and side effects.
    My primary focus is on making reliable, verified changes across multiple files when needed.

    1. SEARCH FIRST, CHANGE LATER
       Before making ANY changes:
       - ALWAYS use search_across_files() first to find ALL related code
       - ALWAYS use find_references() to catch ALL dependencies
       - Document everything I find before proceeding
       - If a change affects multiple files, list ALL files that need updating

    2. PLAN COMPLETELY
       For each set of related changes:
       - List ALL files that need to be modified
       - Explain ALL changes that will be made
       - Show how the changes are connected
       - Get confirmation before proceeding
       - Never make partial changes - either update everything or nothing

    3. EXECUTE CAREFULLY
       When making changes:
       - Make changes in a logical order (dependencies first)
       - ALWAYS provide ALL required parameters to code modification functions
       - Be careful with code indentation - match the indentation level of surrounding code
       - If a change fails, stop and explain why
       - Always apply changes after staging them to ensure they are saved

    4. VERIFY THOROUGHLY
       After changes are made:
       - verify_changes() to check for any additional pending changes
       - Check that ALL related files are consistent
       - Confirm that ALL references are updated
       - Run any necessary validation
       - Ensure all changes are applied

    RULES:
    1. ALWAYS search before changing
    2. ALWAYS find all references
    3. ALWAYS match the indentation level of surrounding code when making changes
    4. NEVER call apply_changes() after update_code, delete_code, or insert_code as they apply automatically
    5. NEVER make partial updates
    6. NEVER skip verification
    7. STOP if verification fails

    I handle these file types: Python, JavaScript/TypeScript, Go, Terraform, JSON/YAML.
    I prioritize correctness over speed and will always explain my actions.
    """

    def __init__(self, **variables):
        """
        Initialize the code editor plugin.

        Args:
            workspace_root: Root directory of the workspace. Defaults to current directory.
        """
        # Initialize the Plugin base class
        super().__init__(**variables)
        
        workspace_root = Path(os.getcwd()).resolve()
        self.workspace_root = workspace_root 
        self._pending_changes: Dict[str, List[CodeChange]] = {}
        self.git_editor = GitBackedCodeEditor(self.workspace_root)

        # Set up logging
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)

        # Create a file handler
        log_file = self.workspace_root / "code_editor.log"
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.INFO)

        # Create a formatter
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        file_handler.setFormatter(formatter)

        # Add the handler to the logger
        self.logger.addHandler(file_handler)

        self.logger.debug(
            "CodeEditorPlugin initialized with Git-based version control"
        )

    def __del__(self):
        """Clean up temporary directory when the object is destroyed."""
        try:
            if hasattr(self, 'git_editor') and self.git_editor and hasattr(self.git_editor, 'temp_dir'):
                shutil.rmtree(self.git_editor.temp_dir)
        except Exception as e:
            logger.error(f"Error cleaning up temporary directory: {str(e)}")

    def get_instructions(self) -> str:
        """Return the plugin instructions for the agent runtime."""
        return self.plugin_instructions

    def _validate_path(self, path: Union[str, Path]) -> Path:
        """
        Resolve and verify that 'path' is inside the workspace root.

        Args:
            path (Union[str, Path]): File or directory path (relative or absolute)

        Returns:
            Path: The fully resolved path within the workspace

        Raises:
            ValueError: If path is empty, invalid, or outside workspace root
        """
        try:
            # Check for empty path
            if not path:
                raise ValueError("Path cannot be empty")

            # Convert to Path object if it's a string
            path_obj = Path(path)

            # Check for parent directory traversal
            if ".." in str(path_obj):
                raise ValueError("Path cannot contain parent directory traversal (..)")

            # For relative paths, join with workspace_root
            if not path_obj.is_absolute():
                full_path = (self.workspace_root / path_obj).resolve()
            else:
                # For absolute paths, resolve first then check if it's under workspace_root
                full_path = path_obj.resolve()

            # Resolve both paths to handle symlinks (especially on macOS where /var -> /private/var)
            workspace_resolved = self.workspace_root.resolve()
            path_resolved = full_path.resolve()

            # Convert both to strings for prefix comparison to handle symlinks
            if not str(path_resolved).startswith(str(workspace_resolved)):
                raise ValueError(f"Path {path} is outside workspace root")

            return full_path

        except Exception as e:
            if isinstance(e, ValueError):
                raise
            raise ValueError(f"Invalid path {path}: {str(e)}")

    # -------------------------------------------------------------------------
    # File Operations Group
    # -------------------------------------------------------------------------

    @agently_function(description="Read the contents of a file.")
    def read_file(
        self,
        path: str,
        start_line: Optional[int] = None,
        end_line: Optional[int] = None,
    ) -> str:
        """
        Read entire file or specific line range.

        Args:
            path (str): Path to the file to read
            start_line (int, optional): First line to read (1-based)
            end_line (int, optional): Last line to read (1-based)

        Returns:
            str: File contents or specified line range

        Raises:
            ValueError: If path is invalid or outside workspace root
        """
        file_path = self._validate_path(path)
        
        # Handle start/end line validation
        if start_line is not None and start_line < 1:
            raise ValueError("start_line must be >= 1")
        if end_line is not None and start_line is not None and end_line < start_line:
            raise ValueError("end_line must be >= start_line")
            
        try:
            # Read the file
            with open(file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
                
            # Return specific lines if requested
            if start_line is not None and end_line is not None:
                # Adjust for 0-based indexing
                subset_lines = lines[start_line - 1:end_line]
                content = "".join(subset_lines)
                print_file_header(str(file_path), start_line, end_line)
            else:
                content = "".join(lines)
                print_file_header(str(file_path))
                
            print("\n" + content)
            return content
        except Exception as e:
            error_msg = f"Error reading file {file_path}: {str(e)}"
            print_result(error_msg, success=False)
            return error_msg

    @agently_function(description="Write content to a file (overwriting).")
    def write_file(self, path: str, content: str) -> str:
        """
        Write content to a file, overwriting any existing content.

        Args:
            path (str): Path to the file to write
            content (str): Content to write to the file

        Returns:
            str: Success message or error

        Raises:
            ValueError: If path is invalid or outside workspace root
        """
        file_path = self._validate_path(path)
        
        try:
            # Create parent directories if they don't exist
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            # Write the file
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
                
            msg = f"Successfully wrote {len(content.splitlines())} lines to {file_path}"
            print_result(msg)
            return msg
        except Exception as e:
            error_msg = f"Error writing to file {file_path}: {str(e)}"
            print_result(error_msg, success=False)
            return error_msg

    @agently_function(description="Delete a file or directory.")
    def delete_file(self, path: str, recursive: bool = False) -> str:
        """
        Delete a file or directory.

        Args:
            path (str): Path to the file or directory to delete
            recursive (bool): If True, recursively delete directories

        Returns:
            str: Success message or error

        Raises:
            ValueError: If path is invalid or outside workspace root
        """
        file_path = self._validate_path(path)
        
        try:
            if file_path.is_dir():
                if recursive:
                    shutil.rmtree(file_path)
                    msg = f"Successfully deleted directory {file_path} and its contents"
                else:
                    os.rmdir(file_path)
                    msg = f"Successfully deleted empty directory {file_path}"
            else:
                os.remove(file_path)
                msg = f"Successfully deleted file {file_path}"
                
            print_result(msg)
            return msg
        except Exception as e:
            error_msg = f"Error deleting {file_path}: {str(e)}"
            print_result(error_msg, success=False)
            return error_msg

    @agently_function(description="List the contents of a directory.")
    def list_dir(self, path: str = ".", max_depth: int = None) -> str:
        """
        List the contents of a directory with pretty formatting.

        Args:
            path (str): Path to the directory to list
            max_depth (int): Maximum depth to list

        Returns:
            str: Formatted directory listing
        """
        try:
            target_path = self._validate_path(path)
            if not target_path.exists():
                return f"Error: Path '{path}' does not exist."

            print_action(f"Generating directory tree for {path}")
            logger.debug(f"Listing directory tree for: {path}")

            def format_size(size_bytes: int) -> str:
                """Format file size in human-readable format."""
                for unit in ["B", "KB", "MB", "GB"]:
                    if size_bytes < 1024:
                        return f"{size_bytes:.1f}{unit}"
                    size_bytes /= 1024
                return f"{size_bytes:.1f}TB"

            def generate_tree(
                directory: Path, prefix: str = "", is_last: bool = True, depth: int = 0
            ) -> List[str]:
                """Recursively generate tree structure."""
                if max_depth is not None and depth > max_depth:
                    return []

                entries = sorted(
                    directory.iterdir(), key=lambda e: (e.is_file(), e.name)
                )
                tree_lines = []

                for i, entry in enumerate(entries):
                    is_last_entry = i == len(entries) - 1

                    # Determine the correct prefix characters
                    if is_last_entry:
                        entry_prefix = prefix + "└── "
                        next_prefix = prefix + "    "
                    else:
                        entry_prefix = prefix + "├── "
                        next_prefix = prefix + "│   "

                    # Add entry with size for files
                    if entry.is_file():
                        size = format_size(entry.stat().st_size)
                        tree_lines.append(f"{entry_prefix}{entry.name} ({size})")
                    else:
                        tree_lines.append(f"{entry_prefix}{entry.name}/")
                        # Recursively process subdirectories
                        tree_lines.extend(
                            generate_tree(entry, next_prefix, is_last_entry, depth + 1)
                        )

                return tree_lines

            # Generate the tree starting from the root
            tree_lines = [str(target_path) + "/"]
            tree_lines.extend(generate_tree(target_path))

            logger.debug(f"Found {len(tree_lines)-1} entries in {path}")
            return "\n".join(tree_lines)

        except Exception as e:
            logger.error(f"Error listing directory {path}: {str(e)}")
            return f"Error listing directory: {str(e)}"

    def _find_snippet_match(
        self,
        file_content: str,
        target: CodeSnippet,
        fuzzy: bool = False,
        context_lines: int = 0,
    ) -> MatchResult:
        """
        Find a matching code snippet in the file content.

        Args:
            file_content: The content to search in
            target: The snippet to find
            fuzzy: Whether to use fuzzy matching
            context_lines: Number of context lines to verify

        Returns:
            MatchResult: The match result
        """
        # Split content into lines for line-by-line comparison
        file_lines = file_content.splitlines()
        if not file_lines:
            return MatchResult(matched=False, error_message="File is empty")

        target_lines = target.content.splitlines()
        if not target_lines:
            # Special case: if target is empty or just whitespace, match any empty line
            for i, line in enumerate(file_lines):
                if not line.strip():
                    return MatchResult(
                        matched=True,
                        start_line=i + 1,
                        end_line=i + 1,
                        match_type="exact",
                        context_matches=True,
                    )
            return MatchResult(matched=False, error_message="No empty lines found")

        # Try to find the snippet
        for i in range(len(file_lines) - len(target_lines) + 1):
            candidate_lines = file_lines[i : i + len(target_lines)]
            candidate = CodeSnippet(
                content="\n".join(candidate_lines),
                start_line=i + 1,
                end_line=i + len(target_lines),
                context_before=file_lines[max(0, i - context_lines) : i],
                context_after=file_lines[
                    i + len(target_lines) : i + len(target_lines) + context_lines
                ],
            )

            if self._matches(target, candidate, fuzzy):
                # Found a match, now verify context if needed
                context_matches = self._verify_context(target, candidate, context_lines)
                match_type = "exact" if target.content == candidate.content else "fuzzy"

                return MatchResult(
                    matched=True,
                    start_line=i + 1,
                    end_line=i + len(target_lines),
                    match_type=match_type,
                    context_matches=context_matches,
                )

        return MatchResult(matched=False, error_message="No matching code found")

    def _verify_context(
        self, target: CodeSnippet, candidate: CodeSnippet, context_lines: int
    ) -> bool:
        """
        Verify that the context lines around a match are similar enough.

        Args:
            target: The snippet we're looking for
            candidate: The snippet we found
            context_lines: Number of context lines to verify

        Returns:
            bool: True if context matches sufficiently
        """
        if context_lines <= 0:
            return True

        def normalize_line(line: str) -> str:
            """Normalize a single line for comparison by removing whitespace."""
            return "".join(line.split())

        # Get the context lines to compare
        target_before = [
            normalize_line(line) for line in target.context_before[-context_lines:]
        ]
        target_after = [
            normalize_line(line) for line in target.context_after[:context_lines]
        ]
        candidate_before = [
            normalize_line(line) for line in candidate.context_before[-context_lines:]
        ]
        candidate_after = [
            normalize_line(line) for line in candidate.context_after[:context_lines]
        ]

        # Pad shorter lists with empty strings to match lengths
        while len(target_before) < context_lines:
            target_before.insert(0, "")
        while len(target_after) < context_lines:
            target_after.append("")
        while len(candidate_before) < context_lines:
            candidate_before.insert(0, "")
        while len(candidate_after) < context_lines:
            candidate_after.append("")

        # Calculate similarity scores
        def similarity_score(list1: List[str], list2: List[str]) -> float:
            """Calculate similarity score between two lists of lines."""
            if not list1 and not list2:
                return 1.0
            matches = sum(1 for a, b in zip(list1, list2) if a == b or not a or not b)
            return matches / max(len(list1), len(list2))

        before_score = similarity_score(target_before, candidate_before)
        after_score = similarity_score(target_after, candidate_after)

        # Consider context matching if similarity is above threshold
        SIMILARITY_THRESHOLD = 0.5  # More lenient threshold
        return (
            before_score >= SIMILARITY_THRESHOLD and after_score >= SIMILARITY_THRESHOLD
        )

    def _similarity_ratio(self, lines1: List[str], lines2: List[str]) -> float:
        """
        Calculate similarity ratio between two lists of lines.

        Args:
            lines1: First list of lines
            lines2: Second list of lines

        Returns:
            float: Similarity ratio (0.0 to 1.0)
        """
        if not lines1 and not lines2:
            return 1.0
        if not lines1 or not lines2:
            return 0.0

        # Compare line by line
        matches = sum(1 for l1, l2 in zip(lines1, lines2) if l1 == l2)
        total = max(len(lines1), len(lines2))
        return matches / total

    def _create_snippet(
        self,
        content: str,
        file_content: Optional[str] = None,
        start_line: Optional[int] = None,
        context_lines: int = 2,
    ) -> CodeSnippet:
        """
        Create a CodeSnippet from content, optionally with context from file.

        Args:
            content: The snippet content
            file_content: Optional full file content for context
            start_line: Optional known start line (1-based)
            context_lines: Number of context lines to include

        Returns:
            CodeSnippet: The created snippet
        """
        snippet_lines = content.splitlines()
        end_line = (
            (start_line + len(snippet_lines) - 1) if start_line else len(snippet_lines)
        )

        context_before = []
        context_after = []

        if file_content and start_line:
            file_lines = file_content.splitlines()
            context_start = max(0, start_line - context_lines - 1)
            context_before = file_lines[context_start : start_line - 1]
            context_after = file_lines[end_line : end_line + context_lines]

        return CodeSnippet(
            content=content,
            start_line=start_line or 1,
            end_line=end_line,
            context_before=context_before,
            context_after=context_after,
        )

    # -------------------------------------------------------------------------
    # Core Code Modification Group
    # -------------------------------------------------------------------------

    @agently_function(description="Update code that matches a target snippet.")
    def update_code(
        self,
        path: str,
        target_snippet: str,
        new_content: str,
        match_type: Literal["exact", "fuzzy"] = "fuzzy",
        context_lines: int = 2,
    ) -> str:
        """
        Update code that matches a target snippet.
        This function automatically applies changes - no separate call to apply_changes() is needed.

        Args:
            path: Path to the file to update
            target_snippet: The code to find and replace
            new_content: The new code to insert
            match_type: Whether to use exact or fuzzy matching
            context_lines: Number of context lines to use for matching

        Returns:
            str: Result of the operation
        """
        try:
            logger.debug(f"Updating code in {path}")
            logger.debug(f"Target snippet: {target_snippet}")
            logger.debug(f"New content: {new_content}")
            logger.debug(f"Match type: {match_type}")
            logger.debug(f"Context lines: {context_lines}")
            
            # Log parameter types to help diagnose issues
            logger.debug(f"Parameter types - path: {type(path)}, target_snippet: {type(target_snippet)}, new_content: {type(new_content)}")
            
            if not path or not isinstance(path, str):
                return "Error: 'path' parameter is required and must be a string"
            if not target_snippet or not isinstance(target_snippet, str):
                return "Error: 'target_snippet' parameter is required and must be a string"
            if not new_content or not isinstance(new_content, str):
                return "Error: 'new_content' parameter is required and must be a string"

            print_action("Preparing to update code")
            print_file_header(path)

            # Stage the file in our Git repo
            file_path = Path(path)
            if not file_path.is_absolute():
                file_path = self.workspace_root / file_path
            temp_path = self.git_editor._stage_file_for_edit(file_path)
            print_subaction("File staged for editing")

            # Read current content
            with open(temp_path, "r", encoding="utf-8") as f:
                file_content = f.read()
            print_subaction("Current content loaded")

            # Create target snippet object
            target = self._create_snippet(
                target_snippet,
                file_content,
                None,  # We don't know the line number yet
                context_lines,
            )

            # Find the matching snippet
            match_result = self._find_snippet_match(
                file_content,
                target,
                fuzzy=(match_type == "fuzzy"),
                context_lines=context_lines,
            )

            if not match_result.matched:
                print_result(
                    f"Could not find matching code: {match_result.error_message}", False
                )
                return (
                    f"Error: Could not find matching code. {match_result.error_message}"
                )

            if not match_result.context_matches:
                print_subaction(
                    f"{styles.yellow('Warning:')} Found match but context differs significantly"
                )
                logger.warning("Found match but context differs significantly")

            # Create the change object
            change = CodeChange(
                file_path=str(file_path),
                change_type=ChangeType.UPDATE,
                target_snippet=self._create_snippet(
                    target_snippet, file_content, match_result.start_line, context_lines
                ),
                new_content=new_content,
            )

            # Add to pending changes
            if str(file_path) not in self._pending_changes:
                self._pending_changes[str(file_path)] = []
            self._pending_changes[str(file_path)].append(change)

            # Apply the change to the temp file
            lines = file_content.splitlines()
            start_idx = match_result.start_line - 1
            end_idx = match_result.end_line
            lines[start_idx:end_idx] = new_content.splitlines()
            new_content = "\n".join(lines)
            if new_content and not new_content.endswith("\n"):
                new_content += "\n"
            with open(temp_path, "w", encoding="utf-8") as f:
                f.write(new_content)

            print_result(
                f"Updated code at lines {match_result.start_line}-{match_result.end_line} ({match_result.match_type} match)"
            )
            
            # Automatically apply changes
            apply_result = self.apply_changes()
            if "Successfully applied changes" in apply_result:
                return (
                    f"Successfully updated code:\n"
                    f"- File: {path}\n"
                    f"- Lines: {match_result.start_line}-{match_result.end_line}\n"
                    f"- Match type: {match_result.match_type}"
                )
            else:
                return f"Error applying changes: {apply_result}"

        except Exception as e:
            logger.error(f"Error updating code in {path}: {str(e)}")
            print_result(f"Error updating code: {str(e)}", False)
            return f"Error updating code: {str(e)}"

    @agently_function(description="Delete code that matches a target snippet.")
    def delete_code(
        self,
        path: str = "",
        target_snippet: str = "",
        match_type: Literal["exact", "fuzzy"] = "exact",
        context_lines: int = 2,
    ) -> str:
        """
        Delete code that matches the target snippet.
        This function automatically applies changes - no separate call to apply_changes() is needed.

        Args:
            path (str): Path to the file to modify
            target_snippet (str): The code snippet to find and delete
            match_type (str): Whether to use 'exact' or 'fuzzy' matching
            context_lines (int): Number of context lines to use for matching

        Returns:
            str: Success message or error
        """
        try:
            # Handle missing parameters with helpful error messages
            if not path:
                files_in_cwd = "\n".join([f"- {f}" for f in os.listdir(self.workspace_root) if os.path.isfile(os.path.join(self.workspace_root, f))])
                return (
                    f"Error: Missing 'path' parameter. Please specify which file to modify.\n"
                    f"Files in current directory:\n{files_in_cwd}"
                )
            if not target_snippet:
                return (
                    f"Error: Missing 'target_snippet' parameter. Please specify the code to delete.\n"
                    f"Example usage: delete_code(path='example.py', target_snippet='def example_function():')"
                )
                
            logger.debug(f"Preparing to delete code from {path}")
            logger.debug(f"Target snippet: {target_snippet}")
            logger.debug(f"Match type: {match_type}")
            logger.debug(f"Context lines: {context_lines}")
            
            # Log parameter types to help diagnose issues
            logger.debug(f"Parameter types - path: {type(path)}, target_snippet: {type(target_snippet)}")

            print_action(f"Preparing to delete code from {path}")

            # Validate and read the file
            file_path = self._validate_path(path)
            if not file_path.is_file():
                return f"Error: File '{path}' does not exist or is not a regular file."

            # Stage the file in our Git repo
            temp_path = self.git_editor._stage_file_for_edit(str(file_path))

            with open(temp_path, "r", encoding="utf-8") as f:
                file_content = f.read()

            # Create snippet objects
            target = self._create_snippet(target_snippet)

            # Find the matching snippet
            match_result = self._find_snippet_match(
                file_content,
                target,
                fuzzy=(match_type == "fuzzy"),
                context_lines=context_lines,
            )

            if not match_result.matched:
                return (
                    f"Error: Could not find matching code. {match_result.error_message}"
                )

            if not match_result.context_matches:
                logger.warning("Found match but context differs significantly")

            # Create the change object
            change = CodeChange(
                file_path=str(file_path),
                change_type=ChangeType.DELETE,
                target_snippet=self._create_snippet(
                    target_snippet, file_content, match_result.start_line, context_lines
                ),
            )

            # Add to pending changes
            if str(file_path) not in self._pending_changes:
                self._pending_changes[str(file_path)] = []
            self._pending_changes[str(file_path)].append(change)

            # Apply the change to the temp file
            lines = file_content.splitlines()
            del lines[match_result.start_line - 1 : match_result.end_line]
            new_content = "\n".join(lines)
            if new_content and not new_content.endswith("\n"):
                new_content += "\n"
            with open(temp_path, "w", encoding="utf-8") as f:
                f.write(new_content)

            print_action(
                f"Added delete change for lines {match_result.start_line}-{match_result.end_line}"
            )
            logger.debug(
                f"Queued delete change in {path} "
                f"(lines {match_result.start_line}-{match_result.end_line}, "
                f"match_type={match_result.match_type})"
            )

            # Automatically apply changes
            result = self.apply_changes()
            if "Successfully applied changes" in result:
                return (
                    f"Successfully deleted code:\n"
                    f"- File: {path}\n"
                    f"- Lines: {match_result.start_line}-{match_result.end_line}\n"
                    f"- Match type: {match_result.match_type}"
                )
            else:
                return f"Error applying changes: {result}"

        except Exception as e:
            logger.error(f"Error deleting code from {path}: {str(e)}")
            return f"Error deleting code: {str(e)}"

    @agently_function(description="Insert code at a specific position in a file.")
    def insert_code(
        self,
        path: str = "",
        new_content: str = "",
        target_snippet: str = "",
        position: Literal["before", "after"] = "after",
        match_type: Literal["exact", "fuzzy"] = "exact",
        context_lines: int = 2,
    ) -> str:
        """
        Insert new code at a specific position in a file.
        This function automatically applies changes - no separate call to apply_changes() is needed.

        Args:
            path (str): Path to the file to modify
            new_content (str): The new code to insert
            target_snippet (str): The code snippet to find for insertion
            position (str): Position to insert the code ('before' or 'after', defaults to 'after')
            match_type (str): Whether to use 'exact' or 'fuzzy' matching
            context_lines (int): Number of context lines to use for matching

        Returns:
            str: Success message or error
        """
        try:
            # Handle missing parameters with helpful error messages
            if not path:
                files_in_cwd = "\n".join([f"- {f}" for f in os.listdir(self.workspace_root) if os.path.isfile(os.path.join(self.workspace_root, f))])
                return (
                    f"Error: Missing 'path' parameter. Please specify which file to modify.\n"
                    f"Files in current directory:\n{files_in_cwd}"
                )
            if not new_content:
                return (
                    f"Error: Missing 'new_content' parameter. Please specify the code to insert.\n"
                    f"Example usage: insert_code(path='example.py', new_content='def new_function():\\n    pass', target_snippet='# Some existing code')"
                )
            if not target_snippet:
                return (
                    f"Error: Missing 'target_snippet' parameter. Please specify where to insert the code.\n"
                    f"Example usage: insert_code(path='example.py', new_content='def new_function():\\n    pass', target_snippet='# Some existing code')"
                )
                
            logger.debug(f"Inserting code in {path}")
            logger.debug(f"Target snippet: {target_snippet}")
            logger.debug(f"New content: {new_content}")
            logger.debug(f"Position: {position}")
            logger.debug(f"Match type: {match_type}")
            logger.debug(f"Context lines: {context_lines}")
            
            # Log parameter types to help diagnose issues
            logger.debug(f"Parameter types - path: {type(path)}, target_snippet: {type(target_snippet)}, new_content: {type(new_content)}")

            print_action(f"Inserting code in {path}")

            # Validate and read the file
            file_path = self._validate_path(path)
            if not file_path.is_file():
                return f"Error: File '{path}' does not exist or is not a regular file."

            # Stage the file in our Git repo
            temp_path = self.git_editor._stage_file_for_edit(str(file_path))

            with open(temp_path, "r", encoding="utf-8") as f:
                file_content = f.read()

            # Create snippet objects
            target = self._create_snippet(target_snippet)

            # Find the matching snippet
            match_result = self._find_snippet_match(
                file_content,
                target,
                fuzzy=(match_type == "fuzzy"),
                context_lines=context_lines,
            )

            if not match_result.matched:
                return (
                    f"Error: Could not find matching code. {match_result.error_message}"
                )

            if not match_result.context_matches:
                logger.warning("Found match but context differs significantly")

            # Create the change object
            change = CodeChange(
                file_path=str(file_path),
                change_type=ChangeType.INSERT,
                target_snippet=self._create_snippet(
                    target_snippet, file_content, match_result.start_line, context_lines
                ),
                new_content=new_content,
                position=position,
            )

            # Add to pending changes
            if str(file_path) not in self._pending_changes:
                self._pending_changes[str(file_path)] = []
            self._pending_changes[str(file_path)].append(change)

            # Apply the change to the temp file
            lines = file_content.splitlines()
            insert_point = match_result.start_line - 1
            if position == "after":
                insert_point = match_result.end_line
            
            # Split new_content into lines and insert them individually
            new_content_lines = new_content.splitlines()
            
            # Insert each line in reverse order to maintain correct positions
            for i, line in enumerate(reversed(new_content_lines)):
                lines.insert(insert_point, line)
            
            new_content = "\n".join(lines)
            if new_content and not new_content.endswith("\n"):
                new_content += "\n"
            with open(temp_path, "w", encoding="utf-8") as f:
                f.write(new_content)

            print_action(
                f"Added insert change for lines {match_result.start_line}-{match_result.end_line}"
            )
            logger.debug(
                f"Queued insert change in {path} "
                f"(lines {match_result.start_line}-{match_result.end_line}, "
                f"match_type={match_result.match_type})"
            )

            # Automatically apply changes
            result = self.apply_changes()
            if "Successfully applied changes" in result:
                return (
                    f"Successfully inserted code:\n"
                    f"- File: {path}\n"
                    f"- Lines: {match_result.start_line}-{match_result.end_line}\n"
                    f"- Match type: {match_result.match_type}"
                )
            else:
                return f"Error applying changes: {result}"

        except Exception as e:
            logger.error(f"Error inserting code into {path}: {str(e)}")
            return f"Error inserting code: {str(e)}"

    @agently_function(description="Search for code snippets in a file.")
    def search_code(
        self,
        path: str,
        query: str,
        match_type: Literal["exact", "fuzzy"] = "exact",
        context_lines: int = 2,
    ) -> str:
        """
        Search for code snippets in a file.

        Args:
            path (str): Path to the file to search
            query (str): The search query
            match_type (str): Whether to use 'exact' or 'fuzzy' matching
            context_lines (int): Number of context lines to use for matching

        Returns:
            str: Result of the search
        """
        try:
            logger.debug(f"Searching for code snippets in {path}")
            logger.debug(f"Query: {query}")
            logger.debug(f"Match type: {match_type}")

            print_action(f"Searching for code snippets in {path}")

            # Validate and read the file
            file_path = self._validate_path(path)
            if not file_path.is_file():
                return f"Error: File '{path}' does not exist or is not a regular file."

            with open(file_path, "r", encoding="utf-8") as f:
                file_content = f.read()

            # Create snippet objects
            target = self._create_snippet(query)

            # Find the matching snippets
            match_results = []
            for i in range(
                len(file_content.splitlines()) - len(target.content.splitlines()) + 1
            ):
                # Extract the candidate snippet
                candidate_lines = file_content.splitlines()[
                    i : i + len(target.content.splitlines())
                ]
                candidate_content = "\n".join(candidate_lines)

                # Create a CodeSnippet for comparison
                candidate = CodeSnippet(
                    content=candidate_content,
                    start_line=i + 1,  # Convert to 1-based
                    end_line=i + len(target.content.splitlines()),
                    context_before=file_content.splitlines()[
                        max(0, i - context_lines) : i
                    ],
                    context_after=file_content.splitlines()[
                        i
                        + len(target.content.splitlines()) : i
                        + len(target.content.splitlines())
                        + context_lines
                    ],
                )

                # Try exact match first
                if candidate.matches(target, fuzzy=False):
                    logger.debug(
                        f"Found exact match at lines {i+1}-{i+len(target.content.splitlines())}"
                    )
                    match_results.append(
                        MatchResult(
                            matched=True,
                            start_line=i + 1,
                            end_line=i + len(target.content.splitlines()),
                            match_type="exact",
                            context_matches=self._verify_context(
                                target, candidate, context_lines
                            ),
                        )
                    )

                # Try fuzzy match if exact match fails and fuzzy is enabled
                elif match_type == "fuzzy" and candidate.matches(target, fuzzy=True):
                    logger.debug(
                        f"Found fuzzy match at lines {i+1}-{i+len(target.content.splitlines())}"
                    )
                    match_results.append(
                        MatchResult(
                            matched=True,
                            start_line=i + 1,
                            end_line=i + len(target.content.splitlines()),
                            match_type="fuzzy",
                            context_matches=self._verify_context(
                                target, candidate, context_lines
                            ),
                        )
                    )

            if not match_results:
                return "No matching snippets found"

            result = "\n".join(
                f"{result.start_line}-{result.end_line}: {result.match_type} match"
                for result in match_results
            )
            return result

        except Exception as e:
            logger.error(f"Error searching for code in {path}: {str(e)}")
            return f"Error searching for code: {str(e)}"

    @agently_function(description="Verify changes before applying them.")
    def verify_changes(self) -> str:
        """
        Verify pending changes before applying them.

        Returns:
            str: Result of the verification
        """
        try:
            logger.debug("Verifying changes")
            print_action("Verifying changes before applying them")

            # Get the diff of staged changes
            result = subprocess.run(
                ["git", "diff", "--staged"],
                cwd=self.git_editor.temp_dir,
                capture_output=True,
                text=True,
                check=True,
            )

            logger.debug(f"Git diff output: {result.stdout}")

            if not result.stdout:
                logger.debug("No changes to verify")
                return "No changes to verify"

            return f"Changes verified:\n{result.stdout}"
        except Exception as e:
            error_msg = f"Error verifying changes: {str(e)}"
            logger.error(error_msg)
            return error_msg

    def _matches(
        self, target: CodeSnippet, candidate: CodeSnippet, fuzzy: bool = False
    ) -> bool:
        """
        Check if two snippets match.

        Args:
            target: The snippet we're looking for
            candidate: The snippet we're checking
            fuzzy: Whether to use fuzzy matching

        Returns:
            bool: True if the snippets match
        """
        if not fuzzy:
            return target.content == candidate.content

        # For fuzzy matching, normalize both contents
        target_lines = target.content.splitlines()
        candidate_lines = candidate.content.splitlines()

        if len(target_lines) != len(candidate_lines):
            return False

        # Compare each line, ignoring whitespace differences
        for target_line, candidate_line in zip(target_lines, candidate_lines):
            target_norm = "".join(target_line.split())
            candidate_norm = "".join(candidate_line.split())
            if target_norm != candidate_norm:
                return False

        return True

    @agently_function(description="Check if there are pending changes to apply.")
    def has_pending_changes(self) -> bool:
        """
        Check if there are pending changes that need to be applied.

        Returns:
            bool: True if there are pending changes, False otherwise
        """
        return bool(self._pending_changes)

    @agently_function(description="Apply pending changes to files.")
    def apply_changes(self) -> str:
        """
        Apply pending changes to files.

        Returns:
            str: Result of the application
        """
        try:
            logger.debug("Applying changes to files")
            print_action("Applying changes to files")

            # Check if there are any pending changes
            if not self._pending_changes:
                logger.debug("No pending changes to apply")
                
                # Check if there are any staged changes in Git
                result = subprocess.run(
                    ["git", "diff", "--staged"],
                    cwd=self.git_editor.temp_dir,
                    capture_output=True,
                    text=True,
                )
                
                if not result.stdout.strip():
                    result = subprocess.run(
                        ["git", "status", "--porcelain"],
                        cwd=self.git_editor.temp_dir,
                        capture_output=True,
                        text=True,
                    )
                    
                    if not result.stdout.strip():
                        return "No changes to apply."
                
                # Apply all staged/modified files
                for root, _, files in os.walk(self.git_editor.temp_dir):
                    rel_root = Path(root).relative_to(self.git_editor.temp_dir)
                    for file in files:
                        if file == ".git" or ".git" in str(rel_root):
                            continue
                        
                        rel_path = rel_root / file
                        if str(rel_path) == ".gitignore":
                            continue
                            
                        try:
                            temp_path = self.git_editor.temp_dir / rel_path
                            abs_path = self.workspace_root / rel_path
                            
                            # Check if file has changed
                            if abs_path.exists():
                                with open(temp_path, "r", encoding="utf-8") as f:
                                    temp_content = f.read()
                                with open(abs_path, "r", encoding="utf-8") as f:
                                    abs_content = f.read()
                                    
                                if temp_content == abs_content:
                                    continue
                            
                            # Copy the file to the workspace
                            abs_path.parent.mkdir(parents=True, exist_ok=True)
                            shutil.copy2(temp_path, abs_path)
                            logger.debug(f"Copied {temp_path} to {abs_path}")
                        except Exception as e:
                            logger.error(f"Error copying {temp_path} to {abs_path}: {str(e)}")
                
                return "Successfully applied changes to all modified files."

            # Group changes by file for atomic application
            results = []
            for file_path, changes in self._pending_changes.items():
                try:
                    # Stage the file in our Git repo
                    temp_path = self.git_editor._stage_file_for_edit(file_path)
                    
                    logger.debug(f"Applying changes to {file_path} (temp path: {temp_path})")

                    # Read current content
                    with open(temp_path, "r", encoding="utf-8") as f:
                        content = f.read()

                    # Apply each change in sequence
                    for change in changes:
                        lines = content.splitlines()

                        if change.change_type == ChangeType.UPDATE:
                            start_idx = change.target_snippet.start_line - 1
                            end_idx = change.target_snippet.end_line
                            lines[start_idx:end_idx] = change.new_content.splitlines()
                        elif change.change_type == ChangeType.DELETE:
                            start_idx = change.target_snippet.start_line - 1
                            end_idx = change.target_snippet.end_line
                            del lines[start_idx:end_idx]
                        elif change.change_type == ChangeType.INSERT:
                            insert_point = change.target_snippet.start_line - 1
                            if change.position == "after":
                                insert_point = change.target_snippet.end_line
                            
                            # Split new_content into lines and insert them individually
                            new_content_lines = change.new_content.splitlines()
                            
                            # Insert each line in reverse order to maintain correct positions
                            for i, line in enumerate(reversed(new_content_lines)):
                                lines.insert(insert_point, line)

                        content = "\n".join(lines)
                        if content and not content.endswith("\n"):
                            content += "\n"

                    # Write updated content back to temp file
                    with open(temp_path, "w", encoding="utf-8") as f:
                        f.write(content)

                    # Copy the temp file directly to the actual file
                    actual_file = Path(file_path)
                    shutil.copy2(temp_path, actual_file)
                    logger.debug(f"Copied {temp_path} to {actual_file}")

                    results.append(f"Successfully applied changes to {file_path}")

                except Exception as e:
                    logger.error(f"Error applying changes to {file_path}: {str(e)}")
                    results.append(
                        f"Error applying changes to {file_path}: {str(e)}"
                    )

            # Clear pending changes
            self._pending_changes.clear()

            if not results:
                return "No changes to apply."

            return "Successfully applied changes:\n" + "\n".join(
                f"- {msg}" for msg in results
            )

        except Exception as e:
            logger.error(f"Error applying changes: {str(e)}")
            return f"Error applying changes: {str(e)}"

    @agently_function(description="Search for code across multiple files.")
    def search_across_files(
        self, query: str, file_pattern: str = "*", case_sensitive: bool = False
    ) -> str:
        """
        Search for code across multiple files.

        Args:
            query: Text to search for
            file_pattern: Glob pattern for files to search (e.g. "*.py")
            case_sensitive: Whether to perform case-sensitive search

        Returns:
            str: Search results with file paths and line numbers
        """
        try:
            logger.debug(f"Searching for code across files matching '{file_pattern}'")
            logger.debug(f"Query: {query}")
            logger.debug(f"Case sensitive: {case_sensitive}")

            print_action(f"Searching for code across files matching '{file_pattern}'")

            # Find all matching files
            matches = []
            for file_path in self.workspace_root.rglob(file_pattern):
                if not file_path.is_file():
                    continue

                try:
                    content = file_path.read_text()
                    rel_path = file_path.relative_to(self.workspace_root)

                    # Perform search
                    for i, line in enumerate(content.splitlines(), 1):
                        if (
                            (query in line)
                            if case_sensitive
                            else (query.lower() in line.lower())
                        ):
                            matches.append(f"{rel_path}:{i}: {line.strip()}")
                except Exception as e:
                    self.logger.warning(f"Error reading {file_path}: {str(e)}")
                    continue

            if not matches:
                return "No matching code found."

            return "\n".join(matches)

        except Exception as e:
            logger.error(f"Error searching files: {str(e)}")
            return f"Error searching files: {str(e)}"

    @agently_function(description="Find references to a symbol across files.")
    def find_references(
        self,
        symbol: str,
        file_pattern: str = "*.py",
        context_lines: int = 2,
        max_results: int = 50,
    ) -> str:
        """
        Find references to a symbol (function, variable, etc.) across files.

        Args:
            symbol (str): The symbol to find references for
            file_pattern (str): Glob pattern for files to search
            context_lines (int): Number of context lines to include
            max_results (int): Maximum number of results to return

        Returns:
            str: Formatted reference results
        """
        try:
            logger.debug(f"Finding references to '{symbol}'")
            logger.debug(f"File pattern: {file_pattern}")
            logger.debug(f"Context lines: {context_lines}")
            logger.debug(f"Max results: {max_results}")

            print_action(f"Finding references to '{symbol}'")

            # Build a regex pattern that matches common symbol usage patterns
            patterns = [
                rf"\b{re.escape(symbol)}\b",  # Word boundary matches
                rf"['\"]({re.escape(symbol)})['\"]",  # String literal matches
                rf"\.{re.escape(symbol)}\b",  # Method/attribute access
                rf"\b{re.escape(symbol)}\s*\(",  # Function calls
                rf"\b{re.escape(symbol)}\s*=",  # Assignments
            ]
            combined_pattern = "|".join(patterns)

            # Find all matching files
            matching_files = list(self.workspace_root.rglob(file_pattern))
            if not matching_files:
                return f"No files found matching pattern: {file_pattern}"

            # Search each file
            results = []
            for file_path in matching_files:
                if not file_path.is_file() or file_path.name.startswith("."):
                    continue

                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        lines = f.readlines()

                    # Find matches in this file
                    for i, line in enumerate(lines):
                        if re.search(combined_pattern, line):
                            # Get context lines
                            start_idx = max(0, i - context_lines)
                            end_idx = min(len(lines), i + context_lines + 1)

                            context = "\n".join(
                                f"{j+1}: {lines[j].rstrip()}"
                                for j in range(start_idx, end_idx)
                            )

                            results.append(
                                {
                                    "file": str(
                                        file_path.relative_to(self.workspace_root)
                                    ),
                                    "line": i + 1,
                                    "content": line.strip(),
                                    "context": context,
                                }
                            )

                            if len(results) >= max_results:
                                break

                except Exception as e:
                    self.logger.warning(f"Error searching file {file_path}: {str(e)}")
                    continue

            if not results:
                return f"No references found for '{symbol}'."

            # Format results
            output = []
            for result in results:
                output.extend(
                    [
                        f"\nFile: {result['file']}",
                        f"Line {result['line']}:",
                        result["context"],
                        "-" * 60,
                    ]
                )

            return "\n".join(output)

        except Exception as e:
            logger.error(f"Error finding references: {str(e)}")
            return f"Error finding references: {str(e)}"

    @agently_function(
        description="Run a shell command with advanced process management."
    )
    def run_terminal_command(
        self,
        command: str,
        cwd: str = "",
        timeout: Optional[int] = None,
        env: Optional[Dict[str, str]] = None,
        shell: bool = True,
        stream_output: bool = False,
    ) -> str:
        """
        Execute a shell command with advanced process management.

        Args:
            command (str): The command to execute
            cwd (str, optional): Working directory for the command
            timeout (int, optional): Timeout in seconds
            env (Dict[str, str], optional): Additional environment variables
            shell (bool): Whether to run command through shell
            stream_output (bool): Whether to stream output in real-time

        Returns:
            str: Formatted command output and status
        """
        try:
            logger.debug(f"Executing command: {command}")
            logger.debug(f"Working directory: {cwd}")
            logger.debug(f"Timeout: {timeout}")
            logger.debug(f"Environment variables: {env}")
            logger.debug(f"Shell: {shell}")
            logger.debug(f"Stream output: {stream_output}")

            print_action(f"Executing command: {command}")

            # Validate working directory
            work_dir = self._validate_path(cwd) if cwd else self.workspace_root
            if not work_dir.exists():
                return f"Error: Working directory '{work_dir}' does not exist"

            # Prepare environment
            process_env = os.environ.copy()
            if env:
                process_env.update(env)

            # Record start time
            start_time = time.time()

            try:
                # Create and start the process
                process = subprocess.Popen(
                    command,
                    cwd=work_dir,
                    env=process_env,
                    shell=shell,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1,  # Line buffered
                    universal_newlines=True,
                )

                stdout_lines = []
                stderr_lines = []
                killed = False

                def read_output():
                    """Read from stdout and stderr."""
                    while True:
                        stdout_line = process.stdout.readline()
                        if stdout_line:
                            stdout_lines.append(stdout_line)
                            if stream_output:
                                print(stdout_line, end="")

                        stderr_line = process.stderr.readline()
                        if stderr_line:
                            stderr_lines.append(stderr_line)
                            if stream_output:
                                print(styles.gray(stderr_line), end="")

                        if (
                            not stdout_line
                            and not stderr_line
                            and process.poll() is not None
                        ):
                            break

                # Start output reading thread
                from threading import Thread

                output_thread = Thread(target=read_output)
                output_thread.daemon = True
                output_thread.start()

                # Wait for completion or timeout
                try:
                    output_thread.join(timeout=timeout)
                    if output_thread.is_alive():
                        # Timeout occurred
                        process.kill()
                        killed = True
                        output_thread.join()

                except KeyboardInterrupt:
                    # Handle user interrupt
                    process.kill()
                    killed = True
                    output_thread.join()

                # Get final output
                stdout = "".join(stdout_lines)
                stderr = "".join(stderr_lines)

                # Calculate duration
                duration = time.time() - start_time

                # Create result object
                result = ProcessResult(
                    command=command,
                    return_code=process.returncode,
                    stdout=stdout,
                    stderr=stderr,
                    duration=duration,
                    killed=killed,
                    error="Process killed (timeout)" if killed else None,
                )

                return result.format_output()

            except subprocess.SubprocessError as e:
                return ProcessResult(
                    command=command,
                    return_code=-1,
                    stdout="",
                    stderr="",
                    duration=time.time() - start_time,
                    error=f"Subprocess error: {str(e)}",
                ).format_output()

        except Exception as e:
            logger.error(f"Error executing command: {str(e)}")
            return f"Error executing command: {str(e)}"

    @agently_function(description="Revert changes made to files.")
    def revert_changes(self, path: str, num_changes: int = 1) -> str:
        """
        Revert changes made to files.

        Args:
            path (str): Path to the file to revert changes for
            num_changes (int): Number of changes to revert (default: 1)

        Returns:
            str: Result of the revert operation
        """
        try:
            logger.debug(f"Reverting changes for {path}")
            logger.debug(f"Number of changes: {num_changes}")

            print_action(f"Reverting changes for {path}")

            # Use Git to revert changes
            self.git_editor.revert_changes(path, num_changes)

            return f"Successfully reverted {num_changes} change(s) to {path}"

        except Exception as e:
            logger.error(f"Error reverting changes: {str(e)}")
            return f"Error reverting changes: {str(e)}"

    @agently_function(description="Get the history of changes made.")
    def get_change_history(self, path: str) -> str:
        """
        Get the history of changes made to a file.

        Args:
            path (str): Path to get history for

        Returns:
            str: Git log with patches
        """
        try:
            logger.debug(f"Getting change history for {path}")
            return self.git_editor.get_change_history(path)
        except Exception as e:
            logger.error(f"Error getting change history: {str(e)}")
            return f"Error getting change history: {str(e)}"

    @agently_function(
        description="Lint code in a file using language-appropriate linters."
    )
    def lint_code(
        self,
        path: str = "",
        fix: bool = False,
    ) -> str:
        """
        Lint code in a file using language-appropriate linters.

        Args:
            path: Path to the file to lint
            fix: Whether to automatically fix issues (if supported by the linter)

        Returns:
            str: Lint results or error message
        """
        # Check if path is provided
        if not path:
            files_in_cwd = "\n".join([f"- {f}" for f in os.listdir(self.workspace_root) if os.path.isfile(os.path.join(self.workspace_root, f))])
            return (
                f"Error: Missing 'path' parameter. Please specify which file to lint.\n"
                f"Files in current directory:\n{files_in_cwd}"
            )
            
        print_action(f"Linting file: {path}")
        logger.debug(f"Linting file: {path}, with fix={fix}")
        
        try:
            file_path = self._validate_path(path)
            if not file_path.is_file():
                return f"Error: File '{path}' does not exist or is not a regular file."

            # Map of extensions to linting commands
            lint_commands = {
                ".py": ["flake8", str(file_path)],
                ".js": ["eslint", str(file_path)],
                ".ts": ["eslint", str(file_path)],
                ".tsx": ["eslint", str(file_path)],
                ".jsx": ["eslint", str(file_path)],
                ".go": ["golint", str(file_path)],
            }

            # Add auto-fix flags if requested
            if fix:
                lint_commands[".py"] = ["black", str(file_path)]
                lint_commands[".js"] = ["eslint", "--fix", str(file_path)]
                lint_commands[".ts"] = ["eslint", "--fix", str(file_path)]
                lint_commands[".tsx"] = ["eslint", "--fix", str(file_path)]
                lint_commands[".jsx"] = ["eslint", "--fix", str(file_path)]
                lint_commands[".go"] = ["gofmt", "-w", str(file_path)]

            # Get the file extension
            ext = file_path.suffix.lower()
            if ext not in lint_commands:
                return f"Error: Unsupported file type: {ext}"

            # Run the linter
            cmd = lint_commands[ext]
            logger.debug(f"Running lint command: {' '.join(cmd)}")
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
            )

            # Check for linting errors
            if result.returncode == 0:
                if result.stdout.strip():
                    return f"Linting passed with notes:\n{result.stdout}"
                return f"Linting passed successfully for {path}"
            else:
                return f"Linting found issues in {path}:\n{result.stderr or result.stdout}"

        except Exception as e:
            logger.error(f"Error linting {path}: {str(e)}")
            return f"Error linting {path}: {str(e)}"

    @agently_function(
        description="Format code in a file using language-appropriate formatters."
    )
    def format_code(
        self,
        path: str,
    ) -> str:
        """
        Format code in a file using language-appropriate formatters.

        Args:
            path: Path to the file to format

        Returns:
            str: Status message indicating formatting results
        """
        print_action(f"Formatting file: {path}...")
        file_path = self._validate_path(path)
        if not file_path.exists():
            return f"Error: File not found: {file_path}"

        # Find the corresponding temp file path
        try:
            # Get relative path from workspace root
            if file_path.is_absolute():
                rel_path = file_path.relative_to(self.workspace_root)
            else:
                rel_path = file_path
            temp_path = (self.git_editor.temp_dir / rel_path).resolve()
            
            # Check if temp file exists (it might not if the file hasn't been staged yet)
            if not temp_path.exists():
                logger.debug(f"Temp file {temp_path} doesn't exist, staging file first")
                temp_path = self.git_editor._stage_file_for_edit(file_path)
        except Exception as e:
            logger.error(f"Error finding temp file for {file_path}: {str(e)}")
            return f"Error finding temp file: {str(e)}"

        # Map of extensions to formatting commands
        format_commands = {
            ".py": ["black", str(temp_path)],
            ".js": ["prettier", "--write", str(temp_path)],
            ".ts": ["prettier", "--write", str(temp_path)],
            ".go": ["gofmt", "-w", str(temp_path)],
            ".tf": ["terraform", "fmt", str(temp_path)],
            ".tfvars": ["terraform", "fmt", str(temp_path)],
            ".json": ["prettier", "--write", str(temp_path)],
            ".yaml": ["prettier", "--write", str(temp_path)],
            ".yml": ["prettier", "--write", str(temp_path)],
        }

        # Get the file extension
        ext = file_path.suffix.lower()
        if ext not in format_commands:
            return f"Error: Unsupported file type: {ext}"

        # Run the formatter
        try:
            cmd = format_commands[ext]
            logger.debug(f"Formatting temp file: {temp_path} with command: {' '.join(cmd)}")
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
            )

            if result.returncode == 0:
                # Make sure changes are staged in Git
                subprocess.run(
                    ["git", "add", str(rel_path)],
                    cwd=self.git_editor.temp_dir,
                    check=True,
                    capture_output=True,
                )
                return f"Successfully formatted {path}"
            else:
                error_msg = result.stderr.strip() or result.stdout.strip()
                return f"Error formatting {path}: {error_msg}"
        except FileNotFoundError:
            return f"Error: Required formatter not found for {ext} files"
        except Exception as e:
            return f"Error formatting {path}: {str(e)}"

