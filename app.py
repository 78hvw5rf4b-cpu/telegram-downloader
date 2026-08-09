import os
import logging
import asyncio
import threading
import json
import requests
from flask import Flask
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

# --- آلية جلب وتحميل مقاطع الفيديو ---

def download_file(url: str, dest_path: str):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    response = requests.get(url, stream=True, timeout=30, headers=headers)
    response.raise_for_status()
    with open(dest_path, 'wb') as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)

def get_video_url_from_api(video_url: str):
    # المحرك الأول
    try:
        api_url = "https://api.cobalt.tools/api/json"
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0"
        }
        payload = {"url": video_url, "vQuality": "720"}
        res = requests.post(api_url, json=payload, headers=headers, timeout=12)
        if res.status_code == 200:
            data = res.json()
            if "url" in data:
                return data["url"]
            elif "picker" in data and len(data["picker"]) > 0:
                return data["picker"][0]["url"]
    except Exception as e:
        logging.error(f"Primary API error: {e}")

    # المحرك الاحتياطي المباشر
    try:
        backup_api = f"https://api.vxtwitter.com/status" if "twitter.com" in video_url or "x.com" in video_url else None
        if backup_api and ("/status/" in video_url):
            tweet_id = video_url.split("/status/")[1].split("?")[0]
            res = requests.get(f"https://api.vxtwitter.com/i/status/{tweet_id}", timeout=10)
            if res.status_code == 200:
                data = res.json()
                if "media_extended" in data and len(data["media_extended"]) > 0:
                    return data["media_extended"][0]["url"]
    except Exception as e:
        logging.error(f"Backup API error: {e}")

    return None

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    register_user(user_id)

    text = update.message.text.strip()
    if not (text.startswith("http://") or text.startswith("https://")):
        await update.message.reply_text("الرجاء إرسال رابط فيديو صحيح.", reply_markup=get_main_keyboard())
        return

    status_msg = await update.message.reply_text("⏳ جاري جلب وتحميل المقطع، انتظر قليلاً...")
    chat_id = update.message.chat_id
    output_file = f"video_{chat_id}.mp4"

    try:
        video_download_url = await asyncio.to_thread(get_video_url_from_api, text)

        if not video_download_url:
            await status_msg.edit_text("❌ تعذر جلب المقطع. تأكد من أن الرابط يعمل وأن المقطع ليس من حساب خاص مغلق.", reply_markup=get_main_keyboard())
            return

        await asyncio.to_thread(download_file, video_download_url, output_file)

        # التأكد من حجم الملف (حد تليجرام 50MB)
        file_size = os.path.getsize(output_file) / (1024 * 1024)
        if file_size > 50:
            await status_msg.edit_text("❌ حجم الفيديو كبير جداً (يتجاوز 50 ميجابايت).", reply_markup=get_main_keyboard())
            os.remove(output_file)
            return

        await status_msg.edit_text("⬆️ جاري إرسال الفيديو...")

        with open(output_file, 'rb') as video:
            await update.message.reply_video(video=video)

        os.remove(output_file)
        await status_msg.delete()

    except Exception as e:
        logging.error(f"Error handling video: {e}")
        await status_msg.edit_text("❌ حدث خطأ أثناء تحميل الفيديو. حاول إرسال الرابط مرة أخرى.", reply_markup=get_main_keyboard())
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
    application.add_handler(CommandHandler("stats", start))
    application.add_handler(CallbackQueryHandler(button_click))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    application.run_polling()

if __name__ == "__main__":
    main()
