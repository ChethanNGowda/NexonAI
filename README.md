# Nexon AI

Nexon AI is a local Windows desktop AI companion named Bob. It combines an Electron desktop avatar with Python voice, speech-to-text, local LLM, and text-to-speech components so Bob can listen, respond, and act like a lightweight desktop assistant.

Nexon AI is not related to the Nexon gaming company.

## Main Features

- Frameless always-on-top Electron companion window
- Bob avatar UI with typed chat and browser speech recognition support
- Electron-to-Python bridge for asking the local Ollama model from the desktop UI
- Python voice loop for microphone recording and transcription
- faster-whisper speech-to-text support
- Ollama-powered local chat using `qwen3:8b`
- Microsoft Edge TTS runtime voice generation
- ElevenLabs voice-design helper script
- Project areas for future automation, vision, file, code-agent, and core assistant modules

## Architecture

- `frontend/` contains the Electron app, renderer UI, Bob avatar assets, and Python voice assistant scripts.
- `frontend/Bob_api.py` is the JSON bridge used by Electron to ask the local model.
- `frontend/Bob_brain.py` records microphone input, transcribes with faster-whisper, sends prompts to Ollama, and invokes Bob TTS.
- `frontend/Bob_tts.py` generates runtime voice audio with Microsoft Edge TTS.
- `frontend/Bob_voice.py` is an ElevenLabs voice-preview/design utility that reads credentials from `.env`.
- `backend/` contains early backend module areas for voice, automation, AI, files, vision, core logic, and code-agent features.
- `config/system_prompt.txt` stores Nexon AI's local assistant behavior prompt.

## Technologies Used

- Windows
- Python
- Electron
- Node.js and npm
- faster-whisper
- Ollama
- Qwen3 8B through Ollama
- Microsoft Edge TTS
- ElevenLabs
- Web Speech API

## Project Structure

```text
NexonAI/
  backend/                 Python backend modules
  config/                  Assistant prompt/config files
  data/                    Local app data
  docs/                    Project documentation
  frontend/                Electron UI and Bob runtime scripts
    assets/phoebe/         Avatar assets
    audio/                 Runtime-generated audio, ignored by Git
    whisper-model/         Downloaded faster-whisper model, ignored by Git
  logs/                    Runtime logs, ignored by Git
  models/                  Local/downloaded model files, ignored by Git
  scripts/                 Utility scripts
  tests/                   Test area
```

## Installation

Install Python 3.11 or newer, Node.js, npm, and Ollama for Windows. Then clone the project and install the Python and Electron dependencies.

## Python Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Some audio packages may require working Windows audio input/output devices. If microphone capture fails, confirm Windows microphone permissions and the selected input device.

## Node/Electron Setup

Install Electron dependencies from the frontend folder:

```powershell
cd frontend
npm install
```

The root `package.json` delegates common commands to `frontend/package.json`.

## Ollama Setup

Install Ollama for Windows, start Ollama, and download the local chat model:

```powershell
ollama pull qwen3:8b
```

`frontend/Bob_brain.py` expects `qwen3:8b` by default.

## Whisper/faster-whisper Setup

Bob uses faster-whisper for local speech-to-text. If `frontend/whisper-model/` exists, the app uses that local model folder. If it does not exist, faster-whisper can download the configured `small` model on first use.

Downloaded Whisper and Hugging Face cache files are intentionally ignored by Git. Do not commit `frontend/whisper-model/`, model binaries, or cache folders.

## ElevenLabs Configuration

Keep real credentials in a local `.env` file and never commit it.

Create `frontend/.env` from the example:

```powershell
Copy-Item .env.example frontend\.env
```

Then fill in:

```text
ELEVENLABS_API_KEY=your-real-key
Bob_VOICE_ID=your-voice-id
```

`frontend/Bob_voice.py` reads these values with `python-dotenv`.

## Environment Variables

| Variable | Required For | Description |
| --- | --- | --- |
| `ELEVENLABS_API_KEY` | ElevenLabs voice design | Your ElevenLabs API key |
| `Bob_VOICE_ID` | ElevenLabs voice workflows | The selected/generated Bob voice ID |

## Running the Application

Start the Electron companion UI from the project root:

```powershell
npm start
```

Or start it from the frontend folder:

```powershell
cd frontend
npm start
```

Ask Bob from the bridge directly:

```powershell
python frontend\Bob_api.py --ask "Hello Bob"
```

Run the Python voice loop:

```powershell
.\.venv\Scripts\Activate.ps1
python frontend\Bob_brain.py
```

Run validation:

```powershell
npm test
python -m py_compile frontend\Bob_api.py frontend\Bob_brain.py frontend\Bob_tts.py
```

Run the ElevenLabs voice-preview helper only after configuring `frontend/.env`:

```powershell
python frontend\Bob_voice.py
```

## Safety and Privacy

- `.env` files are ignored and must stay local.
- Do not commit API keys, passwords, tokens, or personal credentials.
- Python virtual environments and `node_modules` are ignored.
- Runtime audio, logs, local model files, and Hugging Face/Ollama caches are ignored.
- Voice input, generated audio, and local model data may contain private information; review files before sharing builds or logs.
- Ollama models are downloaded locally and should be documented, not committed.

## Future Features

- Deeper desktop automation
- File and project search actions
- Vision-based screen understanding
- Persistent memory with privacy controls
- Unified backend service layer
- Packaged Windows installer
- Configurable voice/model settings in the UI
- Deeper desktop automation commands from the Electron UI

