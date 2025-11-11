import logging
import os
import threading
import pygame
from flask import Flask, send_from_directory, request, jsonify
from telegram import Update
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
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
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

YDL_OPTS_DOWNLOAD = {
    'format': 'bestaudio/best',
    'outtmpl': f"{DOWNLOAD_PATH}/%(title)s.%(ext)s",
    'quiet': True,
    'noplaylist': True,
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '192',
    }],
}

# -----------------------
# Telegram Bot Handlers
# -----------------------
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎶 *Welcome to VoFo Music Bot!*\n\n"
        "Send me any *song name or artist* and I’ll fetch, download, and play it automatically! 🎧",
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

        await msg.edit_text(f"🎵 Downloading: *{title}* ...", parse_mode='Markdown')

        with YoutubeDL(YDL_OPTS_DOWNLOAD) as ydl:
            info = ydl.extract_info(url)
            filename = ydl.prepare_filename(info).replace(".webm", ".mp3").replace(".m4a", ".mp3")

        try:
            pygame.mixer.init()
            pygame.mixer.music.load(filename)
            pygame.mixer.music.play()
        except Exception:
            logger.warning("⚠️ Server environment does not support audio playback (expected on cloud).")

        await update.message.reply_audio(
            audio=open(filename, 'rb'),
            caption=f"🎶 *{title}*\n\nPowered by VoFo 🎧",
            parse_mode='Markdown'
        )

        await msg.edit_text(f"✅ Finished '{title}'")

    except Exception as e:
        logger.error(f"Error: {e}")
        await msg.edit_text("❌ Failed to play or send song. Try again later.")

# -----------------------
# Flask Frontend + API
# -----------------------
app = Flask(__name__, static_folder=".", static_url_path="")

@app.route("/")
def serve_index():
    return send_from_directory(".", "index.html")

@app.route("/search", methods=["GET", "POST"])
def api_search():
    query = request.args.get("q") or request.form.get("query", "")
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

def run_flask():
    app.run(host="0.0.0.0", port=8080)

# -----------------------
# Start Flask + Telegram
# -----------------------
def main():
    # Start Flask in a background thread
    threading.Thread(target=run_flask, daemon=True).start()

    # Run Telegram bot in main thread
    logger.info("🚀 Telegram bot running...")
    app_bot = Application.builder().token(BOT_TOKEN).build()
    app_bot.add_handler(CommandHandler("start", start_command))
    app_bot.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_music_search))
    app_bot.run_polling(allowed_updates=None)

if __name__ == "__main__":
    main()