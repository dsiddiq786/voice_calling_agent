import os
import json
import re
import subprocess
import sys
import tempfile
from html import escape
from pathlib import Path
from typing import Optional

import httpx
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
MODEL = os.getenv("NOMNOSH_WHISPER_MODEL", "base")
_TTS_CACHE: dict[str, bytes] = {}
_SPEECH_CLIENT: Optional[httpx.AsyncClient] = None


def _speech_client() -> httpx.AsyncClient:
    global _SPEECH_CLIENT
    if _SPEECH_CLIENT is None:
        _SPEECH_CLIENT = httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=5.0))
    return _SPEECH_CLIENT


async def transcribe_deepgram(audio: bytes, content_type: str) -> str:
    api_key = os.getenv("DEEPGRAM_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("Deepgram API key is not configured")
    params = [
        ("model", "nova-3"),
        ("language", "ur"),
        ("smart_format", "true"),
        ("punctuate", "true"),
        ("utterances", "false"),
    ]
    # Nova-3 keyterms bias recognition toward the restaurant's real catalog.
    for keyterm in (
        "NomNosh", "Fatima", "Pizza Burger", "Patty O Max", "Razor Max",
        "Grilled Chicken Burger", "Spicy Burger", "Chicken Petty Burger",
        "Arabic Roll", "Behari Roll", "NomNosh Special Platter",
        "Behari Platter", "Pepsi", "Mirinda", "Sting", "Deal One",
        "Deal Two", "Deal Three", "Deal Four", "Deal Five", "Deal Six",
    ):
        params.append(("keyterm", keyterm))
    headers = {
        "Authorization": f"Token {api_key}",
        "Content-Type": content_type or "audio/webm",
    }
    try:
        response = await _speech_client().post(
            "https://api.deepgram.com/v1/listen",
            params=params,
            headers=headers,
            content=audio,
        )
        response.raise_for_status()
        payload = response.json()
        alternative = payload["results"]["channels"][0]["alternatives"][0]
        transcript = alternative["transcript"].strip()
        confidence = float(alternative.get("confidence", 0.0))
        if not transcript or confidence < 0.35:
            return ""
        return transcript
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        raise RuntimeError("Online speech recognition is temporarily unavailable") from exc


def speech_provider() -> str:
    return "deepgram" if os.getenv("DEEPGRAM_API_KEY", "").strip() else "local"


def tts_provider() -> str:
    preferred = os.getenv("TTS_PROVIDER", "auto").strip().lower()
    eleven_key = os.getenv("ELEVENLABS_API_KEY", "").strip()
    eleven_voice = os.getenv("ELEVENLABS_VOICE_ID", "").strip()
    if preferred in {"auto", "elevenlabs"} and eleven_key and eleven_voice:
        return "elevenlabs"
    key = os.getenv("AZURE_SPEECH_KEY", "").strip()
    region = os.getenv("AZURE_SPEECH_REGION", "").strip()
    return "azure" if key and region else "browser"


def urdu_for_tts(text: str) -> str:
    """Convert our controlled Roman-Urdu prompts to script Uzma pronounces naturally."""
    phrases = (
        ("Assalam-o-Alaikum", "السلام علیکم"),
        ("subah bakhair", "صبح بخیر"),
        ("shaam bakhair", "شام بخیر"),
        ("NomNosh", "نوم نوش"),
        ("Nom Nosh", "نوم نوش"),
        ("Fatima", "فاطمہ"),
        ("Nom Nosh call karne ka shukriya", "نوم نوش کال کرنے کا شکریہ"),
        ("Main Fatima hoon", "میں فاطمہ ہوں"),
        ("aaj kya mangwana pasand karein ge", "آج کیا منگوانا پسند کریں گے"),
        ("Allah Hafiz", "اللہ حافظ"),
        ("Bohat shukriya", "بہت شکریہ"),
        ("Nom Nosh ko call karne ka bohat shukriya", "نوم نوش کو کال کرنے کا بہت شکریہ"),
        ("Fatima line par hazir hai", "فاطمہ لائن پر حاضر ہے"),
        ("Jee farmayein, aaj kya order karna pasand karein ge", "جی فرمائیے، آج کیا آرڈر کرنا پسند کریں گے"),
        ("Aapka order", "آپ کا آرڈر"),
        ("aap kya order karna chahein ge", "آپ کیا آرڈر کرنا چاہیں گے"),
        ("main sun rahi hoon", "میں سن رہی ہوں"),
        ("Aur kuch lena chahein ge", "اور کچھ لینا چاہیں گے"),
        ("Aur kuch order karna chahein ge", "اور کچھ آرڈر کرنا چاہیں گے"),
        ("order kitchen ko bhej diya gaya hai", "آرڈر کچن کو بھیج دیا گیا ہے"),
        ("Kya main order confirm kar doon", "کیا میں آرڈر کنفرم کر دوں"),
        ("hamare paas", "ہمارے پاس"),
        ("Aap kis mood mein hain", "آپ کس موڈ میں ہیں"),
        ("Main Fatima bol rahi hoon, Nom Nosh", "میں فاطمہ بول رہی ہوں، نوم نوش"),
        ("Jee farmayein, aaj kya khana pasand karein ge", "جی فرمائیے، آج کیا کھانا پسند کریں گے"),
        ("Jee jee, main sun rahi hoon", "جی جی، میں سن رہی ہوں"),
        ("Batayein, aur kya rakhna hai", "بتائیے، اور کیا رکھنا ہے"),
        ("note kar liya", "نوٹ کر لیا"),
        ("Saath wings ya drink rakh doon", "ساتھ ونگز یا ڈرنک رکھ دوں"),
        ("Saath fries ya drink lena pasand karein ge", "ساتھ فرائز یا ڈرنک لینا پسند کریں گے"),
        ("Aur kuch chahiye, ya isi ko final karein", "اور کچھ چاہیے، یا اسی کو فائنل کریں"),
        ("Aur kuch lena pasand karein ge", "اور کچھ لینا پسند کریں گے"),
        ("Theek jee, aik dafa order repeat kar deti hoon", "ٹھیک جی، ایک دفعہ آرڈر دہرا دیتی ہوں"),
        ("Total", "ٹوٹل"),
        ("banta hai", "بنتا ہے"),
        ("Sab theek hai", "سب ٹھیک ہے"),
        ("Sorry jee, last part miss ho gaya", "معذرت جی، آخری بات سنائی نہیں دی"),
        ("Item ka naam aik dafa dobara bol dein", "آئٹم کا نام ایک دفعہ دوبارہ بول دیں"),
        ("Aap kis category ke options sunna chahein ge", "آپ کس کیٹیگری کے آپشنز سننا چاہیں گے"),
        ("Aap kis category se shuru karein ge", "آپ کس کیٹیگری سے شروع کریں گے"),
        ("Aapko spicy, cheesy ya light option chahiye", "آپ کو اسپائسی، چیزی یا لائٹ آپشن چاہیے"),
        ("In mein se kya pasand karein ge", "ان میں سے کیا پسند کریں گے"),
        ("Agar pasand hai to kahein", "اگر پسند ہے تو کہیں"),
        ("yehi add kar dein", "یہی شامل کر دیں"),
        ("Main", "میں"),
        ("suggest karoon gi", "تجویز کروں گی"),
        ("Is mein", "اس میں"),
        ("Is ki", "اس کی"),
        ("price", "قیمت"),
        ("starting from", "شروع"),
        ("available hain", "دستیاب ہیں"),
        ("popular options hain", "مشہور آپشنز ہیں"),
        ("options bhi available hain", "مزید آپشنز بھی دستیاب ہیں"),
        ("pizzas", "پیزاز"),
        ("burgers", "برگرز"),
        ("deals", "ڈیلز"),
        ("wraps", "ریپس"),
        ("fried items", "فرائیڈ آئٹمز"),
        ("pasta", "پاستا"),
        ("sandwiches", "سینڈوچز"),
        ("drinks", "ڈرنکس"),
        ("aur", "اور"),
        ("mein", "میں"),
        ("hain", "ہیں"),
        ("aik dafa dobara bata dein", "ایک دفعہ دوبارہ بتا دیں"),
        ("aakhri baat clear nahi aayi", "آخری بات واضح نہیں آئی"),
        ("Maazrat", "معذرت"),
        ("Perfect", "پرفیکٹ"),
        ("Theek hai", "ٹھیک ہے"),
        ("Bilkul", "بالکل"),
        ("Jee", "جی"),
        ("jee", "جی"),
        ("rupay", "روپے"),
        ("add kar diya", "شامل کر دیا"),
        ("suggest karoon gi", "تجویز کروں گی"),
        ("price", "قیمت"),
        ("menu", "مینو"),
        ("options", "آپشنز"),
        ("listed", "درج"),
        ("available", "دستیاب"),
        ("order", "آرڈر"),
        ("confirm", "کنفرم"),
        ("kitchen", "کچن"),
    )
    spoken = text
    for roman, urdu in phrases:
        spoken = re.sub(re.escape(roman), urdu, spoken, flags=re.IGNORECASE)
    return spoken


def romanize_transcript(text: str) -> str:
    """Romanize common restaurant Urdu while preserving brand/menu words."""
    phrases = (
        ("السلام علیکم", "Assalam-o-Alaikum"),
        ("کیا کیا", "kya kya"),
        ("آپ کے پاس", "aap ke paas"),
        ("چاہوں گا", "chahoon ga"),
        ("چاہتی ہوں", "chahti hoon"),
        ("چاہتا ہوں", "chahta hoon"),
        ("سجیسٹ کریں", "suggest karein"),
        ("مشورہ دیں", "mashwara dein"),
    )
    words = {
        "جی": "jee", "میں": "main", "مجھے": "mujhe", "ہمیں": "hamein",
        "آپ": "aap", "کے": "ke", "کو": "ko", "سے": "se", "پاس": "paas",
        "کیا": "kya", "کچھ": "kuch", "ہے": "hai", "ہیں": "hain",
        "پیزا": "pizza", "برگر": "burger", "ریپ": "wrap", "رول": "roll",
        "پلیٹر": "platter", "ڈیل": "deal", "ڈرنک": "drink", "پانی": "pani",
        "آرڈر": "order", "کرنا": "karna", "کریں": "karein", "کر": "kar",
        "چاہوں": "chahoon", "چاہتا": "chahta", "چاہتی": "chahti", "گا": "ga",
        "ہوں": "hoon", "سجیسٹ": "suggest", "آپشن": "option", "آپشنز": "options",
        "اویلیبل": "available", "دستیاب": "available", "بتائیں": "batayein",
        "اچھا": "acha", "اچھی": "achi", "ایک": "aik", "دو": "do",
        "تین": "teen", "چار": "chaar", "پانچ": "paanch", "اور": "aur",
        "نہیں": "nahi", "ہاں": "haan", "بس": "bas", "کنفرم": "confirm",
    }
    result = text
    for urdu, roman in phrases:
        result = result.replace(urdu, roman)
    tokens = re.split(r"(\s+|[،,.!?؟])", result)
    return "".join(words.get(token, token) for token in tokens).strip()


async def synthesize_azure(text: str) -> bytes:
    key = os.getenv("AZURE_SPEECH_KEY", "").strip()
    region = os.getenv("AZURE_SPEECH_REGION", "").strip()
    voice = os.getenv("AZURE_SPEECH_VOICE", "ur-PK-UzmaNeural").strip()
    if not key or not region:
        raise RuntimeError("Azure Speech is not configured")
    cache_key = f"{voice}:{text}"
    if cache_key in _TTS_CACHE:
        return _TTS_CACHE[cache_key]
    spoken = escape(urdu_for_tts(text))
    spoken = spoken.replace(". ", ".<break time='140ms'/>")
    ssml = (
        "<speak version='1.0' xml:lang='ur-PK'>"
        f"<voice name='{escape(voice)}'>"
        "<prosody rate='-3%' pitch='default'>"
        f"{spoken}"
        "</prosody></voice></speak>"
    )
    headers = {
        "Ocp-Apim-Subscription-Key": key,
        "Content-Type": "application/ssml+xml",
        "X-Microsoft-OutputFormat": "audio-24khz-48kbitrate-mono-mp3",
        "User-Agent": "NomNosh-Fatima-MVP",
    }
    url = f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1"
    try:
        response = await _speech_client().post(url, headers=headers, content=ssml.encode("utf-8"))
        response.raise_for_status()
        if not response.content:
            raise RuntimeError("Azure returned empty audio")
        if len(_TTS_CACHE) >= 256:
            _TTS_CACHE.pop(next(iter(_TTS_CACHE)))
        _TTS_CACHE[cache_key] = response.content
        return response.content
    except httpx.HTTPError as exc:
        raise RuntimeError("Fatima's online voice is temporarily unavailable") from exc


async def synthesize_elevenlabs(text: str) -> bytes:
    """Generate the Urdu-capable Fatima voice through ElevenLabs v3.

    Flash v2.5 is deliberately not the default: ElevenLabs' published Flash
    language list does not currently include Urdu. Eleven v3 does.
    """
    api_key = os.getenv("ELEVENLABS_API_KEY", "").strip()
    voice_id = os.getenv("ELEVENLABS_VOICE_ID", "").strip()
    model = os.getenv("ELEVENLABS_MODEL", "eleven_v3").strip()
    if not api_key or not voice_id:
        raise RuntimeError("ElevenLabs voice is not configured")
    cache_key = f"elevenlabs:{model}:{voice_id}:{text}"
    if cache_key in _TTS_CACHE:
        return _TTS_CACHE[cache_key]
    # Urdu script gives substantially more reliable Pakistani pronunciation
    # than asking a multilingual model to infer Roman Urdu spellings.
    spoken = urdu_for_tts(text)
    headers = {"xi-api-key": api_key, "Content-Type": "application/json"}
    payload = {
        "text": spoken,
        "model_id": model,
        "language_code": "ur",
        "voice_settings": {
            "stability": 0.58,
            "similarity_boost": 0.78,
            "style": 0.18,
            "use_speaker_boost": True,
            "speed": 1.04,
        },
    }
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream"
    try:
        params = {"output_format": "mp3_22050_32"}
        # Eleven v3 rejects the legacy optimize_streaming_latency parameter.
        if model.startswith("eleven_flash") or model.startswith("eleven_turbo"):
            params["optimize_streaming_latency"] = "3"
        response = await _speech_client().post(
            url,
            params=params,
            headers=headers,
            json=payload,
        )
        response.raise_for_status()
        if not response.content:
            raise RuntimeError("ElevenLabs returned empty audio")
        if len(_TTS_CACHE) >= 256:
            _TTS_CACHE.pop(next(iter(_TTS_CACHE)))
        _TTS_CACHE[cache_key] = response.content
        return response.content
    except httpx.HTTPError as exc:
        raise RuntimeError("Fatima's ElevenLabs voice is temporarily unavailable") from exc


async def synthesize_speech(text: str) -> bytes:
    provider = tts_provider()
    if provider == "elevenlabs":
        try:
            return await synthesize_elevenlabs(text)
        except RuntimeError:
            # A demo call should survive quota or provider incidents when Azure
            # credentials are also present.
            if os.getenv("AZURE_SPEECH_KEY", "").strip() and os.getenv("AZURE_SPEECH_REGION", "").strip():
                return await synthesize_azure(text)
            raise
    if provider == "azure":
        return await synthesize_azure(text)
    raise RuntimeError("No online text-to-speech provider is configured")


async def open_elevenlabs_stream(text: str) -> httpx.Response:
    """Open ElevenLabs without buffering the audio, allowing immediate playback."""
    api_key = os.getenv("ELEVENLABS_API_KEY", "").strip()
    voice_id = os.getenv("ELEVENLABS_VOICE_ID", "").strip()
    model = os.getenv("ELEVENLABS_MODEL", "eleven_v3").strip()
    if not api_key or not voice_id:
        raise RuntimeError("ElevenLabs voice is not configured")
    params = {"output_format": "mp3_22050_32"}
    if model.startswith("eleven_flash") or model.startswith("eleven_turbo"):
        params["optimize_streaming_latency"] = "3"
    payload = {
        "text": urdu_for_tts(text), "model_id": model, "language_code": "ur",
        "voice_settings": {
            "stability": 0.58, "similarity_boost": 0.78, "style": 0.18,
            "use_speaker_boost": True, "speed": 1.04,
        },
    }
    request = _speech_client().build_request(
        "POST", f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream",
        params=params, headers={"xi-api-key": api_key, "Content-Type": "application/json"}, json=payload,
    )
    response = None
    try:
        response = await _speech_client().send(request, stream=True)
        response.raise_for_status()
        return response
    except httpx.HTTPError as exc:
        if response is not None:
            await response.aclose()
        raise RuntimeError("Fatima's ElevenLabs voice is temporarily unavailable") from exc


def transcribe_local(audio: bytes, suffix: str = ".webm") -> str:
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as handle:
        handle.write(audio)
        path = Path(handle.name)
    try:
        worker = subprocess.run(
            [sys.executable, "-m", "app.whisper_worker", str(path), MODEL],
            cwd=Path(__file__).resolve().parent.parent,
            capture_output=True,
            text=True,
            timeout=180,
            start_new_session=True,
        )
        if worker.returncode != 0:
            detail = worker.stderr.strip().splitlines()
            reason = detail[-1] if detail else "Local speech worker failed"
            raise RuntimeError(
                f"Speech worker could not start: {reason}. Run the server from Cursor Terminal on the Mac."
            )
        return json.loads(worker.stdout)["text"].strip()
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Speech transcription timed out on first model load. Please try again.") from exc
    finally:
        path.unlink(missing_ok=True)
