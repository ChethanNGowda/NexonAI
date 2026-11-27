"""
Phase 4 Test Suite — Speech Recognition & Voice Pipeline
========================================================
Covers:
  1.  Voice package exports (backend.voice)
  2.  Voice selection API (set_voice_id, get_voice_id, AVAILABLE_EDGE_VOICES)
  3.  Electron UI & main.js voice selection wiring & persistence schema
  4.  Playback lock & concurrent playback prevention (mocked sounddevice)
  5.  Playback lock released cleanly even on playback failure
  6.  Audio interruption via stop_audio() during active playback
  7.  Microphone error classification (no_input_device, permission_denied, device_disconnected, stream_error)
  8.  Silence handling -> ListenResult(ok=True, status='silence')
  9.  Whisper transcription failure -> ListenResult(ok=False, error_code='transcription_failed')
  10. Edge TTS default behavior (no ElevenLabs credentials required)
  11. Optional ElevenLabs fallback to Edge TTS & zero credential leakage in logs
  12. One-shot assistant.py --ask --voice flag compatibility
  13. IPC daemon set_voice_id command handling (in jarvis.py)
"""

import io
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

VENV_PY = ROOT / ".venv" / "Scripts" / "python.exe"
PYTHON = str(VENV_PY) if VENV_PY.exists() else sys.executable
ASST = str(ROOT / "backend" / "ai" / "assistant.py")

PASS = "[PASS]"
FAIL = "[FAIL]"
results: list[tuple[str, str, str]] = []


def _reg(name: str):
    def deco(fn):
        try:
            detail = fn()
            results.append((name, PASS, detail or ""))
        except Exception as e:
            results.append((name, FAIL, f"{type(e).__name__}: {e}"))
        return fn
    return deco


@_reg("Voice package exports cleanly (backend.voice)")
def test_voice_exports():
    import backend.voice as bv
    for sym in ("speak", "stop_audio", "set_voice_id", "get_voice_id", "SpeechRecognizer", "check_microphone"):
        assert hasattr(bv, sym), f"Missing export: {sym}"
    return "All public voice symbols exported"


@_reg("Voice selection API (set_voice_id / get_voice_id / AVAILABLE_EDGE_VOICES)")
def test_voice_selection_api():
    from backend.voice.tts import AVAILABLE_EDGE_VOICES, get_voice_id, set_voice_id
    required = {"en-GB-RyanNeural", "en-GB-ThomasNeural", "en-US-AriaNeural", "en-US-GuyNeural", "en-US-AnaNeural"}
    assert required.issubset(set(AVAILABLE_EDGE_VOICES)), f"Missing voices: {required - set(AVAILABLE_EDGE_VOICES)}"
    orig = get_voice_id()
    try:
        set_voice_id("en-US-AriaNeural")
        assert get_voice_id() == "en-US-AriaNeural"
    finally:
        set_voice_id(orig)
    return f"Verified {len(AVAILABLE_EDGE_VOICES)} Edge voices"


@_reg("Electron UI & main.js voice selection wiring")
def test_electron_voice_ui():
    html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    main_js = (ROOT / "frontend" / "main.js").read_text(encoding="utf-8")
    renderer_js = (ROOT / "frontend" / "renderer.js").read_text(encoding="utf-8")
    for v in ("en-GB-RyanNeural", "en-GB-ThomasNeural", "en-US-AriaNeural", "en-US-GuyNeural", "en-US-AnaNeural", "elevenlabs"):
        assert v in html, f"Missing voice option '{v}' in index.html"
    assert "activeVoice" in main_js and "set_voice_id" in main_js and "--voice" in main_js
    assert "voiceSelect" in renderer_js and "mic_error" in renderer_js
    return "UI, main.js, and renderer.js voice wiring verified"


@_reg("Concurrent playback prevention (no overlapping audio)")
def test_no_overlapping_playback():
    from backend.voice import tts

    active_count = 0
    max_active = 0
    count_lock = threading.Lock()

    class FakeStream:
        active = True

    def fake_play(data, sr):
        nonlocal active_count, max_active
        with count_lock:
            active_count += 1
            if active_count > max_active:
                max_active = active_count
        time.sleep(0.25)
        with count_lock:
            active_count -= 1

    fake_sd = MagicMock()
    fake_sd.play.side_effect = fake_play
    fake_sd.stop.side_effect = lambda: None
    fake_sd.get_stream.return_value = FakeStream()

    fake_sf = MagicMock()
    fake_sf.read.return_value = (np.zeros(4000, dtype=np.float32), 16000)

    with patch.dict(sys.modules, {"sounddevice": fake_sd, "soundfile": fake_sf}):
        t1 = threading.Thread(target=tts._play_audio_bytes, args=(b"fake1", "mp3"))
        t2 = threading.Thread(target=tts._play_audio_bytes, args=(b"fake2", "mp3"))
        t1.start()
        time.sleep(0.05)
        t2.start()
        t1.join(timeout=5)
        t2.join(timeout=5)

    assert max_active == 1, f"Overlap detected: max_active={max_active}"
    assert not tts.is_speaking(), "is_speaking() remained True after playback"
    return "max_active=1 (serialized cleanly)"


@_reg("Playback lock & speaking state reset on playback failure")
def test_lock_released_on_failure():
    from backend.voice import tts

    fake_sd = MagicMock()
    fake_sd.play.side_effect = RuntimeError("Simulated audio device crash")
    fake_sf = MagicMock()
    fake_sf.read.return_value = (np.zeros(1000, dtype=np.float32), 16000)

    with patch.dict(sys.modules, {"sounddevice": fake_sd, "soundfile": fake_sf}):
        tts._play_audio_bytes(b"bad", "mp3")

    assert not tts.is_speaking(), "is_speaking() must reset to False on error"
    acquired = tts._playback_lock.acquire(timeout=0.5)
    assert acquired, "_playback_lock was leaked after error"
    tts._playback_lock.release()
    return "Lock & state cleanly reset on error"


@_reg("Audio interruption via stop_audio() during active playback")
def test_stop_audio_interrupt():
    from backend.voice import tts

    class FakeStream:
        active = True

    fake_sd = MagicMock()
    fake_sd.get_stream.return_value = FakeStream()
    fake_sf = MagicMock()
    fake_sf.read.return_value = (np.zeros(80000, dtype=np.float32), 16000)  # 5s buffer

    with patch.dict(sys.modules, {"sounddevice": fake_sd, "soundfile": fake_sf}):
        t = threading.Thread(target=tts._play_audio_bytes, args=(b"long", "mp3"))
        t.start()
        deadline = time.time() + 2.0
        while time.time() < deadline and not tts.is_speaking():
            time.sleep(0.02)
        assert tts.is_speaking(), "Playback did not enter speaking state"
        t0 = time.time()
        tts.stop_audio()
        t.join(timeout=2.0)
        elapsed = time.time() - t0

    assert not t.is_alive(), "Playback thread hung after stop_audio()"
    assert not tts.is_speaking(), "is_speaking() still True after stop_audio()"
    return f"Interrupted in {elapsed:.2f}s"


@_reg("Microphone error classification (no device / permission / disconnected / stream)")
def test_mic_error_classification():
    from backend.voice.stt import classify_mic_exception, check_microphone

    assert classify_mic_exception(RuntimeError("Error querying device -1: No default input device"))[0] == "no_input_device"
    assert classify_mic_exception(PermissionError("Access is denied by Windows privacy settings"))[0] == "permission_denied"
    assert classify_mic_exception(RuntimeError("Device disconnected or unplugged (-9999)"))[0] == "device_disconnected"
    assert classify_mic_exception(RuntimeError("Unexpected buffer error"))[0] == "stream_error"

    with patch("backend.voice.stt.sd.query_devices", return_value=[{"name": "Speakers", "max_input_channels": 0}]):
        res = check_microphone()
        assert res["ok"] is False and res["error_code"] == "no_input_device"
    return "All 4 mic error classes verified"


@_reg("Silence & Whisper transcription failure handling (mocked STT)")
def test_silence_and_stt_failure():
    from backend.voice.stt import SpeechRecognizer

    rec = SpeechRecognizer.__new__(SpeechRecognizer)
    rec.model_name = "mock"
    rec.last_error = None

    # 1. Silence: stream returns zeros until idle timeout
    fake_stream = MagicMock()
    fake_stream.__enter__.return_value = fake_stream
    fake_stream.read.return_value = (np.zeros((1600, 1), dtype=np.int16), False)

    with patch("backend.voice.stt.check_microphone", return_value={"ok": True, "input_count": 1}), \
         patch("backend.voice.stt.sd.InputStream", return_value=fake_stream):
        s_res = rec.listen_and_transcribe_result(idle_timeout=0.3)
        assert s_res.ok is True and s_res.status == "silence" and s_res.text == ""

    # 2. Transcription failure: stream captures loud audio, Whisper throws
    loud = np.full((1600, 1), 3000, dtype=np.int16)
    quiet = np.zeros((1600, 1), dtype=np.int16)
    reads = [(loud, False), (loud, False)] + [(quiet, False)] * 10
    fake_stream2 = MagicMock()
    fake_stream2.__enter__.return_value = fake_stream2
    fake_stream2.read.side_effect = reads

    rec.model = MagicMock()
    rec.model.transcribe.side_effect = RuntimeError("Whisper decode boom")

    with patch("backend.voice.stt.check_microphone", return_value={"ok": True, "input_count": 1}), \
         patch("backend.voice.stt.sd.InputStream", return_value=fake_stream2):
        f_res = rec.listen_and_transcribe_result(idle_timeout=1.0, silence_timeout=0.3)
        assert f_res.ok is False and f_res.status == "error" and f_res.error_code == "transcription_failed"

    return "Silence & transcription_failed handled cleanly"


@_reg("Edge TTS default & ElevenLabs fallback without secret leakage")
def test_elevenlabs_fallback_and_no_secret_leak():
    from backend.voice import tts

    stderr_buf = io.StringIO()
    fake_secret = "sk-super-secret-elevenlabs-token-999"

    # Case 1: Missing ElevenLabs key -> falls back cleanly to Edge TTS
    with patch.dict(os.environ, {"ELEVENLABS_API_KEY": "", "ELEVENLABS_VOICE_ID": "", "PHOEBE_VOICE_ID": ""}, clear=False), \
         patch("backend.voice.tts._run_edge_tts", return_value=b"EDGE_AUDIO") as mock_edge, \
         patch("sys.stderr", stderr_buf):
        out = tts.speak("Testing fallback.", voice="elevenlabs", play_audio=False, provider="elevenlabs")
        assert out.endswith("jarvis_response.mp3")
        assert mock_edge.called

    # Case 2: ElevenLabs key present, but client raises -> falls back cleanly AND never logs secret
    stderr_buf2 = io.StringIO()
    with patch.dict(os.environ, {"ELEVENLABS_API_KEY": fake_secret, "ELEVENLABS_VOICE_ID": "voice123"}, clear=False), \
         patch("elevenlabs.client.ElevenLabs", side_effect=RuntimeError(f"Auth failed with {fake_secret}")), \
         patch("backend.voice.tts._run_edge_tts", return_value=b"EDGE_AUDIO"), \
         patch("sys.stderr", stderr_buf2):
        out2 = tts.speak("Testing failure fallback.", voice="elevenlabs", play_audio=False, provider="elevenlabs")
        assert out2.endswith("jarvis_response.mp3")

    logs = stderr_buf2.getvalue()
    assert fake_secret not in logs, "API key leaked into stderr logs!"
    assert "falling back to Edge TTS" in logs
    return "ElevenLabs fallback & secret redaction verified"


@_reg("One-shot worker supports --voice override (assistant.py --ask --voice)")
def test_oneshot_voice_flag():
    r = subprocess.run(
        [PYTHON, ASST, "--ask", "what time is it", "--voice", "en-US-AriaNeural"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=25,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    assert r.returncode == 0, r.stderr[:200]
    obj = json.loads(r.stdout.strip().splitlines()[-1])
    assert obj.get("ok") is True
    return f"ok=True, action={obj.get('action')}"


@_reg("jarvis.py IPC supports set_voice_id & structured mic_error events")
def test_jarvis_ipc_voice_and_errors():
    src = (ROOT / "jarvis.py").read_text(encoding="utf-8")
    assert "set_voice_id" in src
    assert "listen_and_transcribe_result" in src
    assert '"mic_error"' in src
    return "jarvis.py IPC voice & error handling present"


def main():
    print()
    print("=" * 70)
    print("              NEXONAI PHASE 4 VOICE TEST SUITE")
    print("=" * 70)
    passed = failed = 0
    for name, status, detail in results:
        print(f"  {status} {name}")
        if detail:
            print(f"         -> {detail}")
        if status == PASS:
            passed += 1
        else:
            failed += 1
    print()
    print("=" * 70)
    print(f"  Results: {passed}/{passed + failed} passed  |  {failed} failed")
    print("=" * 70)
    print()
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
