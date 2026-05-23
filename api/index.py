import os
import telebot
import google.generativeai as genai
from flask import Flask, request

# Инициализируем токены из переменных окружения Vercel
TG_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Инициализируем бота строго с параметром threaded=False для Serverless
bot = telebot.TeleBot(TG_TOKEN, threaded=False)

# Настраиваем Gemini
genai.configure(api_key=GEMINI_API_KEY)

# Используем "умный" официальный алиас — он сам автоматически выберет самую актуальную версию Flash
model = genai.GenerativeModel('gemini-flash-latest')


def get_clean_question(message):
    """
    Универсальный сборщик текста. Извлекает текст из сообщения или подписи к медиафайлу,
    после чего очищает его от юзернейма бота.
    """
    raw_text = message.text if message.text else message.caption
    if not raw_text:
        return ""
    try:
        bot_username = f"@{bot.get_me().username}"
        return raw_text.replace(bot_username, "").strip()
    except Exception:
        return raw_text.strip()


# === РЕЖИМ 1: Ответ строго по гайду (работает ТОЛЬКО при наличии Reply) ===
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

    original_msg = message.reply_to_message
    guide_text = original_msg.text if original_msg.text else original_msg.caption

    if not guide_text:
        bot.reply_to(message, "⚠️ Чтобы я ответил по гайду, в сообщении должен быть текст или описание под фото!")
        return

    prompt = f"""
    Ты — полезный ИИ-ассистент. Ответь на вопрос пользователя, используя ИСКЛЮЧИТЕЛЬНО предоставленный текст гайда. 
    Если в тексте гайда нет ответа, вежливо скажи, что в данном гайде этой информации нет.

    ТЕКСТ ГАЙДА:
    {guide_text}

    ВОПРОС ПОЛЬЗОВАТЕЛЯ:
    {user_question}
    """

    try:
        response = model.generate_content(prompt)
        bot.reply_to(message, response.text)
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка Gemini API (Режим гайда): {e}")


# === РЕЖИМ 2: Свободное общение (Работает, когда реплая НЕТ) ===
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
        bot.reply_to(message,
                     "Привет! Задай мне любой вопрос, или тегни меня в ответе на сообщение с гайдом, чтобы я помог разобраться! 💡")
        return

    prompt = f"""
    Ты — дружелюбный ИИ-помощник в Telegram-канале. Ответь на вопрос пользователя кратко, дружелюбно и по делу.

    ВОПРОС ПОЛЬЗОВАТЕЛЯ:
    {user_question}
    """

    try:
        response = model.generate_content(prompt)
        bot.reply_to(message, response.text)
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка Gemini API (Свободный режим): {e}")


# Окружение Flask для Vercel
app = Flask(__name__)


@app.route('/', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        try:
            json_string = request.get_data().decode('utf-8')
            update = telebot.types.Update.de_json(json_string)
            bot.process_new_updates([update])
        except Exception as e:
            print(f"Внутренняя ошибка при обработке апдейта: {e}")

        # Строго возвращаем 200 OK, чтобы заблокировать любой цикличный спам повторами от Telegram
        return 'OK', 200

    return 'Forbidden', 403