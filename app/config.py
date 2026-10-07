from __future__ import annotations
import os
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from dotenv import load_dotenv

def decimal_env(key: str) -> Decimal | None:
    raw = os.getenv(key, "").strip()
    if not raw: return None
    try: amount = Decimal(raw)
    except InvalidOperation as exc: raise ValueError(f"{key} must be decimal") from exc
    if not amount.is_finite() or amount <= 0: raise ValueError(f"{key} must be positive")
    return amount

@dataclass(frozen=True)
class Settings:
    bot_token: str
    database_path: Path
    audio_dir: Path
    expected_recipient: str
    expected_amount_etb: Decimal | None
    minimum_amount_etb: Decimal | None
    receipt_base_url: str
    max_screenshot_bytes: int
    http_timeout_seconds: float

    @classmethod
    def from_env(cls) -> Settings:
        load_dotenv()
        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        if not token: raise ValueError("Set TELEGRAM_BOT_TOKEN in .env")
        recipient = os.getenv("EXPECTED_RECIPIENT", "").strip()
        if not recipient: raise ValueError("Set EXPECTED_RECIPIENT in .env")
        exact, minimum = decimal_env("EXPECTED_AMOUNT_ETB"), decimal_env("MINIMUM_AMOUNT_ETB")
        if exact is None and minimum is None: raise ValueError("Set EXPECTED_AMOUNT_ETB or MINIMUM_AMOUNT_ETB in .env")
        if exact is not None and minimum is not None: raise ValueError("Set only one amount rule")
        return cls(token, Path(os.getenv("DATABASE_PATH", "data/payments.sqlite3")),
            Path(os.getenv("AUDIO_DIR", "audio")), recipient, exact, minimum,
            os.getenv("RECEIPT_BASE_URL", "https://transactioninfo.ethiotelecom.et/receipt/").rstrip("/") + "/",
            int(os.getenv("MAX_SCREENSHOT_BYTES", "12000000")), float(os.getenv("HTTP_TIMEOUT_SECONDS", "15")))
