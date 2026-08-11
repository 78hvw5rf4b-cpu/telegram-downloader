# الاستدعاء المباشر للذكاء الاصطناعي مع معالجة الأخطاء وإظهارها
def call_gemini_official(prompt: str, api_key: str):
    models_to_try = ['gemini-1.5-flash', 'gemini-1.5-pro', 'gemini-2.0-flash']
    last_error = ""
    
    try:
        genai.configure(api_key=api_key)
        for model_name in models_to_try:
            try:
                model = genai.GenerativeModel(model_name)
                response = model.generate_content(prompt)
                if response and response.text:
                    return response.text, None
            except Exception as e:
                last_error = str(e)
                continue
    except Exception as e:
        last_error = str(e)

    return None, last_error

async def ask_gemini_official(update: Update, prompt: str):
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        await update.message.reply_text("❌ مفتاح GEMINI_API_KEY غير مضاف في متغيرات Render.")
        return

    msg = await update.message.reply_text("🧠 جاري التفكير...")
    answer, error_msg = await asyncio.to_thread(call_gemini_official, prompt, key)

    if answer:
        if len(answer) > 4000:
            chunks = [answer[i:i+4000] for i in range(0, len(answer), 4000)]
            await msg.edit_text(chunks[0])
            for chunk in chunks[1:]:
                await update.message.reply_text(chunk)
        else:
            await msg.edit_text(answer)
    else:
        # إظهار نص الخطأ الحقيقي القادم من جوجل لتحديده فوراً
        await update.message.reply_text(f"❌ تفاصيل الخطأ من جوجل:\n\n`{error_msg}`", parse_mode="Markdown")
