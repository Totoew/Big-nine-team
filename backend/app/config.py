from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://eris:eris_secret@localhost:5432/eris"
    SECRET_KEY: str = "change_me_in_production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 8  # 8 часов

    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000"
    BOT_SECRET: str = "change_me_bot_secret"
    BOT_URL: str = "http://bot:8081"
    FRONTEND_URL: str = "http://localhost:5173"
    GROQ_API_KEY: str = ""

    @property
    def bot_secret(self) -> str:
        return self.BOT_SECRET

    # Email (IMAP/SMTP) — заполнить на хакатоне
    IMAP_HOST: str = ""
    IMAP_PORT: int = 993
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    EMAIL_USER: str = ""
    EMAIL_PASSWORD: str = ""

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",")]

    class Config:
        env_file = ".env"
        extra = "allow"


settings = Settings()
