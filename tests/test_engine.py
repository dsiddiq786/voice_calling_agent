from datetime import datetime

from app.engine import apply_message, greeting
from app.menu import MENU
from app.models import Session


def test_time_aware_greetings():
    assert "Subah bakhair" in greeting(now=datetime(2026, 1, 1, 9))
    assert "Shaam bakhair" in greeting(now=datetime(2026, 1, 1, 19))
    assert "Nom Nosh call karne ka shukriya" in greeting(now=datetime(2026, 1, 1, 14))
    assert "Main Fatima hoon" in greeting(now=datetime(2026, 1, 1, 14))


def test_adds_multiple_items_and_quantities():
    session = Session(id="test")
    session, created = apply_message(session, "do spicy burger aur aik soft drink")
    assert not created
    assert [(row.item_id, row.quantity) for row in session.cart] == [
        ("spice_burger", 2), ("soft_drink", 1)
    ]
    assert session.total == 810


def test_confirmation_creates_order_signal():
    session = Session(id="test")
    session, _ = apply_message(session, "aik deal one")
    session, created = apply_message(session, "bas")
    assert session.state == "confirming"
    assert not created
    session, created = apply_message(session, "haan confirm")
    assert session.state == "completed"
    assert created
    assert "Allah Hafiz" in session.last_reply


def test_unknown_items_never_enter_cart():
    session = Session(id="test")
    session, _ = apply_message(session, "aik imaginary burger")
    assert session.cart == []
    assert "exact item available menu mein listed nahi" in session.last_reply
    assert "Burgers" in session.last_reply


def test_unintelligible_input_gets_short_human_clarification():
    session = Session(id="test")
    session, _ = apply_message(session, "random distorted transcription")
    assert session.last_reply == "Sorry jee, last part miss ho gaya. Item ka naam aik dafa dobara bol dein?"
    assert "menu" not in session.last_reply.casefold()


def test_hello_starts_a_normal_conversation():
    session = Session(id="test")
    session, created = apply_message(session, "hello")
    assert not created
    assert "Main Fatima hoon" in session.last_reply
    assert session.cart == []


def test_suggestion_can_be_accepted_in_next_turn():
    session = Session(id="test")
    session, _ = apply_message(session, "mujhe kuch spicy suggest karo")
    assert "Spice Burger" in session.last_reply
    assert session.cart == []
    session, _ = apply_message(session, "theek hai woh add kar do")
    assert session.cart[0].item_id == "spice_burger"


def test_budget_suggestion_stays_within_budget():
    session = Session(id="test")
    session, _ = apply_message(session, "700 rupay tak kya acha suggest karein gi")
    suggested = MENU.items[session.last_suggested_item_id]
    assert suggested.price <= 700


def test_menu_question_lists_categories_instead_of_repeating_error():
    session = Session(id="test")
    session, _ = apply_message(session, "menu kya hai")
    assert "burgers" in session.last_reply
    assert "wraps" in session.last_reply


def test_bare_category_lists_real_items_and_prices():
    session = Session(id="test")
    session, _ = apply_message(session, "burger")
    assert "Nom Max Burger" in session.last_reply
    assert "480 rupay" in session.last_reply


def test_real_website_veggie_pizza_can_be_ordered():
    session = Session(id="test")
    session, _ = apply_message(session, "veggie pizza")
    assert session.cart[0].item_id == "veggie_lover"


def test_urdu_generic_pizza_order_lists_real_pizza_option():
    session = Session(id="test")
    session, _ = apply_message(session, "جی میں پیزا آرڈر کرنا چاہوں گا")
    assert "Chicken Fajita" in session.last_reply
    assert "Maazrat" not in session.last_reply


def test_urdu_open_ended_food_request_gets_menu_based_suggestion():
    session = Session(id="test")
    session, _ = apply_message(session, "مجھے کچھ کھانا ہے آپ بتائیں")
    assert "Grilled Chicken Burger" in session.last_reply
    assert session.last_suggested_item_id == "grilled_chicken_burger"


def test_pizza_suggestion_uses_real_pizza_deal_and_contents():
    session = Session(id="test")
    session, _ = apply_message(session, "pizza mein kuch suggest karein")
    assert "Deal 3" in session.last_reply
    assert "Medium Regular Flavor Pizza" in session.last_reply


def test_removes_known_item():
    session = Session(id="test")
    session, _ = apply_message(session, "do spicy burger")
    session, _ = apply_message(session, "spicy burger hatao")
    assert session.cart == []
