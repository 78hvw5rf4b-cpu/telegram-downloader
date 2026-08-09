import os
import logging
import asyncio
import threading
import json
import glob
from flask import Flask
import yt_dlp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

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

# --- نظام حفظ وإحصاء عدد المستخدمين ---
USERS_FILE = "users_data.json"

def load_users():
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, "r") as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()

def save_users(users_set):
    try:
        with open(USERS_FILE, "w") as f:
            json.dump(list(users_set), f)
    except Exception as e:
        logging.error(f"Error saving users: {e}")

users_list = load_users()

def register_user(user_id):
    if user_id not in users_list:
        users_list.add(user_id)
        save_users(users_list)

# --- الأزرار والقائمة الموحدة ---

def get_main_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("🚀 البدء / Start", callback_data="cmd_start"),
            InlineKeyboardButton("📊 الإحصائيات", callback_data="cmd_stats")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    register_user(user_id)
    await update.message.reply_text(
        "أهلاً بك في بوت Abu na9r! 🖐️\nاختر من القائمة أدناه أو أرسل رابط المقطع مباشرة للتحميل:",
        reply_markup=get_main_keyboard()
    )

async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    register_user(user_id)

    if query.data == "cmd_start":
        await query.message.reply_text("أهلاً بك مجدداً! أرسل رابط المقطع للتحميل (Shorts / X / TikTok ...)", reply_markup=get_main_keyboard())
    elif query.data == "cmd_stats":
        total_users = len(users_list)
        await query.message.reply_text(f"📊 **إحصائيات البوت:**\n\nعدد الأشخاص الذين استخدموا البوت: {total_users}", reply_markup=get_main_keyboard())

# --- دالة التحميل المباشر باستخدام yt-dlp المطور ---

def download_video_file(url: str, output_pattern: str):
    ydl_opts = {
        'format': 'b[ext=mp4]/best[ext=mp4]/best',
        'outtmpl': output_pattern,
        'quiet': True,
        'no_warnings': True,
        'nocheckcertificate': True,
        'geo_bypass': True,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Accept-Language': 'en-US,en;q=0.9',
        }
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    register_user(user_id)

    text = update.message.text.strip()
    if not (text.startswith("http://") or text.startswith("https://")):
        await update.message.reply_text("الرجاء إرسال رابط فيديو صحيح.", reply_markup=get_main_keyboard())
        return

    status_msg = await update.message.reply_text("⏳ جاري جلب وتحميل المقطع، انتظر قليلاً...")
    chat_id = update.message.chat_id
    output_pattern = f"video_{chat_id}_%(id)s.%(ext)s"

    try:
        await asyncio.to_thread(download_video_file, text, output_pattern)

        files = glob.glob(f"video_{chat_id}_*")
        if not files:
            await status_msg.edit_text("❌ تعذر تحميل المقطع. تأكد من صحة الرابط أو أن الحساب ليس خاصاً.", reply_markup=get_main_keyboard())
            return

        video_path = files[0]

        # التأكد من حجم الملف (حد تليجرام 50MB)
        file_size = os.path.getsize(video_path) / (1024 * 1024)
        if file_size > 50:
            await status_msg.edit_text("❌ حجم الفيديو كبير جداً (يتجاوز 50 ميجابايت).", reply_markup=get_main_keyboard())
            os.remove(video_path)
            return

        await status_msg.edit_text("⬆️ جاري إرسال الفيديو...")

        with open(video_path, 'rb') as video:
            await update.message.reply_video(video=video)

        os.remove(video_path)
        await status_msg.delete()

    except Exception as e:
        logging.error(f"Error handling video: {e}")
        await status_msg.edit_text("❌ حدث خطأ أثناء التحميل. حاول إرسال الرابط مرة أخرى.", reply_markup=get_main_keyboard())
        for f in glob.glob(f"video_{chat_id}_*"):
            try:
                os.remove(f)
            except Exception:
                pass

def main():
    token = os.environ.get("BOT_TOKEN")
    if not token:
        print("خطأ: لم يتم العثور على BOT_TOKEN!")
        return

    application = Application.builder().token(token).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("stats", start))
    application.add_handler(CallbackQueryHandler(button_click))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    application.run_polling()

if __name__ == "__main__":
    main()
