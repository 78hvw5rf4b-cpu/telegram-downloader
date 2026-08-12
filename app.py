import os
import re
import asyncio
import threading
import yt_dlp
from flask import Flask
from google import genai
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

# 1. إعداد خادم Flask للعمل على Render
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running fine!"

# قراءة المتغيرات البيئية
BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# تهيئة عميل Google GenAI
client = genai.Client(api_key=GEMINI_API_KEY)

# قائمة بحفظ عدد المستخدمين
user_ids = set()

# دالة للتحقق من الروابط
def contains_url(text):
    url_pattern = r'https?://[^\s]+'
    return bool(re.search(url_pattern, text))

# دالة التحميل بواسطة yt-dlp
def download_video(url):
    ydl_opts = {
        'format': 'best[ext=mp4]/best',
        'outtmpl': 'downloaded_video.%(ext)s',
        'quiet': True,
        'no_warnings': True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        return filename

# --- أوامر البوت ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_ids.add(update.effective_user.id)
    await update.message.reply_text(
        "أهلاً بك! 🤖\n\n"
        "1. قم بإرسال أي رابط مقطع (TikTok, Instagram, YouTube) لتحميله فوراً.\n"
        "2. استخدم الأمر /ai متبوعاً بسؤالك للتحدث مع الذكاء الاصطناعي."
    )

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"📊 عدد مستخدمي البوت: {len(user_ids)}")

async def handle_ai(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_ids.add(update.effective_user.id)
    text = " ".join(context.args) if context.args else ""
    
    # إذا أرسل المستخدم /ai فقط دون نص
    if not text:
        await update.message.reply_text("🤖 اكتب سؤالك بعد الأمر /ai، مثلاً:\n`/ai السلام عليكم`", parse_mode="Markdown")
        return

    msg = await update.message.reply_text("جاري التفكير... 🧠")
    
    # محاولة الاستدعاء مع خيارات النماذج الحديثة تجنباً لأخطاء 404
    models_to_try = ['gemini-2.0-flash', 'gemini-2.0-flash-lite']
    response_text = None

    for model_name in models_to_try:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=text,
            )
            response_text = response.text
            break
        except Exception:
            continue

    if response_text:
        await msg.edit_text(response_text)
    else:
        await msg.edit_text("❌ تعذر الاتصال بالذكاء الاصطناعي حالياً، يرجى المحاولة لاحقاً.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_ids.add(update.effective_user.id)
    text = update.message.text

    # إذا كان النص يحتوي على رابط
    if contains_url(text):
        msg = await update.message.reply_text("جاري تحميل المقطع... ⏳")
        try:
            loop = asyncio.get_running_loop()
            file_path = await loop.run_in_executor(None, download_video, text)
            
            with open(file_path, 'rb') as video:
                await update.message.reply_video(video=video)
            
            await msg.delete()
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception as e:
            await msg.edit_text(f"❌ فشل تحميل المقطع: {str(e)}")
    else:
        await update.message.reply_text("أرسل رابط فيديو لتحميله، أو استخدم الأمر /ai لمحادثة الذكاء الاصطناعي.")

def main():
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(CommandHandler("ai", handle_ai))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

    application.run_polling()

if __name__ == '__main__':
    # تشغيل Flask في الخلفية
    port = int(os.environ.get("PORT", 10000))
    threading.Thread(target=lambda: app.run(host='0.0.0.0', port=port)).start()
    main()
