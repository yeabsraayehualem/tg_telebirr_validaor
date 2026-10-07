from __future__ import annotations
import sqlite3
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from app.receipt import Receipt

class BillStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS bills (
                reference TEXT PRIMARY KEY COLLATE NOCASE,
                telegram_user_id INTEGER NOT NULL,
                telegram_name TEXT NOT NULL,
                registered_at TEXT NOT NULL,
                paid_at TEXT NOT NULL,
                recipient TEXT NOT NULL,
                amount_etb TEXT NOT NULL
            )""")

    def connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    def register(self, receipt: Receipt, user_id: int, name: str) -> bool:
        """Same-user retries are idempotent; another user's reuse is rejected."""
        with self.connect() as db:
            db.execute("INSERT OR IGNORE INTO bills VALUES (?, ?, ?, ?, ?, ?, ?)",
                (receipt.reference, user_id, name, datetime.now(timezone.utc).isoformat(),
                 receipt.paid_at.isoformat(), receipt.recipient,
                 str(receipt.amount_etb.quantize(Decimal("0.01")))))
            row = db.execute("SELECT telegram_user_id FROM bills WHERE reference = ?", (receipt.reference,)).fetchone()
            return bool(row and row["telegram_user_id"] == user_id)
