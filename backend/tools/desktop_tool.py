"""
JARVIS / PHOEBE - COMPLETE DESKTOP & PC CONTROL TOOLS
=====================================================
Registered tools providing full Windows PC control:
  - App discovery, launching & process termination
  - User folder access & recent download inspection
  - Workstation lock & desktop minimization
  - Native clipboard reading and writing
  - Comprehensive GPU (NVIDIA RTX), CPU, RAM, Disk, and Network diagnostics
"""

from typing import Any, Dict, List
from backend.ai.tool_registry import global_registry
from backend.automation.system_control import (
    close_app,
    control_media,
    control_volume,
    get_all_disks,
    get_clipboard_text,
    get_comprehensive_diagnostics,
    get_gpu_stats,
    get_recent_files,
    list_running_apps,
    lock_workstation,
    minimize_all_windows,
    open_app,
    open_latest_file,
    open_url,
    open_user_folder,
    set_clipboard_text,
    take_screenshot,
)


@global_registry.register(
    name="desktop_launch_app",
    description="Launch or open any installed application on the user's PC (e.g. Chrome, Steam, Spotify, VS Code, Excel, Word, Discord, Canva, etc.).",
    parameters={
        "type": "object",
        "properties": {
            "app_name": {"type": "string", "description": "Application name to launch."},
        },
        "required": ["app_name"],
    },
)
def tool_launch_app(app_name: str) -> Dict[str, Any]:
    ok, msg = open_app(app_name)
    return {"success": ok, "message": msg}


@global_registry.register(
    name="desktop_close_app",
    description="Close, terminate, or kill a running application or process on the user's PC.",
    parameters={
        "type": "object",
        "properties": {
            "app_name": {"type": "string", "description": "Application name or process to terminate."},
        },
        "required": ["app_name"],
    },
)
def tool_close_app(app_name: str) -> Dict[str, Any]:
    ok, msg = close_app(app_name)
    return {"success": ok, "message": msg}


@global_registry.register(
    name="desktop_list_running_apps",
    description="List active running desktop applications and their memory usage in MB.",
    parameters={
        "type": "object",
        "properties": {
            "limit": {"type": "integer", "description": "Maximum number of apps to list.", "default": 15},
        },
    },
)
def tool_list_running(limit: int = 15) -> List[Dict[str, Any]]:
    return list_running_apps(limit=limit)


@global_registry.register(
    name="desktop_open_folder",
    description="Open a Windows user folder (Downloads, Desktop, Documents, Pictures, Videos, Development) in File Explorer.",
    parameters={
        "type": "object",
        "properties": {
            "folder_name": {"type": "string", "description": "Folder to open (e.g. 'downloads', 'desktop', 'documents', 'development')."},
        },
        "required": ["folder_name"],
    },
)
def tool_open_folder(folder_name: str) -> Dict[str, Any]:
    ok, msg = open_user_folder(folder_name)
    return {"success": ok, "message": msg}


@global_registry.register(
    name="desktop_recent_files",
    description="Inspect the most recently modified or downloaded files in the Downloads or Desktop folder.",
    parameters={
        "type": "object",
        "properties": {
            "folder": {"type": "string", "description": "Folder to check ('downloads' or 'desktop').", "default": "downloads"},
            "limit": {"type": "integer", "description": "Maximum number of files to return.", "default": 5},
        },
    },
)
def tool_recent_files(folder: str = "downloads", limit: int = 5) -> List[Dict[str, Any]]:
    return get_recent_files(folder_name=folder, limit=limit)


@global_registry.register(
    name="desktop_open_latest_download",
    description="Open the most recently downloaded file on the PC.",
    parameters={"type": "object", "properties": {}},
)
def tool_open_latest() -> Dict[str, Any]:
    ok, msg = open_latest_file("downloads")
    return {"success": ok, "message": msg}


@global_registry.register(
    name="desktop_lock_pc",
    description="Lock the Windows computer workstation.",
    parameters={"type": "object", "properties": {}},
)
def tool_lock() -> Dict[str, Any]:
    ok, msg = lock_workstation()
    return {"success": ok, "message": msg}


@global_registry.register(
    name="desktop_show_desktop",
    description="Minimize all open windows to show the Windows desktop.",
    parameters={"type": "object", "properties": {}},
)
def tool_show_desktop() -> Dict[str, Any]:
    ok, msg = minimize_all_windows()
    return {"success": ok, "message": msg}


@global_registry.register(
    name="desktop_clipboard_read",
    description="Read the current text content from the Windows clipboard.",
    parameters={"type": "object", "properties": {}},
)
def tool_read_clipboard() -> Dict[str, Any]:
    text = get_clipboard_text()
    return {"success": True, "text": text}


@global_registry.register(
    name="desktop_clipboard_write",
    description="Copy text to the Windows clipboard.",
    parameters={
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "Text to place on clipboard."},
        },
        "required": ["text"],
    },
)
def tool_write_clipboard(text: str) -> Dict[str, Any]:
    ok = set_clipboard_text(text)
    return {"success": ok, "message": "Copied to clipboard." if ok else "Failed to copy."}


@global_registry.register(
    name="desktop_gpu_diagnostics",
    description="Inspect NVIDIA GPU model, VRAM utilization, and operating temperature.",
    parameters={"type": "object", "properties": {}},
)
def tool_gpu() -> Dict[str, Any]:
    gpu = get_gpu_stats()
    return {"success": gpu is not None, "gpu": gpu}


@global_registry.register(
    name="desktop_hardware_diagnostics",
    description="Retrieve comprehensive hardware diagnostics: CPU, RAM, GPU, storage across all drives, network counters, and battery status.",
    parameters={"type": "object", "properties": {}},
)
def tool_comprehensive_stats() -> Dict[str, Any]:
    diag = get_comprehensive_diagnostics()
    return {"success": True, "diagnostics": diag}


@global_registry.register(
    name="desktop_volume",
    description="Adjust system audio volume (up, down, mute).",
    parameters={
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["up", "down", "mute"], "description": "Volume action to perform."},
        },
        "required": ["action"],
    },
)
def tool_volume(action: str) -> Dict[str, Any]:
    ok, msg = control_volume(action)
    return {"success": ok, "message": msg}


@global_registry.register(
    name="desktop_media",
    description="Control media playback on Windows (play/pause toggle, next track, previous track).",
    parameters={
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["play_pause", "next", "previous"], "description": "Media action to perform."},
        },
        "required": ["action"],
    },
)
def tool_media(action: str) -> Dict[str, Any]:
    ok, msg = control_media(action)
    return {"success": ok, "message": msg}


@global_registry.register(
    name="desktop_screenshot",
    description="Capture and save a full-screen screenshot to disk.",
    parameters={"type": "object", "properties": {}},
)
def tool_screenshot() -> Dict[str, Any]:
    ok, msg = take_screenshot()
    return {"success": ok, "message": msg}
