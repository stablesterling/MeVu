import logging
import os
import threading
import asyncio
from flask import Flask, send_from_directory, request, jsonify
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from yt_dlp import YoutubeDL

# -----------------------
# Config
# -----------------------
BOT_TOKEN = os.getenv("BOT_TOKEN", "8438947587:AAF798xzM76oR8_TY8UyP7u_FpjeFLF7Kss")
DOWNLOAD_PATH = './downloads'
os.makedirs(DOWNLOAD_PATH, exist_ok=True)

# -----------------------
# Logging
# -----------------------
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# -----------------------
# YouTube DL Options
# -----------------------
YDL_OPTS_SEARCH = {
    'format': 'bestaudio/best',
    'quiet': True,
    'noplaylist': True,
    'default_search': 'ytsearch10',
}

# -----------------------
# Telegram Bot Handlers
# -----------------------
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎶 *Welcome to VoFo Music Bot!*\n\n"
        "Send me any *song name or artist* and I’ll fetch and stream it for you instantly! 🎧",
        parse_mode='Markdown'
    )

async def handle_music_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip()
    if not query:
        await update.message.reply_text("❌ Please send a valid song name.")
        return

    msg = await update.message.reply_text(f"🔍 Searching for *{query}* ...", parse_mode='Markdown')

    try:
        with YoutubeDL(YDL_OPTS_SEARCH) as ydl:
            results = ydl.extract_info(query, download=False).get("entries", [])
            if not results:
                await msg.edit_text(f"⚠️ No results found for '{query}'")
                return

        video = results[0]
        title, url = video["title"], video["webpage_url"]

        await msg.edit_text(f"🎵 Fetching stream for: *{title}* ...", parse_mode='Markdown')

        # Extract direct audio stream URL (no download)
        with YoutubeDL({"format": "bestaudio", "quiet": True}) as ydl:
            info = ydl.extract_info(url, download=False)
            audio_url = info.get("url")

        if not audio_url:
            await msg.edit_text("❌ Failed to get audio stream URL.")
            return

        await update.message.reply_audio(
            audio=audio_url,
            caption=f"🎶 *{title}*\n\n▶️ Streamed by VoFo",
            parse_mode='Markdown'
        )

        await msg.edit_text(f"✅ Streaming: *{title}*", parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Error: {e}")
        await msg.edit_text("❌ Failed to play or stream song. Try again later.")

# -----------------------
# Flask Frontend + API
# -----------------------
app = Flask(__name__, static_folder=".", static_url_path="")

@app.route("/")
def serve_index():
    return send_from_directory(".", "index.html")

@app.route("/search", methods=["GET"])
def api_search():
    query = request.args.get("q", "")
    if not query:
        return jsonify([])

    try:
        with YoutubeDL(YDL_OPTS_SEARCH) as ydl:
            info = ydl.extract_info(query, download=False)
            entries = [{"id": v["id"], "title": v["title"]} for v in info.get("entries", [])]
            return jsonify(entries)
    except Exception as e:
        logger.error(f"Search error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/stream/<video_id>")
def api_stream(video_id):
    try:
        with YoutubeDL({"format": "bestaudio", "quiet": True}) as ydl:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
            return jsonify({"audio_url": info.get("url")})
    except Exception as e:
        logger.error(f"Stream error: {e}")
        return jsonify({"error": str(e)}), 500

# -----------------------
# Helper Functions
# -----------------------
async def reset_webhook(token):
    """Delete existing Telegram webhook before polling to avoid 409 conflict"""
    bot = Bot(token)
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("✅ Bot webhook/session reset")

def run_flask():
    """Run Flask app in a background thread"""
    app.run(host="0.0.0.0", port=8080)

# -----------------------
# Start Flask + Telegram
# -----------------------
def main():
    # Reset webhook (fixes 409 Conflict)
    asyncio.run(reset_webhook(BOT_TOKEN))

    # Start Flask frontend
    threading.Thread(target=run_flask, daemon=True).start()

    # Start Telegram Bot
    logger.info("🚀 Telegram bot running with polling...")
    app_bot = Application.builder().token(BOT_TOKEN).build()
    app_bot.add_handler(CommandHandler("start", start_command))
    app_bot.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_music_search))
    app_bot.run_polling(allowed_updates=None)

if __name__ == "__main__":
    main()
