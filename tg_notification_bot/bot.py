import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path

import httpx
from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
)

from config import BOT_TOKEN, BACKEND_URL, FRONTEND_URL, BOT_PORT, BOT_SECRET, UPDATE_INTERVAL

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

SUBSCRIPTIONS_FILE = Path("subscriptions.json")
ALLOWED_USERS_FILE = Path("cache/allowed_users.json")

# ── Хранилище в памяти ────────────────────────────────────────────
subscribers: set[int] = set()
allowed_users: set[int] = set()
admin_users: set[int] = set()


# ── Persistence ───────────────────────────────────────────────────
def load_subscriptions():
    global subscribers
    if SUBSCRIPTIONS_FILE.exists():
        data = json.loads(SUBSCRIPTIONS_FILE.read_text())
        subscribers = set(data.get("subscribers", []))


def save_subscriptions():
    SUBSCRIPTIONS_FILE.write_text(json.dumps({
        "subscribers": list(subscribers),
        "last_updated": datetime.utcnow().isoformat(),
    }, ensure_ascii=False, indent=2))


def load_allowed_cache():
    global allowed_users, admin_users
    if ALLOWED_USERS_FILE.exists():
        data = json.loads(ALLOWED_USERS_FILE.read_text())
        allowed_users = set(data.get("users", []))
        admin_users = set(data.get("admins", []))


def save_allowed_cache(data: dict):
    ALLOWED_USERS_FILE.parent.mkdir(exist_ok=True)
    ALLOWED_USERS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2))


# ── Обновление списка разрешённых пользователей ──────────────────
async def fetch_allowed_users():
    global allowed_users, admin_users
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                f"{BACKEND_URL}/api/telegram/allowed-users",
                headers={"x-bot-secret": BOT_SECRET},
            )
            r.raise_for_status()
            data = r.json()
            allowed_users = set(data.get("users", []))
            admin_users = set(data.get("admins", []))
            save_allowed_cache(data)
            logger.info(f"Allowed users updated: {len(allowed_users)} users, {len(admin_users)} admins")
    except Exception as e:
        logger.warning(f"Failed to fetch allowed users: {e}. Using cache.")
        load_allowed_cache()


async def periodic_update():
    while True:
        await asyncio.sleep(UPDATE_INTERVAL)
        await fetch_allowed_users()


# ── Проверка доступа ──────────────────────────────────────────────
def is_allowed(user_id: int) -> bool:
    return user_id in allowed_users


def is_admin(user_id: int) -> bool:
    return user_id in admin_users


# ── Команды бота ─────────────────────────────────────────────────
@dp.message(Command("start"))
async def cmd_start(message: Message):
    if not is_allowed(message.from_user.id):
        await message.answer("⛔ Доступ запрещён. Обратитесь к администратору.")
        return
    await message.answer(
        "👋 <b>ЭРИС — Служба технической поддержки</b>\n\n"
        "Бот для уведомлений о новых обращениях.\n\n"
        "📋 <b>Команды:</b>\n"
        "/subscribe — подписаться на уведомления\n"
        "/unsubscribe — отписаться\n"
        "/status — статус подключения\n"
        "/help — справка",
        parse_mode="HTML",
    )


@dp.message(Command("subscribe"))
async def cmd_subscribe(message: Message):
    if not is_allowed(message.from_user.id):
        await message.answer("⛔ Доступ запрещён.")
        return
    subscribers.add(message.from_user.id)
    save_subscriptions()
    await message.answer("✅ Вы подписались на уведомления о новых обращениях.")


@dp.message(Command("unsubscribe"))
async def cmd_unsubscribe(message: Message):
    subscribers.discard(message.from_user.id)
    save_subscriptions()
    await message.answer("🔕 Вы отписались от уведомлений.")


@dp.message(Command("status"))
async def cmd_status(message: Message):
    if not is_allowed(message.from_user.id):
        await message.answer("⛔ Доступ запрещён.")
        return
    is_sub = message.from_user.id in subscribers
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{BACKEND_URL}/api/health")
            backend_ok = r.status_code == 200
    except Exception:
        backend_ok = False
    await message.answer(
        f"📊 <b>Статус</b>\n\n"
        f"Бэкенд: {'🟢 доступен' if backend_ok else '🔴 недоступен'}\n"
        f"Подписка: {'✅ активна' if is_sub else '⏸ отключена'}\n"
        f"Подписчиков всего: {len(subscribers)}",
        parse_mode="HTML",
    )


@dp.message(Command("help"))
async def cmd_help(message: Message):
    if not is_allowed(message.from_user.id):
        await message.answer("⛔ Доступ запрещён.")
        return
    text = (
        "📖 <b>Справка</b>\n\n"
        "/subscribe — подписаться на уведомления\n"
        "/unsubscribe — отписаться\n"
        "/status — статус бота и бэкенда\n"
    )
    if is_admin(message.from_user.id):
        text += "\n<b>Администратор:</b>\n/broadcast [текст] — рассылка\n/stats — статистика"
    await message.answer(text, parse_mode="HTML")


@dp.message(Command("broadcast"))
async def cmd_broadcast(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Только для администраторов.")
        return
    text = message.text.removeprefix("/broadcast").strip()
    if not text:
        await message.answer("Использование: /broadcast [текст сообщения]")
        return
    count = 0
    for uid in list(subscribers):
        try:
            await bot.send_message(uid, f"📢 {text}")
            count += 1
        except Exception:
            pass
    await message.answer(f"✅ Сообщение отправлено {count} подписчикам.")


@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Только для администраторов.")
        return
    await message.answer(
        f"📊 <b>Статистика бота</b>\n\n"
        f"Разрешённых пользователей: {len(allowed_users)}\n"
        f"Администраторов: {len(admin_users)}\n"
        f"Подписчиков: {len(subscribers)}",
        parse_mode="HTML",
    )


# ── Inline-кнопки ────────────────────────────────────────────────
@dp.callback_query(F.data.startswith("contacts:"))
async def cb_contacts(callback: CallbackQuery):
    ticket_id = callback.data.split(":")[1]
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                f"{BACKEND_URL}/api/telegram/tickets/{ticket_id}/contacts",
                headers={"x-bot-secret": BOT_SECRET},
            )
            r.raise_for_status()
            c = r.json()
        serials = ", ".join(c.get("device_serials") or []) or "—"
        text = (
            f"👤 <b>Контактные данные — Обращение #{ticket_id}</b>\n\n"
            f"<b>Клиент:</b> {c.get('full_name') or '—'}\n"
            f"<b>Компания:</b> {c.get('company') or '—'}\n"
            f"<b>Email:</b> {c.get('email') or '—'}\n"
            f"<b>Телефон:</b> {c.get('phone') or '—'}\n"
            f"<b>Тип прибора:</b> {c.get('device_type') or '—'}\n"
            f"<b>Зав. номера:</b> {serials}"
        )
    except Exception:
        text = "⚠️ Не удалось получить контакты. Бэкенд недоступен."
    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data.startswith("answer:"))
async def cb_answer(callback: CallbackQuery):
    ticket_id = callback.data.split(":")[1]
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                f"{BACKEND_URL}/api/telegram/tickets/{ticket_id}/generated-answer",
                headers={"x-bot-secret": BOT_SECRET},
            )
            r.raise_for_status()
            data = r.json()
        text = f"🤖 <b>Ответ AI — Обращение #{ticket_id}</b>\n\n{data.get('ai_response', '—')}"
    except Exception:
        text = "⚠️ Не удалось получить ответ AI. Бэкенд недоступен."
    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()


# ── Форматирование уведомления ───────────────────────────────────
TONE_ICON = {"negative": "🔴 СРОЧНО", "positive": "🟢 ЗАПРОС", "neutral": "🟡 НОВОЕ"}
CATEGORY_RU = {
    "malfunction": "Неисправность",
    "breakdown": "Поломка",
    "calibration": "Калибровка",
    "documentation": "Документация",
    "other": "Прочее",
}
CRITICAL_CATEGORIES = {"malfunction", "breakdown"}


def format_ticket_message(ticket: dict) -> str:
    tone = ticket.get("tone") or ticket.get("sentiment", "neutral")
    tone_label = TONE_ICON.get(tone, "🟡 НОВОЕ")
    category = CATEGORY_RU.get(ticket.get("category", "other"), ticket.get("category", "—"))
    serials = ", ".join(ticket.get("device_sn") if isinstance(ticket.get("device_sn"), list)
                        else ([ticket["device_sn"]] if ticket.get("device_sn") else [])) or "—"
    return (
        f"{tone_label} — <b>Обращение #{ticket.get('id', '?')}</b>\n\n"
        f"👤 <b>{ticket.get('full_name', '—')}</b>\n"
        f"🏢 {ticket.get('object') or ticket.get('company', '—')}\n"
        f"📧 {ticket.get('email', '—')}\n"
        f"📞 {ticket.get('phone', '—')}\n"
        f"🔧 {ticket.get('device_type', '—')} | {serials}\n\n"
        f"🏷 <b>Категория:</b> {category}\n"
        f"📝 {ticket.get('description') or ticket.get('summary', '—')}"
    )


def _is_public_url(url: str) -> bool:
    return url.startswith("https://") or (
        url.startswith("http://") and "localhost" not in url and "127.0.0.1" not in url
    )


def ticket_keyboard(ticket_id) -> InlineKeyboardMarkup:
    row = []
    if _is_public_url(FRONTEND_URL):
        row.append(InlineKeyboardButton(text="👀 Открыть", url=f"{FRONTEND_URL}/tickets"))
    row += [
        InlineKeyboardButton(text="👤 Контакты", callback_data=f"contacts:{ticket_id}"),
        InlineKeyboardButton(text="🤖 Ответ AI", callback_data=f"answer:{ticket_id}"),
    ]
    return InlineKeyboardMarkup(inline_keyboard=[row])


def format_critical_message(ticket: dict) -> str:
    ticket_id = ticket.get("id", "?")
    category = ticket.get("category", "")
    category_ru = CATEGORY_RU.get(category, category or "—")
    category_icon = "🔧" if category == "malfunction" else "💥"
    summary = ticket.get("summary") or ticket.get("description") or "—"
    full_name = ticket.get("full_name") or "—"
    email = ticket.get("email") or "—"
    date_str = ticket.get("date_received", "")
    if date_str:
        try:
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            date_str = dt.strftime("%d.%m.%Y, %H:%M")
        except Exception:
            pass
    return (
        f"🚨 <b>СРОЧНОЕ ОБРАЩЕНИЕ — #{ticket_id}</b>\n\n"
        f"{category_icon} <b>Категория:</b> {category_ru}\n"
        f"📋 <b>Тема:</b> {summary}\n"
        f"🕐 <b>Время поступления:</b> {date_str}\n\n"
        f"👤 <b>Отправитель:</b> {full_name}\n"
        f"📧 <b>Email:</b> {email}\n\n"
        "Требуется незамедлительная реакция оператора."
    )


def critical_keyboard(ticket_id) -> InlineKeyboardMarkup | None:
    if _is_public_url(FRONTEND_URL):
        return InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🔍 Открыть обращение", url=f"{FRONTEND_URL}/tickets"),
        ]])
    return None


# ── HTTP-сервер для вебхуков ─────────────────────────────────────
async def handle_webhook(request: web.Request) -> web.Response:
    secret = request.headers.get("X-Bot-Secret", "")
    if secret != BOT_SECRET:
        return web.json_response({"error": "Forbidden"}, status=403)
    try:
        ticket = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    ticket_id = ticket.get("id", "?")
    text = format_ticket_message(ticket)
    keyboard = ticket_keyboard(ticket_id)

    sent = 0
    for uid in list(subscribers):
        try:
            await bot.send_message(uid, text, parse_mode="HTML", reply_markup=keyboard)
            sent += 1
        except Exception as e:
            logger.warning(f"Failed to send to {uid}: {e}")

    logger.info(f"Ticket #{ticket_id} notification sent to {sent} subscribers")
    return web.json_response({"sent": sent})


async def handle_notify_critical(request: web.Request) -> web.Response:
    """Send critical ticket alert to ALL allowed operators (not just subscribers)."""
    secret = request.headers.get("X-Bot-Secret", "")
    if secret != BOT_SECRET:
        return web.json_response({"error": "Forbidden"}, status=403)
    try:
        ticket = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    category = ticket.get("category", "")
    if category not in CRITICAL_CATEGORIES:
        return web.json_response({"sent": 0, "reason": "not_critical"})

    # Обновляем список операторов перед отправкой, чтобы не использовать устаревший кеш
    await fetch_allowed_users()

    ticket_id = ticket.get("id", "?")
    text = format_critical_message(ticket)
    keyboard = critical_keyboard(ticket_id)

    recipients = allowed_users.copy()
    if not recipients:
        logger.warning(f"Critical alert for ticket #{ticket_id}: allowed_users is empty, nobody to notify")
        return web.json_response({"sent": 0, "reason": "no_recipients"})

    sent = 0
    for uid in recipients:
        try:
            kwargs = {"parse_mode": "HTML"}
            if keyboard:
                kwargs["reply_markup"] = keyboard
            await bot.send_message(uid, text, **kwargs)
            sent += 1
        except Exception as e:
            logger.warning(f"Failed to send critical alert to {uid}: {e}")

    logger.info(f"Critical alert for ticket #{ticket_id} sent to {sent}/{len(recipients)} operators")
    return web.json_response({"sent": sent})


async def handle_health(request: web.Request) -> web.Response:
    return web.json_response({
        "status": "ok",
        "subscribers": len(subscribers),
        "allowed_users": len(allowed_users),
    })


async def handle_stats(request: web.Request) -> web.Response:
    return web.json_response({
        "subscribers": len(subscribers),
        "allowed_users": len(allowed_users),
        "admins": len(admin_users),
    })


# ── Запуск ───────────────────────────────────────────────────────
async def main():
    load_subscriptions()
    load_allowed_cache()
    await fetch_allowed_users()

    asyncio.create_task(periodic_update())

    app = web.Application()
    app.router.add_post("/webhook", handle_webhook)
    app.router.add_post("/notify-critical", handle_notify_critical)
    app.router.add_get("/health", handle_health)
    app.router.add_get("/stats", handle_stats)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", BOT_PORT)
    await site.start()
    logger.info(f"HTTP server started on port {BOT_PORT}")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
