"""Hands-free voice assistant command for OpenJarvis."""

from __future__ import annotations

import click


@click.command(
    "voice",
    help="Launch the JARVIS hands-free desktop voice assistant.",
)
@click.option(
    "--always-listen",
    is_flag=True,
    default=False,
    help="Respond to all speech without requiring 'Jarvis' wake-word.",
)
@click.option(
    "--text",
    is_flag=True,
    default=False,
    help="Interactive text mode without microphone.",
)
@click.option(
    "--silent",
    is_flag=True,
    default=False,
    help="Suppress initial startup greeting voice.",
)
def voice(always_listen: bool, text: bool, silent: bool) -> None:
    """Run the hands-free voice loop or text console."""
    import jarvis

    if text:
        jarvis.run_text_mode()
    else:
        jarvis.run_voice_loop(always_listen=always_listen, silent_greeting=silent)


__all__ = ["voice"]
