import logging
import os
import uuid
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, UploadFile, File
from fastapi.responses import FileResponse

logger = logging.getLogger(__name__)
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db, AsyncSessionLocal
from app.models.ticket import Ticket
from app.models.chat_message import ChatMessage
from app.models.ticket_attachment import TicketAttachment
from app.schemas.ticket import TicketOut, TicketUpdate, TicketCreate
from app.schemas.chat import ChatMessageOut, ChatMessageCreate
from app.routers.auth import get_current_user
from app.models.user import User
from app.services.ai_service import analyze_ticket_with_ai, generate_chat_reply
from app.services.email_service import send_email_response, send_chat_message_to_client, get_resolution_examples, _notify_bot_critical, UPLOADS_DIR
from app.services.auth_service import decode_token

router = APIRouter(prefix="/api/tickets", tags=["tickets"])

async def process_ticket_ai(ticket_id: int, ticket_text: str):
    """Background task to analyze ticket with AI and update DB."""
    ai_result = await analyze_ticket_with_ai(ticket_text)

    async with AsyncSessionLocal() as session:
        ticket = await session.get(Ticket, ticket_id)
        if ticket:
            ticket.sentiment = ai_result.get("sentiment")
            ticket.category = ai_result.get("category")
            ticket.ai_response = ai_result.get("draft_response")
            ticket.full_name = ticket.full_name or ai_result.get("full_name")
            ticket.company = ticket.company or ai_result.get("company")
            ticket.phone = ticket.phone or ai_result.get("phone")
            ticket.device_serials = ticket.device_serials or ai_result.get("device_serials") or []
            ticket.device_type = ticket.device_type or ai_result.get("device_type")
            ticket.summary = ticket.summary or ai_result.get("summary")
            await session.commit()
            await session.refresh(ticket)
            await _notify_bot_critical(ticket)


# ── Список заявок ─────────────────────────────────────
@router.get("", response_model=list[TicketOut])
async def list_tickets(
    status: str | None = None,
    sentiment: str | None = None,
    category: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = select(Ticket).order_by(desc(Ticket.date_received))
    if status:
        q = q.where(Ticket.status == status)
    if sentiment:
        q = q.where(Ticket.sentiment == sentiment)
    if category:
        q = q.where(Ticket.category == category)
    result = await db.execute(q)
    return result.scalars().all()


# ── Создать заявку (вручную / AI-агент) ───────────────
@router.post("", response_model=TicketOut, status_code=status.HTTP_201_CREATED)
async def create_ticket(
    payload: TicketCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    ticket = Ticket(**payload.model_dump())
    db.add(ticket)
    await db.commit()
    await db.refresh(ticket)

    ticket_text = ticket.original_email or ticket.summary or ""
    if ticket_text:
        background_tasks.add_task(process_ticket_ai, ticket.id, ticket_text)
    elif ticket.category:
        # Категория задана вручную при создании — уведомить сразу
        background_tasks.add_task(_notify_bot_critical, ticket)

    return ticket


# ── Получить заявку ────────────────────────────────────
@router.get("/{ticket_id}", response_model=TicketOut)
async def get_ticket(
    ticket_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    ticket = await db.get(Ticket, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    return ticket


# ── Обновить заявку ────────────────────────────────────
@router.patch("/{ticket_id}", response_model=TicketOut)
async def update_ticket(
    ticket_id: int,
    payload: TicketUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    ticket = await db.get(Ticket, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    old_category = ticket.category
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(ticket, field, value)
    await db.commit()
    await db.refresh(ticket)
    # Уведомить если категория стала критической
    if ticket.category != old_category:
        await _notify_bot_critical(ticket)
    return ticket


# ── Отправить ответ ────────────────────────────────────
@router.post("/{ticket_id}/send")
async def send_response(
    ticket_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    ticket = await db.get(Ticket, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    if not ticket.ai_response:
        raise HTTPException(status_code=400, detail="Нет текста ответа")

    if not ticket.email:
        raise HTTPException(status_code=400, detail="У заявки нет email адреса отправителя")

    try:
        subject = "Ответ на ваше обращение"
        await send_email_response(ticket.email, subject, ticket.ai_response)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Ошибка отправки письма: {exc}")

    ticket.status = "closed"
    await db.commit()
    return {"success": True, "message": "Ответ отправлен"}


# ── Чат заявки ────────────────────────────────────────
@router.get("/{ticket_id}/chat", response_model=list[ChatMessageOut])
async def get_chat(
    ticket_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.ticket_id == ticket_id)
        .order_by(ChatMessage.created_at)
    )
    return result.scalars().all()


@router.post("/{ticket_id}/chat", response_model=ChatMessageOut, status_code=status.HTTP_201_CREATED)
async def add_chat_message(
    ticket_id: int,
    payload: ChatMessageCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    ticket = await db.get(Ticket, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Заявка не найдена")

    msg = ChatMessage(ticket_id=ticket_id, role=payload.role, text=payload.text)
    db.add(msg)
    await db.commit()
    await db.refresh(msg)

    # При ответе оператора: переводим в "in_progress" и отправляем email клиенту
    if payload.role == "operator":
        if ticket.status == "open":
            ticket.status = "in_progress"
            await db.commit()
        if ticket.email:
            try:
                await send_chat_message_to_client(ticket.email, payload.text, ticket_id)
            except Exception as exc:
                logger.warning(f"Failed to email client for ticket {ticket_id}: {exc}")

    return msg


@router.post("/{ticket_id}/ai-chat", response_model=ChatMessageOut, status_code=status.HTTP_201_CREATED)
async def ask_ai_assistant(
    ticket_id: int,
    payload: ChatMessageCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Operator asks AI — saves ai_query + bot response. Does NOT email client."""
    ticket = await db.get(Ticket, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Заявка не найдена")

    query_msg = ChatMessage(ticket_id=ticket_id, role="ai_query", text=payload.text)
    db.add(query_msg)
    await db.commit()

    result = await db.execute(
        select(ChatMessage)
        .where(
            ChatMessage.ticket_id == ticket_id,
            ChatMessage.role.in_(["user", "bot", "ai_query"]),
        )
        .order_by(ChatMessage.created_at)
    )
    history = [{"role": m.role, "text": m.text} for m in result.scalars().all()]

    ticket_context = ticket.original_email or ticket.summary or ""
    examples = await get_resolution_examples(ticket.category or "malfunction", exclude_ticket_id=ticket_id)
    reply_text = await generate_chat_reply(ticket_context, history, resolution_examples=examples)

    bot_msg = ChatMessage(ticket_id=ticket_id, role="bot", text=reply_text)
    db.add(bot_msg)
    await db.commit()
    await db.refresh(bot_msg)
    return bot_msg


@router.post("/{ticket_id}/chat/reply", response_model=ChatMessageOut, status_code=status.HTTP_201_CREATED)
async def ai_chat_reply(
    ticket_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Legacy endpoint — kept for compatibility."""
    ticket = await db.get(Ticket, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Заявка не найдена")

    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.ticket_id == ticket_id)
        .order_by(ChatMessage.created_at)
    )
    history = [{"role": m.role, "text": m.text} for m in result.scalars().all()]

    ticket_context = ticket.original_email or ticket.summary or ""
    examples = await get_resolution_examples(ticket.category or "malfunction", exclude_ticket_id=ticket_id)
    reply_text = await generate_chat_reply(ticket_context, history, resolution_examples=examples)

    bot_msg = ChatMessage(ticket_id=ticket_id, role="bot", text=reply_text)
    db.add(bot_msg)
    await db.commit()
    await db.refresh(bot_msg)
    return bot_msg


# ── Вложения заявки ───────────────────────────────────
@router.get("/attachments/{attachment_id}/download")
async def download_attachment(
    attachment_id: int,
    token: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    if not token:
        raise HTTPException(status_code=401, detail="Не авторизован")
    user_id = decode_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Недействительный токен")

    att = await db.get(TicketAttachment, attachment_id)
    if not att:
        raise HTTPException(status_code=404, detail="Вложение не найдено")
    full_path = os.path.join(UPLOADS_DIR, att.file_path)
    if not os.path.exists(full_path):
        raise HTTPException(status_code=404, detail="Файл не найден на диске")
    return FileResponse(
        path=full_path,
        filename=att.filename,
        media_type=att.content_type,
    )


@router.get("/{ticket_id}/attachments")
async def get_attachments(
    ticket_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    result = await db.execute(
        select(TicketAttachment)
        .where(TicketAttachment.ticket_id == ticket_id)
        .order_by(TicketAttachment.created_at)
    )
    attachments = result.scalars().all()
    return [
        {
            "id": a.id,
            "filename": a.filename,
            "content_type": a.content_type,
            "file_size": a.file_size,
            "created_at": a.created_at.isoformat(),
        }
        for a in attachments
    ]


@router.post("/{ticket_id}/attachments/upload")
async def upload_attachments(
    ticket_id: int,
    files: list[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    if not files:
        raise HTTPException(status_code=400, detail="Нет файлов для загрузки")
    if len(files) > 3:
        raise HTTPException(status_code=400, detail="Максимум 3 файла")

    ticket = await db.get(Ticket, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Заявка не найдена")

    os.makedirs(UPLOADS_DIR, exist_ok=True)
    result = []
    for upload in files:
        data = await upload.read()
        ext = os.path.splitext(upload.filename or "file")[1]
        unique_name = f"{uuid.uuid4().hex}{ext}"
        file_path = os.path.join(UPLOADS_DIR, unique_name)
        with open(file_path, "wb") as f:
            f.write(data)

        att = TicketAttachment(
            ticket_id=ticket_id,
            filename=upload.filename or unique_name,
            content_type=upload.content_type or "application/octet-stream",
            file_path=unique_name,
            file_size=len(data),
        )
        db.add(att)
        await db.flush()
        await db.refresh(att)
        result.append({"id": att.id, "filename": att.filename, "content_type": att.content_type})

    await db.commit()
    return result
