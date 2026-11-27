"""
JARVIS / PHOEBE - CENTRAL TOOL REGISTRY & DEFINITION
====================================================
Standard schema, execution handler, validation, and error boundaries
for all local and network tools.
"""

import inspect
import logging
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class ToolDefinition:
    def __init__(
        self,
        name: str,
        description: str,
        parameters: Dict[str, Any],
        handler: Callable[..., Any],
        requires_confirmation: bool = False,
    ):
        self.name = name
        self.description = description
        self.parameters = parameters
        self.handler = handler
        self.requires_confirmation = requires_confirmation

    def to_schema(self) -> Dict[str, Any]:
        """Convert to OpenAI / Ollama compatible function tool schema."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def execute(self, **kwargs) -> Dict[str, Any]:
        """Execute tool with error handling."""
        try:
            res = self.handler(**kwargs)
            return {"ok": True, "result": res}
        except Exception as e:
            logger.error("Tool '%s' execution error: %s", self.name, e)
            return {"ok": False, "error": str(e)}


class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, ToolDefinition] = {}

    def register(
        self,
        name: str,
        description: str,
        parameters: Dict[str, Any],
        requires_confirmation: bool = False,
    ):
        """Decorator to register a function as an executable tool."""

        def decorator(fn: Callable[..., Any]):
            tool = ToolDefinition(
                name=name,
                description=description,
                parameters=parameters,
                handler=fn,
                requires_confirmation=requires_confirmation,
            )
            self._tools[name] = tool
            return fn

        return decorator

    def get_tool(self, name: str) -> Optional[ToolDefinition]:
        return self._tools.get(name)

    def list_tools(self) -> List[ToolDefinition]:
        return list(self._tools.values())

    def get_all_schemas(self) -> List[Dict[str, Any]]:
        return [t.to_schema() for t in self._tools.values()]

    def execute_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        tool = self.get_tool(name)
        if not tool:
            return {"ok": False, "error": f"Tool '{name}' not found in registry."}
        return tool.execute(**arguments)


# Global registry instance
global_registry = ToolRegistry()
