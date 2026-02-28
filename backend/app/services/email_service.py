import asyncio
import email
import imaplib
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from email import encoders
from email.header import decode_header
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import aiosmtplib
import httpx
from sqlalchemy import select, desc

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.chat_message import ChatMessage
from app.models.ticket import Ticket
from app.models.ticket_attachment import TicketAttachment
from app.services.ai_service import analyze_ticket_with_ai, generate_chat_reply

UPLOADS_DIR = "/app/uploads"

CRITICAL_CATEGORIES = {"malfunction", "breakdown"}

logger = logging.getLogger(__name__)

# Ищем [#123] или #123 в теме письма для связи с существующей заявкой
_TICKET_ID_RE = re.compile(r'\[?#(\d+)\]?')


def _decode_header_value(value: str | None) -> str:
    if not value:
        return ""
    parts = decode_header(value)
    result = []
    for part, charset in parts:
        if isinstance(part, bytes):
            result.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            result.append(part)
    return " ".join(result)


def _parse_ticket_id(subject: str) -> int | None:
    m = _TICKET_ID_RE.search(subject)
    return int(m.group(1)) if m else None


def _fetch_unseen_emails() -> list[dict]:
    """Sync IMAP fetch — runs in a thread executor."""
    if not settings.IMAP_HOST or not settings.EMAIL_USER or not settings.EMAIL_PASSWORD:
        logger.warning("IMAP not configured, skipping email fetch")
        return []

    messages = []
    try:
        with imaplib.IMAP4_SSL(settings.IMAP_HOST, settings.IMAP_PORT) as imap:
            imap.login(settings.EMAIL_USER, settings.EMAIL_PASSWORD)
            imap.select("INBOX")
            _, id_list = imap.search(None, "UNSEEN")

            for msg_id in id_list[0].split():
                _, data = imap.fetch(msg_id, "(RFC822)")
                raw = data[0][1]
                msg = email.message_from_bytes(raw)

                subject = _decode_header_value(msg.get("Subject"))
                from_ = _decode_header_value(msg.get("From"))

                body = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        if part.get_content_type() == "text/plain":
                            payload = part.get_payload(decode=True)
                            if payload:
                                body = payload.decode(
                                    part.get_content_charset() or "utf-8",
                                    errors="replace",
                                )
                                break
                else:
                    payload = msg.get_payload(decode=True)
                    if payload:
                        body = payload.decode(
                            msg.get_content_charset() or "utf-8",
                            errors="replace",
                        )

                sender_email = from_
                if "<" in from_ and ">" in from_:
                    sender_email = from_.split("<")[1].rstrip(">").strip()

                reply_ticket_id = _parse_ticket_id(subject)

                # Extract attachments (skip text body and html body parts)
                attachments = []
                if msg.is_multipart():
                    for part in msg.walk():
                        part_ct = part.get_content_type()
                        part_disp = part.get("Content-Disposition", "")
                        part_name = part.get_filename()
                        # Skip container types
                        if part.get_content_maintype() == "multipart":
                            continue
                        # Skip plain-text and HTML body parts (unless explicitly attached)
                        if part_ct in ("text/plain", "text/html") and "attachment" not in part_disp:
                            continue
                        # Skip parts with no filename and no attachment disposition
                        if not part_name and "attachment" not in part_disp:
                            continue
                        filename = _decode_header_value(part_name or "file")
                        payload = part.get_payload(decode=True)
                        if payload:
                            attachments.append({
                                "filename": filename,
                                "content_type": part_ct or "application/octet-stream",
                                "data": payload,
                            })

                imap.store(msg_id, "+FLAGS", "\\Seen")

                messages.append({
                    "subject": subject,
                    "from": from_,
                    "email": sender_email,
                    "body": body,
                    "date": datetime.now(timezone.utc),
                    "reply_ticket_id": reply_ticket_id,
                    "attachments": attachments,
                })
    except Exception as e:
        logger.error(f"IMAP error: {e}")

    return messages


async def _save_attachments(ticket_id: int, attachments: list[dict]) -> None:
    """Save attachment files to disk and create DB records."""
    if not attachments:
        return
    os.makedirs(UPLOADS_DIR, exist_ok=True)
    async with AsyncSessionLocal() as session:
        for att in attachments:
            ext = os.path.splitext(att["filename"])[1] or ""
            unique_name = f"{uuid.uuid4().hex}{ext}"
            file_path = os.path.join(UPLOADS_DIR, unique_name)
            with open(file_path, "wb") as f:
                f.write(att["data"])
            session.add(TicketAttachment(
                ticket_id=ticket_id,
                filename=att["filename"],
                content_type=att["content_type"],
                file_path=unique_name,
                file_size=len(att["data"]),
            ))
        await session.commit()
    logger.info(f"Saved {len(attachments)} attachment(s) for ticket #{ticket_id}")


async def _find_open_ticket_by_email(sender_email: str) -> int | None:
    """Return the most recent non-closed ticket id for this email, or None."""
    if not sender_email:
        return None
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Ticket.id)
            .where(Ticket.email == sender_email, Ticket.status != "closed")
            .order_by(desc(Ticket.date_received))
            .limit(1)
        )
        return result.scalar_one_or_none()


async def _notify_bot_critical(ticket: Ticket) -> None:
    """Fire-and-forget: send critical ticket alert to all operators via TG bot."""
    if ticket.category not in CRITICAL_CATEGORIES:
        return
    payload = {
        "id": ticket.id,
        "category": ticket.category,
        "summary": ticket.summary,
        "date_received": ticket.date_received.isoformat(),
        "full_name": ticket.full_name,
        "email": ticket.email,
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                f"{settings.BOT_URL}/notify-critical",
                json=payload,
                headers={"X-Bot-Secret": settings.BOT_SECRET},
            )
        result = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        sent = result.get("sent", 0)
        reason = result.get("reason", "")
        if sent > 0:
            logger.info(f"Critical alert for ticket #{ticket.id}: sent to {sent} operators")
        else:
            logger.warning(f"Critical alert for ticket #{ticket.id}: 0 sent (reason={reason!r}, status={r.status_code})")
    except Exception as e:
        logger.warning(f"Failed to notify bot about ticket #{ticket.id}: {e}")


async def get_resolution_examples(
    category: str,
    exclude_ticket_id: int | None = None,
    limit: int = 3,
) -> list[dict]:
    """Return up to `limit` Q&A pairs from closed tickets of the same category for RAG context."""
    async with AsyncSessionLocal() as session:
        query = (
            select(Ticket)
            .where(Ticket.status == "closed", Ticket.category == category)
        )
        if exclude_ticket_id is not None:
            query = query.where(Ticket.id != exclude_ticket_id)
        query = query.order_by(desc(Ticket.updated_at)).limit(limit)

        result = await session.execute(query)
        tickets = result.scalars().all()

        examples = []
        for t in tickets:
            msgs_result = await session.execute(
                select(ChatMessage)
                .where(
                    ChatMessage.ticket_id == t.id,
                    ChatMessage.role.in_(["user", "operator"]),
                )
                .order_by(ChatMessage.created_at)
            )
            msgs = msgs_result.scalars().all()
            user_msgs = [m.text for m in msgs if m.role == "user"]
            operator_msgs = [m.text for m in msgs if m.role == "operator"]
            if user_msgs and operator_msgs:
                examples.append({
                    "question": user_msgs[0],
                    "answer": operator_msgs[-1],
                })
        return examples


async def _handle_email_reply(msg: dict, ticket_id: int) -> None:
    """Client replied to an existing ticket — add message to chat and generate AI response."""
    ticket_context = ""

    async with AsyncSessionLocal() as session:
        t = await session.get(Ticket, ticket_id)
        if not t or t.status == "closed":
            return

        ticket_context = t.original_email or t.summary or ""
        ticket_category = t.category or "malfunction"
        session.add(ChatMessage(ticket_id=ticket_id, role="user", text=msg["body"]))

        if "вызвать оператора" in msg["body"].lower():
            t.status = "needs_operator"
            logger.info(f"Ticket #{ticket_id} → needs_operator")

        await session.commit()
    logger.info(f"Added client reply to ticket #{ticket_id}")

    await _save_attachments(ticket_id, msg.get("attachments", []))

    # Generate AI response to the new client message
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(ChatMessage)
                .where(
                    ChatMessage.ticket_id == ticket_id,
                    ChatMessage.role.in_(["user", "bot", "ai_query"]),
                )
                .order_by(ChatMessage.created_at)
            )
            history = [{"role": m.role, "text": m.text} for m in result.scalars().all()]

        examples = await get_resolution_examples(ticket_category, exclude_ticket_id=ticket_id)
        reply_text = await generate_chat_reply(ticket_context, history, resolution_examples=examples)

        async with AsyncSessionLocal() as session:
            session.add(ChatMessage(ticket_id=ticket_id, role="bot", text=reply_text))
            await session.commit()

        logger.info(f"AI reply generated for ticket #{ticket_id}")
    except Exception as e:
        logger.error(f"AI reply error for ticket #{ticket_id}: {e}")


async def _handle_new_email(msg: dict) -> None:
    """Create new ticket, run AI, populate chat, email AI response."""
    ticket_id: int

    async with AsyncSessionLocal() as session:
        ticket = Ticket(
            date_received=msg["date"],
            email=msg["email"],
            original_email=f"От: {msg['from']}\nТема: {msg['subject']}\n\n{msg['body']}",
            status="open",
        )
        session.add(ticket)
        await session.commit()
        await session.refresh(ticket)
        ticket_id = ticket.id
        ticket_text = ticket.original_email

    # Save attachments independently — before AI, so they're always persisted
    await _save_attachments(ticket_id, msg.get("attachments", []))

    try:
        ai_result = await analyze_ticket_with_ai(ticket_text)

        async with AsyncSessionLocal() as session:
            t = await session.get(Ticket, ticket_id)
            if t:
                t.sentiment = ai_result.get("sentiment")
                t.category = ai_result.get("category")
                t.ai_response = ai_result.get("draft_response")
                t.full_name = ai_result.get("full_name")
                t.company = ai_result.get("company")
                t.phone = ai_result.get("phone")
                t.device_serials = ai_result.get("device_serials") or []
                t.device_type = ai_result.get("device_type")
                t.summary = ai_result.get("summary")
                await session.commit()

        bot_text = ai_result.get("draft_response", "")

        async with AsyncSessionLocal() as session:
            session.add(ChatMessage(
                ticket_id=ticket_id,
                role="user",
                text=f"От: {msg['from']}\nТема: {msg['subject']}\n\n{msg['body']}",
            ))
            session.add(ChatMessage(ticket_id=ticket_id, role="bot", text=bot_text))
            await session.commit()

        logger.info(f"AI response saved to AI chat for ticket #{ticket_id} (not sent to client)")

        # Уведомить операторов в TG о критической заявке
        async with AsyncSessionLocal() as session:
            t = await session.get(Ticket, ticket_id)
            if t:
                await _notify_bot_critical(t)

    except Exception as e:
        logger.error(f"Error processing new email → ticket #{ticket_id}: {e}")


async def poll_imap_once() -> None:
    """Fetch unseen emails, route to new-ticket or reply handler."""
    loop = asyncio.get_event_loop()
    messages = await loop.run_in_executor(None, _fetch_unseen_emails)

    if not messages:
        return

    logger.info(f"Fetched {len(messages)} new email(s)")

    for msg in messages:
        reply_ticket_id = msg.get("reply_ticket_id")
        if reply_ticket_id:
            await _handle_email_reply(msg, reply_ticket_id)
        else:
            # If no [#N] in subject, check if sender has an open ticket
            existing_id = await _find_open_ticket_by_email(msg["email"])
            if existing_id:
                logger.info(f"Email from {msg['email']} → existing ticket #{existing_id}")
                await _handle_email_reply(msg, existing_id)
            else:
                await _handle_new_email(msg)


async def send_email_response(
    to_email: str, subject: str, body: str, ticket_id: int | None = None
) -> None:
    """Send email via SMTP. Embeds ticket ID in subject for thread tracking."""
    if not settings.SMTP_HOST or not settings.EMAIL_USER or not settings.EMAIL_PASSWORD:
        raise RuntimeError("SMTP не настроен — задайте SMTP_HOST, EMAIL_USER, EMAIL_PASSWORD")

    if ticket_id and f"#{ticket_id}" not in subject:
        subject = f"[#{ticket_id}] {subject}"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.EMAIL_USER
    msg["To"] = to_email
    msg.attach(MIMEText(body, "plain", "utf-8"))

    await aiosmtplib.send(
        msg,
        hostname=settings.SMTP_HOST,
        port=settings.SMTP_PORT,
        username=settings.EMAIL_USER,
        password=settings.EMAIL_PASSWORD,
        start_tls=True,
    )
    logger.info(f"Email sent to {to_email} (ticket #{ticket_id})")


async def send_chat_message_to_client(to_email: str, text: str, ticket_id: int) -> None:
    """Send a chat message to client's email with ticket ID in subject."""
    await send_email_response(to_email, "Ответ на ваше обращение", text, ticket_id)


async def start_email_polling(interval: int = 60) -> None:
    """Infinite async loop — polls IMAP every `interval` seconds."""
    logger.info(f"Email polling started (interval={interval}s)")
    while True:
        try:
            await poll_imap_once()
        except Exception as e:
            logger.error(f"Email polling iteration error: {e}")
        await asyncio.sleep(interval)
