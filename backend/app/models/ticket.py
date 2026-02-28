from datetime import datetime
from sqlalchemy import String, Text, DateTime, ForeignKey, ARRAY, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Данные из письма
    date_received: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    full_name: Mapped[str | None] = mapped_column(String(255))
    company: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(50))
    email: Mapped[str | None] = mapped_column(String(255))
    device_serials: Mapped[list[str] | None] = mapped_column(ARRAY(String))
    device_type: Mapped[str | None] = mapped_column(String(255))

    # AI-анализ
    sentiment: Mapped[str | None] = mapped_column(String(20), index=True)   # positive|neutral|negative
    category: Mapped[str | None] = mapped_column(String(50), index=True)    # malfunction|calibration|documentation|other
    summary: Mapped[str | None] = mapped_column(Text)

    # Тексты
    original_email: Mapped[str | None] = mapped_column(Text)
    ai_response: Mapped[str | None] = mapped_column(Text)

    # Статус
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)  # open|in_progress|closed

    # Связи
    assigned_to: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    assignee: Mapped["User | None"] = relationship("User", back_populates="tickets", foreign_keys=[assigned_to])
    chat_messages: Mapped[list["ChatMessage"]] = relationship("ChatMessage", back_populates="ticket", cascade="all, delete-orphan")
    attachments: Mapped[list["TicketAttachment"]] = relationship("TicketAttachment", back_populates="ticket", cascade="all, delete-orphan")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
