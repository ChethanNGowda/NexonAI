"""
JARVIS / PHOEBE - COMPLETE WINDOWS PC AUTOMATION & SYSTEM ENGINE
================================================================
Comprehensive PC integration covering:
  - Dynamic discovery & launching of all installed applications (.lnk & registry)
  - Running process inspection & termination (closing apps)
  - Windows user folder shortcuts (Downloads, Documents, Desktop, Development)
  - Recent file tracking & opening latest downloads
  - System power controls (Lock PC, Sleep, Show Desktop / Minimize All)
  - Native clipboard inspection and copy/paste
  - Full hardware diagnostics (NVIDIA GPU VRAM & temp, CPU, RAM, Disks, Network, Battery)
  - Audio volume & media playback simulation
  - Screenshots & browser searches
"""

import ctypes
import glob
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
from typing import Any, Dict, List, Optional, Tuple

import psutil
from PIL import ImageGrab

try:
    import win32clipboard
    HAS_WIN32CLIP = True
except Exception:
    HAS_WIN32CLIP = False

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent.parent
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
VK_LWIN = 0x5B
VK_D = 0x44

KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002


def _press_key(vk_code: int, times: int = 1):
    """Simulate key presses via user32 keybd_event."""
    user32 = ctypes.windll.user32
    for _ in range(times):
        user32.keybd_event(vk_code, 0, KEYEVENTF_EXTENDEDKEY, 0)
        time.sleep(0.03)
        user32.keybd_event(vk_code, 0, KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP, 0)
        time.sleep(0.03)


# Static aliases for standard executables and protocol handlers
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
    "brave browser": "brave",
    "settings": "ms-settings:",
    "bluetooth": "ms-settings:bluetooth",
    "bluetooth settings": "ms-settings:bluetooth",
    "wifi": "ms-settings:network-wifi",
    "wifi settings": "ms-settings:network-wifi",
    "sound settings": "ms-settings:sound",
    "display settings": "ms-settings:display",
    "windows update": "ms-settings:windowsupdate",
    "battery settings": "ms-settings:batterysaver",
    "camera": "microsoft.windows.camera:",
    "photos": "ms-photos:",
    "paint": "mspaint",
    "snipping tool": "snippingtool",
    "snip": "snippingtool",
    "steam": "steam",
    "discord": "discord",
    "whatsapp": "whatsapp:",
    "telegram": "tg:",
    "slack": "slack:",
    "word": "winword",
    "excel": "excel",
    "powerpoint": "powerpnt",
    "onenote": "onenote",
    "canva": "canva",
    "git bash": "git-bash",
    "rockstar games": "rockstar games launcher",
    "rockstar": "rockstar games launcher",
    "epic games": "com.epicgames.launcher://",
    "epic": "com.epicgames.launcher://",
    "riot client": "riotclient://",
    "xbox": "xbox:",
    "armoury crate": "armourycrate:",
    "creative cloud": r"C:\Program Files\Adobe\Adobe Creative Cloud\ACC\Creative Cloud.exe",
    "adobe": r"C:\Program Files\Adobe\Adobe Creative Cloud\ACC\Creative Cloud.exe",
}

_CACHED_SHORTCUTS: Optional[Dict[str, str]] = None
_CACHED_STEAM_GAMES: Optional[Dict[str, Dict[str, str]]] = None


def get_installed_steam_games(force_refresh: bool = False) -> Dict[str, Dict[str, str]]:
    """
    Dynamically scan all Steam library folders for installed Steam games.
    Returns mapping of normalized game title -> {'appid': '730', 'name': 'Counter-Strike 2'}.
    """
    global _CACHED_STEAM_GAMES
    if _CACHED_STEAM_GAMES is not None and not force_refresh:
        return _CACHED_STEAM_GAMES

    discovered: Dict[str, Dict[str, str]] = {}
    search_dirs = [
        r"C:\steam\steamapps",
        r"C:\Program Files (x86)\Steam\steamapps",
        r"C:\Program Files\Steam\steamapps",
        r"D:\Steam\steamapps",
        r"D:\SteamLibrary\steamapps",
        r"E:\SteamLibrary\steamapps",
    ]

    try:
        import winreg
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam")
        steam_path, _ = winreg.QueryValueEx(k, "SteamPath")
        if steam_path:
            p = os.path.join(os.path.expandvars(steam_path).replace("/", "\\"), "steamapps")
            if os.path.exists(p) and p not in search_dirs:
                search_dirs.append(p)
    except Exception:
        pass

    for sdir in search_dirs:
        if not os.path.exists(sdir):
            continue
        for acf in glob.glob(os.path.join(sdir, "appmanifest_*.acf")):
            try:
                with open(acf, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                appid_m = re.search(r'"appid"\s+"(\d+)"', content)
                name_m = re.search(r'"name"\s+"([^"]+)"', content)
                if appid_m and name_m:
                    appid = appid_m.group(1)
                    raw_name = name_m.group(1)
                    if "redistributable" in raw_name.lower():
                        continue
                    clean = re.sub(r"[^\w\s-]", "", raw_name).lower().strip()
                    clean = re.sub(r"\s+", " ", clean)
                    entry = {"appid": appid, "name": raw_name}
                    discovered[clean] = entry
                    discovered[raw_name.lower()] = entry

                    # Aliases for natural speech
                    if "counter-strike 2" in clean or "counter strike" in clean:
                        discovered["cs2"] = entry
                        discovered["cs"] = entry
                        discovered["counter strike 2"] = entry
                    elif "red dead redemption 2" in clean:
                        discovered["rdr2"] = entry
                        discovered["red dead"] = entry
                        discovered["red dead 2"] = entry
                    elif "forza horizon 5" in clean:
                        discovered["forza 5"] = entry
                        discovered["forza"] = entry
                    elif "spider-man" in clean or "spiderman" in clean:
                        discovered["spiderman"] = entry
                        discovered["spider man"] = entry
                    elif "the last of us" in clean:
                        discovered["tlou"] = entry
                        discovered["last of us"] = entry
            except Exception:
                continue

    _CACHED_STEAM_GAMES = discovered
    return discovered


def get_installed_shortcuts(force_refresh: bool = False) -> Dict[str, str]:
    """
    Dynamically discover all Windows Start Menu application shortcuts (.lnk).
    Returns mapping of lowercase application name -> full .lnk path.
    """
    global _CACHED_SHORTCUTS
    if _CACHED_SHORTCUTS is not None and not force_refresh:
        return _CACHED_SHORTCUTS

    start_dirs = [
        os.path.expandvars(r"%ProgramData%\Microsoft\Windows\Start Menu\Programs"),
        os.path.expandvars(r"%AppData%\Microsoft\Windows\Start Menu\Programs"),
        os.path.expandvars(r"%LOCALAPPDATA%\Programs"),
    ]

    discovered: Dict[str, str] = {}
    for base in start_dirs:
        if not os.path.exists(base):
            continue
        for lnk in glob.glob(os.path.join(base, "**", "*.lnk"), recursive=True):
            base_name = os.path.splitext(os.path.basename(lnk))[0].lower().strip()
            # Clean common suffixes
            clean_name = re.sub(r"\s*\((?:64-bit|32-bit|x86|new)\)", "", base_name).strip()
            discovered[clean_name] = lnk
            discovered[base_name] = lnk

    _CACHED_SHORTCUTS = discovered
    return discovered


def _find_app_path(name: str) -> Optional[str]:
    """
    Resolve executable or shortcut path using:
      1. Start Menu dynamic shortcuts
      2. Registry App Paths (HKLM & HKCU)
      3. Valve Steam Registry & locations
      4. Known directory paths
      5. System PATH
    """
    clean = re.sub(r"[^\w\s-]", "", name).lower().strip()
    candidates = [clean, f"{clean}.exe"]

    # 1. Dynamic Start Menu Shortcuts check (Fuzzy match)
    shortcuts = get_installed_shortcuts()
    if clean in shortcuts:
        return shortcuts[clean]
    for sc_name, sc_path in shortcuts.items():
        if clean == sc_name or clean in sc_name:
            return sc_path

    # 2. Windows App Paths in Registry
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

    # 3. Check Steam specific registry & paths
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

    # 4. Known common Windows installation directories
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
        os.path.expandvars(r"%LOCALAPPDATA%\Discord\Discord.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Discord\Discord.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Ollama\ollama app.exe"),
        rf"C:\Windows\System32\{clean}.exe",
        rf"C:\Windows\{clean}.exe",
    ]
    for loc in common_locations:
        if os.path.exists(loc) and clean in loc.lower():
            return loc

    # 5. System PATH check
    which_path = shutil.which(clean) or shutil.which(f"{clean}.exe")
    if which_path:
        return which_path

    return None


def open_app(app_name: str) -> Tuple[bool, str]:
    """Launch any application on the user's PC."""
    clean_name = re.sub(r"[^\w\s-]", "", app_name).lower().strip()
    if not clean_name:
        return False, "No application name specified, sir."

    # 0. Check installed Steam games first (e.g. CS2, RDR2, Forza, Spider-Man)
    steam_games = get_installed_steam_games()
    if clean_name in steam_games:
        game = steam_games[clean_name]
        try:
            os.startfile(f"steam://rungameid/{game['appid']}")
            return True, f"Launching {game['name']}, sir. Enjoy your game!"
        except Exception:
            pass

    target = APP_MAP.get(clean_name, clean_name)

    # 1. Special protocol fallback for Steam
    if clean_name == "steam":
        resolved_steam = _find_app_path("steam")
        if resolved_steam and os.path.exists(resolved_steam):
            try:
                os.startfile(resolved_steam)
                return True, "Opening Steam, sir."
            except Exception:
                pass
        try:
            os.startfile("steam://open/main")
            return True, "Opening Steam, sir."
        except Exception:
            pass

    # 2. URI protocols (e.g. ms-settings:, calc:, spotify:)
    if target.endswith(":") or (":" in target and "\\" not in target):
        try:
            os.startfile(target)
            return True, f"Opening {clean_name}, sir."
        except Exception:
            pass

    # 3. Try resolved executable or shortcut path
    resolved = _find_app_path(target)
    if resolved and os.path.exists(resolved):
        try:
            os.startfile(resolved)
            return True, f"Opening {clean_name}, sir."
        except Exception:
            pass

    # 4. Try os.startfile directly with target or target.exe if it exists on PATH or filesystem
    which_target = shutil.which(target) or shutil.which(f"{target}.exe")
    if which_target and os.path.exists(which_target):
        try:
            os.startfile(which_target)
            return True, f"Opening {clean_name}, sir."
        except Exception:
            pass

    return False, f"Could not find application '{clean_name}' on your system, sir."


def close_app(app_name: str) -> Tuple[bool, str]:
    """Close or terminate an active application by name."""
    clean = re.sub(r"[^\w\s-]", "", app_name).lower().strip()
    if not clean:
        return False, "No application specified to close, sir."

    target_procs = []
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            pname = (proc.info["name"] or "").lower()
            if clean in pname or clean in pname.replace(".exe", ""):
                target_procs.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    if not target_procs:
        return False, f"No running process found for '{clean}', sir."

    count = 0
    for proc in target_procs:
        try:
            proc.terminate()
            count += 1
        except Exception:
            try:
                proc.kill()
                count += 1
            except Exception:
                pass

    return True, f"Closed {count} process(es) for '{clean}', sir."


def list_running_apps(limit: int = 15) -> List[Dict[str, Any]]:
    """List major active running applications and their memory usage."""
    apps = []
    seen = set()
    for proc in psutil.process_iter(["pid", "name", "memory_info", "cpu_percent"]):
        try:
            name = proc.info["name"] or ""
            # Filter background system daemons
            if name.lower().endswith(".exe") and name.lower() not in {
                "svchost.exe", "system idle process", "registry", "smss.exe", "csrss.exe", "services.exe", "lsass.exe"
            }:
                mem_mb = round(proc.info["memory_info"].rss / (1024 * 1024), 1)
                if mem_mb > 15:  # meaningful memory usage
                    if name not in seen:
                        seen.add(name)
                        apps.append({
                            "name": name,
                            "pid": proc.info["pid"],
                            "memory_mb": mem_mb,
                        })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    apps.sort(key=lambda x: x["memory_mb"], reverse=True)
    return apps[:limit]


# ============================================================
# USER FOLDERS & RECENT FILES
# ============================================================

def open_user_folder(folder_name: str) -> Tuple[bool, str]:
    """Open standard Windows user folder (Downloads, Desktop, Documents, etc.)."""
    clean = folder_name.lower().strip()
    home = Path.home()

    folder_map = {
        "downloads": home / "Downloads",
        "download": home / "Downloads",
        "desktop": home / "Desktop",
        "documents": home / "Documents",
        "docs": home / "Documents",
        "pictures": home / "Pictures",
        "photos": home / "Pictures",
        "videos": home / "Videos",
        "music": home / "Music",
        "development": home / "MyFiles" / "Development",
        "myfiles": home / "MyFiles",
        "project": BASE_DIR,
    }

    target = folder_map.get(clean)
    if not target or not target.exists():
        # Fallback check under home directory
        cand = home / clean
        if cand.exists() and cand.is_dir():
            target = cand

    if target and target.exists():
        os.startfile(str(target))
        return True, f"Opened {clean} folder, sir."
    return False, f"Could not find folder '{folder_name}', sir."


def get_recent_files(folder_name: str = "downloads", limit: int = 5) -> List[Dict[str, Any]]:
    """Get most recently downloaded or modified files."""
    home = Path.home()
    folder_path = home / "Downloads" if "download" in folder_name.lower() else home / "Desktop"

    if not folder_path.exists():
        return []

    files = []
    for f in folder_path.iterdir():
        if f.is_file():
            try:
                stat = f.stat()
                files.append({
                    "name": f.name,
                    "path": str(f),
                    "size_mb": round(stat.st_size / (1024 * 1024), 2),
                    "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %I:%M %p"),
                    "mtime": stat.st_mtime,
                })
            except Exception:
                continue

    files.sort(key=lambda x: x["mtime"], reverse=True)
    return files[:limit]


def open_latest_file(folder_name: str = "downloads") -> Tuple[bool, str]:
    """Open the most recent file downloaded or created."""
    recent = get_recent_files(folder_name=folder_name, limit=1)
    if not recent:
        return False, f"No recent files found in {folder_name}, sir."

    latest = recent[0]
    try:
        os.startfile(latest["path"])
        return True, f"Opening recent file '{latest['name']}', sir."
    except Exception as e:
        return False, f"Could not open file: {e}"


# ============================================================
# SYSTEM POWER & WORKSPACE CONTROLS
# ============================================================

def lock_workstation() -> Tuple[bool, str]:
    """Lock the Windows workstation immediately."""
    try:
        ctypes.windll.user32.LockWorkStation()
        return True, "Workstation locked, sir."
    except Exception as e:
        return False, f"Could not lock screen: {e}"


def minimize_all_windows() -> Tuple[bool, str]:
    """Show desktop by minimizing all open windows."""
    try:
        # Simulate Win + D
        user32 = ctypes.windll.user32
        user32.keybd_event(VK_LWIN, 0, 0, 0)
        user32.keybd_event(VK_D, 0, 0, 0)
        time.sleep(0.05)
        user32.keybd_event(VK_D, 0, KEYEVENTF_KEYUP, 0)
        user32.keybd_event(VK_LWIN, 0, KEYEVENTF_KEYUP, 0)
        return True, "Desktop displayed, sir."
    except Exception as e:
        return False, f"Could not minimize windows: {e}"


# ============================================================
# NATIVE CLIPBOARD INTEGRATION
# ============================================================

def get_clipboard_text() -> str:
    """Read current text from the Windows clipboard."""
    if HAS_WIN32CLIP:
        try:
            win32clipboard.OpenClipboard()
            if win32clipboard.IsClipboardFormatAvailable(win32clipboard.CF_UNICODETEXT):
                data = win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
                win32clipboard.CloseClipboard()
                return data or ""
            win32clipboard.CloseClipboard()
        except Exception:
            pass

    # Fallback to powershell Get-Clipboard
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-Command", "Get-Clipboard"],
            capture_output=True,
            text=True,
            timeout=2.0,
        )
        return proc.stdout.strip()
    except Exception:
        return ""


def set_clipboard_text(text: str) -> bool:
    """Copy text to the Windows clipboard."""
    if HAS_WIN32CLIP:
        try:
            win32clipboard.OpenClipboard()
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardText(text, win32clipboard.CF_UNICODETEXT)
            win32clipboard.CloseClipboard()
            return True
        except Exception:
            pass

    # Fallback to powershell Set-Clipboard
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", f"Set-Clipboard -Value @'\n{text}\n'@"],
            timeout=2.0,
        )
        return True
    except Exception:
        return False


# ============================================================
# HARDWARE, GPU, NETWORK & DIAGNOSTICS
# ============================================================

def get_gpu_stats() -> Optional[Dict[str, Any]]:
    """Query NVIDIA GPU statistics via nvidia-smi."""
    try:
        proc = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,memory.used,memory.free,temperature.gpu,utilization.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=2.0,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            parts = [p.strip() for p in proc.stdout.strip().split(",")]
            if len(parts) >= 6:
                return {
                    "name": parts[0],
                    "memory_total_mb": int(parts[1]),
                    "memory_used_mb": int(parts[2]),
                    "memory_free_mb": int(parts[3]),
                    "temperature_c": int(parts[4]),
                    "utilization_pct": int(parts[5]),
                }
    except Exception:
        pass
    return None


def get_all_disks() -> List[Dict[str, Any]]:
    """Retrieve storage capacity and free space across all connected drives."""
    disks = []
    for part in psutil.disk_partitions(all=False):
        if "cdrom" in part.opts or part.fstype == "":
            continue
        try:
            usage = shutil.disk_usage(part.mountpoint)
            disks.append({
                "drive": part.device,
                "total_gb": round(usage.total / (1024**3), 1),
                "free_gb": round(usage.free / (1024**3), 1),
                "percent_used": round((usage.used / usage.total) * 100, 1),
            })
        except Exception:
            continue
    return disks


def get_network_stats() -> Dict[str, Any]:
    """Retrieve network input/output counters."""
    net = psutil.net_io_counters()
    return {
        "bytes_sent_mb": round(net.bytes_sent / (1024 * 1024), 1),
        "bytes_recv_mb": round(net.bytes_recv / (1024 * 1024), 1),
    }


def get_comprehensive_diagnostics() -> Dict[str, Any]:
    """Retrieve full hardware, GPU, power, network, and storage diagnostics."""
    now = datetime.now()
    cpu_pct = psutil.cpu_percent(interval=0.1)
    cpu_freq = psutil.cpu_freq()
    mem = psutil.virtual_memory()
    battery = psutil.sensors_battery()
    gpu = get_gpu_stats()
    disks = get_all_disks()
    net = get_network_stats()

    battery_info = None
    if battery:
        battery_info = {
            "percent": int(battery.percent),
            "plugged": battery.power_plugged,
        }

    return {
        "time": now.strftime("%I:%M %p"),
        "date": now.strftime("%A, %B %d, %Y"),
        "cpu": {
            "percent": cpu_pct,
            "cores": psutil.cpu_count(logical=True),
            "freq_ghz": round(cpu_freq.current / 1000.0, 2) if cpu_freq else None,
        },
        "memory": {
            "percent": mem.percent,
            "total_gb": round(mem.total / (1024**3), 1),
            "used_gb": round(mem.used / (1024**3), 1),
            "free_gb": round(mem.available / (1024**3), 1),
        },
        "gpu": gpu,
        "battery": battery_info,
        "disks": disks,
        "network": net,
    }


def format_full_diagnostics_speech(diag: Dict[str, Any]) -> str:
    """Format full system diagnostics into a concise spoken summary."""
    parts = []
    if diag.get("battery"):
        b = diag["battery"]
        state = "charging" if b["plugged"] else "on battery"
        parts.append(f"Battery is at {b['percent']} percent and {state}")

    parts.append(f"CPU is at {diag['cpu']['percent']} percent")
    parts.append(f"RAM at {diag['memory']['percent']} percent")

    if diag.get("gpu"):
        g = diag["gpu"]
        parts.append(f"{g['name']} temperature is {g['temperature_c']} degrees Celsius")

    return ", ".join(parts) + ", sir."


# Legacy compatibility functions
def get_system_stats() -> dict:
    now = datetime.now()
    cpu_pct = psutil.cpu_percent(interval=0.1)
    mem = psutil.virtual_memory()
    disk = shutil.disk_usage("C:\\")
    battery = psutil.sensors_battery()
    battery_info = None
    if battery:
        battery_info = {"percent": int(battery.percent), "plugged": battery.power_plugged}
    return {
        "time": now.strftime("%I:%M %p"),
        "date": now.strftime("%A, %B %d, %Y"),
        "cpu_percent": cpu_pct,
        "memory_percent": mem.percent,
        "disk_free_gb": round(disk.free / (1024**3), 1),
        "battery": battery_info,
    }


def format_stats_speech(stats: dict) -> str:
    parts = []
    if stats.get("battery"):
        bat = stats["battery"]
        state = "plugged in and charging" if bat["plugged"] else "on battery power"
        parts.append(f"Battery is at {bat['percent']} percent and {state}")
    parts.append(f"CPU load is at {stats['cpu_percent']} percent")
    parts.append(f"memory utilization is {stats['memory_percent']} percent")
    return ", ".join(parts) + ", sir."


def control_volume(action: str) -> tuple[bool, str]:
    action = action.lower().strip()
    if "up" in action or "increase" in action or "raise" in action:
        _press_key(VK_VOLUME_UP, times=5)
        return True, "Volume increased, sir."
    elif "down" in action or "decrease" in action or "lower" in action:
        _press_key(VK_VOLUME_DOWN, times=5)
        return True, "Volume decreased, sir."
    elif "mute" in action or "unmute" in action or "silence" in action:
        _press_key(VK_VOLUME_MUTE, times=1)
        return True, "Audio mute toggled, sir."
    return False, f"Unknown volume action: {action}"


def control_media(action: str) -> tuple[bool, str]:
    action = action.lower().strip()
    if "play" in action or "pause" in action or "resume" in action:
        _press_key(VK_MEDIA_PLAY_PAUSE, times=1)
        return True, "Media toggled, sir."
    elif "next" in action or "skip" in action:
        _press_key(VK_MEDIA_NEXT_TRACK, times=1)
        return True, "Next track, sir."
    elif "previous" in action or "prev" in action or "back" in action:
        _press_key(VK_MEDIA_PREV_TRACK, times=1)
        return True, "Previous track, sir."
    elif "stop" in action:
        _press_key(VK_MEDIA_STOP, times=1)
        return True, "Media playback stopped, sir."
    return False, f"Unknown media action: {action}"


def search_web(query: str) -> tuple[bool, str]:
    if not query.strip():
        return False, "Search query was empty, sir."
    url = f"https://www.google.com/search?q={urllib.parse.quote(query.strip())}"
    webbrowser.open(url)
    return True, f"Searching Google for '{query}', sir."


def search_youtube(query: str) -> tuple[bool, str]:
    if not query.strip():
        return False, "YouTube query was empty, sir."
    url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(query.strip())}"
    webbrowser.open(url)
    return True, f"Searching YouTube for '{query}', sir."


def open_url(url: str) -> tuple[bool, str]:
    target = url.strip()
    if not target.startswith("http://") and not target.startswith("https://"):
        target = f"https://{target}"
    webbrowser.open(target)
    return True, f"Navigating to {url}, sir."


def take_screenshot() -> tuple[bool, str]:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = SCREENSHOT_DIR / f"screenshot_{timestamp}.png"
    try:
        img = ImageGrab.grab()
        img.save(str(filename))
        return True, f"Screenshot captured and saved to {filename.name}, sir."
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
            return True, f"Screenshot captured and saved to {filename.name}, sir."
    except Exception as e:
        return False, f"Failed to capture screenshot: {e}"

    return False, "Could not capture display at this moment, sir."
