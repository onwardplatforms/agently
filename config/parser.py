def create_agent_config(yaml_config: Dict[str, Any], config_path: Path) -> AgentConfig:
    """Convert YAML configuration to AgentConfig object.

    Args:
        yaml_config: The YAML configuration dictionary
        config_path: Path to the YAML configuration file

    Returns:
        AgentConfig object
    """
    # Create model config
    model_config = ModelConfig(
        provider=yaml_config["model"]["provider"],
        model=yaml_config["model"]["model"],
        temperature=yaml_config["model"]["temperature"],
        api_key=yaml_config["model"].get("api_key"),
        api_base=yaml_config["model"].get("api_base"),
        api_version=yaml_config["model"].get("api_version"),
        organization=yaml_config["model"].get("organization"),
    )

    # Get agent ID
    agent_id = yaml_config.get("id", f"agent-{uuid.uuid4().hex[:8]}")

    # Get continuous reasoning mode
    continuous_reasoning = yaml_config.get("continuous_reasoning", False)

    # Lists to collect configs
    plugin_configs: List[PluginConfig] = []
    mcp_server_configs: List[MCPServerConfig] = []
    capability_configs: List[CapabilityConfig] = []

    # Process plugins (flat array in the new schema)
    for plugin in yaml_config.get("plugins", []):
        # Get the source type (local or github)
        source_type = plugin["source"]
        # Get the plugin type (sk, mcp, or agently)
        plugin_type = plugin["type"]
        
        if source_type == "local":
            # Handle local plugin
            plugin_path = plugin["path"]
            if not os.path.isabs(plugin_path):
                plugin_path = (config_path.parent / plugin_path).resolve()

            local_source: PluginSourceType = LocalPluginSource(
                path=Path(plugin_path), 
                plugin_type=plugin_type
            )

            # For MCP type plugins, create additional MCP server config
            if plugin_type == "mcp":
                # Get the name for the MCP server (use path basename if not specified)
                name = plugin.get("name", Path(plugin_path).stem)

                if "command" in plugin and "args" in plugin:
                    mcp_server_configs.append(
                        MCPServerConfig(
                            name=name,
                            command=plugin["command"],
                            args=plugin.get("args", []),
                            description=plugin.get("description", ""),
                            variables=plugin.get("variables", {}),
                            source_type="local",
                            source_path=str(plugin_path),
                        )
                    )

            # Add to plugin_configs
            if plugin_type == "mcp":
                # MCP plugins should not have variables according to the schema
                plugin_configs.append(
                    PluginConfig(
                        source=local_source, 
                        variables={}  # Empty dict for MCP plugins
                    )
                )
            else:
                # Regular plugins can have variables
                plugin_configs.append(
                    PluginConfig(
                        source=local_source, 
                        variables=plugin.get("variables", {})
                    )
                )
        elif source_type == "github":
            # Handle GitHub plugin
            repo_url = plugin["url"]
            version = plugin.get("version", "main")
            branch = plugin.get("branch")
            namespace = plugin.get("namespace")
            
            # Determine the Git reference
            git_reference = branch if branch else version
            
            github_source: PluginSourceType = GitHubPluginSource(
                repo_url=repo_url,
                version=git_reference,
                namespace=namespace,
                plugin_type=plugin_type
            )
            
            # For MCP type plugins, create additional MCP server config
            if plugin_type == "mcp":
                # Get the name for the MCP server (use last part of URL if not specified)
                name = plugin.get("name")
                if not name:
                    if "/" in repo_url:
                        name = repo_url.split("/")[-1]
                    else:
                        name = repo_url
                
                if "command" in plugin and "args" in plugin:
                    mcp_server_configs.append(
                        MCPServerConfig(
                            name=name,
                            command=plugin["command"],
                            args=plugin.get("args", []),
                            description=plugin.get("description", ""),
                            variables=plugin.get("variables", {}),
                            source_type="github",
                            source_path=repo_url,
                        )
                    )
            
            # Add to plugin_configs
            if plugin_type == "mcp":
                # MCP plugins should not have variables according to the schema
                plugin_configs.append(
                    PluginConfig(
                        source=github_source,
                        variables={}  # Empty dict for MCP plugins
                    )
                )
            else:
                # Regular plugins can have variables
                plugin_configs.append(
                    PluginConfig(
                        source=github_source, 
                        variables=plugin.get("variables", {})
                    )
                )

    # Process capabilities
    for capability in yaml_config.get("capabilities", []):
        capability_configs.append(
            CapabilityConfig(
                name=capability["name"],
                description=capability.get("description", ""),
                instruction=capability.get("instruction", ""),
                variables=capability.get("variables", {}),
            )
        )

    # Create the agent config
    return AgentConfig(
        id=agent_id,
        name=yaml_config["name"],
        description=yaml_config["description"],
        system_prompt=yaml_config["system_prompt"],
        model=model_config,
        plugins=plugin_configs,
        mcp_servers=mcp_server_configs,
        capabilities=capability_configs,
        log_level=LogLevel.from_string(yaml_config.get("log_level", "none")),
        continuous_reasoning=continuous_reasoning,
    ) 