import os
import logging
import asyncio
import threading
import glob
import time
import requests
from flask import Flask
import yt_dlp
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

CHANNEL_USERNAME = "@Abu_na9r"
CHANNEL_LINK = "https://t.me/Abu_na9r"

# --- سيرفر Flask لضمان التشغيل 24/7 ---
app_web = Flask(__name__)

@app_web.route('/')
def home():
    return "Bot is alive 24/7!"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app_web.run(host="0.0.0.0", port=port)

def self_ping():
    time.sleep(10)
    render_url = os.environ.get("RENDER_EXTERNAL_URL")
    while True:
        try:
            if render_url:
                requests.get(render_url, timeout=10)
            else:
                requests.get("http://127.0.0.1:10000", timeout=10)
        except Exception:
            pass
        time.sleep(300)

threading.Thread(target=run_web, daemon=True).start()
threading.Thread(target=self_ping, daemon=True).start()
# ----------------------------------------

logging.basicConfig(level=logging.INFO)

def register_user(context: ContextTypes.DEFAULT_TYPE, user_id: int):
    if "all_users" not in context.bot_data:
        context.bot_data["all_users"] = set()
    context.bot_data["all_users"].add(user_id)

async def is_subscribed(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
    try:
        member = await context.bot.get_chat_member(chat_id=CHANNEL_USERNAME, user_id=user_id)
        if member.status in ['creator', 'administrator', 'member']:
            return True
    except Exception as e:
        logging.error(f"Subscription Check Error: {e}")
        return True
    return False

def get_bottom_keyboard():
    keyboard = [
        [KeyboardButton("📥 تحميل فيديو / صورة"), KeyboardButton("📢 قناة التحديثات")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

async def post_init(application: Application):
    commands = [
        BotCommand("start", "البدء / القائمة الرئيسية"),
        BotCommand("ai", "سؤال الذكاء الاصطناعي"),
        BotCommand("stats", "إحصائيات البوت"),
    ]
    await application.bot.set_my_commands(commands)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    register_user(context, user_id)

    if not await is_subscribed(context, user_id):
        await update.message.reply_text(f"⚠️ يجب عليك الاشتراك في القناة أولاً:\n{CHANNEL_LINK}")
        return

    await update.message.reply_text(
        "أهلاً بك! 🖐️\nاختر الخدمة من الأزرار بالأسفل، أو أرسل رابطاً مباشراً للتحميل:",
        reply_markup=get_bottom_keyboard()
    )

async def ai_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    register_user(context, user_id)

    if not await is_subscribed(context, user_id):
        await update.message.reply_text(f"⚠️ يجب عليك الاشتراك في القناة أولاً:\n{CHANNEL_LINK}")
        return

    if context.args:
        prompt = " ".join(context.args)
        await ask_gemini_direct(update, prompt)
    else:
        context.user_data["state"] = "waiting_for_ai_prompt"
        await update.message.reply_text("🤖 اكتب سؤالك للذكاء الاصطناعي الآن وسأجيبك فوراً.")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    register_user(context, user_id)
    total_users = len(context.bot_data.get("all_users", set()))
    await update.message.reply_text(f"📊 عدد مستخدمي البوت: {total_users}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    register_user(context, user_id)

    if not await is_subscribed(context, user_id):
        await update.message.reply_text(f"⚠️ يجب عليك الاشتراك في القناة أولاً:\n{CHANNEL_LINK}")
        return

    text = update.message.text.strip()

    if text == "📥 تحميل فيديو / صورة":
        await update.message.reply_text("📥 أرسل رابط المقطع أو الصورة مباشرة.")
        return

    elif text == "📢 قناة التحديثات":
        await update.message.reply_text(f"📢 رابط القناة الرسمية:\n{CHANNEL_LINK}")
        return

    if text.startswith("http://") or text.startswith("https://"):
        await process_download(update.message, context, text)
        return

    if context.user_data.get("state") == "waiting_for_ai_prompt":
        context.user_data["state"] = None
        await ask_gemini_direct(update, text)
        return

    await update.message.reply_text("أرسل رابطاً للتحميل، أو اكتب /ai وسؤالك للذكاء الاصطناعي.")

# معالجة النصوص الطويلة بشكل آمن
def call_gemini_api(prompt: str, api_key: str) -> str:
    models = ["gemini-1.5-flash", "gemini-1.5-pro"]
    for model in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        headers = {"Content-Type": "application/json"}
        
        payload = {
            "contents": [
                {
                    "parts": [{"text": prompt}]
                }
            ],
            "generationConfig": {
                "maxOutputTokens": 2048
            }
        }
        
        try:
            res = requests.post(url, json=payload, headers=headers, timeout=30)
            if res.status_code == 200:
                data = res.json()
                if "candidates" in data and len(data["candidates"]) > 0:
                    parts = data["candidates"][0]["content"]["parts"]
                    return "".join([part.get("text", "") for part in parts])
            else:
                logging.error(f"Gemini API Status Error ({res.status_code}): {res.text}")
        except Exception as e:
            logging.error(f"Gemini API Request Error with {model}: {e}")
            
    return None

async def ask_gemini_direct(update: Update, prompt: str):
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        await update.message.reply_text("❌ مفتاح GEMINI_API_KEY غير مضاف في متغيرات Render.")
        return

    msg = await update.message.reply_text("🧠 جاري التفكير...")
    answer = await asyncio.to_thread(call_gemini_api, prompt, key)

    if answer:
        # إذا كان الرد أقوى من حد تليجرام للرسالة الموحدة (4096 حرف) نجزئه
        if len(answer) > 4000:
            chunks = [answer[i:i+4000] for i in range(0, len(answer), 4000)]
            await msg.edit_text(chunks[0])
            for chunk in chunks[1:]:
                await update.message.reply_text(chunk)
        else:
            await msg.edit_text(answer)
    else:
        await msg.edit_text("❌ حدث خطأ أثناء معالجة النص، يرجى المحاولة مرة أخرى أو تقصير النص قليلاً.")

def download_tiktok_api(url: str, output_path: str) -> bool:
    try:
        api_url = f"https://api.tiklydown.eu.org/api/download?url={url}"
        res = requests.get(api_url, timeout=15)
        if res.status_code == 200:
            data = res.json()
            video_url = data.get("video", {}).get("noWatermark") or data.get("video", {}).get("watermark")
            if video_url:
                v_res = requests.get(video_url, stream=True, timeout=30)
                if v_res.status_code == 200:
                    with open(output_path, 'wb') as f:
                        for chunk in v_res.iter_content(chunk_size=8192):
                            f.write(chunk)
                    return True
    except Exception as e:
        logging.error(f"TikTok Direct API Error: {e}")
    return False

def download_media_general(url: str, output_prefix: str):
    ydl_opts = {
        'format': 'best',
        'outtmpl': f'{output_prefix}_%(id)s.%(ext)s',
        'quiet': True,
        'no_warnings': True,
        'nocheckcertificate': True,
        'geo_bypass': True,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        }
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

async def process_download(message_obj, context, url):
    status_msg = await message_obj.reply_text("⏳ جاري التحميل...")
    chat_id = message_obj.chat_id
    output_prefix = f"media_{chat_id}"
    downloaded_file = None

    try:
        if "tiktok.com" in url or "vt.tiktok.com" in url:
            target_path = f"{output_prefix}_tiktok.mp4"
            success = await asyncio.to_thread(download_tiktok_api, url, target_path)
            if success:
                downloaded_file = target_path

        if not downloaded_file:
            await asyncio.to_thread(download_media_general, url, output_prefix)
            files = glob.glob(f"{output_prefix}_*")
            if files:
                downloaded_file = files[0]

        if not downloaded_file or not os.path.exists(downloaded_file):
            await status_msg.edit_text("❌ تعذر تحميل المحتوى.")
            return

        file_size = os.path.getsize(downloaded_file) / (1024 * 1024)
        if file_size > 50:
            await status_msg.edit_text("❌ حجم الملف كبير جداً.")
            os.remove(downloaded_file)
            return

        await status_msg.edit_text("⬆️ جاري الإرسال...")

        ext = os.path.splitext(downloaded_file)[1].lower()
        if ext in ['.jpg', '.jpeg', '.png', '.webp']:
            with open(downloaded_file, 'rb') as photo:
                await message_obj.reply_photo(photo=photo)
        else:
            with open(downloaded_file, 'rb') as video:
                await message_obj.reply_video(video=video)

        os.remove(downloaded_file)
        await status_msg.delete()

    except Exception as e:
        logging.error(f"Error handling media: {e}")
        await status_msg.edit_text("❌ حدث خطأ أثناء التحميل.")
        for f in glob.glob(f"{output_prefix}*"):
            try:
                os.remove(f)
            except Exception:
                pass

def main():
    token = os.environ.get("BOT_TOKEN")
    if not token:
        print("خطأ: لم يتم العثور على BOT_TOKEN!")
        return

    application = Application.builder().token(token).post_init(post_init).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("ai", ai_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    application.run_polling()

if __name__ == "__main__":
    main()
