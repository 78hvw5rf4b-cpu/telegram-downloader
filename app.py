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

GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
ai_client = genai.Client(api_key=GEMINI_KEY) if GEMINI_KEY else None

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

def get_sub_keyboard():
    keyboard = [
        [InlineKeyboardButton("📢 اشترك في القناة أولاً", url=CHANNEL_LINK)],
        [InlineKeyboardButton("✅ تأكيد الاشتراك", callback_data="check_subscription")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_main_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("📥 تحميل فيديو / صورة", callback_data="mode_download"),
            InlineKeyboardButton("🤖 الذكاء الاصطناعي", callback_data="mode_ai")
        ],
        [
            InlineKeyboardButton("📊 الإحصائيات", callback_data="cmd_stats"),
            InlineKeyboardButton("📢 قناة التحديثات 🎁", url=CHANNEL_LINK)
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# --- الأوامر الرئيسية ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    register_user(context, user_id)

    if not await is_subscribed(context, user_id):
        await update.message.reply_text(
            "⚠️ **تنبيه:**\nيجب عليك الاشتراك في قناة البوت أولاً لاستخدام الخدمات!",
            reply_markup=get_sub_keyboard(),
            parse_mode="Markdown"
        )
        return

    await update.message.reply_text(
        "أهلاً بك في بوت Abu na9r! 🖐️\nاختر الخدمة التي تريدها من الأزرار أدناه:",
        reply_markup=get_main_keyboard()
    )

# --- معالجة الرسائل العادية (روابط أو نصوص) ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    register_user(context, user_id)

    if not await is_subscribed(context, user_id):
        await update.message.reply_text("⚠️ يجب عليك الاشتراك في القناة أولاً!", reply_markup=get_sub_keyboard())
        return

    text = update.message.text.strip()

    # إذا أرسل رابطاً
    if text.startswith("http://") or text.startswith("https://"):
        context.chat_data["pending_url"] = text
        await process_download(update.message, context, text)
        return

    # إذا كان المستخدم في وضع الذكاء الاصطناعي
    if context.user_data.get("state") == "waiting_for_ai_prompt":
        context.user_data["state"] = None
        await ask_gemini(update, text)
        return

    # في حال كتابة نص عالي بدون اختيار خدمة
    await update.message.reply_text(
        "قم باختيار الخدمة من القائمة الرئيسية أو أرسل رابطاً مباشرة للتحميل:",
        reply_markup=get_main_keyboard()
    )

# --- الذكاء الاصطناعي ---
async def ask_gemini(update: Update, prompt: str):
    if not ai_client:
        await update.message.reply_text("❌ مفتاح GEMINI_API_KEY غير متوفر حالياً.", reply_markup=get_main_keyboard())
        return

    msg = await update.message.reply_text("🧠 جاري التفكير...")
    try:
        response = await asyncio.to_thread(
            ai_client.models.generate_content,
            model='gemini-2.5-flash',
            contents=prompt
        )
        await msg.edit_text(response.text, reply_markup=get_main_keyboard())
    except Exception as e:
        logging.error(f"AI Error: {e}")
        await msg.edit_text("❌ حدث خطأ أثناء الاتصال بالذكاء الاصطناعي.", reply_markup=get_main_keyboard())

# --- معالجة الضغط على الأزرار ---
async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    register_user(context, user_id)

    if query.data == "check_subscription":
        if await is_subscribed(context, user_id):
            await query.message.reply_text("✅ تم التأكد من اشتراكك بنجاح!", reply_markup=get_main_keyboard())
        else:
            await query.message.reply_text("❌ لم يتم العثور على اشتراكك بعد!", reply_markup=get_sub_keyboard())
        return

    if not await is_subscribed(context, user_id):
        await query.message.reply_text("⚠️ يجب عليك الاشتراك في القناة أولاً!", reply_markup=get_sub_keyboard())
        return

    if query.data == "mode_ai":
        context.user_data["state"] = "waiting_for_ai_prompt"
        await query.message.reply_text("🤖 **قسم الذكاء الاصطناعي:**\nأرسل سؤالك أو استفسارك الآن للرد عليه.")

    elif query.data == "mode_download":
        await query.message.reply_text("📥 **قسم التحميل:**\nقم بإرسال رابط المقطع أو الصورة من (تيك توك، إنستغرام، يوتيوب...) مباشرة.")

    elif query.data == "cmd_stats":
        total_users = len(context.bot_data.get("all_users", set()))
        await query.message.reply_text(f"📊 **إحصائيات البوت الكلية:**\n\nعدد المستخدمين: {total_users}", reply_markup=get_main_keyboard())

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

async def process_download(message_obj, context, url):
    status_msg = await message_obj.reply_text("⏳ جاري جلب وتحميل المحتوى...")
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
            await status_msg.edit_text("❌ تعذر تحميل المحتوى، تأكد من الرابط.", reply_markup=get_main_keyboard())
            return

        file_size = os.path.getsize(downloaded_file) / (1024 * 1024)
        if file_size > 50:
            await status_msg.edit_text("❌ حجم الملف كبير جداً (يتجاوز 50 ميجابايت).", reply_markup=get_main_keyboard())
            os.remove(downloaded_file)
            return

        await status_msg.edit_text("⬆️ جاري الإرسال...")

        ext = os.path.splitext(downloaded_file)[1].lower()
        if ext in ['.jpg', '.jpeg', '.png', '.webp']:
            with open(downloaded_file, 'rb') as photo:
                await message_obj.reply_photo(photo=photo, reply_markup=get_main_keyboard())
        else:
            with open(downloaded_file, 'rb') as video:
                await message_obj.reply_video(video=video, reply_markup=get_main_keyboard())

        os.remove(downloaded_file)
        await status_msg.delete()

    except Exception as e:
        logging.error(f"Error handling media: {e}")
        await status_msg.edit_text("❌ حدث خطأ أثناء التحميل.", reply_markup=get_main_keyboard())
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
    application.add_handler(CallbackQueryHandler(button_click))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    application.run_polling()

if __name__ == "__main__":
    main()
