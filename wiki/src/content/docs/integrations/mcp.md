---
title: MCP integration
description: Attach explicit stdio MCP servers without hiding their tools or network behavior.
---

Wallbreaker can launch configured MCP servers over stdio and proxy their tools into the agent
registry. Every server is explicit and disabled unless its configuration enables it.

```toml
[[mcp.servers]]
name = "example"
command = "python"
args = ["-m", "example_mcp"]
enabled = false
# tool_prefix = "example_"
```

Review the server's code, arguments, environment, filesystem access and network behavior before
enabling it. MCP tools run with the permissions of the Wallbreaker process.

P4RS3LT0NGV3 is available through native `parsel_*` tools after an explicit library update. An MCP
server wrapper remains available for operators who need out-of-process integration; do not enable
both under colliding tool names.

The detailed repository reference is
[`docs/mcp-integration.md`](https://github.com/Yivas/wallbreaker-hermes/blob/main/docs/mcp-integration.md).
