"""Settings loaded from environment variables and an optional .env file."""
import os
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def load_dotenv(path=BASE_DIR / ".env"):
    """Minimal .env loader (avoids an extra dependency). Existing env vars win."""
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _num(name, default, cast):
    try:
        return cast(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


@dataclass
class Settings:
    ollama_host: str = "http://127.0.0.1:11434"
    ollama_model: str = "gemma3:4b"
    ollama_timeout: float = 180.0
    db_path: str = str(BASE_DIR / "data" / "lazyticket.db")
    manual_minutes_per_ticket: float = 8.0
    duplicate_threshold: float = 0.45


def get_settings():
    load_dotenv()
    db_path = os.environ.get("DB_PATH", "data/lazyticket.db")
    if not Path(db_path).is_absolute():
        db_path = str(BASE_DIR / db_path)
    return Settings(
        ollama_host=os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/"),
        ollama_model=os.environ.get("OLLAMA_MODEL", "gemma3:4b"),
        ollama_timeout=_num("OLLAMA_TIMEOUT", 180.0, float),
        db_path=db_path,
        manual_minutes_per_ticket=_num("MANUAL_MINUTES_PER_TICKET", 8.0, float),
        duplicate_threshold=_num("DUPLICATE_THRESHOLD", 0.45, float),
    )
