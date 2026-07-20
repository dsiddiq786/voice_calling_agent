import json
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Dict, List
from uuid import uuid4

from .models import Order, Session


ROOT = Path(__file__).resolve().parent.parent
ORDERS_PATH = ROOT / "data" / "orders.json"


class Store:
    def __init__(self) -> None:
        self.sessions: Dict[str, Session] = {}
        self.orders: Dict[str, Order] = {}
        self.lock = Lock()
        self._load_orders()

    def _load_orders(self) -> None:
        if ORDERS_PATH.exists():
            for raw in json.loads(ORDERS_PATH.read_text(encoding="utf-8")):
                order = Order.model_validate(raw)
                self.orders[order.id] = order

    def _save_orders(self) -> None:
        ORDERS_PATH.write_text(
            json.dumps([o.model_dump() for o in self.orders.values()], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def new_session(self, caller_phone: str = None) -> Session:
        previous = None
        if caller_phone:
            previous = next(
                (order for order in self.list_orders() if order.customer_phone == caller_phone and order.delivery_address),
                None,
            )
        session = Session(
            id=str(uuid4()),
            customer_phone=caller_phone if previous else None,
            delivery_address=previous.delivery_address if previous else None,
            returning_customer=bool(previous),
        )
        self.sessions[session.id] = session
        return session

    def get_session(self, session_id: str) -> Session:
        return self.sessions[session_id]

    def create_order(self, session: Session) -> Order:
        with self.lock:
            existing = next((o for o in self.orders.values() if o.session_id == session.id), None)
            if existing:
                return existing
            order = Order(
                id=f"NN-{str(uuid4())[:8].upper()}", session_id=session.id,
                customer_name=session.customer_name,
                customer_phone=session.customer_phone,
                delivery_address=session.delivery_address,
                items=session.cart,
                total=session.total, created_at=datetime.now(timezone.utc).isoformat()
            )
            self.orders[order.id] = order
            self._save_orders()
            return order

    def list_orders(self) -> List[Order]:
        return sorted(self.orders.values(), key=lambda item: item.created_at, reverse=True)

    def update_status(self, order_id: str, status: str) -> Order:
        with self.lock:
            order = self.orders[order_id]
            order.status = status
            self._save_orders()
            return order


STORE = Store()
