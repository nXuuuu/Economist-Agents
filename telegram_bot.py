"""
Telegram Bot & Push Notification Handler for Economist Multi-Agent Desk.
Strictly authorized to operate in specified TELEGRAM_ALLOWED_CHAT_ID and TELEGRAM_TOPIC_ID.
Uses Telegram HTML Formatting (parse_mode="HTML") for clean bold headers, bullet cards, and zero parsing errors.
"""

import os
import sys
import glob
import logging
import asyncio
import subprocess
import threading
import requests
import re
import html
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
        return True

    effective_chat = update.effective_chat
    if not effective_chat or str(effective_chat.id).strip() != ALLOWED_CHAT_ID:
        logger.warning(f"Unauthorized chat attempt from ID: {effective_chat.id if effective_chat else 'Unknown'}")
        return False

    if TOPIC_ID:
        message = update.message or (update.callback_query.message if update.callback_query else None)
        if message:
            thread_id = getattr(message, 'message_thread_id', None)
            if thread_id is not None and str(thread_id).strip() != TOPIC_ID:
                logger.warning(f"Unauthorized topic attempt from Thread ID: {thread_id} (Expected: {TOPIC_ID})")
                return False
    return True


# ── Helper: Report Content Parsing & HTML Formatting ───────────────────────────
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


def clean_markdown_for_telegram_html(text: str) -> str:
    """
    Converts standard Markdown into pristine Telegram HTML (<b>, <i>, <code>).
    Removes raw asterisks (**), fixes spacing around colons and parentheses, formats list bullets cleanly,
    and styles section headers with executive icons.
    """
    if not text:
        return ""

    lines = text.split("\n")
    cleaned_lines = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            cleaned_lines.append("")
            continue

        # Horizontal Dividers
        if stripped in ("---", "____________________", "--------------------", "════════════════════"):
            cleaned_lines.append("\n──────────────────────────────\n")
            continue

        # Headers (#, ##, ###)
        if stripped.startswith("# "):
            title = html.unescape(stripped[2:].strip())
            title = re.sub(r'\(\s+', '(', title)
            title = re.sub(r'\s+\)', ')', title)
            safe_title = html.escape(title, quote=False)
            cleaned_lines.append(f"\n\n🏛️ <b>{safe_title.upper()}</b>\n")
            continue

        if stripped.startswith("## "):
            title = html.unescape(stripped[3:].strip())
            safe_title = html.escape(title, quote=False)
            if "English" in safe_title:
                cleaned_lines.append(f"\n\n🇬🇧 <b>{safe_title.upper()}</b>\n")
            elif "Khmer" in safe_title or "ខ្មែរ" in safe_title:
                cleaned_lines.append(f"\n\n🇰🇭 <b>{safe_title}</b>\n")
            else:
                cleaned_lines.append(f"\n\n📌 <b>{safe_title.upper()}</b>\n")
            continue

        if stripped.startswith("### "):
            title = html.unescape(stripped[4:].strip())
            safe_title = html.escape(title, quote=False)
            if "Transmission" in safe_title or "1." in safe_title:
                cleaned_lines.append(f"\n\n🔗 <b>{safe_title}</b>\n")
            elif "Phillips" in safe_title or "Labor" in safe_title or "FRED" in safe_title or "2." in safe_title:
                cleaned_lines.append(f"\n\n📉 <b>{safe_title}</b>\n")
            elif "COT" in safe_title or "Positioning" in safe_title or "3." in safe_title:
                cleaned_lines.append(f"\n\n📊 <b>{safe_title}</b>\n")
            elif "Forecast" in safe_title or "Calendar" in safe_title or "4." in safe_title:
                cleaned_lines.append(f"\n\n🎯 <b>{safe_title}</b>\n")
            else:
                cleaned_lines.append(f"\n\n🔹 <b>{safe_title}</b>\n")
            continue

        # Regular Lines: Fix spacing around colons and parentheses
        processed = line
        processed = re.sub(r'\(\s+', '(', processed)
        processed = re.sub(r'\s+\)', ')', processed)
        processed = re.sub(r'(\w)\s+:\s*', r'\1: ', processed)

        # Inline Code `code`
        processed = re.sub(r'`([^`]+)`', lambda m: f"<code>{html.escape(html.unescape(m.group(1).strip()), quote=False)}</code>", processed)
        # Bold **text**
        processed = re.sub(r'\*\*([^*]+)\*\*', lambda m: f"<b>{html.escape(html.unescape(m.group(1).strip()), quote=False)}</b>", processed)
        # Italic *text*
        processed = re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)', lambda m: f"<i>{html.escape(html.unescape(m.group(1).strip()), quote=False)}</i>", processed)

        # Escape non-tagged parts safely
        parts = re.split(r'(</?[a-z]+>)', processed)
        final_parts = []
        for p in parts:
            if p in ("<b>", "</b>", "<i>", "</i>", "<code>", "</code>"):
                final_parts.append(p)
            else:
                final_parts.append(html.escape(html.unescape(p), quote=False))
        processed = "".join(final_parts)

        # Format List Items / Bullets cleanly with extra spacing between numbered steps
        stripped_proc = processed.strip()
        if re.match(r'^\d+\.\s+', stripped_proc):
            processed = "\n" + stripped_proc
        elif stripped_proc.startswith("* ") or stripped_proc.startswith("- "):
            indent = len(processed) - len(processed.lstrip())
            prefix = "  " * (indent // 2) + "• "
            processed = prefix + stripped_proc[2:].strip()

        cleaned_lines.append(processed)


    result = "\n".join(cleaned_lines)
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
    return clean_markdown_for_telegram_html(raw_eng)


def extract_khmer(content: str) -> str:
    """Extract and format Khmer section of the report."""
    if "---KHMER_SECTION---" in content:
        parts = content.split("---KHMER_SECTION---")
        if len(parts) > 1 and parts[1].strip():
            return clean_markdown_for_telegram_html(parts[1].strip())
    elif "## ភាសាខ្មែរ" in content:
        parts = content.split("## ភាសាខ្មែរ")
        if len(parts) > 1 and parts[1].strip():
            kh_text = "## ភាសាខ្មែរ " + parts[1].strip()
            return clean_markdown_for_telegram_html(kh_text)
    elif "## Khmer Version" in content:
        parts = content.split("## Khmer Version")
        if len(parts) > 1 and parts[1].strip():
            kh_text = "## Khmer Version " + parts[1].strip()
            return clean_markdown_for_telegram_html(kh_text)

    return "⚠️ មិនមានកំណែភាសាខ្មែរសម្រាប់របាយការណ៍នេះទេ។ (No Khmer version found for this report.)"


# ── Helper: Safe Telegram Message Chunking (HTML Mode) ─────────────────────────
def send_long_message_sync(chat_id: str, text: str, topic_id: str = None):
    """Send long HTML formatted text via Telegram HTTP API, splitting into <= 3900 char chunks."""
    if not BOT_TOKEN or not chat_id:
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    
    max_len = 3900
    chunks = [text[i:i + max_len] for i in range(0, len(text), max_len)]
    
    for chunk in chunks:
        payload = {
            "chat_id": chat_id,
            "text": chunk,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }
        if topic_id:
            try:
                payload["message_thread_id"] = int(topic_id)
            except ValueError:
                pass
        try:
            res = requests.post(url, json=payload, timeout=10)
            if res.status_code != 200:
                # Retry plain text if HTML parsing encounters any issue
                payload.pop("parse_mode", None)
                payload["text"] = re.sub(r'<[^>]+>', '', chunk)
                requests.post(url, json=payload, timeout=10)
        except Exception as e:
            logger.error(f"Error sending message chunk: {e}")


async def reply_chunks(update: Update, text: str):
    """Reply to an update splitting long text into multiple messages in HTML mode."""
    max_len = 3900
    chunks = [text[i:i + max_len] for i in range(0, len(text), max_len)]
    for chunk in chunks:
        plain_chunk = re.sub(r'<[^>]+>', '', chunk)
        try:
            if update.message:
                await update.message.reply_text(chunk, parse_mode="HTML", disable_web_page_preview=True)
            elif update.callback_query and update.callback_query.message:
                await update.callback_query.message.reply_text(chunk, parse_mode="HTML", disable_web_page_preview=True)
        except Exception:
            if update.message:
                await update.message.reply_text(plain_chunk, disable_web_page_preview=True)
            elif update.callback_query and update.callback_query.message:
                await update.callback_query.message.reply_text(plain_chunk, disable_web_page_preview=True)


# ── Direct Push Notification ──────────────────────────────────────────────────
def push_report_to_telegram(filename: str, complete_report: str, target_chat_id: str = None, target_topic_id: str = None):
    """Push newly generated report notification to Telegram with language buttons."""
    chat_id = target_chat_id or ALLOWED_CHAT_ID
    topic_id = target_topic_id or TOPIC_ID

    if not BOT_TOKEN or not chat_id:
        logger.info("Telegram notification skipped (BOT_TOKEN or Chat ID missing).")
        return

    # Extract Executive Summary section cleanly
    parts = complete_report.split("---KHMER_SECTION---")
    eng_raw = parts[0] if parts else complete_report

    exec_summary_lines = []
    in_exec = False
    for line in eng_raw.split("\n"):
        l_strip = line.strip()
        if "Executive Summary" in l_strip or "ANALYST EXECUTIVE SUMMARY" in l_strip:
            in_exec = True
            continue
        elif in_exec and (l_strip.startswith("#") or "Transmission Chain" in l_strip or l_strip == "---"):
            break
        if in_exec and l_strip:
            exec_summary_lines.append(l_strip)

    if not exec_summary_lines:
        exec_summary_lines = [l.strip() for l in eng_raw.split("\n") if l.strip() and not l.strip().startswith("#")][:3]

    raw_exec_text = "\n\n".join(exec_summary_lines[:3])
    formatted_exec = clean_markdown_for_telegram_html(raw_exec_text)

    caption = (
        f"<b>📊 MR. ECONOMIST FINHUB</b>\n"
        f"<b>📄 Report Reference:</b> <code>{html.escape(filename)}</code>\n"
        f"──────────────────────────────\n\n"
        f"<b>📌 EXECUTIVE SUMMARY</b>\n"
        f"{formatted_exec}\n\n"
        f"──────────────────────────────\n"
        f"👇 <b>Select language version to read complete analysis:</b>"
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
        "chat_id": chat_id,
        "text": caption,
        "parse_mode": "HTML",
        "reply_markup": keyboard,
        "disable_web_page_preview": True
    }
    if topic_id:
        try:
            payload["message_thread_id"] = int(topic_id)
        except ValueError:
            pass

    try:
        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code == 200:
            logger.info(f"Successfully pushed HTML report alert to Telegram ({filename})")
        else:
            logger.error(f"Failed to push HTML Telegram alert: {resp.text}. Retrying plain text...")
            payload.pop("parse_mode", None)
            payload["text"] = re.sub(r'<[^>]+>', '', caption)
            retry_resp = requests.post(url, json=payload, timeout=10)
            if retry_resp.status_code == 200:
                logger.info(f"Successfully pushed report alert on plain text retry ({filename})")
            else:
                logger.error(f"Failed to push plain text alert retry: {retry_resp.text}")
    except Exception as e:
        logger.error(f"Telegram push error: {e}")


# ── Command & Callback Handlers ───────────────────────────────────────────────
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start and /help commands."""
    if not is_authorized(update):
        return

    msg = (
        "<b>📊 MR. ECONOMIST FINHUB</b>\n"
        "<i>Exclusive Executive Macro Intelligence Desk</i>\n"
        "──────────────────────────────\n\n"
        "📖 <b>WORKFLOW 1: READ LATEST ANALYSIS</b>\n"
        "• Type <code>/latest</code> → Select <b>[ 🇬🇧 English ]</b> or <b>[ 🇰🇭 ភាសាខ្មែរ ]</b>\n"
        "• Or type directly: <code>/english</code> or <code>/khmer</code>\n\n"
        "🚀 <b>WORKFLOW 2: LIVE 5-AGENT RESEARCH RUN</b>\n"
        "• Type <code>/run</code> → Triggers live 5-agent research (~2-3 mins)\n"
        "• The bot will automatically post the fresh report card here with language buttons!\n\n"
        "──────────────────────────────\n"
        "💡 <i>Tip: Tap any blue command above to execute instantly!</i>"
    )
    await update.message.reply_text(msg, parse_mode="HTML")


async def latest_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /latest command by showing language selection inline buttons."""
    if not is_authorized(update):
        return

    filename, content = get_latest_report_content()
    if not content:
        await update.message.reply_text("⚠️ <b>No macro reports found in system yet.</b>", parse_mode="HTML")
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
    msg = (
        "<b>📊 MR. ECONOMIST FINHUB</b>\n"
        f"<b>📄 Latest Reference:</b> <code>{html.escape(filename)}</code>\n"
        "──────────────────────────────\n\n"
        "🌐 <b>Select language version to read:</b>"
    )
    await update.message.reply_text(msg, reply_markup=keyboard, parse_mode="HTML")


async def english_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /english command."""
    if not is_authorized(update):
        return

    filename, content = get_latest_report_content()
    if not content:
        await update.message.reply_text("⚠️ <b>No macro reports found in system yet.</b>", parse_mode="HTML")
        return

    english_text = extract_english(content)
    header = (
        "<b>🇬🇧 ENGLISH MACRO ANALYSIS</b>\n"
        f"<b>📄 Reference:</b> <code>{html.escape(filename)}</code>\n"
        "──────────────────────────────\n\n"
    )
    await reply_chunks(update, f"{header}{english_text}")


async def khmer_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /khmer command."""
    if not is_authorized(update):
        return

    filename, content = get_latest_report_content()
    if not content:
        await update.message.reply_text("⚠️ <b>No macro reports found in system yet.</b>", parse_mode="HTML")
        return

    khmer_text = extract_khmer(content)
    header = (
        "<b>🇰🇭 របាយការណ៍វិភាគម៉ាក្រូសេដ្ឋកិច្ច (ភាសាខ្មែរ)</b>\n"
        f"<b>📄 Reference:</b> <code>{html.escape(filename)}</code>\n"
        "──────────────────────────────\n\n"
    )
    await reply_chunks(update, f"{header}{khmer_text}")


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline button clicks for language choice."""
    if not is_authorized(update):
        await update.callback_query.answer("Unauthorized chat.", show_alert=True)
        return

    query = update.callback_query
    await query.answer()

    filename, content = get_latest_report_content()
    if not content:
        await query.message.reply_text("⚠️ <b>No macro reports found in system yet.</b>", parse_mode="HTML")
        return

    data = query.data
    if data == "report_en":
        eng = extract_english(content)
        header = (
            "<b>🇬🇧 ENGLISH MACRO ANALYSIS</b>\n"
            f"<b>📄 Reference:</b> <code>{html.escape(filename)}</code>\n"
            "──────────────────────────────\n\n"
        )
        await reply_chunks(update, f"{header}{eng}")
    elif data == "report_kh":
        khm = extract_khmer(content)
        header = (
            "<b>🇰🇭 របាយការណ៍វិភាគម៉ាក្រូសេដ្ឋកិច្ច (ភាសាខ្មែរ)</b>\n"
            f"<b>📄 Reference:</b> <code>{html.escape(filename)}</code>\n"
            "──────────────────────────────\n\n"
        )
        await reply_chunks(update, f"{header}{khm}")
    elif data == "report_full":
        full_formatted = clean_markdown_for_telegram_html(content)
        header = (
            "<b>📜 FULL DUAL-LANGUAGE REPORT</b>\n"
            f"<b>📄 Reference:</b> <code>{html.escape(filename)}</code>\n"
            "──────────────────────────────\n\n"
        )
        await reply_chunks(update, f"{header}{full_formatted}")


async def run_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /run command to trigger main.py in background."""
    if not is_authorized(update):
        return

    chat_id = str(update.effective_chat.id) if update.effective_chat else ALLOWED_CHAT_ID
    message = update.message or (update.callback_query.message if update.callback_query else None)
    thread_id = str(getattr(message, 'message_thread_id', '')) if message and getattr(message, 'message_thread_id', None) is not None else TOPIC_ID

    msg = (
        "<b>🚀 STARTING 5-AGENT MACRO RESEARCH DESK...</b>\n"
        "──────────────────────────────\n"
        "• Pulling live FRED economic series...\n"
        "• Scraping ForexFactory calendar & forecasts...\n"
        "• Fetching CFTC COT institutional positioning...\n"
        "• Analyzing Gold (GC=F) & DXY price action...\n\n"
        "⏳ <i>Estimated time: ~2-3 minutes. You will be notified here automatically!</i>"
    )
    await update.message.reply_text(msg, parse_mode="HTML")

    def execute_desk():
        try:
            import main as macro_main
            macro_main.main()
        except Exception as e:
            logger.error(f"Error running macro main: {e}")
            send_long_message_sync(
                chat_id=chat_id,
                text=f"⚠️ <b>Macro Research Desk Error:</b> <code>{html.escape(str(e))}</code>",
                topic_id=thread_id
            )

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


_webhook_loop = None
_webhook_thread = None
_loop_lock = threading.Lock()


def get_webhook_event_loop():
    """Get or create persistent background event loop for Webhook execution."""
    global _webhook_loop, _webhook_thread
    with _loop_lock:
        if _webhook_loop is None or _webhook_loop.is_closed():
            _webhook_loop = asyncio.new_event_loop()
            def start_loop(loop):
                asyncio.set_event_loop(loop)
                loop.run_forever()
            _webhook_thread = threading.Thread(target=start_loop, args=(_webhook_loop,), daemon=True)
            _webhook_thread.start()
    return _webhook_loop


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
    """Process incoming JSON payload from Flask /telegram/webhook POST request on persistent event loop."""
    try:
        loop = get_webhook_event_loop()
        asyncio.run_coroutine_threadsafe(process_webhook_update_async(update_dict), loop)
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
