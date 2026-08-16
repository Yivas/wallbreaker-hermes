"""P4RS3LT0NGV3 MCP server.

Exposes the full elder-plinius/P4RS3LT0NGV3 transform catalog (222 transforms across
11 categories) plus the universal decoder over the Model Context Protocol, by driving
the upstream Node bridge (scripts/cli_bridge.js) headlessly. No npm build required.
"""

from .bridge import BridgeError, repo_dir

__all__ = ["BridgeError", "repo_dir", "__version__"]

__version__ = "0.2.2"
