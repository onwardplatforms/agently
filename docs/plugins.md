# Agently Plugins

Agently supports plugins to extend its functionality. Plugins can be loaded from local directories or GitHub repositories.

## Plugin Naming Convention

Agently plugins on GitHub should follow this naming convention:

- Repository name should start with the prefix `agently-plugin-`
- Example: `agently-plugin-hello`

This convention helps with discoverability and organization of plugins.

## Plugin Configuration

Plugins are configured in the `agently.yaml` file under the `plugins` section:

```yaml
plugins:
  # Local plugins
  local:
    - source: "./plugins/my-local-plugin"
      variables:
        key: "value"
  
  # GitHub plugins
  github:
    - source: "username/plugin-name"
      version: "main"
      variables:
        key: "value"
```

### GitHub Plugin Source Formats

The `source` field for GitHub plugins supports multiple formats:

1. Short format (recommended): `username/plugin-name`
   - Example: `onwardplatforms/hello`
   - The `agently-plugin-` prefix will be added automatically

2. Full GitHub path: `github.com/username/agently-plugin-name`
   - Example: `github.com/onwardplatforms/agently-plugin-hello`

3. Full URL: `https://github.com/username/agently-plugin-name`
   - Example: `https://github.com/onwardplatforms/agently-plugin-hello`

## Managing Plugins

Plugins are managed using a Terraform-like workflow:

```bash
# Step 1: Initialize plugins based on your agently.yaml
agently init

# Step 2: Run your agent (requires prior initialization)
agently run
```

The `init` command synchronizes your installed plugins with those defined in your configuration:
1. Installs any missing plugins
2. Cleans up the lockfile by removing plugins that are no longer in your config
3. With `--force`, reinstalls all plugins even if they are already installed

The `run` command executes your agent, but requires that plugins have been initialized first. If plugins are missing or the configuration has changed, you'll be prompted to run `init` again.

This workflow ensures that your environment is properly set up before running your agent, making the process more explicit and predictable.

## Listing Installed Plugins

To see what plugins are currently installed:

```bash
agently list
```

## Plugin Storage

Plugins are stored in the `.agently/plugins` directory with a structure that omits the `agently-plugin-` prefix:

```
.agently/plugins/
  username/
    plugin-name/
      main/
        # Plugin files
```

This makes paths shorter and more manageable. 