# Telebirr protected-audio bot

Python Telegram bot that accepts a Telebirr receipt reference or screenshot, checks the official receipt page, registers the reference once in SQLite, then sends audio with Telegram content protection.

## Setup

Requires Python 3.11+, a Telegram bot token, and Tesseract OCR for screenshot uploads. On Ubuntu/Debian, install the OCR executable with:

    sudo apt update && sudo apt install tesseract-ocr

The Python package pytesseract alone is not enough; the tesseract system executable must be available on PATH.

    python3 -m venv .venv
    . .venv/bin/activate
    pip install -e .
    cp .env.example .env

Set TELEGRAM_BOT_TOKEN, EXPECTED_RECIPIENT, and either EXPECTED_AMOUNT_ETB or MINIMUM_AMOUNT_ETB in .env. The recipient and price are configurable because they are not specified yet. Put audio files in audio/, then run python -m app.

SQLite is created at data/payments.sqlite3. References are unique case-insensitively. Reuse by the same Telegram user is idempotent; another user's reuse is rejected as an invalid bill. Screenshots are processed in memory and not saved.

## Flow

- Users can type a reference or send a screenshot. OCR reads the labeled Transaction Number; if OCR fails, it asks the user to type it.
- The bot fetches https://transactioninfo.ethiotelecom.et/receipt/{reference} and requires successful status, payment date, recipient, positive amount, and a matching reference if displayed.
- Recipient and amount rules are checked before registration. The stored data includes Telegram user ID/name, registration date, payment date, recipient, amount, and reference.
- Audio files are sent with protect_content=True; Telegram blocks forwarding/saving but cannot prevent external recording or copying.

The parser uses the official page's Completed status, Credited Party name, Payment date, and Settled Amount fields (not the separate Total Paid Amount). It fails closed when required data is missing.
