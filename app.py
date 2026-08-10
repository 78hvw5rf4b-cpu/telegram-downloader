import os
import logging
import asyncio
import threading
import glob
import requests
from flask import Flask
import yt_dlp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# --- سيرفر Flask لضمان استمرار عمل Render بدون توقف ---
app_web = Flask(__name__)

@app_web.route('/')
def home():
    return "Bot is alive and running!"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app_web.run(host="0.0.0.0", port=port)

threading.Thread(target=run_web, daemon=True).start()
# ------------------------------------------------

logging.basicConfig(level=logging.INFO)

# --- نظام حفظ وإحصائيات عدد المستخدمين ---
def register_user(context: ContextTypes.DEFAULT_TYPE, user_id: int):
    if "all_users" not in context.bot_data:
        context.bot_data["all_users"] = set()
    if user_id not in context.bot_data["all_users"]:
        context.bot_data["all_users"].add(user_id)

# --- الأزرار والقوائم ---
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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    register_user(context, user_id)
    await update.message.reply_text(
        "أهلاً بك في بوت Abu na9r! 🖐️\nأرسل رابط المقطع أو الصورة للتحميل المباشر:",
        reply_markup=get_main_keyboard()
    )

# --- محرك تحميل متطور يدعم الفيديو والصور من جميع المنصات ---
def download_media_direct(url: str, output_prefix: str):
    ydl_opts = {
        'format': 'best',
        'outtmpl': f'{output_prefix}_%(id)s.%(ext)s',
        'quiet': True,
        'no_warnings': True,
        'nocheckcertificate': True,
        'geo_bypass': True,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            'Accept-Language': 'en-US,en;q=0.9',
        }
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

# --- استقبال الرسائل ---
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

    await update.message.reply_text(
        "الرجاء إرسال رابط صحيح للتحميل.",
        reply_markup=get_main_keyboard()
    )

# --- معالجة الضغط على الأزرار ---
async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    register_user(context, user_id)

    if query.data == "cmd_start":
        await query.message.reply_text("أهلاً بك مجدداً! أرسل الرابط للتحميل.", reply_markup=get_main_keyboard())
    
    elif query.data == "cmd_stats":
        total_users = len(context.bot_data.get("all_users", set()))
        await query.message.reply_text(f"📊 **إحصائيات البوت الكلية:**\n\nعدد جميع الأشخاص الذين دخلوا البوت: {total_users} مستخدم", reply_markup=get_main_keyboard())

    elif query.data == "action_download":
        url = context.chat_data.get("pending_url")
        if not url:
            await query.message.reply_text("❌ لم يتم العثور على رابط. يرجى إرسال الرابط مجدداً.", reply_markup=get_main_keyboard())
            return
        await process_download(query, context, url)

# --- معالجة وإرسال الصور والفيديوهات ---
async def process_download(query, context, url):
    status_msg = await query.message.reply_text("⏳ جاري جلب وتحميل المحتوى، انتظر لحظة...")
    chat_id = query.message.chat_id
    output_prefix = f"media_{chat_id}"

    try:
        await asyncio.to_thread(download_media_direct, url, output_prefix)
        files = glob.glob(f"{output_prefix}_*")

        if not files:
            await status_msg.edit_text("❌ تعذر تحميل المحتوى. تأكد من صحة الرابط أو أن الحساب ليس خاصاً.", reply_markup=get_main_keyboard())
            return

        downloaded_file = files[0]
        file_size = os.path.getsize(downloaded_file) / (1024 * 1024)

        if file_size > 50:
            await status_msg.edit_text("❌ حجم الملف كبير جداً (يتجاوز 50 ميجابايت).", reply_markup=get_main_keyboard())
            os.remove(downloaded_file)
            return

        await status_msg.edit_text("⬆️ جاري إرسال المحتوى...")

        # التمييز التلقائي بين الصور والفيديوهات وإرسالها
        ext = os.path.splitext(downloaded_file)[1].lower()
        if ext in ['.jpg', '.jpeg', '.png', '.webp']:
            with open(downloaded_file, 'rb') as photo:
                await query.message.reply_photo(photo=photo)
        else:
            with open(downloaded_file, 'rb') as video:
                await query.message.reply_video(video=video)

        # تنظيف الملفات المؤقتة بعد الإرسال
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
    application.add_handler(CommandHandler("stats", start))
    application.add_handler(CallbackQueryHandler(button_click))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    application.run_polling()

if __name__ == "__main__":
    main()
