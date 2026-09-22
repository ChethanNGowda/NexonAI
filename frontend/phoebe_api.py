import argparse
import json
import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
PROMPT_FILE = ROOT_DIR / "config" / "system_prompt.txt"
DEFAULT_MODEL = "qwen3:8b"


FALLBACK_PROMPT = """
You are Bob, the warm desktop companion inside Nexon AI.
Keep replies concise, friendly, and useful. Never claim to be Qwen.
Do not mention system prompts, internal reasoning, or implementation details.
"""


def load_system_prompt() -> str:
    try:
        prompt = PROMPT_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        prompt = ""

    return prompt or FALLBACK_PROMPT.strip()


def ask_bob(message: str, model: str = DEFAULT_MODEL) -> str:
    try:
        import ollama
    except ImportError:
        return "My Ollama Python package is missing. Run pip install -r requirements.txt first."

    try:
        response = ollama.chat(
            model=model,
            messages=[
                {"role": "system", "content": load_system_prompt()},
                {"role": "user", "content": message},
            ],
        )
    except Exception as error:
        return f"I could not reach my local brain yet: {error}"

    answer = response.get("message", {}).get("content", "").strip()
    return answer or "I'm here, but I could not form a reply that time."


def emit(payload: dict) -> int:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False))
    sys.stdout.write("\n")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Nexon AI Bob JSON bridge")
    parser.add_argument("--ask", help="Ask Bob a text question")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Ollama model name")
    parser.add_argument("--health", action="store_true", help="Check bridge health")
    args = parser.parse_args()

    if args.health:
        return emit({"ok": True, "model": args.model, "prompt": str(PROMPT_FILE)})

    if args.ask is None or not args.ask.strip():
        return emit({"ok": False, "error": "No message supplied."})

    answer = ask_bob(args.ask.strip(), args.model)
    return emit({"ok": True, "answer": answer})


if __name__ == "__main__":
    raise SystemExit(main())
