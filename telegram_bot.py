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


def clean_markdown_for_telegram(text: str) -> str:
    """Format standard markdown for Telegram: converts # headers to bold emoji titles and cleans up spacing."""
    if not text:
        return ""

    lines = text.split("\n")
    cleaned_lines = []

    for line in lines:
        stripped = line.strip()
        
        # Header 1 (# ...)
        if stripped.startswith("# "):
            title = stripped[2:].strip().replace(" ( ", " (").replace(" )", ")")
            cleaned_lines.append(f"\n🏛️ **{title.upper()}**\n")
        # Header 2 (## ...)
        elif stripped.startswith("## "):
            title = stripped[3:].strip()
            if "English" in title:
                cleaned_lines.append(f"\n🇬🇧 **{title.upper()}**\n")
            elif "Khmer" in title or "ខ្មែរ" in title:
                cleaned_lines.append(f"\n🇰🇭 **{title}**\n")
            else:
                cleaned_lines.append(f"\n📌 **{title.upper()}**\n")
        # Header 3 (### ...)
        elif stripped.startswith("### "):
            title = stripped[4:].strip()
            if "Transmission" in title or "1." in title:
                cleaned_lines.append(f"\n🔗 **{title}**")
            elif "Phillips" in title or "Labor" in title or "2." in title:
                cleaned_lines.append(f"\n📉 **{title}**")
            elif "COT" in title or "Positioning" in title or "3." in title:
                cleaned_lines.append(f"\n📊 **{title}**")
            elif "Forecast" in title or "4." in title:
                cleaned_lines.append(f"\n🎯 **{title}**")
            else:
                cleaned_lines.append(f"\n🔹 **{title}**")
        elif stripped == "---":
            cleaned_lines.append("──────────────────────────────")
        else:
            # Fix awkward spaces inside parentheses like '( 3.53% )' -> '(3.53%)'
            fixed_line = re.sub(r'\(\s+', '(', line)
            fixed_line = re.sub(r'\s+\)', ')', fixed_line)
            cleaned_lines.append(fixed_line)

    result = "\n".join(cleaned_lines)
    # Remove multiple consecutive blank lines
    result = re.sub(r'\n{3,}', '\n\n', result)
    return result.strip()


def extract_english(content: str) -> str:
    """Extract and format English section of the report."""
    if "---KHMER_SECTION---" in content:
        raw_eng = content.split("---KHMER_SECTION---")[0].strip()
    elif "## ភាសាខ្មែរ" in content:
        raw_eng = content.split("## ភាសាខ្មែរ")[0].strip()
    elif "## Khmer Version" in content:
        raw_eng = content.split("## Khmer Version")[0].strip()
    else:
        raw_eng = content.strip()
    return clean_markdown_for_telegram(raw_eng)


def extract_khmer(content: str) -> str:
    """Extract and format Khmer section of the report."""
    if "---KHMER_SECTION---" in content:
        parts = content.split("---KHMER_SECTION---")
        if len(parts) > 1 and parts[1].strip():
            return clean_markdown_for_telegram(parts[1].strip())
    elif "## ភាសាខ្មែរ" in content:
        parts = content.split("## ភាសាខ្មែរ")
        if len(parts) > 1 and parts[1].strip():
            kh_text = "## ភាសាខ្មែរ " + parts[1].strip()
            return clean_markdown_for_telegram(kh_text)
    elif "## Khmer Version" in content:
        parts = content.split("## Khmer Version")
        if len(parts) > 1 and parts[1].strip():
            kh_text = "## Khmer Version " + parts[1].strip()
            return clean_markdown_for_telegram(kh_text)

    return "⚠️ មិនមានកំណែភាសាខ្មែរសម្រាប់របាយការណ៍នេះទេ។ (No Khmer version found for this report.)"


# ── Helper: Safe Telegram Message Chunking ───────────────────────────────────
def send_long_message_sync(chat_id: str, text: str, topic_id: str = None):
    """Send long markdown text via Telegram HTTP API, splitting into <= 4000 char chunks."""
    if not BOT_TOKEN:
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    
    max_len = 3900
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
                payload.pop("parse_mode", None)
                requests.post(url, json=payload, timeout=10)
        except Exception as e:
            logger.error(f"Error sending message chunk: {e}")


async def reply_chunks(update: Update, text: str):
    """Reply to an update splitting long text into multiple messages."""
    max_len = 3900
    chunks = [text[i:i + max_len] for i in range(0, len(text), max_len)]
    for chunk in chunks:
        try:
            if update.message:
                await update.message.reply_text(chunk, parse_mode="Markdown", disable_web_page_preview=True)
            elif update.callback_query and update.callback_query.message:
                await update.callback_query.message.reply_text(chunk, parse_mode="Markdown", disable_web_page_preview=True)
        except Exception:
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

    formatted_summary = extract_english(complete_report)
    lines = [l for l in formatted_summary.split("\n") if l.strip()]
    
    # Extract executive summary bullet points
    brief_lines = []
    for l in lines[:15]:
        if "GLOBAL MACRO" in l or "ENGLISH VERSION" in l:
            continue
        brief_lines.append(l)
    
    brief_text = "\n".join(brief_lines)[:900]

    caption = (
        f"📊 **MR. ECONOMIST FINHUB**\n"
        f"📄 *Report Reference:* `{filename}`\n"
        f"──────────────────────────────\n\n"
        f"{brief_text}\n\n"
        f"──────────────────────────────\n"
        f"👇 *Select language version to read complete analysis:*"
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


# ── Webhook Registration & Processing ───────────────────────────────────────
def setup_webhook(host_url: str):
    """Register Webhook URL with Telegram API for on-demand cold starts."""
    if not BOT_TOKEN or not host_url:
        return
    clean_host = host_url.strip().rstrip('/')
    webhook_url = f"{clean_host}/telegram/webhook"
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook?url={webhook_url}"
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            logger.info(f"Registered Telegram Webhook: {webhook_url}")
        else:
            logger.error(f"Failed to register Webhook: {resp.text}")
    except Exception as e:
        logger.error(f"Error setting Webhook: {e}")


_telegram_app = None

def get_telegram_application():
    global _telegram_app
    if _telegram_app is None:
        if not BOT_TOKEN:
            return None
        _telegram_app = Application.builder().token(BOT_TOKEN).build()
        _telegram_app.add_handler(CommandHandler(["start", "help"], start_command))
        _telegram_app.add_handler(CommandHandler("latest", latest_command))
        _telegram_app.add_handler(CommandHandler(["english", "report_en"], english_command))
        _telegram_app.add_handler(CommandHandler(["khmer", "report_kh"], khmer_command))
        _telegram_app.add_handler(CommandHandler("run", run_command))
        _telegram_app.add_handler(CallbackQueryHandler(button_callback))
    return _telegram_app


async def process_webhook_update_async(update_dict: dict):
    app = get_telegram_application()
    if not app:
        return
    if not getattr(app, '_initialized', False):
        await app.initialize()
        await app.start()
    update = Update.de_json(update_dict, app.bot)
    await app.process_update(update)


def process_webhook_update(update_dict: dict):
    """Process incoming JSON payload from Flask /telegram/webhook POST request."""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(process_webhook_update_async(update_dict))
        loop.close()
    except Exception as e:
        logger.error(f"Error processing webhook update: {e}")


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


