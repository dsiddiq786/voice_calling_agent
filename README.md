# Fatima — Real-time Restaurant Voice Agent

Fatima is a local MVP for a Pakistani restaurant order-taking voice agent. It is designed for a natural Roman Urdu ordering experience, starting with NomNosh in Sahiwal and structured so the platform can later support multiple restaurants.

## What works now

- Real-time browser call using ElevenLabs WebRTC
- Roman Urdu / English food-term conversation with a concise professional greeting
- ElevenLabs Fatima voice, interruption handling, and live transcripts
- Menu-aware suggestions and deal awareness
- Live cart tools: add, remove, read total, save delivery address, and confirm order
- Kitchen order dashboard
- Deepgram STT and an existing OpenAI-powered text/serial-call fallback

## Architecture

```text
Customer microphone
  → ElevenLabs WebRTC agent (speech, turn-taking, interruption)
  → browser client tools
  → FastAPI cart + menu validation
  → kitchen orders dashboard
```

The realtime agent does not calculate prices or mutate orders itself. The local backend validates exact catalog items and totals before the UI is updated or an order is confirmed.

## Requirements

- macOS (Apple Silicon supported)
- Python 3.11+ recommended
- Node.js 20+
- ElevenLabs API key and Fatima voice ID
- Deepgram / OpenAI keys only if you also use the legacy fallback pipeline

## Setup

```bash
cp .env.example .env
./scripts/setup.sh
NPM_CONFIG_CACHE=/tmp/fatima-npm npm install
NOMNOSH_PORT=8026 ./scripts/run.sh
```

Open <http://127.0.0.1:8026/customer> and grant microphone access when prompted. Start a new call after any agent configuration change because realtime settings are loaded at call start.

## Environment variables

Never commit real credentials. Configure these in `.env`:

```dotenv
ELEVENLABS_API_KEY=your_key
ELEVENLABS_VOICE_ID=your_fatima_voice_id
ELEVENLABS_FATIMA_AGENT_ID=your_realtime_agent_id

# Optional legacy/fallback services
OPENAI_API_KEY=your_key
DEEPGRAM_API_KEY=your_key
AZURE_SPEECH_KEY=your_key
AZURE_SPEECH_REGION=eastus
```

## Tests

```bash
.venv/bin/pytest -q
```

## Scope note

This is a local demo, not yet a production phone system. Production rollout needs SIP/telephony routing, persistent multi-tenant restaurant data, user authentication, monitoring, encrypted secrets, call recordings with consent, human transfer/failover, and a Pakistani telephone-audio evaluation set.
