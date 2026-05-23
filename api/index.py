import os
import json
import telebot
import google.generativeai as genai
from flask import Flask, request

# Инициализируем токены
TG_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

bot = telebot.TeleBot(TG_TOKEN, threaded=False)

# Настраиваем Gemini через классическую легкую библиотеку
genai.configure(api_key=GEMINI_API_KEY)
model = genai.Model(model_name='models/gemini-1.5-flash')


def get_clean_question(message):
    raw_text = message.text if message.text else message.caption
    if not raw_text:
        return ""
    try:
        bot_username = f"@{bot.get_me().username}"
        return raw_text.replace(bot_username, "").strip()
    except Exception:
        return raw_text


# === РЕЖИМ 1: Ответ строго по гайду (работает ТОЛЬКО когда есть Reply) ===
@bot.message_handler(
    func=lambda message: (
            message.reply_to_message is not None and
            (f"@{bot.get_me().username}" in (message.text or "") or f"@{bot.get_me().username}" in (
                    message.caption or ""))
    )
)
def handle_guide_reply(message):
    user_question = get_clean_question(message)
    bot.send_chat_action(message.chat.id, 'typing')

    guide_text = message.reply_to_message.text if message.reply_to_message.text else message.reply_to_message.caption

    if not guide_text:
        bot.reply_to(message, "⚠️ Чтобы я ответил по гайду, в сообщении должен быть текст или описание под фото!")
        return

    prompt = f"""
    Ты — полезный ИИ-ассистент в Telegram-канале. Твоя задача — ответить на вопрос пользователя, используя ИСКЛЮЧИТЕЛЬНО предоставленный текст гайда.
    Если в тексте гайда нет ответа на этот вопрос, вежливо ответь, что в данном гайде этой информации нет.

    ТЕКСТ ГАЙДА:
    {guide_text}

    ВОПРОС ПОЛЬЗОВАТЕЛЯ:
    {user_question}
    """

    try:
        response = model.generate_content(prompt)
        bot.reply_to(message, response.text)
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка ИИ (Режим гайда): {e}")


# === РЕЖИМ 2: Свободное общение (работает когда реплая НЕТ, просто тег в чате) ===
@bot.message_handler(
    func=lambda message: (
            message.reply_to_message is None and
            (f"@{bot.get_me().username}" in (message.text or "") or f"@{bot.get_me().username}" in (
                    message.caption or ""))
    )
)
def handle_free_chat(message):
    user_question = get_clean_question(message)
    bot.send_chat_action(message.chat.id, 'typing')

    if not user_question:
        bot.reply_to(message, "Привет! Задай мне вопрос, или тегни в ответе на гайд, чтобы я помог разобраться! 💡")
        return

    prompt = f"""
    Ты — дружелюбный ИИ-помощник в Telegram-канале. Ответь на вопрос пользователя кратко и по делу.

    ВОПРОС ПОЛЬЗОВАТЕЛЯ:
    {user_question}
    """

    try:
        response = model.generate_content(prompt)
        bot.reply_to(message, response.text)
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка ИИ (Свободный режим): {e}")


# Окружение Flask для Vercel
app = Flask(__name__)


@app.route('/', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return 'OK', 200
    return 'Forbidden', 403