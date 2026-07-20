import re
from datetime import datetime
from typing import List, Tuple
from zoneinfo import ZoneInfo

from .menu import MENU, MenuItem, normalize
from .models import CartItem, Session


NUMBER_WORDS = {
    "aik": 1, "ek": 1, "one": 1, "ایک": 1,
    "do": 2, "two": 2, "دو": 2,
    "teen": 3, "three": 3, "تین": 3,
    "char": 4, "chaar": 4, "four": 4, "چار": 4,
    "panch": 5, "five": 5, "پانچ": 5,
    "chay": 6, "six": 6, "چھ": 6,
}

CONFIRM_WORDS = {"han", "haan", "yes", "confirm", "theek", "ok", "okay", "جی", "ہاں", "ٹھیک", "کنفرم"}
CANCEL_WORDS = {"nahi", "nahin", "no", "cancel", "change", "نہیں", "کینسل", "تبدیل"}
DONE_PHRASES = ("bas", "bus", "itna", "confirm", "order complete", "بس", "اتنا", "کنفرم")
GREETING_WORDS = {
    "hi", "hello", "hey", "hy", "salam", "salaam", "assalamualaikum",
    "assalam o alaikum", "assalam alaikum", "asalamu alaikum", "اسلام علیکم", "السلام علیکم", "ہیلو"
}
SUGGESTION_PHRASES = (
    "suggest", "recommend", "kya acha", "kya accha", "kya mangwaun",
    "kya order", "help me", "madad", "samajh nahi", "kuch khana", "bhook",
    "aap bata", "مشورہ", "کیا اچھا", "کیا لوں", "کیا کھاؤں", "آپ بتائیں",
    "کچھ کھانا", "بھوک", "سجیسٹ", "سجیسٹ کریں", "تجویز", "مشورہ دیں"
)
ACCEPT_SUGGESTION_PHRASES = (
    "add kar do", "yehi", "yahi", "woh add", "wo add", "theek hai woh",
    "ٹھیک ہے", "یہی", "ایڈ کر"
)
MENU_WORDS = (
    "menu", "options", "available", "kya kya", "dikhao", "batao",
    "مینو", "کیا کیا", "آپشن", "آپشنز", "اویلیبل", "دستیاب", "کیا ہے"
)
CATEGORY_WORDS = {
    "burger": "Burgers", "burgers": "Burgers", "برگر": "Burgers",
    "wrap": "Wraps & Rolls", "roll": "Wraps & Rolls", "ریپ": "Wraps & Rolls", "رول": "Wraps & Rolls",
    "platter": "Platters", "پلیٹر": "Platters",
    "drink": "Beverages", "drinks": "Beverages", "beverage": "Beverages", "پینے": "Beverages",
    "deal": "Super Deals", "deals": "Super Deals", "ڈیل": "Super Deals",
    "pasta": "Pastas", "پاستا": "Pastas",
    "sandwich": "Sandwiches", "سینڈوچ": "Sandwiches",
    "fries": "Fried Cravings", "wings": "Fried Cravings", "فرائز": "Fried Cravings",
}


def greeting(name: str = "Fatima", now: datetime = None) -> str:
    now = now or datetime.now(ZoneInfo("Asia/Karachi"))
    if now.hour < 12:
        detail = "Subah bakhair. "
    elif now.hour >= 18:
        detail = "Shaam bakhair. "
    else:
        detail = ""
    return (
        f"Assalam-o-Alaikum! {detail}Nom Nosh call karne ka shukriya. "
        f"Main {name} hoon—jee, aaj kya mangwana pasand karein ge?"
    ).replace("  ", " ")


def quantity_before(text: str, alias: str) -> int:
    normalized = normalize(text)
    start = normalized.find(alias)
    prefix = normalized[max(0, start - 18):start].split()
    if not prefix:
        return 1
    token = prefix[-1]
    if token.isdigit():
        return max(1, min(20, int(token)))
    return NUMBER_WORDS.get(token, 1)


def cart_summary(session: Session) -> str:
    lines = [f"{item.quantity} {item.name}" for item in session.cart]
    joined = ", ".join(lines)
    return (
        f"Theek jee, aik dafa order repeat kar deti hoon: {joined}. "
        f"Total {session.total} rupay banta hai. Sab theek hai, confirm kar doon?"
    )


def natural_follow_up(item: MenuItem) -> str:
    if "Pizza" in item.category:
        return "Saath wings ya drink rakh doon?"
    if item.category == "Burgers":
        return "Saath fries ya drink lena pasand karein ge?"
    if item.category in {"Super Deals", "Delivery Deals", "Mega Nosh Deal"}:
        return "Aur kuch chahiye, ya isi ko final karein?"
    if item.category == "Beverages":
        return "Aur khane mein kya rakhna hai jee?"
    return "Aur kuch lena pasand karein ge?"


def recommendation(text: str) -> MenuItem:
    budget_match = re.search(r"(?:budget|under|tak|تک)\s*(?:rs\.?\s*)?(\d{2,5})", text)
    if not budget_match:
        budget_match = re.search(r"(\d{2,5})\s*(?:rupay|rupees|rs|روپے)", text)
    if budget_match:
        budget = int(budget_match.group(1))
        choices = [item for item in MENU.items.values() if item.price <= budget and item.category != "Beverage"]
        if choices:
            return max(choices, key=lambda item: item.price)
    if any(word in text for word in ("spicy", "teekha", "teekhi", "مرچ", "سپائسی")):
        return MENU.items["spice_burger"]
    if any(word in text for word in ("family", "sab ke liye", "زیادہ لوگ")):
        return MENU.items["deal_5"]
    if "pizza" in text or "پیزا" in text:
        return MENU.items["deal_3"]
    if any(word in text for word in ("deal", "offer", "value", "ڈیل")):
        return MENU.items["deal_2"]
    if any(word in text for word in ("light", "halka", "wrap", "ہلکا")):
        return MENU.items["arabic_roll"]
    if "burger" in text or "برگر" in text:
        return MENU.items["grilled_chicken_burger"]
    if any(word in text for word in ("drink", "cold drink", "pani", "ڈرنک", "پانی")):
        return MENU.items["soft_drink"]
    return MENU.items["grilled_chicken_burger"]


def format_options(items: List[MenuItem], limit: int = None) -> str:
    selected = items if limit is None else items[:limit]
    return ", ".join(
        f"{item.name}, {'starting from ' if item.price_from else ''}{item.price} rupay"
        for item in selected
    )


def describe_item(item: MenuItem) -> str:
    contents = ", ".join(item.details)
    if contents:
        return f"Main {item.name} suggest karoon gi. Is mein {contents} hain, aur price {item.price} rupay hai."
    return f"Main {item.name} suggest karoon gi. Is ki price {item.price} rupay hai."


def menu_help(text: str) -> str:
    if "pizza" in text or "پیزا" in text:
        choices = [
            MENU.items["chicken_fajita"], MENU.items["malai_boti_pizza"],
            MENU.items["crown_crust_pizza"],
        ]
        return (
            f"Jee, pizza mein popular options hain: {format_options(choices)}. "
            "Regular, chef special ya premium pizza mein se kya pasand karein ge?"
        )
    for word, category in CATEGORY_WORDS.items():
        if word in text:
            items = [item for item in MENU.items.values() if item.category == category]
            limit = None if any(term in text for term in ("all", "sab", "saray", "تمام", "سارے")) else 3
            more = max(0, len(items) - (limit or len(items)))
            tail = f" Aur {more} options bhi available hain." if more else ""
            return f"Jee, {category} mein {format_options(items, limit)}.{tail} In mein se kya pasand karein ge?"
    categories = ", ".join(MENU.categories())
    return (
        "Jee, hamare paas pizzas, burgers, deals, wraps, fried items, pasta, "
        "sandwiches aur drinks available hain. Aap kis mood mein hain?"
    )


def apply_message(session: Session, raw_text: str) -> Tuple[Session, bool]:
    text = normalize(raw_text)
    created_order = False

    if session.state == "completed":
        session.last_reply = "Yeh order pehle hi confirm ho chuka hai jee. Naya order shuru karne ke liye New Order dabayein."
        return session, False

    if session.state == "confirming":
        tokens = set(text.split())
        if tokens & CONFIRM_WORDS:
            session.state = "completed"
            session.last_reply = "Bohat shukriya jee! Aapka order kitchen ko bhej diya gaya hai. Allah Hafiz."
            return session, True
        if tokens & CANCEL_WORDS:
            session.state = "ordering"
            session.last_reply = "Bilkul jee, batayein order mein kya tabdeeli karni hai?"
            return session, False
        session.last_reply = "Maazrat jee, order confirm karna hai ya is mein tabdeeli karni hai?"
        return session, False

    if text in GREETING_WORDS or text.replace(" ", "") in {word.replace(" ", "") for word in GREETING_WORDS}:
        if session.cart:
            session.last_reply = "Jee jee, main sun rahi hoon. Batayein, aur kya rakhna hai?"
        else:
            session.last_reply = greeting()
        return session, False

    if session.last_suggested_item_id and any(phrase in text for phrase in ACCEPT_SUGGESTION_PHRASES):
        item = MENU.items[session.last_suggested_item_id]
        existing = next((row for row in session.cart if row.item_id == item.id), None)
        if existing:
            existing.quantity += 1
        else:
            session.cart.append(CartItem(item_id=item.id, name=item.name, quantity=1, unit_price=item.price))
        session.last_suggested_item_id = None
        session.last_reply = f"Perfect jee, aik {item.name} note kar liya. {natural_follow_up(item)}"
        return session, False

    is_menu_question = any(word in text for word in MENU_WORDS)
    is_bare_category = any(text == word for word in CATEGORY_WORDS)
    if is_menu_question or is_bare_category:
        session.last_reply = menu_help(text)
        return session, False

    if any(phrase in text for phrase in SUGGESTION_PHRASES):
        item = recommendation(text)
        session.last_suggested_item_id = item.id
        session.last_reply = (
            f"Jee, {describe_item(item)} "
            "Agar pasand hai to kahein, yehi add kar dein."
        )
        return session, False

    if any(word in text.split() for word in ("remove", "hatao", "hata", "nikal", "ہٹاؤ", "نکال")):
        matches = MENU.match_all(text)
        if matches:
            ids = {item.id for item, _ in matches}
            session.cart = [item for item in session.cart if item.item_id not in ids]
            session.last_reply = "Theek jee, woh item hata diya. Ab aur koi change karni hai?"
        else:
            session.last_reply = "Kaunsa item hatana hai jee?"
        return session, False

    matches = MENU.match_all(text)
    added: List[CartItem] = []
    for menu_item, alias in matches:
        quantity = quantity_before(text, alias)
        existing = next((row for row in session.cart if row.item_id == menu_item.id), None)
        if existing:
            existing.quantity += quantity
        else:
            cart_item = CartItem(
                item_id=menu_item.id, name=menu_item.name,
                quantity=quantity, unit_price=menu_item.price
            )
            session.cart.append(cart_item)
            added.append(cart_item)

    wants_done = any(phrase in text for phrase in DONE_PHRASES)
    if wants_done and session.cart:
        session.state = "confirming"
        session.last_reply = cart_summary(session)
    elif matches:
        names = ", ".join(f"{quantity_before(text, alias)} {item.name}" for item, alias in matches)
        last_item = matches[-1][0]
        session.last_reply = f"Bilkul jee, {names} note kar liya. {natural_follow_up(last_item)}"
    elif not session.cart:
        mentioned_category = next(
            (word for word in ("pizza", "پیزا", *CATEGORY_WORDS.keys()) if word in text),
            None,
        )
        if mentioned_category:
            if mentioned_category == "پیزا":
                session.last_reply = menu_help(mentioned_category)
            else:
                session.last_reply = (
                    "Yeh exact item available menu mein listed nahi hai jee. " + menu_help(mentioned_category)
                )
        else:
            session.last_reply = "Sorry jee, last part miss ho gaya. Item ka naam aik dafa dobara bol dein?"
    else:
        session.last_reply = "Jee, aur kuch add karna hai ya order confirm kar doon?"
    return session, created_order
