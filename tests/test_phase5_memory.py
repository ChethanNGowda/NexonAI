"""
NexonAI Phase 5 Test Suite — Ollama Integration & Conversational Memory
=======================================================================
Covers:
  [MOCKED / OFFLINE]
  1.  Chat vs embedding model filtering (backend + frontend wiring)
  2.  Missing-model & embedding-model fallback with warning
  3.  Corrupted & empty memory DB graceful recovery (preserves file)
  4.  Duplicate message prevention & empty message filtering
  5.  clear_history() vs clear_all() preservation/wiping
  6.  Semantic retrieval ranking, deduplication & context separation
  7.  Keyword fallback & embedding timeout/failure recovery
  8.  Thinking-output cleanup (closed, stray, unclosed, streaming, malformed)

  [LIVE LOCAL OLLAMA]
  9.  Live assistant.py --models excludes nomic-embed-text from chat list
  10. Live qwen3.5:4b & qwen3-vl:4b chat + clean thinking output
  11. Live cross-process conversational memory persistence (temp DB)
  12. Live nomic-embed-text:latest semantic embedding & retrieval
"""

import io
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.ai.ollama_client import OllamaClient, is_embedding_model
from backend.ai.assistant import CentralAssistant
from backend.memory.memory_manager import MemoryManager
from backend.memory.retrieval import RetrievalEngine

TESTS = []


def _reg(name: str, category: str):
    def deco(fn):
        TESTS.append((name, category, fn))
        return fn
    return deco


# ==============================================================================
# MOCKED / OFFLINE TESTS
# ==============================================================================

@_reg("Chat vs embedding model filtering (backend + frontend)", "MOCKED")
def test_chat_vs_embedding_filtering():
    assert is_embedding_model("nomic-embed-text:latest") is True
    assert is_embedding_model("all-minilm:latest") is True
    assert is_embedding_model("qwen3.5:4b") is False
    assert is_embedding_model("qwen3-vl:4b") is False

    client = OllamaClient()
    fake_models = [
        {"name": "qwen3.5:4b"},
        {"name": "qwen3-vl:4b"},
        {"name": "nomic-embed-text:latest"},
    ]
    with patch.object(client, "list_installed_models", return_value=fake_models):
        chat_models = client.get_chat_model_names()
        embed_models = client.get_embedding_model_names()
        assert chat_models == ["qwen3.5:4b", "qwen3-vl:4b"]
        assert embed_models == ["nomic-embed-text:latest"]
        assert "nomic-embed-text:latest" not in chat_models

    renderer_src = (ROOT_DIR / "frontend" / "renderer.js").read_text(encoding="utf-8")
    assert '!lower.includes("embed")' in renderer_src
    return f"chat={chat_models}, embed={embed_models}"


@_reg("Missing-model & embedding-model fallback with warning", "MOCKED")
def test_missing_model_fallback():
    client = OllamaClient()
    installed = ["qwen3.5:4b", "qwen3-vl:4b", "nomic-embed-text:latest"]
    with patch.object(client, "get_installed_model_names", return_value=installed):
        # Valid manual selection preserved
        assert client.resolve_chat_model("qwen3.5:4b") == "qwen3.5:4b"
        assert client.last_model_warning is None

        # Missing model falls back with warning
        resolved = client.resolve_chat_model("does-not-exist:99b")
        assert resolved in ("qwen3-vl:4b", "qwen3.5:4b")
        assert client.last_model_warning and "not installed" in client.last_model_warning

        # Embedding model requested for chat falls back with warning
        resolved_emb = client.resolve_chat_model("nomic-embed-text:latest")
        assert resolved_emb in ("qwen3-vl:4b", "qwen3.5:4b")
        assert client.last_model_warning and "embedding model" in client.last_model_warning
    return "Manual selection preserved; missing/embed fallbacks emit warnings"


@_reg("Corrupted & empty memory DB graceful recovery (preserves file)", "MOCKED")
def test_corrupted_memory_db_graceful():
    with tempfile.TemporaryDirectory() as tmpdir:
        corrupt_path = Path(tmpdir) / "corrupt_memory.db"
        corrupt_bytes = b"NOT A VALID SQLITE DATABASE FILE 12345"
        corrupt_path.write_bytes(corrupt_bytes)

        mm = MemoryManager(db_path=corrupt_path)
        assert mm.is_corrupted_fallback is True
        # Original file must NOT be deleted or overwritten
        assert corrupt_path.exists() and corrupt_path.read_bytes() == corrupt_bytes

        # In-memory fallback still operates cleanly
        mm.save_message("user", "Hello after corruption")
        hist = mm.get_recent_history(limit=5)
        assert len(hist) == 1 and hist[0]["content"] == "Hello after corruption"

        # Empty DB initializes cleanly
        empty_path = Path(tmpdir) / "empty_memory.db"
        mm2 = MemoryManager(db_path=empty_path)
        assert mm2.is_corrupted_fallback is False
        assert mm2.get_recent_history(limit=5) == []
    return "Corrupted file preserved; in-memory fallback operational"


@_reg("Duplicate message prevention & empty message filtering", "MOCKED")
def test_duplicate_message_prevention():
    with tempfile.TemporaryDirectory() as tmpdir:
        mm = MemoryManager(db_path=Path(tmpdir) / "mem.db")
        mm.save_message("user", "   ")  # ignored
        mm.save_message("user", "What is the weather?")
        mm.save_message("user", "What is the weather?")  # consecutive duplicate ignored
        mm.save_message("assistant", "It is sunny.")
        mm.save_message("assistant", "It is sunny.")  # consecutive duplicate ignored

        hist = mm.get_recent_history(limit=10)
        assert len(hist) == 2
        assert hist[0]["content"] == "What is the weather?"
        assert hist[1]["content"] == "It is sunny."
    return "Duplicates & empty messages filtered cleanly"


@_reg("clear_history() preserves research/prefs; clear_all() wipes all", "MOCKED")
def test_memory_clearing():
    with tempfile.TemporaryDirectory() as tmpdir:
        mm = MemoryManager(db_path=Path(tmpdir) / "mem.db")
        mm.save_message("user", "Remember this")
        mm.save_research_report("Quantum computing", "Summary", "# Report", [{"title": "Src"}])
        mm.set_preference("theme", "dark")

        mm.clear_history()
        assert mm.get_recent_history() == []
        assert len(mm.get_recent_research()) == 1
        assert mm.get_preference("theme") == "dark"

        mm.clear_all()
        assert mm.get_recent_history() == []
        assert mm.get_recent_research() == []
        assert mm.get_preference("theme") is None
    return "clear_history and clear_all verified"


@_reg("Semantic retrieval ranking, deduplication & context separation", "MOCKED")
def test_semantic_retrieval_and_separation():
    engine = RetrievalEngine()

    def fake_embed(text: str):
        t = text.lower()
        if "python" in t or "flask" in t:
            return [1.0, 0.0, 0.0]
        if "coffee" in t:
            return [0.0, 1.0, 0.0]
        return [0.0, 0.0, 1.0]

    with patch.object(engine, "embed_text", side_effect=fake_embed):
        results = engine.find_relevant_context(
            "Tell me about python frameworks",
            [
                "I like morning coffee",
                "Flask is a Python web framework",
                "Flask is a Python web framework",  # duplicate
                "Unrelated astronomy fact",
            ],
            top_k=3,
            min_similarity=0.5,
        )
        assert len(results) == 1
        assert "Flask" in results[0]["text"]
        assert results[0]["score"] > 0.9

    # Verify CentralAssistant separates retrieved context from primary system prompt
    with tempfile.TemporaryDirectory() as tmpdir:
        mm = MemoryManager(db_path=Path(tmpdir) / "mem.db")
        for i in range(8):
            mm.save_message("user", f"Older message {i} about python flask" if i == 0 else f"Filler {i}")

        assistant = CentralAssistant()
        assistant.memory = mm
        assistant.retrieval = engine

        captured_messages = []

        def fake_chat(messages, **kwargs):
            captured_messages.extend(messages)
            return "Here is your answer."

        with patch.object(engine, "embed_text", side_effect=fake_embed), \
             patch.object(assistant.ollama, "chat", side_effect=fake_chat):
            res = assistant.process("How do I use flask?", play_speech=False, force_mode="chat")
            assert res["ok"] is True

        system_msgs = [m for m in captured_messages if m["role"] == "system"]
        assert len(system_msgs) == 2
        assert "[RETRIEVED MEMORY CONTEXT" in system_msgs[1]["content"]
        assert "Older message 0 about python flask" in system_msgs[1]["content"]
    return "Deduplicated semantic match injected in separate context block"


@_reg("Keyword fallback & embedding timeout/failure recovery", "MOCKED")
def test_keyword_fallback_on_embedding_failure():
    engine = RetrievalEngine()
    with patch.object(engine.ollama, "get_embedding", side_effect=TimeoutError("Ollama timed out")):
        results = engine.find_relevant_context(
            "database migration",
            [
                "We completed the SQLite database migration yesterday",
                "The weather is nice today",
            ],
            top_k=2,
        )
        assert len(results) == 1
        assert "database migration" in results[0]["text"]
    return "Recovered from TimeoutError via keyword-overlap fallback"


@_reg("Thinking-output cleanup (closed, stray, unclosed, streaming, malformed)", "MOCKED")
def test_thinking_output_cleanup():
    client = OllamaClient()
    assert client._clean_thinking("<think>internal reasoning</think>Hello world!") == "Hello world!"
    assert client._clean_thinking("some prefill</think>Final answer.") == "Final answer."
    assert client._clean_thinking("Prefix <think>unclosed reasoning") == "Prefix"
    assert client._clean_thinking("<think>only thinking</think>") == ""

    # Test streaming suppresses <think> tokens & handles malformed JSON lines
    stream_lines = [
        b'{"message":{"content":"<think>secret"}}\n',
        b'NOT_JSON\n',
        b'{"message":{"content":" thought</think>Visible "}}\n',
        b'{"message":{"content":"reply"}}\n',
    ]
    fake_resp = io.BytesIO(b"".join(stream_lines))
    fake_resp.__enter__ = lambda s=fake_resp: s
    fake_resp.__exit__ = lambda *a: None

    streamed_pieces = []
    with patch.object(client, "resolve_chat_model", return_value="qwen3.5:4b"), \
         patch("urllib.request.urlopen", return_value=fake_resp):
        out = client.chat(
            [{"role": "user", "content": "Hi"}],
            stream_callback=streamed_pieces.append,
        )
    assert out == "Visible reply"
    assert "<think>" not in "".join(streamed_pieces)
    assert "secret" not in "".join(streamed_pieces)
    return "All thinking tag variants & streaming suppression verified"


# ==============================================================================
# LIVE LOCAL OLLAMA TESTS
# ==============================================================================

@_reg("Live assistant.py --models excludes nomic-embed-text from chat list", "LIVE")
def test_live_models_endpoint():
    r = subprocess.run(
        [sys.executable, str(ROOT_DIR / "backend" / "ai" / "assistant.py"), "--models"],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout.strip())
    assert data.get("ok") is True
    chat_models = data.get("installed_models", [])
    embed_models = data.get("embedding_models", [])
    assert all("embed" not in m.lower() for m in chat_models), f"Embed model leaked: {chat_models}"
    assert any("nomic-embed-text" in m for m in embed_models), f"Expected nomic-embed-text in {embed_models}"
    return f"chat={chat_models}, embed={embed_models}"


@_reg("Live qwen3.5:4b & qwen3-vl:4b chat + clean thinking output", "LIVE")
def test_live_qwen_models():
    client = OllamaClient()
    assert client.is_available(), "Ollama is not reachable at 127.0.0.1:11434"
    installed = client.get_chat_model_names()
    tested = []
    for model_name in ("qwen3.5:4b", "qwen3-vl:4b"):
        if model_name not in installed:
            continue
        reply = client.chat(
            [
                {"role": "system", "content": "Reply in one short sentence."},
                {"role": "user", "content": "Say hello and confirm you are ready."},
            ],
            model=model_name,
            max_tokens=80,
        )
        assert reply and not reply.startswith("Ollama error:"), f"{model_name} failed: {reply}"
        assert "<think>" not in reply and "</think>" not in reply, f"Thinking tag leaked in {model_name}: {reply}"
        tested.append(model_name)
    assert len(tested) >= 1, "Neither qwen3.5:4b nor qwen3-vl:4b was available"
    return f"Tested live: {tested}"


@_reg("Live cross-process conversational memory persistence (temp DB)", "LIVE")
def test_live_cross_process_memory():
    with tempfile.TemporaryDirectory() as tmpdir:
        temp_db = Path(tmpdir) / "phase5_test_memory.db"
        env = os.environ.copy()
        env["NEXON_MEMORY_DB"] = str(temp_db)

        assistant_py = str(ROOT_DIR / "backend" / "ai" / "assistant.py")

        # Process 1: Tell Phoebe a unique code
        r1 = subprocess.run(
            [
                sys.executable,
                assistant_py,
                "--ask",
                "Remember this secret project code for our conversation: AURORA-742.",
                "--model",
                "qwen3.5:4b",
            ],
            capture_output=True,
            text=True,
            env=env,
            timeout=60,
        )
        assert r1.returncode == 0, r1.stderr
        d1 = json.loads(r1.stdout.strip().splitlines()[-1])
        assert d1.get("ok") is True

        # Process 2 (brand new Python process): Ask for the code
        r2 = subprocess.run(
            [
                sys.executable,
                assistant_py,
                "--ask",
                "What was the secret project code I just told you?",
                "--model",
                "qwen3.5:4b",
            ],
            capture_output=True,
            text=True,
            env=env,
            timeout=60,
        )
        assert r2.returncode == 0, r2.stderr
        d2 = json.loads(r2.stdout.strip().splitlines()[-1])
        ans2 = d2.get("spoken_answer", "")
        assert "AURORA-742" in ans2 or "742" in ans2, f"Expected recall of AURORA-742, got: {ans2}"
    return f"Cross-process recall succeeded: {ans2[:80]}"


@_reg("Live nomic-embed-text:latest semantic embedding & retrieval", "LIVE")
def test_live_nomic_embeddings():
    engine = RetrievalEngine()
    vec = engine.embed_text("Python local AI assistant")
    assert isinstance(vec, list) and len(vec) > 100, "Expected embedding vector from nomic-embed-text"

    results = engine.find_relevant_context(
        "How do I bake sourdough bread?",
        [
            "Sourdough fermentation requires flour, water, and a wild yeast starter.",
            "NVIDIA CUDA accelerates PyTorch matrix multiplication on GPUs.",
        ],
        top_k=2,
    )
    assert len(results) >= 1
    assert "Sourdough" in results[0]["text"], f"Expected Sourdough ranked first, got: {results}"
    return f"dim={len(vec)}, top_score={results[0]['score']:.3f}"


def main():
    print("\n" + "=" * 72)
    print("         NEXONAI PHASE 5 OLLAMA & MEMORY TEST SUITE")
    print("=" * 72)

    passed = 0
    failed = 0
    for name, category, fn in TESTS:
        try:
            detail = fn()
            passed += 1
            print(f"  [PASS] [{category}] {name}")
            if detail:
                print(f"         -> {detail}")
        except Exception as e:
            failed += 1
            print(f"  [FAIL] [{category}] {name}")
            print(f"         -> {type(e).__name__}: {e}")

    print("\n" + "=" * 72)
    print(f"  Results: {passed}/{len(TESTS)} passed  |  {failed} failed")
    print("=" * 72 + "\n")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
