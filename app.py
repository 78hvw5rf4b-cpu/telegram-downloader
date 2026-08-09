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

# --- نظام حفظ دائم ومضمون لعدد المستخدمين ---
def register_user(context: ContextTypes.DEFAULT_TYPE, user_id: int):
    if "all_users" not in context.bot_data:
        context.bot_data["all_users"] = set()
    if user_id not in context.bot_data["all_users"]:
        context.bot_data["all_users"].add(user_id)

# --- الأزرار والقائمة الموحدة ---
CHANNEL_LINK = "https://t.me/Abu_na9r"

def get_main_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("🚀 البدء / Start", callback_data="cmd_start"),
            InlineKeyboardButton("📊 الإحصائيات", callback_data="cmd_stats")
        ],
        [
            InlineKeyboardButton("💬 دردشة مع الذكاء الاصطناعي 🤖", callback_data="cmd_ai_chat")
        ],
        [
            InlineKeyboardButton("📢 قناة التحديثات وكل شي جديد 🎁", url=CHANNEL_LINK)
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_action_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("📥 تحميل المقطع", callback_data="action_download"),
            InlineKeyboardButton("🤖 تحليل بالذكاء الاصطناعي", callback_data="action_ai")
        ],
        [
            InlineKeyboardButton("📢 قناة التحديثات وكل شي جديد 🎁", url=CHANNEL_LINK)
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    register_user(context, user_id)
    context.chat_data["ai_mode"] = False
    await update.message.reply_text(
        "أهلاً بك في بوت Abu na9r! 🖐️\nيمكنك إرسال رابط لتحميله أو تحليله، أو الضغط على 'دردشة' للتحدث مع الذكاء الاصطناعي:",
        reply_markup=get_main_keyboard()
    )

# --- محرك خاص ومباشر لمقاطع TikTok لتجاوز الحظر ---
def download_tiktok_direct(url: str, output_path: str) -> bool:
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
        logging.error(f"TikTok Direct API error: {e}")
    return False

# --- دالة التحميل العامة للمنصات الأخرى ---
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

# --- استخراج بيانات الفيديو للذكاء الاصطناعي ---
def get_video_info(url: str):
    try:
        ydl_opts = {'quiet': True, 'no_warnings': True, 'skip_download': True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return info.get('title', ''), info.get('description', '')
    except Exception as e:
        logging.error(f"Error fetching info: {e}")
        return "", ""

# --- محرك الذكاء الاصطناعي Gemini ---
def ask_gemini_ai(prompt: str) -> str:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return "⚠️ خدمة الذكاء الاصطناعي تحتاج إضافة GEMINI_API_KEY في متغيرات البيئة بالاستضافة."
    
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{
            "parts": [{"text": prompt}]
        }]
    }
    try:
        res = requests.post(endpoint, json=payload, headers=headers, timeout=30)
        if res.status_code == 200:
            data = res.json()
            return data['candidates'][0]['content']['parts'][0]['text']
        else:
            return "❌ تعذر الحصول على استجابة من الذكاء الاصطناعي حالياً."
    except Exception as e:
        logging.error(f"Gemini API Error: {e}")
        return "❌ حدث خطأ أثناء الاتصال بخدمة الذكاء الاصطناعي."

# --- استقبال الرسائل ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    register_user(context, user_id)

    text = update.message.text.strip()

    # 1. إذا أرسل المستخدم رابطاً (ينتقل فوراً لخيارات الفيديو)
    if text.startswith("http://") or text.startswith("https://"):
        context.chat_data["pending_url"] = text
        await update.message.reply_text(
            "✨ تم استلام الرابط بنجاح! اختر الخدمة المطلوبة:",
            reply_markup=get_action_keyboard()
        )
        return

    # 2. إذا كان مفتاح الدردشة مفعّلاً لدى المستخدم
    if context.chat_data.get("ai_mode") is True:
        status_msg = await update.message.reply_text("🤖 يفكر الذكاء الاصطناعي...")
        ai_reply = await asyncio.to_thread(ask_gemini_ai, text)
        await status_msg.edit_text(f"🤖 **الذكاء الاصطناعي:**\n\n{ai_reply}", reply_markup=get_main_keyboard())
        return

    # 3. النص العادي دون تفعيل الوضع
    await update.message.reply_text(
        "الرجاء إرسال رابط فيديو صحيح للتحميل، أو اضغط زر '💬 دردشة مع الذكاء الاصطناعي' للتحدث معي مباشرة.",
        reply_markup=get_main_keyboard()
    )

# --- معالجة الضغط على الأزرار ---
async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    register_user(context, user_id)

    if query.data == "cmd_start":
        context.chat_data["ai_mode"] = False
        await query.message.reply_text("أهلاً بك مجدداً! أرسل رابط المقطع للتحميل أو اختر الدردشة.", reply_markup=get_main_keyboard())
    
    elif query.data == "cmd_stats":
        total_users = len(context.bot_data.get("all_users", set()))
        await query.message.reply_text(f"📊 **إحصائيات البوت الكلية:**\n\nعدد جميع الأشخاص الذين دخلوا البوت: {total_users} مستخدم", reply_markup=get_main_keyboard())
    
    elif query.data == "cmd_ai_chat":
        context.chat_data["ai_mode"] = True
        await query.message.reply_text("💬 **تم تفعيل وضع الدردشة!**\n\nاسألني أو اسولف معي عن أي موضوع تريد، اكتب سؤالك ورسالتك الآن مباشرة 👇", reply_markup=get_main_keyboard())

    elif query.data == "action_download":
        url = context.chat_data.get("pending_url")
        if not url:
            await query.message.reply_text("❌ لم يتم العثور على رابط. يرجى إرسال الرابط مجدداً.", reply_markup=get_main_keyboard())
            return
        await process_download(query, context, url)
        
    elif query.data == "action_ai":
        url = context.chat_data.get("pending_url")
        if not url:
            await query.message.reply_text("❌ لم يتم العثور على رابط. يرجى إرسال الرابط مجدداً.", reply_markup=get_main_keyboard())
            return
        await process_ai_analysis(query, context, url)

# --- معالجة التحميل ---
async def process_download(query, context, url):
    status_msg = await query.message.reply_text("⏳ جاري جلب وتحميل المقطع، انتظر قليلاً...")
    chat_id = query.message.chat_id
    video_path = None

    try:
        if "tiktok.com" in url:
            output_file = f"video_{chat_id}.mp4"
            success = await asyncio.to_thread(download_tiktok_direct, url, output_file)
            if success:
                video_path = output_file
            else:
                output_pattern = f"video_{chat_id}_%(id)s.%(ext)s"
                await asyncio.to_thread(download_video_file, url, output_pattern)
                files = glob.glob(f"video_{chat_id}_*")
                if files:
                    video_path = files[0]
        else:
            output_pattern = f"video_{chat_id}_%(id)s.%(ext)s"
            await asyncio.to_thread(download_video_file, url, output_pattern)
            files = glob.glob(f"video_{chat_id}_*")
            if files:
                video_path = files[0]

        if not video_path or not os.path.exists(video_path):
            await status_msg.edit_text("❌ تعذر تحميل المقطع. تأكد من صحة الرابط أو أن الحساب ليس خاصاً.", reply_markup=get_main_keyboard())
            return

        file_size = os.path.getsize(video_path) / (1024 * 1024)
        if file_size > 50:
            await status_msg.edit_text("❌ حجم الفيديو كبير جداً (يتجاوز 50 ميجابايت).", reply_markup=get_main_keyboard())
            os.remove(video_path)
            return

        await status_msg.edit_text("⬆️ جاري إرسال الفيديو...")

        with open(video_path, 'rb') as video:
            await query.message.reply_video(video=video)

        os.remove(video_path)
        await status_msg.delete()

    except Exception as e:
        logging.error(f"Error handling video: {e}")
        await status_msg.edit_text("❌ حدث خطأ أثناء التحميل. حاول إرسال الرابط مرة أخرى.", reply_markup=get_main_keyboard())
        for f in glob.glob(f"video_{chat_id}*"):
            try:
                os.remove(f)
            except Exception:
                pass

# --- معالجة تحليل الفيديو بالذكاء الاصطناعي ---
async def process_ai_analysis(query, context, url):
    status_msg = await query.message.reply_text("🤖 جاري استخراج معلومات الفيديو وتحليل المحتوى بالذكاء الاصطناعي...")
    
    title, description = await asyncio.to_thread(get_video_info, url)
    
    prompt = (
        "أنت مساعد ذكي ومحترف. قم بتقديم ملخص وشرح باللغة العربية الواضحة والشائقة لهذا الفيديو بناءً على عنوانه ووصفه:\n\n"
        f"عنوان الفيديو: {title if title else 'غير متاح'}\n"
        f"وصف الفيديو: {description if description else 'غير متاح'}\n"
        f"رابط الفيديو: {url}\n\n"
        "قدم ملخصاً للنقاط الرئيسية وأهم الفوائد باختصار وجاذبية."
    )
    
    ai_response = await asyncio.to_thread(ask_gemini_ai, prompt)
    
    final_text = f"🤖 **تحليل الذكاء الاصطناعي للمقطع:**\n\n{ai_response}"
    await status_msg.edit_text(final_text, reply_markup=get_main_keyboard())

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
