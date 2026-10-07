from __future__ import annotations
import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import quote
import httpx
from bs4 import BeautifulSoup

class ReceiptError(Exception):
    """Receipt failed verification or parsing."""

@dataclass(frozen=True)
class Receipt:
    reference: str
    paid_at: datetime
    recipient: str
    amount_etb: Decimal

def norm(value: str) -> str:
    return re.sub(r"[^a-z]", "", value.casefold())

def parse_receipt(reference: str, html: str) -> Receipt:
    soup = BeautifulSoup(html, "html.parser")
    fields: dict[str, str] = {}
    rows = soup.select("tr")
    cell_rows: list[list[str]] = []
    for row in rows:
        cells = [" ".join(cell.stripped_strings) for cell in row.find_all(["td", "th"], recursive=False)]
        cells = [re.sub(r"\s+", " ", value).strip() for value in cells]
        cell_rows.append(cells)
        if len(cells) == 2:
            fields[norm(cells[0])] = cells[1]
    # Telebirr's receipt has a header row (Invoice No., Payment date, Settled Amount)
    # followed by a separate row containing their values.
    for i, cells in enumerate(cell_rows[:-1]):
        labels = [norm(cell) for cell in cells]
        if any("paymentdate" in label for label in labels) and any("settledamount" in label for label in labels):
            values = cell_rows[i + 1]
            for label, value in zip(labels, values):
                if label and value:
                    fields[label] = value
                    if "paymentdate" in label: fields["transactiontime"] = value
                    if "settledamount" in label: fields["amount"] = value
                    if "invoiceno" in label or "transactionnumber" in label: fields["transactionnumber"] = value

    text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
    def get(*labels: str) -> str | None:
        return next((fields.get(norm(label)) for label in labels if fields.get(norm(label))), None)
    date_text = get("Transaction Time", "Payment Date", "Date")
    recipient = get("Credited Party name", "Transaction To", "Paid To", "Recipient", "Receiver")
    amount_text = get("Settled Amount", "Amount", "Transaction Amount", "Payment Amount")
    page_ref = get("Invoice No.", "Transaction Number", "Reference", "Reference Number")
    if not date_text or not recipient or not amount_text:
        raise ReceiptError("Receipt page is missing required payment fields")
    if not page_ref:
        raise ReceiptError("Receipt page is missing its transaction reference")
    if page_ref.casefold() != reference.casefold():
        raise ReceiptError("Receipt reference does not match")
    if not re.search(r"(?<![a-z])(?:successful|completed)(?![a-z])", text, re.I):
        raise ReceiptError("Receipt does not show successful payment")

    date_text = date_text.replace("T", " ").replace("Z", "+00:00")
    paid_at = None
    for fmt in ("%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M:%S", "%d-%m-%Y %H:%M:%S"):
        try:
            paid_at = datetime.strptime(date_text[:19], fmt)
            break
        except ValueError:
            pass
    if paid_at is None:
        try: paid_at = datetime.fromisoformat(date_text)
        except ValueError as exc: raise ReceiptError("Unsupported payment date format") from exc
    amount_match = re.search(r"[+-]?\s*[\d,]+(?:\.\d{1,2})?", amount_text)
    if not amount_match: raise ReceiptError("Unsupported amount format")
    try: amount = Decimal(amount_match.group(0).replace(",", "").replace(" ", "").replace("+", ""))
    except InvalidOperation as exc: raise ReceiptError("Unsupported amount format") from exc
    if not amount.is_finite() or amount <= 0: raise ReceiptError("Amount is not a positive payment")
    return Receipt(reference, paid_at, recipient, amount)

def reference_candidates(reference: str) -> list[str]:
    """Generate OCR-confusion alternatives, preserving the original first."""
    from itertools import combinations
    swaps = {"O": "0", "0": "O", "I": "1", "1": "I", "L": "1", "S": "5", "5": "S", "B": "8", "8": "B", "Z": "2", "2": "Z"}
    positions = [(i, swaps[c]) for i, c in enumerate(reference.upper()) if c in swaps][:3]
    candidates = [reference.upper()]
    for count in range(1, len(positions) + 1):
        for selected in combinations(positions, count):
            variant = list(reference.upper())
            for position, replacement in selected:
                variant[position] = replacement
            candidate = "".join(variant)
            if candidate not in candidates:
                candidates.append(candidate)
    return candidates


async def fetch_receipt(reference: str, base_url: str, timeout: float) -> Receipt:
    if not re.fullmatch(r"[A-Za-z0-9-]{5,80}", reference):
        raise ReceiptError("Reference format is invalid")
    last_error: ReceiptError | None = None
    verified: list[Receipt] = []
    for candidate in reference_candidates(reference):
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                response = await client.get(
                    base_url + quote(candidate, safe=""),
                    headers={"User-Agent": "Mozilla/5.0"},
                )
                response.raise_for_status()
            if "html" not in response.headers.get("content-type", "").casefold():
                raise ReceiptError("Unexpected receipt response")
            verified.append(parse_receipt(candidate, response.text))
        except httpx.HTTPError:
            last_error = ReceiptError("Could not verify reference with receipt service")
        except ReceiptError as exc:
            last_error = exc
    if len(verified) == 1:
        return verified[0]
    if len(verified) > 1:
        raise ReceiptError("More than one OCR reference variant matched a receipt")
    raise last_error or ReceiptError("Receipt could not be verified")
