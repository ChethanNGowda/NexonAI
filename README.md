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

8. **Windows Desktop Automation & OpenJarvis Tools**:
   - Instant zero-latency actions (<10ms) for app launching (Chrome, Steam, Spotify, VS Code, etc.), volume control, media playback, system stats, and screenshots.
   - Registered as native tools in OpenJarvis.

9. **Interactive Electron Desktop Companion**:
   - Floating widget with Phoebe avatar, animated mood states, and speech bubbles.
   - Mode selector (`Chat`, `Search`, `Research`).
   - Live research progress card with cancel button.
   - Collapsible verified sources drawer with clickable links and copy-to-clipboard button.

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
│   │   ├── file_search.py          # Local file search tool
│   │   ├── document_reader.py      # PDF, text, and code document reader tool
│   │   └── desktop_tool.py         # Windows automation tools
│   ├── memory/
│   │   ├── memory_manager.py       # SQLite persistent memory (data/memory.db)
│   │   ├── embeddings.py           # Local vector embeddings (nomic-embed-text)
│   │   └── retrieval.py            # Hybrid semantic & keyword context retrieval
│   ├── automation/
│   │   └── system_control.py       # Windows OS automation (apps, volume, media, stats)
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

### 3. Run All 11 Diagnostics

Ensure all hardware, speech models, local Ollama, web search, scraper, and database are functional:
```powershell
python test_all.py
```

Expected output:
```
[1/7] Testing System Automation...                   [OK]
[2/7] Testing OpenJarvis Registered Desktop Tools... [OK]
[3/7] Testing OpenJarvis Edge-TTS Speech Synthesis...[OK]
[4/7] Testing Whisper Speech-to-Text Model...        [OK]
[5/7] Testing Fast Intent Router & Assistant...      [OK]
[6/7] Checking AI Intelligence Connectivity...       [OK] (Ollama: qwen3-vl:4b)
[7/7] Checking Audio Devices...                      [OK]
[8/11] Testing Multi-Engine Internet Search...       [OK]
[9/11] Testing Website Content Extractor...          [OK]
[10/11] Testing Persistent SQLite Memory...          [OK]
[11/11] Testing Unified Assistant Brain...           [OK]
=================================================================
              ALL 11 DIAGNOSTICS COMPLETE
=================================================================
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
