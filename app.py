import os
import logging
import asyncio
import threading
import glob
from flask import Flask
import yt_dlp
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# --- سيرفر Flask لإرضاء Render ومنعه من الإغلاق ---
app_web = Flask(__name__)

@app_web.route('/')
def home():
    return "Bot is alive!"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app_web.run(host="0.0.0.0", port=port)

threading.Thread(target=run_web, daemon=True).start()
# ------------------------------------------------

logging.basicConfig(level=logging.INFO)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("أهلاً معك بوت Abu na9r ارسل رابط المقطع")

def download_video_file(url: str, output_pattern: str):
    ydl_opts = {
        # صيغة تعمل بكفاءة مع X (Twitter) واليوتيوب Shorts وتيك توك وانستجرام
        'format': 'best[ext=mp4]/best',
        'outtmpl': output_pattern,
        'quiet': True,
        'no_warnings': True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text.strip()
    if not (text.startswith("http://") or text.startswith("https://")):
        await update.message.reply_text("الرجاء إرسال رابط فيديو صحيح.")
        return

    status_msg = await update.message.reply_text("⏳ جاري تحميل الفيديو، انتظر قليلاً...")
    chat_id = update.message.chat_id
    output_pattern = f"video_{chat_id}_%(id)s.%(ext)s"

    try:
        await asyncio.to_thread(download_video_file, text, output_pattern)

        files = glob.glob(f"video_{chat_id}_*")
        if not files:
            await status_msg.edit_text("❌ تعذر تحميل الفيديو. تأكد من صحة الرابط أو أن الحساب ليس خاصاً.")
            return

        video_path = files[0]
        
        # التأكد من حجم الملف (حد تليجرام المباشر 50MB)
        file_size = os.path.getsize(video_path) / (1024 * 1024)
        if file_size > 50:
            await status_msg.edit_text("❌ حجم الفيديو كبير جداً (يتجاوز 50 ميجابايت).")
            os.remove(video_path)
            return

        await status_msg.edit_text("⬆️ جاري إرسال الفيديو...")

        with open(video_path, 'rb') as video:
            await update.message.reply_video(video=video)

        os.remove(video_path)
        await status_msg.delete()

    except Exception as e:
        logging.error(f"Error: {e}")
        await status_msg.edit_text("❌ حدث خطأ أثناء تحميل الفيديو.")
        for f in glob.glob(f"video_{chat_id}_*"):
            try:
                os.remove(f)
            except Exception:
                pass

def main():
    token = os.environ.get("BOT_TOKEN")
    if not token:
        print("خطأ: لم يتم العثور على BOT_TOKEN في متغيرات البيئة!")
        return

    application = Application.builder().token(token).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    application.run_polling()

if __name__ == "__main__":
    main()
