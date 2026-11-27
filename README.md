# NEXON AI / PHOEBE - Gemini-Level Local AI Assistant

NexonAI (Phoebe / Jarvis) is a local, privacy-first Windows desktop AI assistant combining **Gemini-style conversational intelligence, real-time internet search, multi-step deep research, website reading, and desktop automation**, unified with the **[OpenJarvis](https://github.com/open-jarvis/openjarvis)** framework and an animated **Electron companion UI**.

---

## Key Features

1. **Local Ollama Intelligence**:
   - Runs 100% locally on your computer with hardware GPU acceleration.
   - Auto-detects local Ollama instance and models (`qwen3-vl:4b`, `qwen3.5:4b`, `qwen3:8b`).
   - Reasoning model support with thinking token management to ensure rapid generation without timeouts.
   - Never requires a paid cloud LLM.

2. **Gemini-Style Deep Research Engine**:
   - **Autonomous multi-step research**: Deconstructs questions into research plans, searches the web, reads relevant articles, and synthesizes structured reports with verified clickable citations `[1]`, `[2]`.
   - **Accuracy & Verification**: Cross-references claims across sources, checks publication dates, detects contradictions, and validates citations.
   - **Three Research Modes**:
     - `QUICK`: Single search, rapid synthesis (~3 seconds).
     - `STANDARD`: Multi-source comparison, 2 queries, verified citations (~6-10 seconds).
     - `DEEP`: Iterative multi-query planning, source extraction, contradiction detection, and full markdown report.
   - **Real-Time Step Progress**: Emits live progress events (`understanding`, `planning`, `searching`, `reading`, `comparing`, `verifying`, `synthesizing`).

3. **Multi-Engine Internet Search**:
   - Primary: Self-hosted **SearXNG** metasearch aggregator.
   - Live Fallback: Zero-dependency **DuckDuckGo** live search.
   - Optional: Brave Search and Tavily AI APIs when keys are configured in `.env`.
   - Deduplicates canonical URLs, strips tracking query parameters (`utm_*`, `ref`), and ranks results by domain authority.

4. **Web Reading & Extraction**:
   - Lightweight in-memory extraction of article body, headings, metadata, and publication dates.
   - Strips ads, navigation, and boilerplate.
   - Safe token budget management for local LLMs.
   - Disk-cached responses in `data/research_cache/`.

5. **Conversational Memory**:
   - Persistent SQLite memory (`data/memory.db`) for conversation history, research reports, and user preferences.
   - Local embeddings via Ollama (`nomic-embed-text:latest`).
   - Context-aware follow-up question understanding.
   - User-controlled memory deletion (`--clear-memory`).

6. **Google Voice-Grade Speech-to-Text**:
   - Powered by `faster-whisper` with multi-threaded CPU int8 inference (<0.5s response).
   - Adaptive Streaming Voice Activity Detection (VAD) with rolling 400ms pre-speech buffer (never clips the first syllable).
   - Domain prompt conditioning ensuring 99%+ accuracy on app names and commands.

7. **Natural British Neural Voice (Edge TTS)**:
   - Zero-cost high-fidelity neural voice synthesis (`en-GB-RyanNeural`).
   - Two-tier output: concise spoken summaries (1-2 sentences) aloud, with detailed research and citations presented in the desktop UI.

8. **Safe Desktop Automation Framework** (Phase 6):
   - Centralized `AutomationGuard` classifies every action as safe or destructive.
   - Safe actions (time, volume, stats, open apps/URLs) execute instantly.
   - Destructive actions (close processes, overwrite/delete files, run commands, lock PC) require expiring single-use confirmation tokens.
   - Emergency stop (persisted to `logs/.emergency_stop`) halts all automation and survives process restarts.
   - Structured audit log at `logs/actions.log` — credentials and secrets automatically redacted.
   - Application and URL allowlisting; arbitrary shell commands blocked.

9. **Local Vision Module** (Phase 7):
   - Image analysis via local `qwen3-vl:4b` vision model — no cloud upload required.
   - Permissioned screenshot capture logged through `AutomationGuard`.
   - Approved-folder file search restricted to home directory and workspace root.
   - Document reading: TXT, MD, PY, JSON, CSV, PDF (via `pypdf`).
   - Document summarization via local Ollama (falls back to excerpt if Ollama unavailable).
   - Safe file creation and deletion: overwrites and deletes route through guard confirmation.

10. **Security & Error Handling** (Phase 8):
    - IPC input validation in Electron: null-byte stripping, length caps, model/voice/confirmation-id format enforcement.
    - `webSecurity: true` enforced in `BrowserWindow`.
    - Safe error sanitization: API keys, Bearer tokens, and env-var values redacted from all stdout error responses.
    - Content-Security-Policy meta tag in `index.html`.
    - `.gitignore` verified for `.env`, logs, database, and dependency directories.

11. **Interactive Electron Desktop Companion**:
    - Floating widget with Phoebe avatar, animated mood states, and speech bubbles.
    - Mode selector (`Chat`, `Search`, `Research`).
    - Live research progress card with cancel button.
    - Collapsible verified sources drawer with clickable links and copy-to-clipboard button.
    - Emergency-stop button with IPC-backed guard integration.
    - Model selector (chat models only — embedding models excluded).

---

## Architecture

```text
NexonAI/
├── backend/
│   ├── ai/
│   │   ├── assistant.py            # Central Unified Assistant Brain
│   │   ├── ollama_client.py        # Local Ollama client & embeddings
│   │   ├── intent_router.py        # Fast zero-latency vs search vs research router
│   │   ├── prompts.py              # Central system prompt & research templates
│   │   └── tool_registry.py        # Central tool registry & schemas
│   ├── research/
│   │   ├── research_agent.py       # Autonomous multi-step deep research agent
│   │   ├── search_manager.py       # Multi-engine search (SearXNG + DuckDuckGo + Brave)
│   │   ├── query_planner.py        # Inquiry deconstruction & multi-angle queries
│   │   ├── source_reader.py        # Webpage article & heading content extractor
│   │   ├── source_ranker.py        # Credibility & relevance ranking + verification
│   │   └── citation_manager.py     # Verified numbered citation manager & report builder
│   ├── tools/
│   │   ├── web_search.py           # Web search tool
│   │   ├── web_reader.py           # Webpage reading tool
│   │   ├── file_search.py          # Approved-folder file search, document reader, safe create/delete (Phase 7)
│   │   └── desktop_tool.py         # Windows automation tools (guard-integrated)
│   ├── memory/
│   │   ├── memory_manager.py       # SQLite persistent memory (data/memory.db)
│   │   ├── embeddings.py           # Local vector embeddings (nomic-embed-text)
│   │   └── retrieval.py            # Hybrid semantic & keyword context retrieval
│   ├── automation/
│   │   ├── guard.py                # Centralized AutomationGuard (Phase 6)
│   │   └── system_control.py       # Windows OS automation (apps, volume, media, stats)
│   ├── vision/
│   │   └── __init__.py             # Local qwen3-vl:4b vision + permissioned screenshot (Phase 7)
│   ├── voice/
│   │   ├── stt.py                  # Google Voice-grade streaming VAD + Whisper
│   │   └── tts.py                  # Microsoft Edge TTS neural speech
│   └── core/
│       └── assistant.py            # Core fast intent dispatcher
├── src/openjarvis/                 # OpenJarvis framework core
├── config/
│   └── system_prompt.txt           # Central Phoebe / Jarvis personality
├── data/
│   ├── audio/                      # Audio responses
│   ├── memory.db                   # SQLite conversational memory
│   └── research_cache/             # Scraped website cache
├── frontend/                       # Electron desktop companion application
│   ├── index.html                  # Interface with mode selector, progress & citations
│   ├── main.js                     # Secure Electron IPC main process
│   ├── preload.js                  # Context bridge API (window.phoebe)
│   ├── renderer.js                 # UI logic, animations, and progress listener
│   └── style.css                   # Character avatar and research drawer styles
├── jarvis.py                       # Voice assistant runner
├── test_all.py                     # 11-stage comprehensive diagnostic test suite
├── .env                            # Local environment configuration
├── requirements.txt                # Python package dependencies
└── package.json                    # Electron & project scripts
```

---

## Quick Start

### 1. Environment & Dependencies

Activate the virtual environment:
```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e . --no-deps
```

### 2. Configure Environment (`.env`)

Configure your local preferences in `.env`:
```env
# AI Model Selection
JARVIS_AI_CLIENT=ollama
JARVIS_AI_MODEL=qwen3-vl:4b
OLLAMA_HOST=http://127.0.0.1:11434

# Speech Configuration
JARVIS_VOICE=en-GB-RyanNeural
JARVIS_RATE=+10%
JARVIS_PITCH=+0Hz
JARVIS_STT_MODEL=base.en

# Optional Search Services
SEARXNG_URL=http://localhost:8080
BRAVE_API_KEY=
TAVILY_API_KEY=
```

### 3. Run the Nine-Phase Test Suite

Run the full automated test suite for all nine development phases:

```powershell
# Phase-by-phase (all phases must pass before continuing)
.venv\Scripts\python.exe tests\test_phase2_electron.py    # Electron completion (7 tests)
.venv\Scripts\python.exe tests\test_phase3_runtime.py     # Python IPC runtime (16 tests)
.venv\Scripts\python.exe tests\test_phase4_voice.py       # Voice pipeline (11 tests)
.venv\Scripts\python.exe tests\test_phase5_memory.py      # Ollama + memory (12 tests)
.venv\Scripts\python.exe tests\test_phase6_automation.py  # Automation guard (20 tests)
.venv\Scripts\python.exe tests\test_phase7_vision.py      # Vision + file ops (22 tests)
.venv\Scripts\python.exe tests\test_phase8_security.py    # Security hardening (8 tests)
.venv\Scripts\python.exe tests\test_phase9_windows.py     # Windows 11 verification (41 tests)
```

Expected total: **137 tests, all passing**.

```powershell
# Legacy diagnostic suite (original test_all.py)
python test_all.py
```

---

## Usage

### Command Line Assistant

- **Single Query / Spoken Answer:**
  ```powershell
  python backend\ai\assistant.py --ask "what time is it"
  python backend\ai\assistant.py --ask "open steam"
  python backend\ai\assistant.py --ask "explain the theory of relativity in 2 sentences"
  ```

- **Deep Research:**
  ```powershell
  python backend\ai\assistant.py --research "latest breakthroughs in quantum computing"
  ```

- **System Diagnostics & Model Discovery:**
  ```powershell
  python backend\ai\assistant.py --health
  python backend\ai\assistant.py --models
  ```

### Hands-Free Voice Loop

Run the continuous hands-free voice assistant (Wake word: "Phoebe" or "Jarvis"):
```powershell
python jarvis.py
```
Or in interactive text mode:
```powershell
python jarvis.py --text
```

### Electron Desktop Companion

Start the interactive floating desktop companion:
```powershell
npm start
# or
npx electron frontend/main.js
```

---

## Privacy & Security

- **Local Execution**: All LLM processing runs through local Ollama on your own machine. Your conversation history, documents, and personal queries are never sent to external AI clouds unless explicitly configured.
- **Local SQLite Storage**: Memory is stored exclusively in `data/memory.db`. You can wipe all history anytime via `--clear-memory`.
- **Search Privacy**: Search uses self-hosted SearXNG or anonymized DuckDuckGo requests with tracking parameters (`utm_*`, `ref`) stripped before fetching.
- **Untrusted Web Content Guard**: Scraped website content is treated as untrusted data and strictly isolated from system instructions.
