import asyncio
import json
import os
from urllib.parse import urlencode

import websockets
from fastapi import WebSocket, WebSocketDisconnect

from .speech import romanize_transcript
from .menu import MENU


BASE_KEYTERMS = (
    "NomNosh", "Fatima", "Nom Max Burger", "Deal One", "Deal Two",
    "Deal Three", "Malai Boti Pizza", "Chicken Fajita", "Chicken Tikka",
    "Spice Burger", "Grilled Chicken Burger", "Farid Town", "Sahiwal",
)


def _keyterms() -> tuple[str, ...]:
    """Bias recognition toward every real catalog term, not only a few demos."""
    catalog = tuple(item.name for item in MENU.items.values())
    conversational = (
        "order confirm kar dein", "confirm kar do", "yeh order kar dein",
        "bas please", "Allah Hafiz", "delivery address", "mobile number",
        "half litre", "one and a half litre", "large", "medium", "regular",
    )
    return tuple(dict.fromkeys(BASE_KEYTERMS + catalog + conversational))


async def proxy_live_transcription(browser: WebSocket) -> None:
    key = os.getenv("DEEPGRAM_API_KEY", "").strip()
    await browser.accept()
    if not key:
        await browser.send_json({"type": "error", "message": "Deepgram is not configured"})
        await browser.close(code=1011)
        return
    params = [
        ("model", "nova-3"), ("language", "ur"), ("smart_format", "true"),
        ("punctuate", "true"), ("interim_results", "true"),
        # 600ms avoids cutting off natural Urdu pauses while remaining fast.
        ("endpointing", "600"), ("vad_events", "true"),
    ] + [("keyterm", term) for term in _keyterms()]
    url = f"wss://api.deepgram.com/v1/listen?{urlencode(params)}"
    try:
        async with websockets.connect(
            url,
            additional_headers={"Authorization": f"Token {key}"},
            ping_interval=10,
            ping_timeout=10,
        ) as deepgram:
            final_parts = []
            latest_transcript = ""

            async def send_audio() -> None:
                while True:
                    message = await browser.receive()
                    if message.get("bytes"):
                        await deepgram.send(message["bytes"])
                    elif message.get("text"):
                        await deepgram.send(message["text"])
                    elif message.get("type") == "websocket.disconnect":
                        return

            async def receive_text() -> None:
                async for raw in deepgram:
                    if not isinstance(raw, str):
                        continue
                    payload = json.loads(raw)
                    if payload.get("type") != "Results":
                        continue
                    alternative = payload.get("channel", {}).get("alternatives", [{}])[0]
                    transcript = alternative.get("transcript", "").strip()
                    if transcript:
                        latest_transcript = transcript
                    if transcript and payload.get("is_final"):
                        # Deepgram can re-send the final phrase. Keep one copy.
                        if not final_parts or final_parts[-1] != transcript:
                            final_parts.append(transcript)
                    if transcript:
                        await browser.send_json({
                            "type": "interim",
                            "text": " ".join(final_parts) if final_parts else transcript,
                        })
                    if payload.get("speech_final") and (final_parts or latest_transcript):
                        text = " ".join(final_parts).strip() or latest_transcript
                        await browser.send_json({
                            "type": "final",
                            "text": text,
                            "display_text": romanize_transcript(text),
                        })
                        final_parts.clear()
                        latest_transcript = ""

            tasks = {asyncio.create_task(send_audio()), asyncio.create_task(receive_text())}
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            for task in done:
                task.result()
    except (WebSocketDisconnect, websockets.WebSocketException, OSError, ValueError, KeyError):
        try:
            await browser.send_json({"type": "error", "message": "Live transcription disconnected"})
        except Exception:
            pass
