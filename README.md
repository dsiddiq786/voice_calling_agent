# NomNosh Voice Order MVP

Roman-Urdu restaurant order taker for Apple Silicon. Phase 1 proves the full ordering loop before telephone/SIP integration:

1. Customer speaks or types an order.
2. OpenAI powers Fatima's natural conversation and returns structured actions.
3. The backend validates every action against the restaurant catalog.
4. The customer confirms the itemized total.
5. The confirmed order appears on the kitchen dashboard.

OpenAI handles conversation, but it cannot directly invent or change catalog records. Item IDs, prices, cart mutations, and final confirmation are validated by the backend. If OpenAI is unavailable, the app falls back to the basic rule engine.

## API configuration

Create `.env` in the project root and add your keys. Never commit or paste real keys into chat.

```dotenv
OPENAI_API_KEY=your_openai_api_key
OPENAI_MODEL=gpt-5.4-mini
DEEPGRAM_API_KEY=your_deepgram_api_key
AZURE_SPEECH_KEY=your_azure_speech_key
AZURE_SPEECH_REGION=eastus
AZURE_SPEECH_VOICE=ur-PK-UzmaNeural
```

`OPENAI_API_KEY` comes from the OpenAI Platform API Keys page. A ChatGPT subscription does not include API usage; API billing is managed separately on the Platform.

## Quick start

On macOS, double-click `Start NomNosh.command` and keep its Terminal window open.

Or start it manually:

```bash
./scripts/setup.sh
./scripts/run.sh
```

Open <http://127.0.0.1:8010/customer>. The restaurant dashboard is at <http://127.0.0.1:8010/dashboard>.

Run tests with:

```bash
./scripts/test.sh
```

## Voice pipeline

The preferred live pipeline is Deepgram for Urdu speech recognition and Azure `ur-PK-UzmaNeural` for Fatima's voice. Local Whisper remains only as the offline fallback.

```bash
./scripts/install-speech.sh
```

The first local transcription downloads an open Whisper model. The default is the CPU-compatible `base` model. Override it with `NOMNOSH_WHISPER_MODEL`.

## Important

`data/menu.json` contains the NomNosh Sahiwal catalog imported from the restaurant website on 2026-07-19. Restaurant staff must still verify prices, variants, and availability before a real pilot.
