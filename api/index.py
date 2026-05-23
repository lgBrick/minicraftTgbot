import os
import telebot
import google.generativeai as genai
from flask import Flask, request

# Инициализируем токены
TG_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

bot = telebot.TeleBot(TG_TOKEN, threaded=False)

# УСКОРЕНИЕ: Получаем юзернейм бота один раз при запуске (экономит время на каждый запрос)
bot_info = bot.get_me()
BOT_USERNAME = f"@{bot_info.username}"

# НАСТРОЙКА ИИ: Используем ПРАВИЛЬНЫЙ класс GenerativeModel
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-flash-latest')


def get_clean_question(message):
    raw_text = message.text if message.text else message.caption
    if not raw_text:
        return ""
    # Удаляем тег бота из текста, чтобы он не сбивал нейросеть
    return raw_text.replace(BOT_USERNAME, "").strip()


def is_real_reply(message):
    """Умный фильтр, который отличает настоящий реплай от системных сообщений тем (форумов) Telegram"""
    if message.reply_to_message is None:
        return False
    # В группах с темами обычные сообщения технически являются реплаями на ID темы. Отсекаем это:
    if getattr(message, 'message_thread_id', None) is not None:
        if message.reply_to_message.message_id == message.message_thread_id:
            return False
    return True


# === РЕЖИМ 1: Ответ на реплай (Гайд ИЛИ Контекст диалога) ===
@bot.message_handler(
    func=lambda message: (
            is_real_reply(message) and
            (BOT_USERNAME in (message.text or "") or BOT_USERNAME in (message.caption or ""))
    )
)
def handle_guide_reply(message):
    user_question = get_clean_question(message)
    bot.send_chat_action(message.chat.id, 'typing')

    original_msg = message.reply_to_message
    guide_text = original_msg.text if original_msg.text else original_msg.caption

    if not guide_text:
        bot.reply_to(message, "⚠️ Чтобы я мог ответить, в исходном сообщении должен быть текст или описание под фото!")
        return

    # УМНЫЙ ПРОМПТ: Бот сам поймет, это строгий гайд или просто переписка с пользователем
    prompt = f"""
    Ты — полезный и дружелюбный ИИ-ассистент в Telegram-чате.
    Пользователь задал вопрос, ответив на другое сообщение.

    ИСХОДНОЕ СООБЩЕНИЕ (Гайд или контекст):
    {guide_text}

    ВОПРОС ПОЛЬЗОВАТЕЛЯ:
    {user_question}

    Твоя задача:
    1. Если Исходное сообщение похоже на гайд, инструкцию или правило, отвечай СТРОГО по нему. Если там нет ответа, так и скажи: "К сожалению, в этом гайде нет нужной информации".
    2. Если Исходное сообщение — это просто обычная переписка (например, твое же прошлое сообщение), просто поддержи диалог и ответь живо, учитывая этот контекст. Не веди себя как робот!
    """

    try:
        response = model.generate_content(prompt)
        bot.reply_to(message, response.text)
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка ИИ (Режим реплая): {e}")


# === РЕЖИМ 2: Свободное общение (просто тег в чате, БЕЗ реплая) ===
@bot.message_handler(
    func=lambda message: (
            not is_real_reply(message) and
            (BOT_USERNAME in (message.text or "") or BOT_USERNAME in (message.caption or ""))
    )
)
def handle_free_chat(message):
    user_question = get_clean_question(message)
    bot.send_chat_action(message.chat.id, 'typing')

    if not user_question:
        bot.reply_to(message,
                     "Привет! Задай мне любой вопрос или тегни меня в ответе на гайд, чтобы я помог разобраться! 💡")
        return

    # ЖИВОЙ ПРОМПТ: Делаем бота крутым собеседником
    prompt = f"""
    Ты — крутой, умный и дружелюбный ИИ-помощник в Telegram-группе.
    Твоя задача — естественно и живо поддерживать диалог с пользователем.
    Веди себя как человек: используй эмодзи по смыслу, давай развернутые и интересные ответы, шути, если это уместно.
    Никогда не начинай ответ со слов "Я искусственный интеллект". Просто общайся!

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
        try:
            json_string = request.get_data().decode('utf-8')
            update = telebot.types.Update.de_json(json_string)
            bot.process_new_updates([update])
        except Exception as e:
            # Ловим скрытые ошибки Flask, чтобы Telegram не зацикливал сообщения
            print(f"Ошибка вебхука: {e}")

        return 'OK', 200
    return 'Forbidden', 403