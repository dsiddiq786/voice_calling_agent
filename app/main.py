from pathlib import Path
from typing import Literal
import os

import httpx
from fastapi import FastAPI, File, HTTPException, UploadFile, WebSocket
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .agent import AgentUnavailable, apply_agent_message, llm_available
from .engine import greeting
from .live_speech import proxy_live_transcription
from .menu import MENU
from .models import CallMetricsRequest, CartItem, MessageRequest, RealtimeCartRequest, SessionCreateRequest
from .speech import (
    speech_provider,
    romanize_transcript,
    synthesize_speech as generate_speech,
    open_elevenlabs_stream,
    transcribe_deepgram,
    transcribe_local,
    tts_provider,
)
from .store import STORE


ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"
app = FastAPI(title="NomNosh Voice Order MVP", version="0.1.0")
app.mount("/static", StaticFiles(directory=STATIC), name="static")
NODE_MODULES = ROOT / "node_modules"
if NODE_MODULES.exists():
    # The browser SDK is served locally; the ElevenLabs secret never reaches it.
    app.mount("/vendor", StaticFiles(directory=NODE_MODULES), name="vendor")


@app.get("/")
def home():
    return FileResponse(STATIC / "index.html")


@app.get("/customer")
def customer():
    return FileResponse(STATIC / "customer.html")


@app.get("/dashboard")
def dashboard():
    return FileResponse(STATIC / "dashboard.html")


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "restaurant": MENU.restaurant["name"],
        "speech_to_text": speech_provider(),
        "text_to_speech": tts_provider(),
        "conversation_engine": "openai" if llm_available() else "rules",
    }


@app.get("/api/realtime/conversation-token")
async def realtime_conversation_token():
    """Mint a short-lived ElevenLabs token for the browser WebRTC session.

    This endpoint deliberately returns only the one-time conversation token. The
    ElevenLabs API key remains in .env on this machine.
    """
    api_key = os.getenv("ELEVENLABS_API_KEY")
    agent_id = os.getenv("ELEVENLABS_FATIMA_AGENT_ID")
    if not api_key or not agent_id:
        raise HTTPException(503, "Realtime Fatima is not configured yet")
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            response = await client.get(
                "https://api.elevenlabs.io/v1/convai/conversation/token",
                params={"agent_id": agent_id},
                headers={"xi-api-key": api_key},
            )
    except httpx.HTTPError as exc:
        raise HTTPException(503, "Could not reach the realtime voice service") from exc
    if response.status_code >= 300:
        raise HTTPException(503, "Realtime voice service rejected the session")
    token = response.json().get("token")
    if not token:
        raise HTTPException(503, "Realtime voice service returned no session token")
    return {"conversation_token": token}


@app.get("/api/menu")
def menu():
    return {"restaurant": MENU.restaurant, "items": [item.__dict__ for item in MENU.items.values()]}


@app.post("/api/sessions")
def create_session(request: SessionCreateRequest = None):
    session = STORE.new_session(request.caller_phone if request else None)
    session.last_reply = greeting()
    if session.returning_customer:
        session.last_reply = (
            "Assalam-o-Alaikum. Nom Nosh ko dobara call karne ka bohat shukriya. "
            "Fatima line par hazir hai—jee, aaj kya mangwana pasand karein ge?"
        )
    session.last_spoken_reply = session.last_reply
    return session


@app.post("/api/sessions/{session_id}/messages")
async def send_message(session_id: str, request: MessageRequest):
    try:
        session = STORE.get_session(session_id)
    except KeyError as exc:
        raise HTTPException(404, "Session not found") from exc
    try:
        session, should_create_order = await apply_agent_message(session, request.text)
    except AgentUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    order = STORE.create_order(session) if should_create_order else None
    return {"session": session, "order": order}


@app.post("/api/realtime/sessions/{session_id}/cart")
def realtime_cart_action(session_id: str, request: RealtimeCartRequest):
    """Small, deterministic tool surface for the realtime agent.

    The LLM never calculates money or mutates the cart itself; the browser's
    ElevenLabs client calls this local endpoint and returns the result to it.
    """
    try:
        session = STORE.get_session(session_id)
    except KeyError as exc:
        raise HTTPException(404, "Session not found") from exc

    if request.action == "summary":
        return {"ok": True, "cart": session.cart, "total": session.total, "delivery_address": session.delivery_address}
    if request.action == "set_delivery":
        if len(request.address.strip()) < 8:
            return {"ok": False, "message": "Address is too short; ask for house/building and area."}
        session.delivery_address = request.address.strip()
        return {"ok": True, "delivery_address": session.delivery_address, "total": session.total}
    if request.action == "confirm":
        if not session.cart:
            return {"ok": False, "message": "Cart is empty."}
        order = STORE.create_order(session)
        session.state = "completed"
        session.end_call_requested = True
        return {"ok": True, "order_id": order.id, "cart": session.cart, "total": session.total}

    matches = MENU.match_all(request.item_name)
    if not matches:
        return {"ok": False, "message": "No exact menu item matched.", "available_items": [item.name for item in MENU.items.values()]}
    item = matches[0][0]
    if request.action == "remove":
        before = len(session.cart)
        session.cart = [line for line in session.cart if line.item_id != item.id]
        return {"ok": before != len(session.cart), "cart": session.cart, "total": session.total, "removed": item.name}

    existing = next((line for line in session.cart if line.item_id == item.id), None)
    if existing:
        existing.quantity = min(20, existing.quantity + request.quantity)
    else:
        session.cart.append(CartItem(item_id=item.id, name=item.name, quantity=request.quantity, unit_price=item.price))
    return {"ok": True, "added": item.name, "cart": session.cart, "total": session.total}


@app.post("/api/sessions/{session_id}/call-summary")
def call_summary(session_id: str, metrics: CallMetricsRequest):
    try:
        session = STORE.get_session(session_id)
    except KeyError as exc:
        raise HTTPException(404, "Session not found") from exc
    # OpenAI's current gpt-5.4-mini list pricing: $0.75/M input, $4.50/M output.
    openai_cost = (session.openai_input_tokens * 0.75 + session.openai_output_tokens * 4.50) / 1_000_000
    browser_delay = sum(metrics.response_delays_ms) / len(metrics.response_delays_ms) if metrics.response_delays_ms else 0
    llm_delay = sum(session.llm_response_ms) / len(session.llm_response_ms) if session.llm_response_ms else 0
    return {
        "duration_seconds": round(metrics.duration_seconds, 1),
        "human_talk_seconds": round(metrics.human_talk_seconds, 1),
        "ai_talk_seconds": round(metrics.ai_talk_seconds, 1),
        "average_response_delay_ms": round(browser_delay or llm_delay),
        "llm_response_delay_ms": round(llm_delay),
        "openai": {"input_tokens": session.openai_input_tokens, "output_tokens": session.openai_output_tokens, "estimated_usd": round(openai_cost, 6)},
        # Provider plans differ, so report billable units rather than invent a price.
        "deepgram": {"audio_seconds": round(metrics.human_talk_seconds, 1)},
        "elevenlabs": {"characters": metrics.elevenlabs_characters},
        "known_estimated_usd": round(openai_cost, 6),
    }


@app.post("/api/transcribe")
async def transcribe_audio(audio: UploadFile = File(...)):
    raw = await audio.read()
    if len(raw) > 15_000_000:
        raise HTTPException(413, "Audio file is too large")
    suffix = Path(audio.filename or "audio.webm").suffix or ".webm"
    try:
        if speech_provider() == "deepgram":
            text = await transcribe_deepgram(raw, audio.content_type or "audio/webm")
        else:
            text = transcribe_local(raw, suffix)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    return {"text": text, "display_text": romanize_transcript(text)}


@app.websocket("/api/live-transcribe")
async def live_transcribe(websocket: WebSocket):
    await proxy_live_transcription(websocket)


@app.post("/api/synthesize")
async def synthesize_speech(request: MessageRequest):
    if not request.text.strip() or len(request.text) > 1000:
        raise HTTPException(400, "Speech text is invalid")
    try:
        if tts_provider() == "elevenlabs":
            upstream = await open_elevenlabs_stream(request.text.strip())

            async def chunks():
                try:
                    async for chunk in upstream.aiter_bytes():
                        yield chunk
                finally:
                    await upstream.aclose()

            return StreamingResponse(chunks(), media_type="audio/mpeg", headers={"X-TTS-Provider": "elevenlabs"})
        audio = await generate_speech(request.text.strip())
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    return Response(content=audio, media_type="audio/mpeg")


@app.get("/api/orders")
def list_orders():
    return STORE.list_orders()


@app.patch("/api/orders/{order_id}/status")
def update_order_status(order_id: str, status: Literal["new", "accepted", "preparing", "ready", "completed"]):
    try:
        return STORE.update_status(order_id, status)
    except KeyError as exc:
        raise HTTPException(404, "Order not found") from exc
