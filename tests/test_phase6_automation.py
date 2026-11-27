"""
NexonAI Phase 6 Test Suite — Safe Automation Framework
======================================================
Covers all 20 required safety, confirmation, command/URL validation,
secret redaction, concurrent audit logging, emergency stop, and fast-intent tests.
All destructive OS operations are mocked.
"""

import json
import os
import sys
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.automation.guard import AutomationGuard
from backend.automation import system_control
from backend.core.assistant import handle_fast_intent
from backend.tools.desktop_tool import (
    tool_close_app,
    tool_lock,
    tool_run_approved_command,
)

TESTS = []


def _reg(name: str):
    def deco(fn):
        TESTS.append((name, fn))
        return fn
    return deco


def _make_guard(tmpdir: str, ttl: float = 60.0) -> tuple[AutomationGuard, Path]:
    log_path = Path(tmpdir) / "actions.log"
    estop_path = Path(tmpdir) / ".emergency_stop"
    return AutomationGuard(log_path=log_path, estop_path=estop_path, default_ttl_seconds=ttl), log_path


def _read_logs(log_path: Path) -> list[dict]:
    if not log_path.exists():
        return []
    return [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]


@_reg("1. Safe actions execute without unnecessary confirmation")
def test_safe_actions_no_confirm():
    with tempfile.TemporaryDirectory() as tmp:
        guard, log_path = _make_guard(tmp)
        for act in ("time", "date", "battery", "diagnostics", "control_volume", "open_app", "open_url"):
            d = guard.authorize_safe_action(act, "test_target")
            assert d.allowed is True and d.status == "allowed"
        entries = _read_logs(log_path)
        assert len(entries) == 7 and all(e["status"] == "allowed" for e in entries)
    return "7 safe action classes authorized immediately"


@_reg("2. Destructive actions remain pending until confirmation")
def test_destructive_pending_until_confirmed():
    with tempfile.TemporaryDirectory() as tmp:
        guard, _ = _make_guard(tmp)
        executed = []
        d = guard.request_confirmation(
            "close_app", "notepad", "Close notepad",
            callback=lambda: (executed.append("notepad") or True, "Closed notepad"),
        )
        assert d.allowed is False and d.status == "pending_confirm" and d.confirmation_id
        assert executed == []

        c = guard.confirm_action(d.confirmation_id, expected_action="close_app", expected_target="notepad")
        assert c.allowed is True and c.status == "confirmed"
        assert executed == ["notepad"]
    return "Executed only after explicit confirmation"


@_reg("3. Denied actions never execute")
def test_denied_actions_never_execute():
    with tempfile.TemporaryDirectory() as tmp:
        guard, log_path = _make_guard(tmp)
        executed = []
        d = guard.request_confirmation(
            "lock_pc", "workstation", "Lock PC",
            callback=lambda: (executed.append("locked") or True, "Locked"),
        )
        deny = guard.deny_action(d.confirmation_id)
        assert deny.allowed is False and deny.status == "denied"
        assert executed == []
        assert any(e["status"] == "denied" for e in _read_logs(log_path))
    return "Denied action blocked and logged"


@_reg("4. Expired confirmation IDs are rejected")
def test_expired_confirmation_rejected():
    with tempfile.TemporaryDirectory() as tmp:
        guard, _ = _make_guard(tmp, ttl=0.05)
        executed = []
        d = guard.request_confirmation(
            "close_app", "calc", "Close calc",
            callback=lambda: (executed.append("calc") or True, "Closed"),
        )
        time.sleep(0.1)
        c = guard.confirm_action(d.confirmation_id)
        assert c.allowed is False and c.status == "blocked" and "expired" in c.message.lower()
        assert executed == []
    return "Expired confirmation rejected cleanly"


@_reg("5. Reused confirmation IDs are rejected")
def test_reused_confirmation_rejected():
    with tempfile.TemporaryDirectory() as tmp:
        guard, _ = _make_guard(tmp)
        count = [0]
        def _cb():
            count[0] += 1
            return True, "Done"

        d = guard.request_confirmation("close_app", "notepad", "Close notepad", callback=_cb)
        c1 = guard.confirm_action(d.confirmation_id)
        c2 = guard.confirm_action(d.confirmation_id)
        assert c1.allowed is True and c2.allowed is False and c2.status == "blocked"
        assert count[0] == 1
    return "Single-use confirmation enforced"


@_reg("6. Altered action targets are rejected")
def test_altered_target_rejected():
    with tempfile.TemporaryDirectory() as tmp:
        guard, _ = _make_guard(tmp)
        executed = []
        d = guard.request_confirmation(
            "close_app", "notepad", "Close notepad",
            callback=lambda: (executed.append("ran") or True, "Closed"),
        )
        c = guard.confirm_action(d.confirmation_id, expected_action="close_app", expected_target="explorer")
        assert c.allowed is False and c.status == "blocked" and "target mismatch" in c.message.lower()
        assert executed == []
    return "Altered target rejected without execution"


@_reg("7. Unknown actions are blocked")
def test_unknown_actions_blocked():
    with tempfile.TemporaryDirectory() as tmp:
        guard, _ = _make_guard(tmp)
        d1 = guard.authorize_safe_action("format_c_drive", "C:")
        d2 = guard.request_confirmation("format_c_drive", "C:", "Format drive")
        assert d1.allowed is False and d1.status == "blocked"
        assert d2.allowed is False and d2.status == "blocked"
    return "Unknown action never classified as safe"


@_reg("8. Arbitrary shell commands are blocked")
def test_arbitrary_shell_commands_blocked():
    with tempfile.TemporaryDirectory() as tmp:
        guard, _ = _make_guard(tmp)
        for bad in (
            "powershell -enc SQBFAFgA",
            "cmd /c dir",
            "taskkill /F /IM explorer.exe",
            "rm -rf /",
            "shutdown /s /t 0",
            "git push --force",
        ):
            ok, _, err = guard.validate_command(bad)
            assert ok is False, f"Should have blocked: {bad}"
    return "All 6 arbitrary/dangerous shell commands blocked"


@_reg("9. Shell injection payloads are rejected")
def test_shell_injection_rejected():
    with tempfile.TemporaryDirectory() as tmp:
        guard, _ = _make_guard(tmp)
        for payload in (
            "whoami; calc.exe",
            "whoami && echo pwned",
            "whoami | findstr a",
            "ping $(whoami)",
            "hostname > out.txt",
            "whoami\ncalc",
        ):
            ok, _, _ = guard.validate_command(payload)
            assert ok is False, f"Injection payload not rejected: {payload}"
    return "All 6 shell injection payloads rejected"


@_reg("10. Approved commands require confirmation")
def test_approved_commands_require_confirmation():
    with tempfile.TemporaryDirectory() as tmp:
        guard, _ = _make_guard(tmp)
        with patch("backend.automation.guard.get_automation_guard", return_value=guard), \
             patch("subprocess.Popen") as mock_popen:
            mock_proc = MagicMock()
            mock_proc.poll.return_value = 0
            mock_proc.returncode = 0
            mock_proc.communicate.return_value = ("desktop\\user\n", "")
            mock_popen.return_value = mock_proc

            d = system_control.execute_approved_command_guarded("whoami")
            assert d.allowed is False and d.status == "pending_confirm"
            assert not mock_popen.called

            c = guard.confirm_action(d.confirmation_id)
            assert c.allowed is True and c.status == "confirmed"
            assert mock_popen.called
            assert mock_popen.call_args.kwargs.get("shell") is False
    return "Approved command queued, confirmed, and executed with shell=False"


@_reg("11. Unsafe URL schemes are rejected")
def test_unsafe_urls_rejected():
    with tempfile.TemporaryDirectory() as tmp:
        guard, _ = _make_guard(tmp)
        for bad_url in (
            "javascript:alert(1)",
            "file:///C:/Windows/System32/calc.exe",
            "data:text/html,<script>alert(1)</script>",
            "vbscript:msgbox(1)",
            "ftp://example.com/file",
            "",
        ):
            ok, _, _ = guard.validate_url(bad_url)
            assert ok is False, f"Unsafe URL should be rejected: {bad_url}"
    return "All 6 unsafe/malformed URLs rejected"


@_reg("12. Valid HTTP/HTTPS URLs are accepted")
def test_valid_urls_accepted():
    with tempfile.TemporaryDirectory() as tmp:
        guard, _ = _make_guard(tmp)
        for good_url in ("https://example.com", "http://localhost:8080/status", "python.org"):
            ok, norm, err = guard.validate_url(good_url)
            assert ok is True, f"Valid URL rejected ({err}): {good_url}"
            assert norm.startswith(("http://", "https://"))
    return "HTTP/HTTPS URLs validated cleanly"


@_reg("13. Secrets are redacted from logs and responses")
def test_secret_redaction():
    with tempfile.TemporaryDirectory() as tmp:
        guard, log_path = _make_guard(tmp)
        fake_secret = "sk-test-super-secret-value-987654"
        with patch.dict(os.environ, {"OPENAI_API_KEY": fake_secret}, clear=False):
            redacted = guard.redact_secrets(f"Failed with key={fake_secret} and Bearer abcdef123456")
            assert fake_secret not in redacted
            assert "abcdef123456" not in redacted
            assert "[REDACTED]" in redacted

            guard.log_action("execute_command", f"target {fake_secret}", "failed", detail=f"error {fake_secret}")
            raw_log = log_path.read_text(encoding="utf-8")
            assert fake_secret not in raw_log
    return "Env secrets & token patterns redacted from logs and responses"


@_reg("14. Action logging records all relevant outcomes")
def test_action_logging_outcomes():
    with tempfile.TemporaryDirectory() as tmp:
        guard, log_path = _make_guard(tmp)
        guard.authorize_safe_action("time", "clock")  # allowed
        d1 = guard.request_confirmation("close_app", "app1", "Close app1", callback=lambda: (True, "ok"))  # pending_confirm
        guard.confirm_action(d1.confirmation_id)  # confirmed
        d2 = guard.request_confirmation("close_app", "app2", "Close app2", callback=lambda: (False, "fail"))  # pending_confirm
        guard.confirm_action(d2.confirmation_id)  # failed
        d3 = guard.request_confirmation("lock_pc", "pc", "Lock")
        guard.deny_action(d3.confirmation_id)  # denied
        guard.authorize_safe_action("unknown_bad_op", "x")  # blocked

        statuses = {e["status"] for e in _read_logs(log_path)}
        for expected in ("allowed", "pending_confirm", "confirmed", "failed", "denied", "blocked"):
            assert expected in statuses, f"Missing status '{expected}' in {statuses}"
    return f"All 6 statuses recorded: {sorted(statuses)}"


@_reg("15. Concurrent logging does not corrupt entries")
def test_concurrent_logging():
    with tempfile.TemporaryDirectory() as tmp:
        guard, log_path = _make_guard(tmp)
        errors = []

        def worker(idx: int):
            try:
                for j in range(15):
                    guard.log_action("time", f"worker-{idx}-{j}", "allowed", detail="concurrent")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        entries = _read_logs(log_path)
        assert len(entries) == 90
    return "90 concurrent JSON log entries parsed cleanly without corruption"


@_reg("16. Emergency stop blocks new actions")
def test_emergency_stop_blocks_new_actions():
    with tempfile.TemporaryDirectory() as tmp:
        guard, _ = _make_guard(tmp)
        res = guard.trigger_emergency_stop("Unit test estop")
        assert res["emergency_stopped"] is True
        assert guard.is_emergency_stopped() is True

        d_safe = guard.authorize_safe_action("time", "clock")
        d_dest = guard.request_confirmation("close_app", "notepad", "Close")
        assert d_safe.allowed is False and d_safe.status == "blocked"
        assert d_dest.allowed is False and d_dest.status == "blocked"

        # Persists across new guard instance (simulating restart)
        guard2 = AutomationGuard(log_path=Path(tmp) / "actions.log", estop_path=Path(tmp) / ".emergency_stop")
        assert guard2.is_emergency_stopped() is True
    return "Emergency stop blocks actions and persists across restart"


@_reg("17. Emergency stop invalidates pending confirmations")
def test_emergency_stop_invalidates_pending():
    with tempfile.TemporaryDirectory() as tmp:
        guard, _ = _make_guard(tmp)
        executed = []
        d = guard.request_confirmation(
            "close_app", "notepad", "Close",
            callback=lambda: (executed.append("ran") or True, "ok"),
        )
        res = guard.trigger_emergency_stop("Halt")
        assert res["invalidated_confirmations"] == 1
        assert guard.reset_emergency_stop(authorized=True)["ok"] is True

        c = guard.confirm_action(d.confirmation_id)
        assert c.allowed is False and c.status == "blocked"
        assert executed == []
    return "Pending confirmation invalidated by emergency stop"


@_reg("18. Reset requires explicit authorization")
def test_reset_requires_authorization():
    with tempfile.TemporaryDirectory() as tmp:
        guard, _ = _make_guard(tmp)
        guard.trigger_emergency_stop("Test")
        r_unauth = guard.reset_emergency_stop(authorized=False)
        assert r_unauth["ok"] is False and guard.is_emergency_stopped() is True

        r_auth = guard.reset_emergency_stop(authorized=True)
        assert r_auth["ok"] is True and guard.is_emergency_stopped() is False
    return "Unauthorized reset refused; authorized reset succeeded"


@_reg("19. Active cancellable automation responds to emergency stop")
def test_active_cancellable_automation_estop():
    with tempfile.TemporaryDirectory() as tmp:
        guard, _ = _make_guard(tmp)
        cancel_called = threading.Event()
        task = guard.register_cancellable_task("task_1", cancel_fn=cancel_called.set)
        assert not task.cancel_event.is_set()

        res = guard.trigger_emergency_stop("Stop active task")
        assert res["cancelled_tasks"] == 1
        assert task.cancel_event.is_set()
        assert cancel_called.is_set()
        guard.unregister_cancellable_task("task_1")
    return "Active task cancel_event and cancel_fn triggered"


@_reg("20. Existing safe fast intents & guarded tools work without executing destructive ops")
def test_safe_fast_intents_and_guarded_tools():
    with tempfile.TemporaryDirectory() as tmp:
        guard, _ = _make_guard(tmp)
        with patch("backend.automation.guard.get_automation_guard", return_value=guard):
            act_time, msg_time = handle_fast_intent("what time is it")
            assert act_time == "time" and "currently" in msg_time.lower()

            act_date, msg_date = handle_fast_intent("what is today's date")
            assert act_date == "date" and "today" in msg_date.lower()

            # Destructive intent via handle_fast_intent must request confirmation (not lock!)
            with patch("ctypes.windll", create=True) as mock_windll:
                act_lock, msg_lock = handle_fast_intent("lock pc")
                assert act_lock == "confirm_required" and "confirmation required" in msg_lock.lower()
                assert not mock_windll.user32.LockWorkStation.called

            # Destructive tool calls must return requires_confirmation=True
            r_close = tool_close_app("notepad")
            assert r_close["requires_confirmation"] is True and r_close["success"] is False

            r_lock = tool_lock()
            assert r_lock["requires_confirmation"] is True and r_lock["success"] is False

            r_cmd = tool_run_approved_command("whoami")
            assert r_cmd["requires_confirmation"] is True and r_cmd["success"] is False
    return "Safe fast intents work; destructive intents/tools require confirmation"


def main():
    print("\n" + "=" * 72)
    print("       NEXONAI PHASE 6 SAFE AUTOMATION TEST SUITE")
    print("=" * 72)
    passed = 0
    failed = 0
    for name, fn in TESTS:
        try:
            detail = fn()
            passed += 1
            print(f"  [PASS] {name}")
            if detail:
                print(f"         -> {detail}")
        except Exception as e:
            failed += 1
            print(f"  [FAIL] {name}")
            print(f"         -> {type(e).__name__}: {e}")
    print("\n" + "=" * 72)
    print(f"  Results: {passed}/{len(TESTS)} passed  |  {failed} failed")
    print("=" * 72 + "\n")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
