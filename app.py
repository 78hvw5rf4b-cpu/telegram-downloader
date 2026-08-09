import os
import logging
import asyncio
import threading
import glob
import json
import requests
from flask import Flask
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

# --- نظام حفظ وإحصاء المستخدمين ---
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

# --- الأوامر الأساسية ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    register_user(user_id)
    await update.message.reply_text("أهلاً معك بوت Abu na9r، أرسل رابط المقطع للتحميل.")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    register_user(user_id)
    total_users = len(users_list)
    await update.message.reply_text(f"📊 **إحصائيات البوت:**\n\nعدد الأشخاص الذين استخدموا البوت: {total_users}")

# --- آلية التحميل المباشرة التلقائية ---

def download_file(url: str, dest_path: str):
    response = requests.get(url, stream=True, timeout=30)
    response.raise_for_status()
    with open(dest_path, 'wb') as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    register_user(user_id)

    text = update.message.text.strip()
    if not (text.startswith("http://") or text.startswith("https://")):
        await update.message.reply_text("الرجاء إرسال رابط فيديو صحيح.")
        return

    status_msg = await update.message.reply_text("⏳ جاري جلب وتحميل المقطع، انتظر قليلاً...")
    chat_id = update.message.chat_id
    output_file = f"video_{chat_id}.mp4"

    try:
        # استخدام Cobalt API المفتوح لتجاوز حظر يوتيوب/X السحابي
        api_url = "https://api.cobalt.tools/api/json"
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        payload = {
            "url": text,
            "vQuality": "720"
        }

        res = await asyncio.to_thread(requests.post, api_url, json=payload, headers=headers, timeout=15)
        data = res.json()

        if "url" not in data:
            await status_msg.edit_text("❌ تعذر تحميل هذا الرابط. تأكد أن المقطع ليس من حساب خاص.")
            return

        video_download_url = data["url"]

        await asyncio.to_thread(download_file, video_download_url, output_file)

        file_size = os.path.getsize(output_file) / (1024 * 1024)
        if file_size > 50:
            await status_msg.edit_text("❌ حجم الفيديو كبير جداً (يتجاوز 50 ميجابايت).")
            os.remove(output_file)
            return

        await status_msg.edit_text("⬆️ جاري إرسال الفيديو...")

        with open(output_file, 'rb') as video:
            await update.message.reply_video(video=video)

        os.remove(output_file)
        await status_msg.delete()

    except Exception as e:
        logging.error(f"Error handling video: {e}")
        await status_msg.edit_text("❌ حدث خطأ أثناء جلب الفيديو. جرب رابطاً آخر.")
        if os.path.exists(output_file):
            try:
                os.remove(output_file)
            except Exception:
                pass

def main():
    token = os.environ.get("BOT_TOKEN")
    if not token:
        print("خطأ: لم يتم العثور على BOT_TOKEN!")
        return

    application = Application.builder().token(token).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    application.run_polling()

if __name__ == "__main__":
    main()
