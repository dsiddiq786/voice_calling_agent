from fastapi.testclient import TestClient

from app.main import app
from app.store import STORE


client = TestClient(app)


def test_complete_order_flow(monkeypatch):
    # Unit tests must not consume or depend on a developer's live API quota.
    monkeypatch.setenv("OPENAI_API_KEY", "")
    original_order_ids = set(STORE.orders)
    session = client.post("/api/sessions").json()
    response = client.post(
        f"/api/sessions/{session['id']}/messages",
        json={"text": "do spicy burger aur aik small water"},
    )
    assert response.status_code == 200
    assert response.json()["session"]["total"] == 780
    client.post(f"/api/sessions/{session['id']}/messages", json={"text": "bas"})
    confirmed = client.post(
        f"/api/sessions/{session['id']}/messages", json={"text": "haan confirm"}
    ).json()
    assert confirmed["order"]["total"] == 780
    for order_id in set(STORE.orders) - original_order_ids:
        del STORE.orders[order_id]
    STORE._save_orders()
