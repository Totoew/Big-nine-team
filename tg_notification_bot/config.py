import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")
BOT_PORT = int(os.getenv("BOT_PORT", "8081"))
BOT_SECRET = os.getenv("BOT_SECRET", "change_me_bot_secret")
UPDATE_INTERVAL = int(os.getenv("UPDATE_INTERVAL", "300"))
