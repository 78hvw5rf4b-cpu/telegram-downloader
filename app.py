import os
import logging
import asyncio
import threading
import glob
import time
import requests
from flask import Flask
import yt_dlp
from google import genai
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# --- سيرفر Flask لإبقاء البوت متصلاً 24 ساعة ---
app_web = Flask(__name__)

@app_web.route('/')
def home():
    return "Bot is alive and running 24/7!"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app_web.run(host="0.0.0.0", port=port)

# نظام Ping تلقائي يمنع Render من إيقاف السيرفر
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
        time.sleep(300) # يرسل نبضة كل 5 دقائق

threading.Thread(target=run_web, daemon=True).start()
threading.Thread(target=self_ping, daemon=True).start()
# ------------------------------------------------

logging.basicConfig(level=logging.INFO)

# --- إعداد الذكاء الاصطناعي Gemini ---
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
ai_client = genai.Client(api_key=GEMINI_KEY) if GEMINI_KEY else None

# --- إحصائيات المستخدمين ---
def register_user(context: ContextTypes.DEFAULT_TYPE, user_id: int):
    if "all_users" not in context.bot_data:
        context.bot_data["all_users"] = set()
    if user_id not in context.bot_data["all_users"]:
        context.bot_data["all_users"].add(user_id)

CHANNEL_LINK = "https://t.me/Abu_na9r"

def get_main_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("🚀 البدء / Start", callback_data="cmd_start"),
            InlineKeyboardButton("📊 الإحصائيات", callback_data="cmd_stats")
        ],
        [
            InlineKeyboardButton("📢 قناة التحديثات وكل شي جديد 🎁", url=CHANNEL_LINK)
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_action_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("📥 تحميل المحتوى", callback_data="action_download")
        ],
        [
            InlineKeyboardButton("📢 قناة التحديثات وكل شي جديد 🎁", url=CHANNEL_LINK)
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# --- الأوامر الأساسية ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    register_user(context, user_id)
    await update.message.reply_text(
        "أهلاً بك في بوت Abu na9r! 🖐️\n\n"
        "• أرسل لي **رابط مقطع أو صورة** للتحميل المباشر.\n"
        "• أو اكتب سؤالك مباشرة أو عبر الأمر `/ai` للإجابة بالذكاء الاصطناعي!",
        reply_markup=get_main_keyboard(),
        parse_mode="Markdown"
    )

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    register_user(context, user_id)
    total_users = len(context.bot_data.get("all_users", set()))
    await update.message.reply_text(
        f"📊 **إحصائيات البوت الكلية:**\n\nعدد الأشخاص الذين دخلوا البوت: {total_users} مستخدم",
        reply_markup=get_main_keyboard(),
        parse_mode="Markdown"
    )

async def ai_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    register_user(context, user_id)
    
    prompt = " ".join(context.args)
    if not prompt:
        await update.message.reply_text("الرجاء كتابة سؤالك بعد الأمر، مثال:\n`/ai كيف أتعلم البرمجة؟`", parse_mode="Markdown")
        return

    await ask_gemini(update, prompt)

# --- دالة استدعاء الذكاء الاصطناعي ---
async def ask_gemini(update: Update, prompt: str):
    if not ai_client:
        await update.message.reply_text("❌ لم يتم إضافة GEMINI_API_KEY صحيح في متغيرات البيئة بـ Render.")
        return

    msg = await update.message.reply_text("🧠 جاري التفكير...")
    try:
        response = await asyncio.to_thread(
            ai_client.models.generate_content,
            model='gemini-2.5-flash',
            contents=prompt
        )
        await msg.edit_text(response.text)
    except Exception as e:
        logging.error(f"AI Error: {e}")
        await msg.edit_text("❌ حدث خطأ أثناء الاتصال بالذكاء الاصطناعي. تأكد من صحة API Key.")

# --- محركات التحميل ---
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

# --- معالجة الرسائل ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    register_user(context, user_id)

    text = update.message.text.strip()

    if text.startswith("http://") or text.startswith("https://"):
        context.chat_data["pending_url"] = text
        await update.message.reply_text(
            "✨ تم استلام الرابط بنجاح! اضغط على زر التحميل أدناه:",
            reply_markup=get_action_keyboard()
        )
        return

    await ask_gemini(update, text)

# --- معالجة الأزرار ---
async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    register_user(context, user_id)

    if query.data == "cmd_start":
        await query.message.reply_text("أهلاً بك مجدداً! أرسل رابطاً للتحميل أو اسأل الذكاء الاصطناعي.", reply_markup=get_main_keyboard())
    
    elif query.data == "cmd_stats":
        total_users = len(context.bot_data.get("all_users", set()))
        await query.message.reply_text(f"📊 **إحصائيات البوت الكلية:**\n\nعدد الأشخاص الذين دخلوا البوت: {total_users} مستخدم", reply_markup=get_main_keyboard())

    elif query.data == "action_download":
        url = context.chat_data.get("pending_url")
        if not url:
            await query.message.reply_text("❌ لم يتم العثور على رابط. يرجى إرسال الرابط مجدداً.", reply_markup=get_main_keyboard())
            return
        await process_download(query, context, url)

# --- التحميل والإرسال ---
async def process_download(query, context, url):
    status_msg = await query.message.reply_text("⏳ جاري جلب وتحميل المحتوى، انتظر لحظة...")
    chat_id = query.message.chat_id
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
            await status_msg.edit_text("❌ تعذر تحميل المحتوى. تأكد من صحة الرابط أو أن الحساب ليس خاصاً.", reply_markup=get_main_keyboard())
            return

        file_size = os.path.getsize(downloaded_file) / (1024 * 1024)
        if file_size > 50:
            await status_msg.edit_text("❌ حجم الملف كبير جداً (يتجاوز 50 ميجابايت).", reply_markup=get_main_keyboard())
            os.remove(downloaded_file)
            return

        await status_msg.edit_text("⬆️ جاري إرسال المحتوى...")

        ext = os.path.splitext(downloaded_file)[1].lower()
        if ext in ['.jpg', '.jpeg', '.png', '.webp']:
            with open(downloaded_file, 'rb') as photo:
                await query.message.reply_photo(photo=photo)
        else:
            with open(downloaded_file, 'rb') as video:
                await query.message.reply_video(video=video)

        os.remove(downloaded_file)
        await status_msg.delete()

    except Exception as e:
        logging.error(f"Error handling media: {e}")
        await status_msg.edit_text("❌ حدث خطأ أثناء التحميل. حاول إرسال الرابط مرة أخرى.", reply_markup=get_main_keyboard())
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

    application = Application.builder().token(token).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("ai", ai_command))
    application.add_handler(CallbackQueryHandler(button_click))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    application.run_polling()

if __name__ == "__main__":
    main()
