"""
Telegram Bot & Push Notification Handler for Economist Multi-Agent Desk.
Strictly authorized to operate in specified TELEGRAM_ALLOWED_CHAT_ID and TELEGRAM_TOPIC_ID.
"""

import os
import sys
import glob
import logging
import asyncio
import subprocess
import threading
import requests
from dotenv import load_dotenv

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

load_dotenv()

# Set up logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Credentials & Channel/Topic Restrictions
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
ALLOWED_CHAT_ID = os.environ.get("TELEGRAM_ALLOWED_CHAT_ID", "").strip()
TOPIC_ID = os.environ.get("TELEGRAM_TOPIC_ID", "").strip()


# ── Helper: Authorization Check ───────────────────────────────────────────────
def is_authorized(update: Update) -> bool:
    """Verify that incoming command/query is strictly from the configured Chat ID and Topic ID."""
    if not ALLOWED_CHAT_ID:
        # If no restriction configured, allow execution
        return True

    effective_chat = update.effective_chat
    if not effective_chat or str(effective_chat.id) != ALLOWED_CHAT_ID:
        logger.warning(f"Unauthorized chat attempt from ID: {effective_chat.id if effective_chat else 'Unknown'}")
        return False

    if TOPIC_ID:
        message = update.message or (update.callback_query.message if update.callback_query else None)
        if message:
            thread_id = getattr(message, 'message_thread_id', None)
            if thread_id is not None and str(thread_id) != TOPIC_ID:
                logger.warning(f"Unauthorized topic attempt from Thread ID: {thread_id} (Expected: {TOPIC_ID})")
                return False
    return True


# ── Helper: Report Content Parsing ────────────────────────────────────────────
def get_latest_report_file() -> str:
    """Locate the path of the latest macro_report_X.md file."""
    reports_dir = "reports"
    if not os.path.exists(reports_dir):
        return ""
    files = [f for f in os.listdir(reports_dir) if f.startswith("macro_report_") and f.endswith(".md")]
    if not files:
        return ""
    try:
        files.sort(key=lambda x: int(x.split("_")[-1].replace(".md", "")) if "_" in x else 0)
    except Exception:
        files.sort()
    return os.path.join(reports_dir, files[-1])


def get_latest_report_content() -> tuple[str, str]:
    """Read the latest report and return (filename, complete_content)."""
    filepath = get_latest_report_file()
    if not filepath or not os.path.exists(filepath):
        return "", ""
    filename = os.path.basename(filepath)
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    return filename, content


def extract_english(content: str) -> str:
    """Extract English section of the report."""
    parts = content.split("---KHMER_SECTION---")
    return parts[0].strip() if parts else content.strip()


def extract_khmer(content: str) -> str:
    """Extract Khmer section of the report."""
    parts = content.split("---KHMER_SECTION---")
    if len(parts) > 1 and parts[1].strip():
        return parts[1].strip()
    return "⚠️ មិនមានកំណែភាសាខ្មែរសម្រាប់របាយការណ៍នេះទេ។ (No Khmer version found for this report.)"


# ── Helper: Safe Telegram Message Chunking ───────────────────────────────────
def send_long_message_sync(chat_id: str, text: str, topic_id: str = None):
    """Send long markdown text via Telegram HTTP API, splitting into <= 4000 char chunks."""
    if not BOT_TOKEN:
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    
    # Split text into chunks
    max_len = 4000
    chunks = [text[i:i + max_len] for i in range(0, len(text), max_len)]
    
    for chunk in chunks:
        payload = {
            "chat_id": chat_id,
            "text": chunk,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True
        }
        if topic_id:
            payload["message_thread_id"] = int(topic_id)
        try:
            res = requests.post(url, json=payload, timeout=10)
            if res.status_code != 200:
                # Retry without markdown if parsing error
                payload.pop("parse_mode", None)
                requests.post(url, json=payload, timeout=10)
        except Exception as e:
            logger.error(f"Error sending message chunk: {e}")


async def reply_chunks(update: Update, text: str):
    """Reply to an update splitting long text into multiple messages."""
    max_len = 4000
    chunks = [text[i:i + max_len] for i in range(0, len(text), max_len)]
    for chunk in chunks:
        try:
            if update.message:
                await update.message.reply_text(chunk, parse_mode="Markdown", disable_web_page_preview=True)
            elif update.callback_query and update.callback_query.message:
                await update.callback_query.message.reply_text(chunk, parse_mode="Markdown", disable_web_page_preview=True)
        except Exception:
            # Fallback without markdown formatting if Telegram markdown parser fails
            if update.message:
                await update.message.reply_text(chunk, disable_web_page_preview=True)
            elif update.callback_query and update.callback_query.message:
                await update.callback_query.message.reply_text(chunk, disable_web_page_preview=True)


# ── Direct Push Notification ──────────────────────────────────────────────────
def push_report_to_telegram(filename: str, complete_report: str):
    """Push newly generated report notification to Telegram with language buttons."""
    if not BOT_TOKEN or not ALLOWED_CHAT_ID:
        logger.info("Telegram notification skipped (BOT_TOKEN or ALLOWED_CHAT_ID missing).")
        return

    summary = extract_english(complete_report)
    lines = summary.split("\n")
    exec_summary = []
    for line in lines[:25]:
        exec_summary.append(line)
    brief_text = "\n".join(exec_summary)

    caption = (
        f"📊 **Mr. Economist FINHUB**\n"
        f"📄 *New Report:* `{filename}`\n\n"
        f"{brief_text[:1200]}\n\n"
        f"👇 *Choose language version to read full report:*"
    )

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    keyboard = {
        "inline_keyboard": [
            [
                {"text": "🇬🇧 English", "callback_data": "report_en"},
                {"text": "🇰🇭 ភាសាខ្មែរ", "callback_data": "report_kh"}
            ],
            [
                {"text": "📜 Full Dual-Language", "callback_data": "report_full"}
            ]
        ]
    }
    
    payload = {
        "chat_id": ALLOWED_CHAT_ID,
        "text": caption,
        "parse_mode": "Markdown",
        "reply_markup": keyboard,
        "disable_web_page_preview": True
    }
    if TOPIC_ID:
        payload["message_thread_id"] = int(TOPIC_ID)

    try:
        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code == 200:
            logger.info(f"Successfully pushed report alert to Telegram ({filename})")
        else:
            logger.error(f"Failed to push Telegram alert: {resp.text}")
    except Exception as e:
        logger.error(f"Telegram push error: {e}")


# ── Command & Callback Handlers ───────────────────────────────────────────────
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start and /help commands."""
    if not is_authorized(update):
        return

    msg = (
        "📊 **Mr. Economist FINHUB**\n"
        "_Exclusive Team Intelligence Desk_\n\n"
        "📖 **Workflow 1: Read Latest Existing Report**\n"
        "• Type `/latest` → Select **[ 🇬🇧 English ]** or **[ 🇰🇭 ភាសាខ្មែរ ]**\n"
        "• Or type directly: `/english` or `/khmer`\n\n"
        "🚀 **Workflow 2: Run New Live Analysis**\n"
        "• Type `/run` → Triggers live 5-agent research (~2-3 mins)\n"
        "• The bot will automatically post the fresh report here with language buttons!\n\n"
        "💡 _Tip: Tap any command above to execute instantly!_"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")


async def latest_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /latest command by showing language selection inline buttons."""
    if not is_authorized(update):
        return

    filename, content = get_latest_report_content()
    if not content:
        await update.message.reply_text("⚠️ No macro reports found in system yet.")
        return

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🇬🇧 English", callback_data="report_en"),
            InlineKeyboardButton("🇰🇭 ភាសាខ្មែរ", callback_data="report_kh")
        ],
        [
            InlineKeyboardButton("📜 Full Dual-Language", callback_data="report_full")
        ]
    ])
    await update.message.reply_text(
        f"📊 **Latest Report:** `{filename}`\n🌐 Please select language:",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )


async def english_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /english command."""
    if not is_authorized(update):
        return

    filename, content = get_latest_report_content()
    if not content:
        await update.message.reply_text("⚠️ No macro reports found in system yet.")
        return

    english_text = extract_english(content)
    await reply_chunks(update, f"🇬🇧 **English Macro Analysis ({filename})**\n\n{english_text}")


async def khmer_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /khmer command."""
    if not is_authorized(update):
        return

    filename, content = get_latest_report_content()
    if not content:
        await update.message.reply_text("⚠️ No macro reports found in system yet.")
        return

    khmer_text = extract_khmer(content)
    await reply_chunks(update, f"🇰🇭 **របាយការណ៍វិភាគម៉ាក្រូសេដ្ឋកិច្ច ({filename})**\n\n{khmer_text}")


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline button clicks for language choice."""
    if not is_authorized(update):
        await update.callback_query.answer("Unauthorized chat.", show_alert=True)
        return

    query = update.callback_query
    await query.answer()

    filename, content = get_latest_report_content()
    if not content:
        await query.message.reply_text("⚠️ No macro reports found in system yet.")
        return

    data = query.data
    if data == "report_en":
        eng = extract_english(content)
        await reply_chunks(update, f"🇬🇧 **English Macro Analysis ({filename})**\n\n{eng}")
    elif data == "report_kh":
        khm = extract_khmer(content)
        await reply_chunks(update, f"🇰🇭 **របាយការណ៍វិភាគម៉ាក្រូសេដ្ឋកិច្ច ({filename})**\n\n{khm}")
    elif data == "report_full":
        await reply_chunks(update, f"📜 **Full Macro Report ({filename})**\n\n{content}")


async def run_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /run command to trigger main.py in background."""
    if not is_authorized(update):
        return

    await update.message.reply_text("🚀 **Starting 5-Agent Macro Research Desk...**\nYou will be notified here once the report is generated!")

    def execute_desk():
        try:
            subprocess.run([sys.executable, "main.py"], check=True)
        except Exception as e:
            logger.error(f"Error running main.py: {e}")

    thread = threading.Thread(target=execute_desk)
    thread.daemon = True
    thread.start()


# ── Main Bot Runner ───────────────────────────────────────────────────────────
def main():
    if not BOT_TOKEN:
        print("Error: TELEGRAM_BOT_TOKEN environment variable is not set in .env.")
        print("Please configure TELEGRAM_BOT_TOKEN and TELEGRAM_ALLOWED_CHAT_ID.")
        return

    print(f"Starting Telegram Bot... (Authorized Chat: {ALLOWED_CHAT_ID or 'ALL'}, Topic: {TOPIC_ID or 'ANY'})")
    
    # Create dedicated event loop for background thread execution
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler(["start", "help"], start_command))
    app.add_handler(CommandHandler("latest", latest_command))
    app.add_handler(CommandHandler(["english", "report_en"], english_command))
    app.add_handler(CommandHandler(["khmer", "report_kh"], khmer_command))
    app.add_handler(CommandHandler("run", run_command))
    app.add_handler(CallbackQueryHandler(button_callback))

    # Disable signal handling so polling works inside secondary/daemon Gunicorn threads
    app.run_polling(stop_signals=None)


if __name__ == "__main__":
    main()

