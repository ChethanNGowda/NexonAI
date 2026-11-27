"""
NEXONAI / PHOEBE — CENTRALIZED SAFE AUTOMATION GUARD
====================================================
Permission-based desktop automation safety layer providing:
  - Explicit action classification (safe vs. destructive vs. unknown)
  - Expiring, single-use, target-bound confirmation tokens
  - Strict command allowlist & shell-injection prevention
  - HTTP/HTTPS URL validation
  - Environment-variable & credential redaction
  - Thread-safe audit logging to logs/actions.log
  - Persistent emergency-stop kill switch & cancellable task tracking
"""

from __future__ import annotations

import json
import os
import re
import shlex
import secrets
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlparse

_ROOT = Path(__file__).resolve().parent.parent.parent
_DEFAULT_LOG_PATH = _ROOT / "logs" / "actions.log"
_DEFAULT_ESTOP_PATH = _ROOT / "logs" / ".emergency_stop"

# ------------------------------------------------------------------------------
# Action Classification Tables
# ------------------------------------------------------------------------------

SAFE_ACTIONS = frozenset({
    "time",
    "date",
    "battery",
    "diagnostics",
    "gpu",
    "storage",
    "running_apps",
    "recent_downloads",
    "clipboard",
    "clipboard_read",
    "clipboard_write",
    "volume_up",
    "volume_down",
    "volume_mute",
    "control_volume",
    "media_toggle",
    "media_next",
    "media_prev",
    "control_media",
    "open_app",
    "open_url",
    "open_folder",
    "open_latest",
    "show_desktop",
    "file_search",
    "google_search",
    "youtube_search",
    "spotify_search",
    "screenshot",
    "read_system_info",
})

DESTRUCTIVE_ACTIONS = frozenset({
    "close_app",
    "lock_pc",
    "lock_workstation",
    "execute_command",
    "run_command",
    "overwrite_file",
    "delete_file",
    "system_shutdown",
    "system_restart",
})

# Strict allowlist of non-destructive diagnostic/utility executables
APPROVED_COMMANDS = frozenset({
    "whoami",
    "hostname",
    "ipconfig",
    "ping",
    "systeminfo",
    "tasklist",
    "where",
    "python",
    "git",
})

_GIT_ALLOWED_SUBCOMMANDS = frozenset({"status", "log", "branch", "diff", "rev-parse"})

_SHELL_INJECTION_PATTERNS = (
    ";",
    "&&",
    "||",
    "|",
    "`",
    "$(",
    "${",
    ">",
    "<",
    "\n",
    "\r",
)

_BLOCKED_EXECUTABLES = frozenset({
    "cmd",
    "cmd.exe",
    "powershell",
    "powershell.exe",
    "pwsh",
    "pwsh.exe",
    "bash",
    "sh",
    "wscript",
    "cscript",
    "mshta",
    "reg",
    "regedit",
    "del",
    "erase",
    "rmdir",
    "rd",
    "format",
    "shutdown",
    "taskkill",
})

_SENSITIVE_ENV_KEY_RE = re.compile(
    r"(?:KEY|TOKEN|SECRET|PASSWORD|PASS|AUTH|CREDENTIAL|WEBHOOK)",
    re.IGNORECASE,
)

_SECRET_TEXT_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"AIza[0-9A-Za-z_\-]{12,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9._\-]{8,}", re.IGNORECASE),
    re.compile(r"https://discord(?:app)?\.com/api/webhooks/\S+", re.IGNORECASE),
    re.compile(
        r"(?:api_key|apikey|token|secret|password)\s*[:=]\s*['\"]?[^\s'\"]{4,}['\"]?",
        re.IGNORECASE,
    ),
)


@dataclass
class GuardDecision:
    allowed: bool
    status: str  # allowed | pending_confirm | confirmed | denied | blocked | failed | emergency_stop
    action: str
    target: str
    message: str
    confirmation_id: str = ""
    result: Any = None


@dataclass
class PendingConfirmation:
    confirmation_id: str
    action: str
    target: str
    description: str
    callback: Optional[Callable[[], Tuple[bool, str]]]
    created_at: float
    expires_at: float
    used: bool = False


@dataclass
class CancellableTask:
    task_id: str
    cancel_event: threading.Event = field(default_factory=threading.Event)
    cancel_fn: Optional[Callable[[], None]] = None


class AutomationGuard:
    """Centralized safety guard for all NexonAI desktop automation."""

    def __init__(
        self,
        log_path: Optional[Path] = None,
        estop_path: Optional[Path] = None,
        default_ttl_seconds: float = 60.0,
    ):
        self._log_path = log_path
        self._estop_path = estop_path
        self.default_ttl_seconds = default_ttl_seconds

        self._lock = threading.Lock()
        self._log_lock = threading.Lock()
        self._emergency_event = threading.Event()
        self._pending: Dict[str, PendingConfirmation] = {}
        self._latest_pending_id: Optional[str] = None
        self._active_tasks: Dict[str, CancellableTask] = {}

        # Sync in-memory emergency state with persisted sentinel if present
        if self._resolve_estop_path().exists():
            self._emergency_event.set()

    def _resolve_log_path(self) -> Path:
        if self._log_path is not None:
            return self._log_path
        env_log = os.getenv("NEXON_ACTIONS_LOG", "").strip()
        return Path(env_log) if env_log else _DEFAULT_LOG_PATH

    def _resolve_estop_path(self) -> Path:
        if self._estop_path is not None:
            return self._estop_path
        env_estop = os.getenv("NEXON_EMERGENCY_STOP_FILE", "").strip()
        return Path(env_estop) if env_estop else _DEFAULT_ESTOP_PATH

    # ------------------------------------------------------------------
    # Secret Redaction
    # ------------------------------------------------------------------

    def redact_secrets(self, text: str) -> str:
        """Redact environment secrets, API keys, tokens, and webhooks from text."""
        if not text:
            return ""
        out = str(text)

        # Redact live sensitive environment variable values (length >= 6)
        for k, v in os.environ.items():
            if v and len(v) >= 6 and _SENSITIVE_ENV_KEY_RE.search(k):
                if v in out:
                    out = out.replace(v, "[REDACTED]")

        for pattern in _SECRET_TEXT_PATTERNS:
            out = pattern.sub("[REDACTED]", out)

        return out

    # ------------------------------------------------------------------
    # Audit Logging (logs/actions.log)
    # ------------------------------------------------------------------

    def log_action(
        self,
        action: str,
        target: str,
        status: str,
        confirmation_id: str = "",
        detail: str = "",
    ) -> None:
        """Append a thread-safe structured audit entry to logs/actions.log."""
        log_file = self._resolve_log_path()
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": str(action),
            "target": self.redact_secrets(str(target))[:200],
            "status": str(status),
            "confirmation_id": str(confirmation_id),
            "detail": self.redact_secrets(str(detail))[:300],
        }
        line = json.dumps(entry, ensure_ascii=False) + "\n"
        with self._log_lock:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            with open(log_file, "a", encoding="utf-8") as fh:
                fh.write(line)

    # ------------------------------------------------------------------
    # Action Classification
    # ------------------------------------------------------------------

    def classify_action(self, action: str) -> str:
        """Classify an action as 'safe', 'destructive', or 'unknown'."""
        norm = (action or "").strip().lower()
        if norm in SAFE_ACTIONS:
            return "safe"
        if norm in DESTRUCTIVE_ACTIONS:
            return "destructive"
        return "unknown"

    # ------------------------------------------------------------------
    # URL & Command Validation
    # ------------------------------------------------------------------

    def validate_url(self, url: str) -> Tuple[bool, str, str]:
        """
        Validate that a URL uses http/https and has a valid host.
        Returns (ok, normalized_url, error_message).
        """
        raw = (url or "").strip()
        if not raw or any(ch in raw for ch in ("\n", "\r", "\x00")):
            return False, "", "Empty or malformed URL."

        lower = raw.lower()
        # Reject explicit unsafe schemes before any normalization
        if ":" in raw.split("/", 1)[0] and not (lower.startswith("http://") or lower.startswith("https://")):
            return False, "", f"Unsafe URL scheme rejected: {raw.split(':', 1)[0]}"

        candidate = raw if (lower.startswith("http://") or lower.startswith("https://")) else f"https://{raw}"
        try:
            parsed = urlparse(candidate)
        except Exception:
            return False, "", "Malformed URL."

        if parsed.scheme not in {"http", "https"}:
            return False, "", f"Unsupported URL scheme '{parsed.scheme}'."
        if not parsed.netloc or "@" in parsed.netloc or " " in parsed.netloc:
            return False, "", "Invalid URL host."

        return True, candidate, ""

    def validate_command(self, command: str | List[str]) -> Tuple[bool, List[str], str]:
        """
        Validate a command against the strict allowlist and reject shell injection.
        Returns (ok, argv_list, error_message).
        """
        if isinstance(command, list):
            parts = [str(p) for p in command if str(p).strip()]
            raw_joined = " ".join(parts)
        else:
            raw_joined = str(command or "").strip()
            if not raw_joined:
                return False, [], "Empty command."
            for marker in _SHELL_INJECTION_PATTERNS:
                if marker in raw_joined:
                    return False, [], f"Rejected shell metacharacter '{marker.strip() or 'newline'}'."
            try:
                parts = shlex.split(raw_joined, posix=False)
            except ValueError as e:
                return False, [], f"Malformed command syntax: {e}"

        if not parts:
            return False, [], "Empty command."

        for part in parts:
            for marker in _SHELL_INJECTION_PATTERNS:
                if marker in part:
                    return False, [], "Rejected shell injection payload in arguments."

        exe_name = Path(parts[0]).name.lower()
        if exe_name in _BLOCKED_EXECUTABLES:
            return False, [], f"Executable '{exe_name}' is blocked."

        base_exe = exe_name[:-4] if exe_name.endswith(".exe") else exe_name
        if base_exe not in APPROVED_COMMANDS:
            return False, [], f"Command '{base_exe}' is not in the approved command allowlist."

        if base_exe == "git":
            if len(parts) < 2 or parts[1].lower() not in _GIT_ALLOWED_SUBCOMMANDS:
                return False, [], "Only read-only git subcommands (status, log, branch, diff, rev-parse) are approved."
        if base_exe == "python":
            if parts[1:] != ["--version"]:
                return False, [], "Only 'python --version' is approved for direct command execution."

        return True, parts, ""

    # ------------------------------------------------------------------
    # Emergency Stop & Cancellable Task Tracking
    # ------------------------------------------------------------------

    def is_emergency_stopped(self) -> bool:
        """Return True if emergency stop is currently active."""
        if self._emergency_event.is_set():
            return True
        if self._resolve_estop_path().exists():
            self._emergency_event.set()
            return True
        return False

    def register_cancellable_task(
        self,
        task_id: str,
        cancel_fn: Optional[Callable[[], None]] = None,
    ) -> CancellableTask:
        """Register an active cancellable automation task."""
        task = CancellableTask(task_id=task_id, cancel_fn=cancel_fn)
        with self._lock:
            if self.is_emergency_stopped():
                task.cancel_event.set()
            self._active_tasks[task_id] = task
        return task

    def unregister_cancellable_task(self, task_id: str) -> None:
        """Unregister a finished cancellable task."""
        with self._lock:
            self._active_tasks.pop(task_id, None)

    def trigger_emergency_stop(self, reason: str = "Emergency stop triggered") -> Dict[str, Any]:
        """Activate emergency stop, invalidate pending confirmations, and cancel active tasks."""
        self._emergency_event.set()
        estop_file = self._resolve_estop_path()
        estop_file.parent.mkdir(parents=True, exist_ok=True)
        estop_file.write_text(
            json.dumps({"stopped_at": datetime.now(timezone.utc).isoformat(), "reason": self.redact_secrets(reason)}),
            encoding="utf-8",
        )

        cancelled_count = 0
        invalidated_count = 0
        with self._lock:
            for pending in self._pending.values():
                if not pending.used:
                    pending.used = True
                    invalidated_count += 1
            self._pending.clear()
            self._latest_pending_id = None

            for task in list(self._active_tasks.values()):
                task.cancel_event.set()
                if task.cancel_fn:
                    try:
                        task.cancel_fn()
                    except Exception:
                        pass
                cancelled_count += 1

        self.log_action(
            action="emergency_stop",
            target="automation",
            status="emergency_stop",
            detail=f"{reason} (invalidated={invalidated_count}, cancelled={cancelled_count})",
        )
        return {
            "ok": True,
            "emergency_stopped": True,
            "invalidated_confirmations": invalidated_count,
            "cancelled_tasks": cancelled_count,
            "message": "Emergency stop activated. All automation is halted until explicitly reset.",
        }

    def reset_emergency_stop(self, authorized: bool = False) -> Dict[str, Any]:
        """Explicitly reset emergency stop. Refuses if authorized is not True."""
        if not authorized:
            self.log_action(
                action="reset_emergency_stop",
                target="automation",
                status="blocked",
                detail="Reset attempted without explicit authorization",
            )
            return {
                "ok": False,
                "emergency_stopped": self.is_emergency_stopped(),
                "message": "Explicit authorization is required to reset emergency stop.",
            }

        self._emergency_event.clear()
        estop_file = self._resolve_estop_path()
        if estop_file.exists():
            try:
                estop_file.unlink()
            except OSError:
                pass

        self.log_action(
            action="reset_emergency_stop",
            target="automation",
            status="allowed",
            detail="Emergency stop explicitly reset",
        )
        return {
            "ok": True,
            "emergency_stopped": False,
            "message": "Emergency stop reset. Automation resumed.",
        }

    # ------------------------------------------------------------------
    # Authorization & Confirmation
    # ------------------------------------------------------------------

    def authorize_safe_action(self, action: str, target: str = "") -> GuardDecision:
        """Verify emergency stop is off and action is explicitly classified as safe."""
        if self.is_emergency_stopped():
            msg = "Automation is halted by emergency stop. Reset emergency stop first."
            self.log_action(action, target, "blocked", detail="Blocked by emergency stop")
            return GuardDecision(allowed=False, status="blocked", action=action, target=target, message=msg)

        kind = self.classify_action(action)
        if kind == "safe":
            self.log_action(action, target, "allowed")
            return GuardDecision(allowed=True, status="allowed", action=action, target=target, message="Allowed.")

        if kind == "destructive":
            msg = f"Action '{action}' is destructive and requires explicit confirmation."
            self.log_action(action, target, "blocked", detail="Destructive action called without confirmation")
            return GuardDecision(allowed=False, status="blocked", action=action, target=target, message=msg)

        msg = f"Unknown action '{action}' is blocked by safety policy."
        self.log_action(action, target, "blocked", detail="Unknown action blocked")
        return GuardDecision(allowed=False, status="blocked", action=action, target=target, message=msg)

    def request_confirmation(
        self,
        action: str,
        target: str,
        description: str,
        callback: Optional[Callable[[], Tuple[bool, str]]] = None,
        ttl_seconds: Optional[float] = None,
    ) -> GuardDecision:
        """Create a single-use, expiring, target-bound pending confirmation."""
        if self.is_emergency_stopped():
            msg = "Automation is halted by emergency stop. Reset emergency stop first."
            self.log_action(action, target, "blocked", detail="Blocked by emergency stop")
            return GuardDecision(allowed=False, status="blocked", action=action, target=target, message=msg)

        kind = self.classify_action(action)
        if kind == "unknown":
            msg = f"Unknown action '{action}' cannot be confirmed and is blocked."
            self.log_action(action, target, "blocked", detail="Unknown action rejected")
            return GuardDecision(allowed=False, status="blocked", action=action, target=target, message=msg)

        ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl_seconds
        now = time.monotonic()
        cid = secrets.token_hex(4)
        pending = PendingConfirmation(
            confirmation_id=cid,
            action=action,
            target=str(target),
            description=self.redact_secrets(description),
            callback=callback,
            created_at=now,
            expires_at=now + ttl,
        )
        with self._lock:
            self._pending[cid] = pending
            self._latest_pending_id = cid

        msg = (
            f"Confirmation required ({cid}): {pending.description}. "
            f"Say 'confirm' or confirm ID {cid} to proceed, or 'cancel' to deny."
        )
        self.log_action(action, target, "pending_confirm", confirmation_id=cid, detail=pending.description)
        return GuardDecision(
            allowed=False,
            status="pending_confirm",
            action=action,
            target=str(target),
            message=msg,
            confirmation_id=cid,
        )

    def get_latest_pending_id(self) -> Optional[str]:
        with self._lock:
            return self._latest_pending_id

    def confirm_action(
        self,
        confirmation_id: Optional[str] = None,
        expected_action: Optional[str] = None,
        expected_target: Optional[str] = None,
    ) -> GuardDecision:
        """Validate and execute a single-use pending confirmation."""
        if self.is_emergency_stopped():
            msg = "Automation is halted by emergency stop."
            self.log_action("confirm", str(confirmation_id or ""), "blocked", detail="Emergency stop active")
            return GuardDecision(allowed=False, status="blocked", action="confirm", target="", message=msg)

        with self._lock:
            cid = confirmation_id or self._latest_pending_id
            pending = self._pending.get(cid) if cid else None

            if not pending:
                self.log_action("confirm", str(cid or ""), "blocked", confirmation_id=str(cid or ""), detail="Unknown confirmation ID")
                return GuardDecision(
                    allowed=False,
                    status="blocked",
                    action="confirm",
                    target="",
                    message="No valid pending confirmation found.",
                    confirmation_id=str(cid or ""),
                )

            if pending.used:
                self.log_action(pending.action, pending.target, "blocked", confirmation_id=pending.confirmation_id, detail="Confirmation ID already used")
                return GuardDecision(
                    allowed=False,
                    status="blocked",
                    action=pending.action,
                    target=pending.target,
                    message="This confirmation has already been used.",
                    confirmation_id=pending.confirmation_id,
                )

            if time.monotonic() > pending.expires_at:
                pending.used = True
                self._pending.pop(pending.confirmation_id, None)
                if self._latest_pending_id == pending.confirmation_id:
                    self._latest_pending_id = None
                self.log_action(pending.action, pending.target, "blocked", confirmation_id=pending.confirmation_id, detail="Confirmation expired")
                return GuardDecision(
                    allowed=False,
                    status="blocked",
                    action=pending.action,
                    target=pending.target,
                    message="Confirmation expired. Please request the action again.",
                    confirmation_id=pending.confirmation_id,
                )

            if expected_action is not None and expected_action != pending.action:
                self.log_action(pending.action, pending.target, "blocked", confirmation_id=pending.confirmation_id, detail=f"Altered action rejected ({expected_action})")
                return GuardDecision(
                    allowed=False,
                    status="blocked",
                    action=pending.action,
                    target=pending.target,
                    message="Confirmation rejected: action mismatch.",
                    confirmation_id=pending.confirmation_id,
                )

            if expected_target is not None and str(expected_target) != pending.target:
                self.log_action(pending.action, pending.target, "blocked", confirmation_id=pending.confirmation_id, detail="Altered target rejected")
                return GuardDecision(
                    allowed=False,
                    status="blocked",
                    action=pending.action,
                    target=pending.target,
                    message="Confirmation rejected: target mismatch.",
                    confirmation_id=pending.confirmation_id,
                )

            # Consume single-use token before execution
            pending.used = True
            if self._latest_pending_id == pending.confirmation_id:
                self._latest_pending_id = None

        if pending.callback is None:
            self.log_action(pending.action, pending.target, "confirmed", confirmation_id=pending.confirmation_id)
            return GuardDecision(
                allowed=True,
                status="confirmed",
                action=pending.action,
                target=pending.target,
                message=f"Confirmed {pending.action} on {pending.target}.",
                confirmation_id=pending.confirmation_id,
            )

        try:
            ok, msg = pending.callback()
            safe_msg = self.redact_secrets(msg)
            status = "confirmed" if ok else "failed"
            self.log_action(pending.action, pending.target, status, confirmation_id=pending.confirmation_id, detail=safe_msg)
            return GuardDecision(
                allowed=ok,
                status=status,
                action=pending.action,
                target=pending.target,
                message=safe_msg,
                confirmation_id=pending.confirmation_id,
            )
        except Exception as e:
            safe_err = self.redact_secrets(f"{type(e).__name__}: {e}")
            self.log_action(pending.action, pending.target, "failed", confirmation_id=pending.confirmation_id, detail=safe_err)
            return GuardDecision(
                allowed=False,
                status="failed",
                action=pending.action,
                target=pending.target,
                message=f"Action failed: {safe_err}",
                confirmation_id=pending.confirmation_id,
            )

    def deny_action(self, confirmation_id: Optional[str] = None) -> GuardDecision:
        """Deny and invalidate a pending confirmation."""
        with self._lock:
            cid = confirmation_id or self._latest_pending_id
            pending = self._pending.get(cid) if cid else None
            if not pending or pending.used:
                return GuardDecision(
                    allowed=False,
                    status="blocked",
                    action="deny",
                    target="",
                    message="No pending confirmation to cancel.",
                    confirmation_id=str(cid or ""),
                )
            pending.used = True
            self._pending.pop(pending.confirmation_id, None)
            if self._latest_pending_id == pending.confirmation_id:
                self._latest_pending_id = None

        self.log_action(pending.action, pending.target, "denied", confirmation_id=pending.confirmation_id)
        return GuardDecision(
            allowed=False,
            status="denied",
            action=pending.action,
            target=pending.target,
            message=f"Cancelled {pending.action} for '{pending.target}'.",
            confirmation_id=pending.confirmation_id,
        )


_global_guard: Optional[AutomationGuard] = None


def get_automation_guard() -> AutomationGuard:
    global _global_guard
    if _global_guard is None:
        _global_guard = AutomationGuard()
    return _global_guard


def trigger_emergency_stop(reason: str = "User triggered emergency stop") -> Dict[str, Any]:
    return get_automation_guard().trigger_emergency_stop(reason=reason)


def reset_emergency_stop(authorized: bool = False) -> Dict[str, Any]:
    return get_automation_guard().reset_emergency_stop(authorized=authorized)


def is_emergency_stopped() -> bool:
    return get_automation_guard().is_emergency_stopped()
