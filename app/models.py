from typing import List, Literal, Optional

from pydantic import BaseModel, Field, computed_field


class CartItem(BaseModel):
    item_id: str
    name: str
    quantity: int = Field(ge=1, le=20)
    unit_price: int
    notes: str = ""

    @computed_field
    @property
    def line_total(self) -> int:
        return self.quantity * self.unit_price


class Session(BaseModel):
    id: str
    state: Literal["ordering", "confirming", "completed"] = "ordering"
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    delivery_address: Optional[str] = None
    returning_customer: bool = False
    saved_address_confirmed: bool = False
    last_suggested_item_id: Optional[str] = None
    cart: List[CartItem] = Field(default_factory=list)
    last_reply: str = ""
    last_spoken_reply: str = ""
    end_call_requested: bool = False
    conversation: List[str] = Field(default_factory=list)
    openai_input_tokens: int = 0
    openai_output_tokens: int = 0
    llm_turns: int = 0
    offered_value_deal_id: Optional[str] = None
    llm_response_ms: List[float] = Field(default_factory=list)

    @computed_field
    @property
    def total(self) -> int:
        return sum(item.line_total for item in self.cart)


class MessageRequest(BaseModel):
    text: str = Field(min_length=1, max_length=1000)


class RealtimeCartRequest(BaseModel):
    action: Literal["add", "remove", "summary", "set_delivery", "confirm"]
    item_name: str = Field(default="", max_length=120)
    quantity: int = Field(default=1, ge=1, le=20)
    address: str = Field(default="", max_length=500)


class SessionCreateRequest(BaseModel):
    caller_phone: Optional[str] = None


class CallMetricsRequest(BaseModel):
    duration_seconds: float = Field(ge=0, le=7200)
    human_talk_seconds: float = Field(ge=0, le=7200)
    ai_talk_seconds: float = Field(ge=0, le=7200)
    response_delays_ms: List[float] = Field(default_factory=list)
    elevenlabs_characters: int = Field(default=0, ge=0, le=100000)


class Order(BaseModel):
    id: str
    session_id: str
    customer_name: Optional[str]
    customer_phone: Optional[str] = None
    delivery_address: Optional[str] = None
    items: List[CartItem]
    total: int
    status: Literal["new", "accepted", "preparing", "ready", "completed"] = "new"
    created_at: str
