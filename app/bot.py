from __future__ import annotations
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from app.config import Settings
from app.database import BillStore
from app.ocr import ScreenshotError, extract_reference
from app.receipt import Receipt, ReceiptError, fetch_receipt

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def valid_payment(receipt: Receipt, settings: Settings) -> bool:
    if settings.expected_recipient and receipt.recipient.casefold() != settings.expected_recipient.casefold(): return False
    if settings.expected_amount_etb is not None: return receipt.amount_etb == settings.expected_amount_etb
    if settings.minimum_amount_etb is not None: return receipt.amount_etb >= settings.minimum_amount_etb
    return True

def display_name(update: Update) -> str:
    user = update.effective_user
    if not user: return "Unknown"
    return " ".join(x for x in (user.first_name, user.last_name) if x).strip() or user.username or str(user.id)

async def send_audio(update: Update, context: ContextTypes.DEFAULT_TYPE, settings: Settings) -> None:
    chat = update.effective_chat
    if not chat: return
    files = sorted(p for p in settings.audio_dir.iterdir() if p.is_file() and p.suffix.lower() in {".mp3", ".m4a", ".ogg", ".wav"}) if settings.audio_dir.exists() else []
    if not files:
        await context.bot.send_message(chat.id, "Payment verified, but no audio files are configured yet.")
        return
    for path in files:
        with path.open("rb") as audio:
            await context.bot.send_audio(chat_id=chat.id, audio=audio, title=path.stem, protect_content=True)

async def verify(update: Update, context: ContextTypes.DEFAULT_TYPE, reference: str) -> None:
    settings: Settings = context.application.bot_data["settings"]
    message, user = update.effective_message, update.effective_user
    if not message or not user: return
    try: receipt = await fetch_receipt(reference, settings.receipt_base_url, settings.http_timeout_seconds)
    except ReceiptError as e:
        logger.info(f"Receipt verification failed \n {str(e)}")
        await message.reply_text("Invalid bill: I couldn't verify this transaction reference.")
        return
    if not valid_payment(receipt, settings):
        await message.reply_text("Invalid bill: the recipient or amount doesn't match.")
        return
    store: BillStore = context.application.bot_data["store"]
    if not store.register(receipt, user.id, display_name(update)):
        await message.reply_text("Invalid bill: this reference is already registered to another user.")
        return
    await message.reply_text("Payment verified. Sending your audio now.")
    await send_audio(update, context, settings)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text("Send your Telebirr transaction reference or receipt screenshot. After verification, the bot sends your audio with Telegram content protection.")

async def text_reference(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message and message.text: await verify(update, context, message.text.strip().upper())

async def image_reference(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: Settings = context.application.bot_data["settings"]
    message = update.effective_message
    if not message: return
    photo = message.photo[-1] if message.photo else message.document
    if not photo or (message.document and not (message.document.mime_type or "").startswith("image/")): return
    if photo.file_size and photo.file_size > settings.max_screenshot_bytes:
        await message.reply_text("That screenshot is too large. Please send a smaller image.")
        return
    telegram_file = await photo.get_file()
    data = bytes(await telegram_file.download_as_bytearray())
    if len(data) > settings.max_screenshot_bytes:
        await message.reply_text("That screenshot is too large. Please send a smaller image.")
        return
    try: reference = extract_reference(data)
    except ScreenshotError as exc:
        await message.reply_text(str(exc))
        return
    print(f"OCR extracted transaction reference: {reference}", flush=True)
    await verify(update, context, reference)

def main() -> None:
    settings = Settings.from_env()
    application = Application.builder().token(settings.bot_token).build()
    application.bot_data["settings"] = settings
    application.bot_data["store"] = BillStore(settings.database_path)
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_reference))
    application.add_handler(MessageHandler(filters.PHOTO | filters.Document.IMAGE, image_reference))
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__": main()
