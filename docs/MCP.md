# ThumbShield MCP servers

The V3 demo exposes three stdio MCP servers from the project root:

```powershell
.\.venv\Scripts\python.exe -m mcp_servers.scanner_server
.\.venv\Scripts\python.exe -m mcp_servers.casestore_server
.\.venv\Scripts\python.exe -m mcp_servers.policy_server
```

The installed MCP v2 SDK documents `MCPServer` as the replacement for the older `FastMCP` import; the servers use that equivalent and `mcp.run()` stdio transport. Configure the same commands in Claude Desktop/Claude Code with the project working directory. All paths are confined to `data/`, and the fetch service only permits the local synthetic portal by default.
