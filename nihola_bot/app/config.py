"""Sozlamalar: hammasi .env faylidan o'qiladi (token kod ichida saqlanmaydi)."""
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _ids(raw: str) -> frozenset[int]:
    out = set()
    for part in (raw or "").replace(" ", "").split(","):
        if part.lstrip("-").isdigit():
            out.add(int(part))
    return frozenset(out)


def _chat_id(raw: str) -> int | str:
    raw = (raw or "").strip()
    if raw.lstrip("-").isdigit():
        return int(raw)
    if raw and not raw.startswith("@"):
        raw = "@" + raw
    return raw


@dataclass(frozen=True)
class Settings:
    bot_token: str
    channel_id: int | str
    admin_ids: frozenset[int]
    leads_chat_id: int | str | None
    realtor_name: str
    realtor_phone: str
    realtor_username: str
    db_path: Path
    media_dir: Path
    watermark_text: str
    digest_hour: int
    timezone: str

    @property
    def channel_public_username(self) -> str | None:
        if isinstance(self.channel_id, str) and self.channel_id.startswith("@"):
            return self.channel_id[1:]
        return None


def load_settings() -> Settings:
    db_path = Path(os.getenv("DB_PATH", "nihola.db"))
    media_dir = Path(os.getenv("MEDIA_DIR", "media"))
    leads = os.getenv("LEADS_CHAT_ID", "").strip()
    return Settings(
        bot_token=os.getenv("BOT_TOKEN", "").strip(),
        channel_id=_chat_id(os.getenv("CHANNEL_ID", "")),
        admin_ids=_ids(os.getenv("ADMIN_IDS", "")),
        leads_chat_id=_chat_id(leads) if leads else None,
        realtor_name=os.getenv("REALTOR_NAME", "Nihola").strip(),
        realtor_phone=os.getenv("REALTOR_PHONE", "").strip(),
        realtor_username=os.getenv("REALTOR_USERNAME", "").strip().lstrip("@"),
        db_path=db_path if db_path.is_absolute() else BASE_DIR / db_path,
        media_dir=media_dir if media_dir.is_absolute() else BASE_DIR / media_dir,
        watermark_text=os.getenv("WATERMARK_TEXT", "Nihola Estate").strip(),
        digest_hour=int(os.getenv("DIGEST_HOUR", "19") or 19),
        timezone=os.getenv("TIMEZONE", "Asia/Tashkent").strip(),
    )


settings = load_settings()


class Runtime:
    """Ishga tushganda to'ldiriladigan qiymatlar (bot username va h.k.)."""

    bot_username: str = ""


runtime = Runtime()
