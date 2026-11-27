"""
JARVIS / PHOEBE - LOCAL OLLAMA CLIENT & INTELLIGENCE CONNECTOR
==============================================================
Manages local Ollama connectivity, model discovery, generation,
reasoning token management, and local embeddings.
"""

import json
import logging
import os
import re
import urllib.error
import urllib.request
from typing import Any, Callable, Dict, Generator, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
PREFERRED_MODELS = ["qwen3-vl:4b", "qwen3.5:4b", "qwen3:8b", "llama3.2:3b", "mistral:latest"]
PREFERRED_EMBED_MODELS = ["nomic-embed-text:latest", "nomic-embed-text", "all-minilm"]


class OllamaClient:
    def __init__(self, host: str = DEFAULT_OLLAMA_HOST):
        self.host = host
        self._cached_models: Optional[List[str]] = None

    def is_available(self) -> bool:
        """Check if local Ollama daemon is reachable."""
        try:
            req = urllib.request.Request(f"{self.host}/api/tags", headers={"User-Agent": "NexonAI"})
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                return resp.status == 200
        except Exception:
            return False

    def list_installed_models(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """List all models installed locally in Ollama."""
        try:
            req = urllib.request.Request(f"{self.host}/api/tags", headers={"User-Agent": "NexonAI"})
            with urllib.request.urlopen(req, timeout=2.5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                models = data.get("models", [])
                self._cached_models = [m.get("name", "") for m in models]
                return models
        except Exception as e:
            logger.warning("Could not list Ollama models: %s", e)
            return []

    def get_installed_model_names(self) -> List[str]:
        """Return simple list of installed model names."""
        models = self.list_installed_models()
        return [m.get("name", "") for m in models if m.get("name")]

    def resolve_chat_model(self, requested_model: Optional[str] = None) -> str:
        """Resolve the best available local model."""
        if requested_model:
            return requested_model

        env_model = os.getenv("JARVIS_AI_MODEL", "").strip()
        if env_model:
            return env_model

        installed = self.get_installed_model_names()
        for pref in PREFERRED_MODELS:
            for name in installed:
                if pref in name:
                    return name

        # Any non-embedding model
        for name in installed:
            if "embed" not in name:
                return name

        return "qwen3-vl:4b"

    def resolve_embed_model(self) -> Optional[str]:
        """Resolve available local embedding model (e.g. nomic-embed-text)."""
        installed = self.get_installed_model_names()
        for pref in PREFERRED_EMBED_MODELS:
            for name in installed:
                if pref in name:
                    return name
        return None

    def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.5,
        max_tokens: int = 400,
        stream_callback: Optional[Callable[[str], None]] = None,
    ) -> str:
        """
        Send a conversation to Ollama chat API.
        Handles thinking models (Qwen 3 / DeepSeek) cleanly by prefilling '</think>'
        to avoid wasting generation budget on internal monologue.
        """
        target_model = self.resolve_chat_model(model)

        # Clone and manage thinking prefill for reasoning models
        chat_msgs = [dict(m) for m in messages]
        if chat_msgs and chat_msgs[-1].get("role") == "user":
            chat_msgs.append({"role": "assistant", "content": "</think>"})

        payload = {
            "model": target_model,
            "messages": chat_msgs,
            "stream": stream_callback is not None,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

        try:
            req = urllib.request.Request(
                f"{self.host}/api/chat",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )

            if stream_callback is not None:
                accumulated = []
                with urllib.request.urlopen(req, timeout=120) as resp:
                    for line in resp:
                        if not line:
                            continue
                        chunk = json.loads(line.decode("utf-8"))
                        piece = chunk.get("message", {}).get("content", "")
                        if piece:
                            accumulated.append(piece)
                            stream_callback(piece)
                full_text = "".join(accumulated).strip()
                return self._clean_thinking(full_text)
            else:
                with urllib.request.urlopen(req, timeout=120) as resp:
                    chunk = json.loads(resp.read().decode("utf-8"))
                    msg = chunk.get("message", {})
                    content = msg.get("content", "").strip() or msg.get("thinking", "").strip()
                    return self._clean_thinking(content)

        except urllib.error.URLError as e:
            return f"Ollama connection error: {e}. Ensure Ollama is running on {self.host}."
        except Exception as e:
            return f"Ollama error: {e}"

    def generate_json(
        self,
        prompt: str,
        system_instruction: str,
        model: Optional[str] = None,
        max_tokens: int = 500,
    ) -> Dict[str, Any]:
        """Generate structured JSON response using Ollama."""
        target_model = self.resolve_chat_model(model)
        payload = {
            "model": target_model,
            "messages": [
                {"role": "system", "content": f"{system_instruction}\nRespond ONLY in valid JSON."},
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": "</think>{"},
            ],
            "stream": False,
            "format": "json",
            "options": {
                "temperature": 0.2,
                "num_predict": max_tokens,
            },
        }

        try:
            req = urllib.request.Request(
                f"{self.host}/api/chat",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=35) as resp:
                res = json.loads(resp.read().decode("utf-8"))
                text = res.get("message", {}).get("content", "").strip()
                if not text.startswith("{"):
                    text = "{" + text
                return json.loads(text)
        except Exception as e:
            logger.warning("JSON generation parse failed (%s), extracting fallback JSON", e)
            return self._extract_json_fallback(prompt, system_instruction, target_model)

    def _extract_json_fallback(self, prompt: str, system: str, model: str) -> Dict[str, Any]:
        """Fallback JSON extraction via regex."""
        raw = self.chat(
            [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            model=model,
            temperature=0.1,
        )
        match = re.search(r"(\{.*\})", raw, flags=re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except Exception:
                pass
        return {}

    def get_embedding(self, text: str) -> Optional[List[float]]:
        """Compute text embedding vector via local Ollama."""
        embed_model = self.resolve_embed_model()
        if not embed_model:
            return None

        payload = {"model": embed_model, "prompt": text}
        try:
            req = urllib.request.Request(
                f"{self.host}/api/embeddings",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data.get("embedding")
        except Exception as e:
            logger.warning("Embedding generation failed: %s", e)
            return None

    def _clean_thinking(self, content: str) -> str:
        """Strip internal thinking tags if present."""
        if "<think>" in content:
            if "</think>" in content:
                content = content.split("</think>")[-1].strip()
            else:
                content = re.sub(r"^<think>\s*", "", content).strip()
        return content


# Global instance
_default_client: Optional[OllamaClient] = None


def get_ollama_client() -> OllamaClient:
    global _default_client
    if _default_client is None:
        _default_client = OllamaClient()
    return _default_client
