"""
=============================================================================
DISCORD INTEGRATION FOR PHOEBE / JARVIS (NEXON AI)
=============================================================================
Supports:
  1. Discord Webhooks (post instant notifications, research summaries, and chat)
  2. Full Two-Way Discord Bot (chat 24/7 in Discord servers/DMs using local Ollama)
=============================================================================
"""

import os
import sys
import json
import asyncio
import logging
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional, Dict, Any, List

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

logger = logging.getLogger("PhoebeDiscord")

# =============================================================================
# 1. DISCORD WEBHOOK CLIENT (Zero-configuration / Instant)
# =============================================================================

def send_discord_webhook(
    content: str,
    webhook_url: Optional[str] = None,
    username: str = "Phoebe (NexonAI)",
    avatar_url: Optional[str] = None,
    embeds: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Send a message or embed to a Discord channel via Webhook.
    Does not require a Discord Bot account or OAuth token.
    """
    url = webhook_url or os.getenv("DISCORD_WEBHOOK_URL", "").strip()
    if not url:
        return {
            "ok": False,
            "error": "No DISCORD_WEBHOOK_URL configured. Please set DISCORD_WEBHOOK_URL in your .env file."
        }

    payload: Dict[str, Any] = {
        "content": content[:2000] if content else "",
        "username": username,
    }
    if avatar_url:
        payload["avatar_url"] = avatar_url
    if embeds:
        payload["embeds"] = embeds[:10]

    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "NexonAI-Phoebe/1.0",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            # Discord webhooks return 204 No Content on success
            if resp.status in (200, 204):
                return {"ok": True, "status": resp.status, "message": "Message posted to Discord successfully."}
            return {"ok": False, "status": resp.status, "error": f"Unexpected status: {resp.status}"}
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode("utf-8", errors="ignore")
        return {"ok": False, "status": e.code, "error": f"HTTP {e.code}: {err_msg}"}
    except Exception as e:
        return {"ok": False, "error": f"Failed to send Discord message: {e}"}


def send_research_to_discord(
    topic: str,
    summary: str,
    sources: Optional[List[Dict[str, str]]] = None,
    webhook_url: Optional[str] = None,
) -> Dict[str, Any]:
    """Format and send a Gemini-style research report to Discord with rich embeds."""
    embed: Dict[str, Any] = {
        "title": f"🔬 Research Report: {topic[:200]}",
        "description": summary[:4000] if summary else "No summary available.",
        "color": 0x5865F2,  # Discord Blurple
        "footer": {
            "text": "Generated locally by Phoebe (NexonAI) using Ollama",
        },
    }

    if sources:
        fields = []
        for i, s in enumerate(sources[:5], 1):
            title = s.get("title", f"Source {i}")[:250]
            url = s.get("url", "")
            fields.append({
                "name": f"[{i}] {title}",
                "value": f"[Read Article]({url})" if url else "Local Reference",
                "inline": False,
            })
        if fields:
            embed["fields"] = fields

    return send_discord_webhook(
        content=f"**New Research Findings for:** *{topic}*",
        webhook_url=webhook_url,
        embeds=[embed],
    )


# =============================================================================
# 2. TWO-WAY DISCORD BOT (Chat 24/7 using Local Ollama)
# =============================================================================

def run_discord_bot(token: Optional[str] = None):
    """
    Launch full two-way Discord bot powered by the Unified AI Assistant.
    Listens for @mentions or DMs and replies in real-time.
    """
    try:
        import discord
        from discord.ext import commands
    except ImportError:
        print("[ERROR] discord.py is not installed. Run: pip install discord.py", file=sys.stderr)
        return

    from backend.ai.assistant import UnifiedAssistant

    bot_token = token or os.getenv("DISCORD_BOT_TOKEN", "").strip()
    if not bot_token:
        print(
            "\n[DISCORD BOT] No DISCORD_BOT_TOKEN found in .env!\n"
            "To use the two-way Discord Bot:\n"
            "  1. Go to https://discord.com/developers/applications\n"
            "  2. Create an Application -> Bot -> Reset Token\n"
            "  3. Enable 'Message Content Intent'\n"
            "  4. Add DISCORD_BOT_TOKEN=your_token_here to .env\n",
            file=sys.stderr,
        )
        return

    intents = discord.Intents.default()
    intents.message_content = True

    bot = commands.Bot(command_prefix="!", intents=intents)
    assistant = UnifiedAssistant()

    @bot.event
    async def on_ready():
        print(f"\n=======================================================")
        print(f" [DISCORD BOT] Phoebe is logged in as {bot.user} (ID: {bot.user.id})")
        print(f" [DISCORD BOT] Connected to {len(bot.guilds)} server(s). Ready to chat!")
        print(f"=======================================================\n")
        activity = discord.Activity(type=discord.ActivityType.listening, name="your commands | Powered by NexonAI")
        await bot.change_presence(status=discord.Status.online, activity=activity)

    @bot.event
    async def on_message(message: discord.Message):
        if message.author == bot.user or message.author.bot:
            return

        is_dm = isinstance(message.channel, discord.DMChannel)
        is_mentioned = bot.user in message.mentions

        if is_dm or is_mentioned:
            # Strip bot mention from query text
            clean_prompt = message.clean_content.replace(f"@{bot.user.name}", "").strip()
            if not clean_prompt:
                await message.reply("Hello! I am Phoebe, your desktop AI companion. How can I assist you today?")
                return

            async with message.channel.typing():
                loop = asyncio.get_running_loop()
                # Run local Ollama AI synthesis in executor so it doesn't block async event loop
                res = await loop.run_in_executor(None, assistant.process, clean_prompt)
                answer = res.get("spoken_answer") or res.get("markdown_report") or "I could not generate a response, sir."

                # Discord 2000 character message limit handling
                if len(answer) <= 2000:
                    await message.reply(answer)
                else:
                    chunks = [answer[i:i + 1950] for i in range(0, len(answer), 1950)]
                    for chunk in chunks:
                        await message.channel.send(chunk)

        await bot.process_commands(message)

    bot.run(bot_token)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Phoebe Discord Integration")
    parser.add_argument("--bot", action="store_true", help="Launch full two-way Discord bot")
    parser.add_argument("--send", type=str, help="Send a test message via Discord webhook")
    parser.add_argument("--webhook", type=str, help="Webhook URL override")
    args = parser.parse_args()

    if args.send:
        res = send_discord_webhook(args.send, webhook_url=args.webhook)
        print(json.dumps(res, indent=2))
    elif args.bot:
        run_discord_bot()
    else:
        parser.print_help()
