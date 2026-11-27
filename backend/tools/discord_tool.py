"""
=============================================================================
DISCORD TOOL FOR PHOEBE / JARVIS
=============================================================================
Allows the AI assistant and user to send messages and research summaries directly to Discord.
=============================================================================
"""

from typing import Dict, Any, Optional
from backend.ai.tool_registry import ToolRegistry, BaseTool, ToolSpec, ToolResult
from backend.integrations.discord_client import send_discord_webhook, send_research_to_discord


@ToolRegistry.register("discord_send_message")
class DiscordSendMessageTool(BaseTool):
    """Tool to send messages or research updates to Discord."""

    tool_id = "discord_send_message"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="discord_send_message",
            description="Send a chat message or notification to Discord via configured webhook.",
            parameters={
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "The message text to send to Discord.",
                    },
                    "topic": {
                        "type": "string",
                        "description": "Optional title or topic if sending an announcement or research report.",
                    },
                },
                "required": ["message"],
            },
            category="communication",
        )

    def execute(self, message: str, topic: Optional[str] = None, **kwargs: Any) -> ToolResult:
        if topic:
            res = send_research_to_discord(topic=topic, summary=message)
        else:
            res = send_discord_webhook(content=message)

        if res.get("ok"):
            return ToolResult(
                tool_name=self.spec.name,
                content="Message successfully posted to Discord.",
                success=True,
                data=res,
            )
        return ToolResult(
            tool_name=self.spec.name,
            content=f"Failed to post to Discord: {res.get('error', 'Unknown error')}",
            success=False,
            data=res,
        )
