from datetime import datetime
from pydantic import BaseModel


class TicketOut(BaseModel):
    id: int
    date_received: datetime
    full_name: str | None
    company: str | None
    phone: str | None
    email: str | None
    device_serials: list[str] | None = []
    device_type: str | None
    sentiment: str | None
    category: str | None
    summary: str | None
    original_email: str | None
    ai_response: str | None
    status: str
    assigned_to: int | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TicketUpdate(BaseModel):
    status: str | None = None
    ai_response: str | None = None
    assigned_to: int | None = None
    full_name: str | None = None
    company: str | None = None
    phone: str | None = None
    email: str | None = None
    device_serials: list[str] | None = None
    device_type: str | None = None
    sentiment: str | None = None
    category: str | None = None
    summary: str | None = None


class TicketCreate(BaseModel):
    date_received: datetime
    full_name: str | None = None
    company: str | None = None
    phone: str | None = None
    email: str | None = None
    device_serials: list[str] = []
    device_type: str | None = None
    sentiment: str | None = None
    category: str | None = None
    summary: str | None = None
    original_email: str | None = None
    ai_response: str | None = None
    status: str = "open"
