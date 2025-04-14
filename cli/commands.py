def _initialize_plugins(config_path, quiet=False, force=False, agent_id=None):
    """Initialize plugins and MCP servers based on a configuration file.

    Args:
        config_path: Path to the agent configuration file
        quiet: Whether to reduce output verbosity
        force: Force reinstallation of all plugins and MCP servers
        agent_id: Optional ID of specific agent to initialize

    Returns:
        Dict with plugin statistics

    Raises:
        FileNotFoundError: If the configuration file does not exist
    """
    # Load the agent configuration
    config_path = Path(config_path)
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    if force and not quiet:
        click.echo("Force mode enabled: reinstalling all plugins")

    # Parse YAML configuration to extract plugins
    try:
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML in configuration file: {e}")

    # Determine lockfile path (at the same level as .agently folder)
    lockfile_path = Path.cwd() / "agently.lockfile.json"

    # Create empty lockfile if it doesn't exist or load existing one
    if not lockfile_path.exists():
        logger.info("Creating new lockfile")
        lockfile = {
            "agents": {},
            "plugins": {"sk": {}, "mcp": {}, "agently": {}}  # Add agently to supported types
        }
    else:
        # Load existing lockfile
        with open(lockfile_path, "r") as f:
            try:
                lockfile = json.load(f)
            except json.JSONDecodeError:
                logger.error("Invalid lockfile, creating new one")
                lockfile = {
                    "agents": {},
                    "plugins": {"sk": {}, "mcp": {}, "agently": {}}
                }

        # Ensure lockfile has correct structure
        if "agents" not in lockfile:
            lockfile["agents"] = {}
        if "plugins" not in lockfile:
            lockfile["plugins"] = {"sk": {}, "mcp": {}, "agently": {}}
        elif "sk" not in lockfile["plugins"]:
            lockfile["plugins"]["sk"] = {}
        elif "mcp" not in lockfile["plugins"]:
            lockfile["plugins"]["mcp"] = {}
        elif "agently" not in lockfile["plugins"]:
            lockfile["plugins"]["agently"] = {}

    # Check if we have a multi-agent config
    if "agents" in config and config["agents"]:
        # Multi-agent configuration
        agents_to_process = []
        
        if agent_id:
            # Find specific agent
            agent = next((a for a in config["agents"] if a.get("id") == agent_id), None)
            if not agent:
                raise ValueError(f"Agent with ID '{agent_id}' not found in configuration")
            
            agents_to_process.append(agent)
            if not quiet:
                click.echo(f"Initializing plugins for agent: {agent.get('name')} ({agent_id})")
        else:
            # Initialize all agents
            agents_to_process = config["agents"]
            if not quiet:
                click.echo(f"Initializing plugins for {len(agents_to_process)} agents")
    else:
        # This should not happen with the new schema
        raise ValueError("No agents found in configuration")

    # Stats counters
    stats = {
        "added": 0,
        "updated": 0,
        "unchanged": 0,
        "removed": 0,
        "failed": 0,
    }

    # Process each agent
    for agent in agents_to_process:
        agent_id = agent.get("id", f"agent-{uuid4().hex[:8]}")
        agent_name = agent.get("name", "default")
        
        if not quiet:
            click.echo(f"\nProcessing agent: {agent_name} ({agent_id})")
        
        # Ensure agent exists in lockfile
        if agent_id not in lockfile["agents"]:
            lockfile["agents"][agent_id] = {
                "name": agent_name,
                "plugins": {"sk": {}, "mcp": {}, "agently": {}}
            }
        # Ensure all plugin types exist in agent's plugins
        if "plugins" not in lockfile["agents"][agent_id]:
            lockfile["agents"][agent_id]["plugins"] = {"sk": {}, "mcp": {}, "agently": {}}
        if "sk" not in lockfile["agents"][agent_id]["plugins"]:
            lockfile["agents"][agent_id]["plugins"]["sk"] = {}
        if "mcp" not in lockfile["agents"][agent_id]["plugins"]:
            lockfile["agents"][agent_id]["plugins"]["mcp"] = {}
        if "agently" not in lockfile["agents"][agent_id]["plugins"]:
            lockfile["agents"][agent_id]["plugins"]["agently"] = {}
        
        # Get plugins for this agent (flat array in new schema)
        plugins = agent.get("plugins", [])
        
        # Display plugin statuses in Terraform-like format
        total_plugins = len(plugins)
        
        if not quiet and total_plugins > 0:
            click.echo(f"Found {total_plugins} plugins for agent {agent_name}")
        
        # Track which plugins are installed and which to remove
        installed_plugins = {"sk": set(), "mcp": set(), "agently": set()}
        to_add = {"sk": set(), "mcp": set(), "agently": set()}
        to_update = {"sk": set(), "mcp": set(), "agently": set()}
        unchanged = {"sk": set(), "mcp": set(), "agently": set()}
        failed = {"sk": set(), "mcp": set(), "agently": set()}
        
        # Process plugins from flat array
        for plugin_config in plugins:
            source_type = plugin_config["source"]
            plugin_type = plugin_config["type"]  # Required in new schema
            
            if source_type == "local":
                # Process local plugin
                source_path = plugin_config["path"]
                
                abs_source_path = config_path.parent / source_path if not os.path.isabs(source_path) else Path(source_path)
                
                # Use the same naming approach as during detection
                plugin_name = os.path.basename(source_path)
                
                # Determine plugin key for tracking
                plugin_key = f"local/{plugin_name}"
                
                # Handle plugin based on its type
                if plugin_type == "agently":
                    # For agently type, we need to ensure variables are provided
                    if "variables" not in plugin_config:
                        if not quiet:
                            click.echo(f"{styles.red('✗')} Failed to install {plugin_key}: 'agently' type plugins must include variables")
                        failed[plugin_type].add(plugin_key)
                        stats["failed"] += 1
                        continue
                    
                    # Check if plugin exists in lockfile
                    agent_plugin_section = lockfile["agents"][agent_id]["plugins"][plugin_type]
                    if plugin_key in agent_plugin_section:
                        unchanged[plugin_type].add(plugin_key)
                        if not quiet:
                            click.echo(f"- {plugin_key} is up to date")
                    else:
                        to_add[plugin_type].add(plugin_key)
                        if not quiet:
                            click.echo(f"- Installing {plugin_key}...")

                    try:
                        # For agently type, we're loading the base plugin but tracking it as agently type
                        # This is the key change - use "sk" for loading but maintain "agently" for tracking
                        local_source = LocalPluginSource(
                            path=abs_source_path,
                            namespace="local",
                            name=plugin_name,
                            force_reinstall=force,
                            plugin_type="sk"  # Use sk type for loading
                        )
                        
                        # Load plugin
                        plugin_class = local_source.load()
                        
                        # Get plugin info for lockfile
                        plugin_info = local_source._get_plugin_info(plugin_class)
                        
                        # Add variables from config
                        plugin_info["variables"] = plugin_config["variables"]
                        
                        # Add to installed plugins
                        installed_plugins[plugin_type].add(plugin_key)
                        
                        # Update lockfile with plugin info
                        lockfile["agents"][agent_id]["plugins"][plugin_type][plugin_key] = plugin_info
                        # Also update shared plugins for backward compatibility
                        lockfile["plugins"][plugin_type][plugin_key] = plugin_info
                        
                        if plugin_key in to_add[plugin_type]:
                            stats["added"] += 1
                        else:
                            stats["unchanged"] += 1
                            
                    except Exception as e:
                        logger.error(f"Failed to install local plugin {source_path}: {e}")
                        failed[plugin_type].add(plugin_key)
                        stats["failed"] += 1
                        if not quiet:
                            click.echo(f"{styles.red('✗')} Failed to install {plugin_key}: {e}")
                
                elif plugin_type == "sk" or plugin_type == "mcp":
                    # Standard handling for sk and mcp plugins
                    local_source = LocalPluginSource(
                        path=abs_source_path,
                        namespace="local",
                        name=plugin_name,
                        force_reinstall=force,
                        plugin_type=plugin_type
                    )
                    
                    # Determine if plugin needs to be added/updated
                    agent_plugin_section = lockfile["agents"][agent_id]["plugins"][plugin_type]
                    if plugin_key in agent_plugin_section:
                        # Check if update needed
                        lockfile_sha = agent_plugin_section[plugin_key].get("sha", "")
                        if force or local_source.needs_update(lockfile_sha):
                            to_update[plugin_type].add(plugin_key)
                            if not quiet:
                                click.echo(f"- Updating {plugin_key} from local path...")
                        else:
                            unchanged[plugin_type].add(plugin_key)
                            if not quiet:
                                click.echo(f"- {plugin_key} is up to date")
                    else:
                        to_add[plugin_type].add(plugin_key)
                        if not quiet:
                            click.echo(f"- Installing {plugin_key}...")
                    
                    try:
                        # Load plugin
                        plugin_class = local_source.load()
                        
                        # Get plugin info for lockfile
                        plugin_info = local_source._get_plugin_info(plugin_class)
                        
                        # Add variables from config if present
                        if "variables" in plugin_config:
                            plugin_info["variables"] = plugin_config["variables"]
                        
                        # Add to installed plugins
                        installed_plugins[plugin_type].add(plugin_key)
                        
                        # Update lockfile with plugin info
                        lockfile["agents"][agent_id]["plugins"][plugin_type][plugin_key] = plugin_info
                        # Also update shared plugins (backward compatibility)
                        lockfile["plugins"][plugin_type][plugin_key] = plugin_info
                        
                        if plugin_key in to_add[plugin_type]:
                            stats["added"] += 1
                        elif plugin_key in to_update[plugin_type]:
                            stats["updated"] += 1
                        else:
                            stats["unchanged"] += 1
                        
                    except Exception as e:
                        logger.error(f"Failed to install local plugin {source_path}: {e}")
                        failed[plugin_type].add(plugin_key)
                        stats["failed"] += 1
                        if not quiet:
                            click.echo(f"{styles.red('✗')} Failed to install {plugin_key}: {e}")
                
                else:
                    # Unsupported plugin type
                    if not quiet:
                        click.echo(f"{styles.red('✗')} Unsupported plugin type: {plugin_type}")
                    failed["sk"].add(plugin_key)  # Just for tracking
                    stats["failed"] += 1
            
            elif source_type == "github":
                # Process GitHub plugin
                repo_url = plugin_config["url"]
                version = plugin_config.get("version", plugin_config.get("branch", "main"))
                
                # Determine plugin key (will be updated after source is created)
                plugin_key = f"github/{os.path.basename(repo_url)}"
                
                if plugin_type == "agently":
                    # For agently type, we need to ensure variables are provided
                    if "variables" not in plugin_config:
                        if not quiet:
                            click.echo(f"{styles.red('✗')} Failed to install {plugin_key}: 'agently' type plugins must include variables")
                        failed[plugin_type].add(plugin_key)
                        stats["failed"] += 1
                        continue
                    
                    try:
                        # Create source with sk type for loading but track as agently
                        source = GitHubPluginSource(
                            repo_url=repo_url,
                            plugin_path=plugin_config.get("plugin_path", ""),
                            namespace=plugin_config.get("namespace", ""),
                            name=plugin_config.get("name", ""),
                            version=version,
                            force_reinstall=force,
                            plugin_type="sk"  # Use sk for loading
                        )
                        
                        # Update plugin key with namespace and name
                        plugin_key = f"{source.namespace}/{source.name}"
                        
                        # Check if plugin exists in lockfile
                        agent_plugin_section = lockfile["agents"][agent_id]["plugins"][plugin_type]
                        if plugin_key in agent_plugin_section:
                            unchanged[plugin_type].add(plugin_key)
                            if not quiet:
                                click.echo(f"- {plugin_key} is up to date")
                        else:
                            to_add[plugin_type].add(plugin_key)
                            if not quiet:
                                click.echo(f"- Installing {plugin_key} {version}...")
                        
                        # Load plugin
                        plugin_class = source.load()
                        
                        # Get plugin info for lockfile
                        plugin_info = source._get_plugin_info(plugin_class)
                        
                        # Add variables from config
                        plugin_info["variables"] = plugin_config["variables"]
                        
                        # Add to installed plugins
                        installed_plugins[plugin_type].add(plugin_key)
                        
                        # Update lockfile with plugin info
                        lockfile["agents"][agent_id]["plugins"][plugin_type][plugin_key] = plugin_info
                        # Also update shared plugins (backward compatibility)
                        lockfile["plugins"][plugin_type][plugin_key] = plugin_info
                        
                        if plugin_key in to_add[plugin_type]:
                            stats["added"] += 1
                        else:
                            stats["unchanged"] += 1
                        
                    except Exception as e:
                        logger.error(f"Failed to install GitHub plugin {repo_url}: {e}")
                        failed[plugin_type].add(plugin_key)
                        stats["failed"] += 1
                        if not quiet:
                            click.echo(f"{styles.red('✗')} Failed to install {plugin_key}: {e}")
                
                elif plugin_type == "sk" or plugin_type == "mcp":
                    # Standard handling for sk and mcp plugins
                    # Create a GitHubPluginSource
                    source = GitHubPluginSource(
                        repo_url=repo_url,
                        plugin_path=plugin_config.get("plugin_path", ""),
                        namespace=plugin_config.get("namespace", ""),
                        name=plugin_config.get("name", ""),
                        version=version,
                        force_reinstall=force,
                        plugin_type=plugin_type
                    )
                    
                    # Update plugin key with namespace and name
                    plugin_key = f"{source.namespace}/{source.name}"
                    
                    # Determine if plugin needs to be added/updated
                    agent_plugin_section = lockfile["agents"][agent_id]["plugins"][plugin_type]
                    if plugin_key in agent_plugin_section:
                        # Check if update needed
                        lockfile_sha = agent_plugin_section[plugin_key].get("sha", "")
                        if force or source.needs_update(lockfile_sha):
                            to_update[plugin_type].add(plugin_key)
                            if not quiet:
                                click.echo(f"- Updating {plugin_key} to {version}...")
                        else:
                            unchanged[plugin_type].add(plugin_key)
                            if not quiet:
                                click.echo(f"- {plugin_key} is up to date")
                    else:
                        to_add[plugin_type].add(plugin_key)
                        if not quiet:
                            click.echo(f"- Installing {plugin_key} {version}...")
                    
                    try:
                        # Load plugin
                        plugin_class = source.load()
                        
                        # Get plugin info for lockfile
                        plugin_info = source._get_plugin_info(plugin_class)
                        
                        # Add variables from config if present
                        if "variables" in plugin_config:
                            plugin_info["variables"] = plugin_config["variables"]
                        
                        # Add to installed plugins
                        installed_plugins[plugin_type].add(plugin_key)
                        
                        # Update lockfile with plugin info
                        lockfile["agents"][agent_id]["plugins"][plugin_type][plugin_key] = plugin_info
                        # Also update shared plugins (backward compatibility)
                        lockfile["plugins"][plugin_type][plugin_key] = plugin_info
                        
                        if plugin_key in to_add[plugin_type]:
                            stats["added"] += 1
                        elif plugin_key in to_update[plugin_type]:
                            stats["updated"] += 1
                        else:
                            stats["unchanged"] += 1
                        
                    except Exception as e:
                        logger.error(f"Failed to install GitHub plugin {repo_url}: {e}")
                        failed[plugin_type].add(plugin_key)
                        stats["failed"] += 1
                        if not quiet:
                            click.echo(f"{styles.red('✗')} Failed to install {plugin_key}: {e}")
                
                else:
                    # Unsupported plugin type
                    if not quiet:
                        click.echo(f"{styles.red('✗')} Unsupported plugin type: {plugin_type}")
                    failed["sk"].add(plugin_key)  # Just for tracking
                    stats["failed"] += 1
                    
        # Remove plugins that are no longer in the config for this agent
        for plugin_type in ["sk", "mcp", "agently"]:
            agent_plugin_section = lockfile["agents"][agent_id]["plugins"].get(plugin_type, {})
            if plugin_type not in lockfile["agents"][agent_id]["plugins"]:
                lockfile["agents"][agent_id]["plugins"][plugin_type] = {}
                continue
                
            current_plugins = set(agent_plugin_section.keys())
            config_plugins = installed_plugins[plugin_type]
            
            for plugin_key in current_plugins - config_plugins:
                agent_plugin_section.pop(plugin_key, None)
                if not quiet:
                    click.echo(f"- Removing {plugin_key}...")
                stats["removed"] += 1
    
    # Write updated lockfile
    with open(lockfile_path, "w") as f:
        json.dump(lockfile, f, indent=2)
    
    # Display summary
    if not quiet:
        click.echo("\nAgent initialization summary:")
        click.echo(format_apply_summary(
            stats["added"],
            stats["updated"],
            stats["unchanged"],
            stats["removed"],
            stats["failed"]
        ))
    
    return stats 