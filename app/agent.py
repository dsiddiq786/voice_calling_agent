import json
import os
import re
import time
from pathlib import Path
from typing import Optional, Tuple

import httpx
from dotenv import load_dotenv

from .engine import apply_message
from .menu import MENU, normalize
from .models import CartItem, Session


ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


class AgentUnavailable(RuntimeError):
    """Raised when an explicitly configured LLM cannot serve the turn."""


def llm_available() -> bool:
    return bool(os.getenv("OPENAI_API_KEY", "").strip())


def _menu_context(query: str = "", session: Optional[Session] = None) -> str:
    """Keep expensive LLM context to the relevant menu slice."""
    lowered = normalize(query)
    category_words = {
        "pizza": "Pizzas", "burger": "Burgers", "wrap": "Wraps & Rolls", "roll": "Wraps & Rolls",
        "deal": "Super Deals", "drink": "Beverages", "platter": "Platters", "pasta": "Pastas",
        "sandwich": "Sandwiches", "fries": "Fried Cravings", "wings": "Fried Cravings",
    }
    categories = {category for word, category in category_words.items() if word in lowered}
    selected_ids = {row.item_id for row in (session.cart if session else [])}
    if session:
        upgrade = _value_upgrade(session)
        if upgrade:
            selected_ids.add(upgrade["deal_id"])
    if session and session.last_suggested_item_id:
        selected_ids.add(session.last_suggested_item_id)
    for item in MENU.items.values():
        aliases = " ".join(item.aliases).casefold()
        if item.id in lowered or item.name.casefold() in lowered or any(word in lowered for word in aliases.split() if len(word) > 3):
            selected_ids.add(item.id)
    selected = [item for item in MENU.items.values() if item.id in selected_ids or item.category in categories]
    if not selected:
        return "MENU CATEGORIES: " + ", ".join(sorted({item.category for item in MENU.items.values()}))
    rows = []
    for item in selected[:16]:
        contents = f" | contains: {', '.join(item.details)}" if item.details else ""
        price = f"from {item.price}" if item.price_from else str(item.price)
        rows.append(f"{item.id} | {item.name} | Rs {price} | {item.category}{contents}")
    return "\n".join(rows)


def _value_upgrade(session: Session) -> Optional[dict]:
    """Deterministic money-saving check; the LLM must not guess deal maths."""
    quantities = {row.item_id: row.quantity for row in session.cart}
    offers = (
        ("deal_1", ("nom_max_burger", "french_fries", "soft_drink")),
        ("deal_2", ("spice_burger", "french_fries", "soft_drink")),
    )
    for deal_id, components in offers:
        if all(quantities.get(component, 0) >= 1 for component in components):
            separate = sum(MENU.items[component].price for component in components)
            deal = MENU.items[deal_id]
            if separate > deal.price:
                return {"deal_id": deal_id, "deal_name": deal.name, "separate": separate, "deal_price": deal.price, "saving": separate - deal.price, "remove_ids": list(components)}
    return None


TURN_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "reply": {"type": "string"},
        "spoken_reply": {"type": "string"},
        "customer_phone": {"type": ["string", "null"]},
        "delivery_address": {"type": ["string", "null"]},
        "remove_item_ids": {
            "type": "array",
            "items": {"type": "string"},
        },
        "end_call": {"type": "boolean"},
        "saved_address_choice": {"type": "string", "enum": ["none", "yes", "no"]},
        "action": {
            "type": "string",
            "enum": ["none", "add", "remove", "request_confirm", "confirm", "cancel"],
        },
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "id": {"type": "string"},
                    "quantity": {"type": "integer", "minimum": 1, "maximum": 20},
                    "notes": {"type": "string"},
                },
                "required": ["id", "quantity", "notes"],
            },
        },
        "suggested_item_id": {"type": ["string", "null"]},
    },
    "required": ["reply", "spoken_reply", "customer_phone", "delivery_address", "remove_item_ids", "end_call", "saved_address_choice", "action", "items", "suggested_item_id"],
}


def _instructions(menu_context: str) -> str:
    return f"""
You are Fatima, a warm, quick, genuinely human-sounding order taker at Nom Nosh Sahiwal.
Customers speak Urdu script, Roman Urdu, Punjabi-influenced Urdu, or mixed English.

STYLE
- Reply in natural conversational Roman Urdu by default, normally 1-2 short sentences suitable for speech.
- If the customer speaks mainly English, reply in simple natural English. Understand Urdu script and Punjabi-influenced Urdu, but keep the reply easy for a Pakistani caller.
- reply is the text shown on screen. spoken_reply must express the identical message in natural Urdu script for the voice engine.
- spoken_reply must use Urdu-script transliterations for product names and actions. Do not leave Latin words such as add, final, confirm, deal, burger, pizza, or drink in spoken_reply.
- Never dump a long menu. Ask one useful preference, then suggest at most 2-3 relevant choices.
- Sound attentive: acknowledge what the customer meant before asking the next question.
- Avoid repetitive phrases, corporate language, and robotic lists.
- Use easy-to-pronounce wording and punctuation. Prefer 8-14 words per sentence.
- Speak like a friendly Pakistani restaurant order taker, not a formal IVR. Prefer everyday acknowledgements such as "sahi hai", "theek", "haan ji", "acha", "done", "chalein", and "bas". Vary them naturally.
- Do not begin consecutive replies with "jee bilkul", "zaroor jee", "aik lamha", or "bohat acha". Use those only when they genuinely fit.
- For an immediate acknowledgement while checking a price/tool, say something short and human such as "haan, check karti hoon", "sahi, total nikalti hoon", or "theek, dekhti hoon"—never a robotic filler.
- Say product details conversationally. Do not sound like a database, advertisement, or written menu.
- Never mix English filler such as "starting from" into Roman Urdu; say "qeemat ... rupay se shuru hoti hai".
- Use respectful gender-neutral Urdu by default. Never guess gender from a name or voice.
- If the customer explicitly says how they want to be addressed, naturally follow that preference.
- Act like an experienced Sahiwal order taker: relaxed, confident, helpful, and quick—not a questionnaire.
- Infer obvious references from recent context. If the customer says "yeh wali", "wohi", or "fries drink wali", choose the uniquely matching last option instead of repeating choices.
- Give one confident recommendation with a human reason. Example: "Nom Max pasand aya hai to Deal 1 behtar rahegi—fries aur drink bhi aa jaye gi."
- Never ask another taste question when the caller already supplied a useful preference such as filling, spicy, light, budget, or number of people.
- Burger guidance: filling -> recommend only Nom D Max Burger; grilled/lighter -> Grilled Chicken Burger; spicy budget -> Spice Burger.
- Value upgrade: Nom Max Burger -> Deal 1; Spice Burger -> Deal 2. Explain once that fries and a drink are included, then let the customer decide.
- Before asking for delivery details or confirmation, obey VALUE SAVING CHECK if supplied. Offer that deal once, stating its exact saving. Do not silently replace the cart: wait for the caller's approval. If approved, add the deal and remove exactly the listed standalone items.
- When exactly one catalog option fits the caller's words and recent context, recommend or select it directly instead of presenting alternatives.
- Do not ask permission twice. Once the customer clearly chooses an item, add it and move forward.
- If the cart is non-empty and the caller says a natural confirmation such as "yeh order kar dein", "bas please", "confirm kar dein", or "order kar do", treat it as a request to complete the current order. Ask only for the one missing delivery detail, if any.
- If the caller is already in the confirmation state and says any of those natural confirmations, set action=confirm. Do not make them repeat a formal phrase.
- Upsell at most once per order, only when genuinely useful. Never pressure, deceive, create fake scarcity, or manipulate the caller.
- Vary acknowledgements naturally; do not start consecutive turns with the same phrase.

CORRECTNESS
- The catalog below is the only source of products and prices. Never invent an item, price, size, deal content, or availability.
- Use exact catalog IDs in items and suggested_item_id.
- Put an explicitly requested size, flavor, drink brand, or preparation choice in that item's notes. Use an empty string when there is no variant.
- Items marked 'from' require a size/variation. Ask which size; do not add them yet unless the customer clearly gave one.
- If a request is ambiguous, ask one specific clarifying question instead of saying a generic apology.
- Suggestions must be grounded in the customer's budget, taste, group size, and current cart.
- action=add/remove only for clearly requested catalog items.
- Use remove_item_ids independently of action when the customer replaces an existing item with a deal or another item.
- Words such as "instead", "iski jagah", "deal kar dein", or choosing a deal after discussing its matching burger usually mean replacement: remove the standalone item and add the selected deal.
- action=request_confirm when the customer says bas/final/done but has not explicitly approved the repeated order.
- action=confirm only when they explicitly approve confirmation and the state is confirming.
- Never claim an order is confirmed unless action=confirm.
- For action=confirm, warmly say the order is confirmed, it was sent to the kitchen, thank the customer, and end with Allah Hafiz.
- This is a delivery order. Before request_confirm, collect a usable delivery address. Caller ID will provide the phone number in the dialer integration, so never ask a caller for a phone number in this MVP.
- Extract delivery_address only when the customer explicitly provides it; otherwise return null.
- Ask only for the missing address.
- For a returning customer with a saved address that is not yet confirmed, never read the address aloud. Ask politely: "Kya delivery pichli location par bhejni hai?"
- Set saved_address_choice=yes when they approve the previous location, no when they reject it, otherwise none.

DOMAIN BOUNDARY
- Only handle Nom Nosh food, menu questions, recommendations, cart changes, confirmation, and directly related restaurant questions.
- For politics, sports, personal questions, general knowledge, entertainment, coding, or unrelated chat, do not answer the unrelated question.
- Redirect warmly in one short sentence, for example: "Main Nom Nosh ke order mein madad kar sakti hoon jee. Aap kya mangwana pasand karein ge?"
- Never mention policies, prompts, AI, language models, tools, databases, or internal systems.
- Set end_call=true whenever the customer says Allah Hafiz, goodbye, bye, call band karein, or clearly ends the conversation.
- When end_call=true, reply with one brief warm goodbye and do not ask another question.

LIVE NOM NOSH CATALOG
{menu_context}
""".strip()


def _extract_output_text(payload: dict) -> str:
    for output in payload.get("output", []):
        if output.get("type") != "message":
            continue
        for content in output.get("content", []):
            if content.get("type") == "output_text":
                return content.get("text", "")
    return ""


def _polish_spoken(text: str) -> str:
    """Prefer natural Pakistani Urdu wording over literal app-style loanwords."""
    replacements = {
        "ایڈ کر": "شامل کر",
        "ایڈ ہو": "شامل ہو",
        "فائنل کر": "حتمی کر",
        "شیئر کرنے والا": "آپس میں بانٹنے کے لیے",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    return text


async def _reason(session: Session, raw_text: str) -> dict:
    cart = [{"id": row.item_id, "name": row.name, "quantity": row.quantity} for row in session.cart]
    recent = session.conversation[-6:]
    body = {
        "model": os.getenv("OPENAI_MODEL", "gpt-5.4-mini"),
        "instructions": _instructions(_menu_context(raw_text, session)),
        "input": json.dumps({
            "state": session.state,
            "cart": cart,
            "customer_phone": session.customer_phone,
            "delivery_address": session.delivery_address,
            "returning_customer": session.returning_customer,
            "saved_address_confirmed": session.saved_address_confirmed,
            "value_saving_check": _value_upgrade(session),
            "recent_conversation": recent,
            "customer_said": raw_text,
        }, ensure_ascii=False),
        "reasoning": {"effort": "none"},
        "max_output_tokens": 180,
        "text": {"format": {"type": "json_schema", "name": "order_turn", "strict": True, "schema": TURN_SCHEMA}},
    }
    headers = {
        "Authorization": f"Bearer {os.environ['OPENAI_API_KEY'].strip()}",
        "Content-Type": "application/json",
    }
    timeout = httpx.Timeout(10.0, connect=5.0)
    started = time.perf_counter()
    response = await _openai_client().post("https://api.openai.com/v1/responses", headers=headers, json=body)
    session.llm_response_ms.append((time.perf_counter() - started) * 1000)
    session.llm_response_ms = session.llm_response_ms[-30:]
    response.raise_for_status()
    payload = response.json()
    usage = payload.get("usage", {})
    session.openai_input_tokens += int(usage.get("input_tokens", 0) or 0)
    session.openai_output_tokens += int(usage.get("output_tokens", 0) or 0)
    session.llm_turns += 1
    return json.loads(_extract_output_text(payload))


_OPENAI_CLIENT: Optional[httpx.AsyncClient] = None


def _openai_client() -> httpx.AsyncClient:
    global _OPENAI_CLIENT
    if _OPENAI_CLIENT is None:
        _OPENAI_CLIENT = httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=5.0))
    return _OPENAI_CLIENT


def _normalize_phone(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    value = value.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))
    digits = "".join(character for character in value if character.isdigit())
    if not digits:
        # Customers naturally dictate Pakistani numbers as words; do not make
        # an LLM guess them. This recognises Urdu, Roman Urdu and English.
        normalized_words = value.casefold()
        for source, replacement in (("تیزیرو", "three zero"), ("ونتی", "one three"), ("تین زیرو", "three zero")):
            normalized_words = normalized_words.replace(source, replacement)
        words = re.findall(r"[a-z]+|[\u0600-\u06ff]+|\d+", normalized_words)
        spoken_digits = {
            "zero": "0", "oh": "0", "o": "0", "زیرو": "0", "صفر": "0", "او": "0",
            "one": "1", "won": "1", "ایک": "1", "ون": "1",
            "two": "2", "to": "2", "دو": "2", "ٹو": "2",
            "three": "3", "teen": "3", "تین": "3", "تری": "3",
            "four": "4", "char": "4", "chaar": "4", "چار": "4", "فور": "4",
            "five": "5", "paanch": "5", "پانچ": "5", "فائیو": "5",
            "six": "6", "chay": "6", "چھ": "6", "سکس": "6",
            "seven": "7", "saat": "7", "سات": "7", "سیون": "7",
            "eight": "8", "aath": "8", "آٹھ": "8", "ایٹ": "8",
            "nine": "9", "no": "9", "نو": "9", "نائن": "9",
        }
        digits = "".join(spoken_digits.get(word, word if word.isdigit() else "") for word in words)
    if digits.startswith("92") and len(digits) == 12:
        digits = "0" + digits[2:]
    return digits if len(digits) == 11 and digits.startswith("03") else None


def _mutate(session: Session, turn: dict) -> bool:
    phone = _normalize_phone(turn.get("customer_phone"))
    address = (turn.get("delivery_address") or "").strip()
    saved_choice = turn.get("saved_address_choice", "none")
    if phone:
        session.customer_phone = phone
    if len(address) >= 6:
        session.delivery_address = address
        session.saved_address_confirmed = True
    elif saved_choice == "yes" and session.delivery_address:
        session.saved_address_confirmed = True
    elif saved_choice == "no":
        session.delivery_address = None
        session.saved_address_confirmed = False
    action = turn["action"]
    valid = [(MENU.items[row["id"]], row["quantity"], row.get("notes", "").strip()) for row in turn["items"] if row["id"] in MENU.items]
    remove_ids = {item_id for item_id in turn.get("remove_item_ids", []) if item_id in MENU.items}
    if remove_ids:
        session.cart = [row for row in session.cart if row.item_id not in remove_ids]
    if action == "add":
        for item, quantity, notes in valid:
            existing = next((row for row in session.cart if row.item_id == item.id), None)
            if existing:
                existing.quantity += quantity
                if notes:
                    existing.notes = notes
            else:
                session.cart.append(CartItem(item_id=item.id, name=item.name, quantity=quantity, unit_price=item.price, notes=notes))
    elif action == "remove":
        ids = {item.id for item, _, _ in valid}
        session.cart = [row for row in session.cart if row.item_id not in ids]
    elif action == "request_confirm" and session.cart and session.delivery_address and (not session.returning_customer or session.saved_address_confirmed):
        session.state = "confirming"
    elif action == "cancel":
        session.state = "ordering"
    elif action == "confirm" and session.state == "confirming" and session.cart and session.delivery_address and (not session.returning_customer or session.saved_address_confirmed):
        session.state = "completed"
        return True
    suggested = turn.get("suggested_item_id")
    session.last_suggested_item_id = suggested if suggested in MENU.items else None
    return False


async def apply_agent_message(session: Session, raw_text: str) -> Tuple[Session, bool]:
    if not llm_available():
        return apply_message(session, raw_text)
    # A named menu item is not a reasoning task. Routing these turns through
    # the deterministic menu engine removes an LLM round trip and its cost.
    normalized = normalize(raw_text)
    exact_items = MENU.match_all(normalized)
    conversational_intent = any(word in normalized for word in (
        "suggest", "recommend", "deal", "cheaper", "budget", "address", "confirm", "bas", "final",
        "سجیسٹ", "مشورہ", "پتہ", "کنفرم", "بچ", "ڈیل",
    ))
    if exact_items and not conversational_intent:
        session, created = apply_message(session, raw_text)
        session.last_spoken_reply = session.last_reply
        upgrade = _value_upgrade(session)
        if upgrade and session.offered_value_deal_id != upgrade["deal_id"]:
            session.offered_value_deal_id = upgrade["deal_id"]
            session.last_reply = (
                f"Aik behtar option hai jee: {upgrade['deal_name']} Rs {upgrade['deal_price']} ki hai. "
                f"Aap Rs {upgrade['saving']} bacha lein ge. Deal kar doon?"
            )
            session.last_spoken_reply = session.last_reply
        session.conversation.extend([f"Customer: {raw_text}", f"Fatima: {session.last_reply}"])
        session.conversation = session.conversation[-12:]
        return session, created
    try:
        dictated_phone = _normalize_phone(raw_text)
        turn = await _reason(session, raw_text)
        created = _mutate(session, turn)
        if dictated_phone:
            session.customer_phone = dictated_phone
        session.last_reply = turn["reply"].strip()
        session.last_spoken_reply = _polish_spoken(turn["spoken_reply"].strip())
        session.end_call_requested = bool(turn.get("end_call"))
        upgrade = _value_upgrade(session)
        if turn["action"] == "add" and upgrade and session.offered_value_deal_id != upgrade["deal_id"]:
            session.offered_value_deal_id = upgrade["deal_id"]
            session.last_reply = (
                f"Aik behtar option hai jee: {upgrade['deal_name']} Rs {upgrade['deal_price']} ki hai. "
                f"Isi burger, regular fries aur drink ka alag total Rs {upgrade['separate']} banta hai—"
                f"aap Rs {upgrade['saving']} bacha lein ge. Deal kar doon?"
            )
            session.last_spoken_reply = (
                f"ایک بہتر آپشن ہے جی۔ ڈیل {upgrade['deal_name'].split()[-1]}، {upgrade['deal_price']} روپے کی ہے۔ "
                f"اسی برگر، ریگولر فرائز اور ڈرنک میں {upgrade['saving']} روپے بچ جائیں گے۔ ڈیل کر دوں؟"
            )
        if session.cart and turn["action"] in {"request_confirm", "confirm"} and not session.delivery_address:
            session.state = "ordering"
            session.last_reply = "Shukriya jee. Ab delivery ka mukammal address bata dein."
            session.last_spoken_reply = "شکریہ جی۔ اب ڈیلیوری کا مکمل پتہ بتا دیں۔"
        elif session.cart and turn["action"] in {"request_confirm", "confirm"} and session.returning_customer and not session.saved_address_confirmed:
            session.state = "ordering"
            session.last_reply = "Jee, kya delivery pichli location par bhejni hai?"
            session.last_spoken_reply = "جی، کیا ڈیلیوری پچھلی لوکیشن پر بھیجنی ہے؟"
        elif session.state == "confirming":
            summary = ", ".join(
                f"{item.quantity} {item.name}{f' ({item.notes})' if item.notes else ''}"
                for item in session.cart
            )
            session.last_reply = (
                f"Theek jee, order repeat kar doon: {summary}. Total {session.total} rupay. "
                "Sab theek hai, confirm kar doon?"
            )
            session.last_spoken_reply = session.last_reply
        if created:
            session.last_reply = "Perfect jee, order confirm ho gaya. Kitchen ko bhej diya hai. Bohat shukriya, Allah Hafiz!"
            session.last_spoken_reply = "پرفیکٹ جی، آرڈر کنفرم ہو گیا۔ کچن کو بھیج دیا ہے۔ بہت شکریہ، اللہ حافظ!"
        session.conversation.extend([f"Customer: {raw_text}", f"Fatima: {session.last_reply}"])
        session.conversation = session.conversation[-12:]
        return session, created
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 429:
            raise AgentUnavailable(
                "OpenAI API quota is unavailable. Enable API billing or add credits, then retry."
            ) from exc
        raise AgentUnavailable("OpenAI could not serve this conversation turn.") from exc
    except (httpx.HTTPError, KeyError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise AgentUnavailable("OpenAI could not serve this conversation turn.") from exc
