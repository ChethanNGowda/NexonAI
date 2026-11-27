"""Desktop automation tools for OpenJarvis on Windows (apps, media, volume, stats, screenshots)."""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.tools._stubs import BaseTool, ToolSpec

logger = logging.getLogger(__name__)

# Base directories
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
SCREENSHOT_DIR = BASE_DIR / "data" / "screenshots"
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

# Windows Virtual Key Codes
VK_VOLUME_MUTE = 0xAD
VK_VOLUME_DOWN = 0xAE
VK_VOLUME_UP = 0xAF
VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_STOP = 0xB2
VK_MEDIA_PLAY_PAUSE = 0xB3

KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002

APP_MAP = {
    "chrome": "chrome",
    "google chrome": "chrome",
    "browser": "chrome",
    "notepad": "notepad",
    "calculator": "calc",
    "calc": "calc",
    "vs code": "code",
    "vscode": "code",
    "code": "code",
    "spotify": "spotify",
    "terminal": "wt",
    "windows terminal": "wt",
    "cmd": "cmd",
    "command prompt": "cmd",
    "powershell": "powershell",
    "file explorer": "explorer",
    "explorer": "explorer",
    "files": "explorer",
    "task manager": "taskmgr",
    "taskmgr": "taskmgr",
    "edge": "msedge",
    "microsoft edge": "msedge",
    "brave": "brave",
    "settings": "ms-settings:",
    "steam": "steam",
    "discord": "discord",
}


def _press_key(vk_code: int, times: int = 1):
    """Simulate key presses via user32 keybd_event."""
    try:
        import ctypes
        user32 = ctypes.windll.user32
        for _ in range(times):
            user32.keybd_event(vk_code, 0, KEYEVENTF_EXTENDEDKEY, 0)
            time.sleep(0.03)
            user32.keybd_event(vk_code, 0, KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP, 0)
            time.sleep(0.03)
    except Exception as e:
        logger.warning("Key press simulation failed: %s", e)


def _find_app_path(name: str):
    """Resolve executable path using registry App Paths, common directories, and PATH."""
    clean = re.sub(r"[^\w\s-]", "", name).lower().strip()
    candidates = [clean, f"{clean}.exe"]

    try:
        import winreg
        for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            for cand in candidates:
                try:
                    k = winreg.OpenKey(hive, rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{cand}")
                    val, _ = winreg.QueryValueEx(k, "")
                    if val:
                        val = os.path.expandvars(val).strip('"')
                        if os.path.exists(val):
                            return val
                except OSError:
                    pass
    except Exception:
        pass

    # Check Steam specific registry
    if clean == "steam":
        try:
            import winreg
            for hive, subkey in [
                (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam"),
            ]:
                try:
                    k = winreg.OpenKey(hive, subkey)
                    for val_name in ("SteamExe", "InstallPath", "SteamPath"):
                        try:
                            val, _ = winreg.QueryValueEx(k, val_name)
                            if val:
                                val = os.path.expandvars(val).replace("/", "\\").strip('"')
                                if val.lower().endswith("steam.exe") and os.path.exists(val):
                                    return val
                                exe_cand = os.path.join(val, "steam.exe")
                                if os.path.exists(exe_cand):
                                    return exe_cand
                        except OSError:
                            pass
                except OSError:
                    pass
        except Exception:
            pass

    common_locations = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
        r"C:\Steam\steam.exe",
        r"C:\Program Files (x86)\Steam\steam.exe",
        r"C:\Program Files\Steam\steam.exe",
        r"D:\Steam\steam.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Discord\Discord.exe"),
        rf"C:\Windows\System32\{clean}.exe",
        rf"C:\Windows\{clean}.exe",
    ]
    for loc in common_locations:
        if os.path.exists(loc) and clean in loc.lower():
            return loc

    which_path = shutil.which(clean) or shutil.which(f"{clean}.exe")
    if which_path:
        return which_path

    return None


@ToolRegistry.register("desktop_open_app")
class DesktopOpenAppTool(BaseTool):
    """Tool to launch desktop applications on Windows."""

    tool_id = "desktop_open_app"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="desktop_open_app",
            description="Launch or open a desktop application on Windows (e.g. Chrome, Notepad, Calculator, VS Code, Spotify, File Explorer, Terminal).",
            parameters={
                "type": "object",
                "properties": {
                    "app_name": {
                        "type": "string",
                        "description": "The name or alias of the application to launch (e.g. 'chrome', 'notepad', 'calc', 'vscode', 'spotify', 'explorer').",
                    }
                },
                "required": ["app_name"],
            },
            category="desktop",
        )

    def execute(self, app_name: str = "", **kwargs: Any) -> ToolResult:
        clean_name = re.sub(r"[^\w\s-]", "", app_name).lower().strip()
        if not clean_name:
            return ToolResult(tool_name=self.spec.name, content="No application name provided.", success=False)

        target = APP_MAP.get(clean_name, clean_name)

        # 1. Special protocol for Steam
        if clean_name == "steam":
            resolved_steam = _find_app_path("steam")
            if resolved_steam and os.path.exists(resolved_steam):
                try:
                    os.startfile(resolved_steam)
                    return ToolResult(tool_name=self.spec.name, content="Launched Steam.", success=True)
                except Exception:
                    pass
            try:
                os.startfile("steam://open/main")
                return ToolResult(tool_name=self.spec.name, content="Launched Steam.", success=True)
            except Exception:
                pass

        # 2. URI protocols
        if target.endswith(":") or (":" in target and not "\\" in target):
            try:
                os.startfile(target)
                return ToolResult(tool_name=self.spec.name, content=f"Opened Windows {clean_name}.", success=True)
            except Exception:
                pass

        # 3. Registry resolved path
        resolved = _find_app_path(target)
        if resolved and os.path.exists(resolved):
            try:
                os.startfile(resolved)
                return ToolResult(tool_name=self.spec.name, content=f"Launched {clean_name}.", success=True)
            except Exception:
                pass

        # 4. Check system path
        which_target = shutil.which(target) or shutil.which(f"{target}.exe")
        if which_target and os.path.exists(which_target):
            try:
                os.startfile(which_target)
                return ToolResult(tool_name=self.spec.name, content=f"Launched {clean_name}.", success=True)
            except Exception:
                pass

        return ToolResult(tool_name=self.spec.name, content=f"Application '{clean_name}' was not found on this system.", success=False)


@ToolRegistry.register("desktop_volume_control")
class DesktopVolumeControlTool(BaseTool):
    """Tool to adjust Windows master audio volume."""

    tool_id = "desktop_volume_control"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="desktop_volume_control",
            description="Adjust Windows audio volume (actions: 'up', 'down', 'mute').",
            parameters={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["up", "down", "mute"],
                        "description": "Volume action to perform.",
                    }
                },
                "required": ["action"],
            },
            category="desktop",
        )

    def execute(self, action: str = "up", **kwargs: Any) -> ToolResult:
        act = action.lower().strip()
        if "up" in act or "increase" in act:
            _press_key(VK_VOLUME_UP, times=5)
            return ToolResult(tool_name=self.spec.name, content="Volume increased.", success=True)
        elif "down" in act or "decrease" in act:
            _press_key(VK_VOLUME_DOWN, times=5)
            return ToolResult(tool_name=self.spec.name, content="Volume decreased.", success=True)
        elif "mute" in act or "unmute" in act:
            _press_key(VK_VOLUME_MUTE, times=1)
            return ToolResult(tool_name=self.spec.name, content="Audio mute toggled.", success=True)
        return ToolResult(tool_name=self.spec.name, content=f"Unknown volume action: {action}", success=False)


@ToolRegistry.register("desktop_media_control")
class DesktopMediaControlTool(BaseTool):
    """Tool to control media playback."""

    tool_id = "desktop_media_control"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="desktop_media_control",
            description="Control media playback on Windows (actions: 'play_pause', 'next', 'previous', 'stop').",
            parameters={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["play_pause", "next", "previous", "stop"],
                        "description": "Media action to perform.",
                    }
                },
                "required": ["action"],
            },
            category="desktop",
        )

    def execute(self, action: str = "play_pause", **kwargs: Any) -> ToolResult:
        act = action.lower().strip()
        if "play" in act or "pause" in act:
            _press_key(VK_MEDIA_PLAY_PAUSE, times=1)
            return ToolResult(tool_name=self.spec.name, content="Media play/pause toggled.", success=True)
        elif "next" in act or "skip" in act:
            _press_key(VK_MEDIA_NEXT_TRACK, times=1)
            return ToolResult(tool_name=self.spec.name, content="Skipped to next track.", success=True)
        elif "previous" in act or "prev" in act:
            _press_key(VK_MEDIA_PREV_TRACK, times=1)
            return ToolResult(tool_name=self.spec.name, content="Returned to previous track.", success=True)
        elif "stop" in act:
            _press_key(VK_MEDIA_STOP, times=1)
            return ToolResult(tool_name=self.spec.name, content="Media stopped.", success=True)
        return ToolResult(tool_name=self.spec.name, content=f"Unknown media action: {action}", success=False)


@ToolRegistry.register("desktop_system_stats")
class DesktopSystemStatsTool(BaseTool):
    """Tool to retrieve hardware diagnostics and time."""

    tool_id = "desktop_system_stats"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="desktop_system_stats",
            description="Retrieve real-time Windows hardware stats (CPU, Memory, Disk, Battery percentage/charging status, current time and date).",
            parameters={"type": "object", "properties": {}},
            category="desktop",
        )

    def execute(self, **kwargs: Any) -> ToolResult:
        try:
            import psutil
            now = datetime.now()
            time_str = now.strftime("%I:%M %p")
            date_str = now.strftime("%A, %B %d, %Y")

            cpu_pct = psutil.cpu_percent(interval=0.1)
            mem = psutil.virtual_memory()
            disk = shutil.disk_usage("C:\\")

            battery = psutil.sensors_battery()
            battery_info = None
            if battery:
                battery_info = {
                    "percent": int(battery.percent),
                    "plugged": battery.power_plugged,
                }

            stats = {
                "time": time_str,
                "date": date_str,
                "cpu_percent": cpu_pct,
                "memory_percent": mem.percent,
                "disk_free_gb": round(disk.free / (1024**3), 1),
                "battery": battery_info,
            }
            return ToolResult(tool_name=self.spec.name, content=json.dumps(stats), metadata=stats, success=True)
        except Exception as e:
            return ToolResult(tool_name=self.spec.name, content=f"Failed to get system stats: {e}", success=False)


@ToolRegistry.register("desktop_take_screenshot")
class DesktopScreenshotTool(BaseTool):
    """Tool to take full screen screenshots."""

    tool_id = "desktop_take_screenshot"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="desktop_take_screenshot",
            description="Capture a full-screen screenshot and save it to data/screenshots.",
            parameters={"type": "object", "properties": {}},
            category="desktop",
        )

    def execute(self, **kwargs: Any) -> ToolResult:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = SCREENSHOT_DIR / f"screenshot_{timestamp}.png"

        try:
            from PIL import ImageGrab
            img = ImageGrab.grab()
            img.save(str(filename))
            return ToolResult(
                tool_name=self.spec.name,
                content=f"Screenshot captured and saved to {filename.name}.",
                metadata={"file_path": str(filename)},
                success=True,
            )
        except Exception:
            pass

        try:
            ps_cmd = (
                f"Add-Type -AssemblyName System.Windows.Forms, System.Drawing; "
                f"$b = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds; "
                f"$bmp = New-Object System.Drawing.Bitmap($b.Width, $b.Height); "
                f"$g = [System.Drawing.Graphics]::FromImage($bmp); "
                f"$g.CopyFromScreen($b.Location, [System.Drawing.Point]::Empty, $b.Size); "
                f"$bmp.Save('{str(filename)}'); $bmp.Dispose(); $g.Dispose()"
            )
            os.system(f'powershell -WindowStyle Hidden -Command "{ps_cmd}"')
            if filename.exists():
                return ToolResult(
                    tool_name=self.spec.name,
                    content=f"Screenshot captured and saved to {filename.name}.",
                    metadata={"file_path": str(filename)},
                    success=True,
                )
        except Exception as e:
            return ToolResult(tool_name=self.spec.name, content=f"Failed to capture screenshot: {e}", success=False)

        return ToolResult(tool_name=self.spec.name, content="Could not capture screenshot.", success=False)


@ToolRegistry.register("desktop_web_search")
class DesktopWebSearchTool(BaseTool):
    """Tool to search Google or YouTube and open in default browser."""

    tool_id = "desktop_web_search"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="desktop_web_search",
            description="Search Google or YouTube in the user's default browser.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search term or question."},
                    "engine": {
                        "type": "string",
                        "enum": ["google", "youtube"],
                        "description": "Search engine to open ('google' or 'youtube').",
                    },
                },
                "required": ["query"],
            },
            category="desktop",
        )

    def execute(self, query: str = "", engine: str = "google", **kwargs: Any) -> ToolResult:
        if not query.strip():
            return ToolResult(tool_name=self.spec.name, content="Empty search query.", success=False)

        q = urllib.parse.quote(query.strip())
        if engine.lower() == "youtube":
            url = f"https://www.youtube.com/results?search_query={q}"
        else:
            url = f"https://www.google.com/search?q={q}"

        webbrowser.open(url)
        return ToolResult(tool_name=self.spec.name, content=f"Opened browser search for '{query}' on {engine}.", success=True)


__all__ = [
    "DesktopOpenAppTool",
    "DesktopVolumeControlTool",
    "DesktopMediaControlTool",
    "DesktopSystemStatsTool",
    "DesktopScreenshotTool",
    "DesktopWebSearchTool",
]
