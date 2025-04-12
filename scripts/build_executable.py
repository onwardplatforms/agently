#!/usr/bin/env python3
"""
Build script for creating standalone executables using PyInstaller.
"""
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import importlib.metadata

def get_platform():
    """Get the current platform name."""
    system = platform.system().lower()
    if system == "darwin":
        return "macos"
    return system

def get_executable_extension():
    """Get the appropriate extension for executable files on the current platform."""
    if platform.system().lower() == "windows":
        return ".exe"
    return ""

def get_package_version():
    """Get the current package version."""
    try:
        # This will get the version from the installed package
        return importlib.metadata.version("agently-cli")
    except importlib.metadata.PackageNotFoundError:
        # If running in a development environment
        try:
            from setuptools_scm import get_version
            return get_version(root='..', relative_to=__file__)
        except:
            # Fallback to a default version if all else fails
            print("Warning: Could not determine package version, using fallback")
            return "0.2.1"

def build_executable():
    """Build standalone executable for the current platform."""
    platform_name = get_platform()
    executable_extension = get_executable_extension()
    output_dir = os.path.join("dist", "executables", platform_name)
    
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    # Create build directory for bundle
    build_dir = os.path.join(os.getcwd(), "build", "agently_bundle")
    os.makedirs(build_dir, exist_ok=True)
    
    # Copy the entire agently package to the bundle directory
    project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    agently_src = os.path.join(project_dir, "agently")
    agently_dst = os.path.join(build_dir, "agently")
    
    # Remove previous copy if exists
    if os.path.exists(agently_dst):
        shutil.rmtree(agently_dst)
    
    # Copy the entire package
    shutil.copytree(agently_src, agently_dst)
    
    # Get current version
    version = get_package_version()
    print(f"Building executable for version: {version}")
    
    # Ensure version files exist and have correct version
    version_file = os.path.join(agently_dst, "_version.py")
    with open(version_file, "w") as f:
        f.write(f'__version__ = "{version}"\n')
        f.write(f'version = "{version}"\n')
    
    # Also update the version.py file which is used by the CLI
    version_file = os.path.join(agently_dst, "version.py")
    with open(version_file, "w") as f:
        f.write(f'"""Version information."""\n\n')
        f.write(f'__all__ = ["__version__", "__version_tuple__", "version", "version_tuple"]\n\n')
        f.write(f'__version__ = "{version}"\n')
        f.write(f'version = "{version}"\n')
        f.write(f'version_tuple = tuple(version.split("."))\n')
        f.write(f'__version_tuple__ = version_tuple\n')
    
    # Create a standalone entry point script
    entry_script = os.path.join(build_dir, "entry_point.py")
    with open(entry_script, "w") as f:
        f.write("""
#!/usr/bin/env python3
\"\"\"
Standalone entry point for the agently CLI.
\"\"\"
import sys
import os

try:
    # Add the bundled modules to the path
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    
    # Import the CLI directly
    from agently.cli.commands import cli
    
    if __name__ == "__main__":
        # Run the CLI with the provided arguments
        sys.exit(cli())
except Exception as e:
    print(f"Error running agently: {e}")
    sys.exit(1)
""")
    
    # Create a PyInstaller hook file to ensure all modules are included
    hooks_dir = os.path.join(tempfile.gettempdir(), "agently_hooks")
    os.makedirs(hooks_dir, exist_ok=True)
    
    try:
        # Ensure agently is installed in development mode
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-e", "."])
        
        # Schema path check
        schema_path = os.path.join(project_dir, "agently", "config", "schema.json")
        if not os.path.exists(schema_path):
            print(f"Warning: Schema file not found at {schema_path}, creating an empty one")
            os.makedirs(os.path.dirname(schema_path), exist_ok=True)
            with open(schema_path, "w") as f:
                f.write("{}")
        
        # Data files to include
        data_files = [
            (schema_path, "agently/config"),
            (agently_dst, "agently")
        ]
        
        # Build executable using PyInstaller
        cmd = [
            "pyinstaller",
            "--onefile",  # Create a single executable file
            "--name", f"agently{executable_extension}",
            "--specpath", "build/specs",
            "--workpath", f"build/{platform_name}",
            "--distpath", output_dir,
            "--clean",  # Clean build files before building
            "--additional-hooks-dir", hooks_dir,
            "--hidden-import", "click",
            "--hidden-import", "json",
            "--hidden-import", "yaml",
            "--hidden-import", "dotenv",
        ]
        
        # Add data files
        for src, dst in data_files:
            cmd.extend(["--add-data", f"{src}{os.pathsep}{dst}"])
        
        # Add entry script
        cmd.append(entry_script)
        
        # Add icon if available
        if platform_name == "windows" and os.path.exists("agently/assets/icon.ico"):
            cmd.extend(["--icon", "agently/assets/icon.ico"])
        elif platform_name == "macos" and os.path.exists("agently/assets/icon.icns"):
            cmd.extend(["--icon", "agently/assets/icon.icns"])
        
        print(f"Building standalone executable for {platform_name}...")
        subprocess.check_call(cmd)
        
        print(f"Executable built successfully in {output_dir}")
        return os.path.join(output_dir, f"agently{executable_extension}")
    finally:
        # Clean up the temporary files
        if os.path.exists(entry_script):
            os.unlink(entry_script)
        if os.path.exists(hooks_dir):
            shutil.rmtree(hooks_dir)

if __name__ == "__main__":
    # Make sure the project directory is in Python's path
    project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if project_dir not in sys.path:
        sys.path.insert(0, project_dir)
    
    executable_path = build_executable()
    print(f"Executable available at: {executable_path}") 