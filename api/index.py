import os
import telebot
import google.generativeai as genai
from flask import Flask, request

# Инициализируем токены из переменных окружения Vercel
TG_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Инициализируем бота строго с параметром threaded=False для Serverless
bot = telebot.TeleBot(TG_TOKEN, threaded=False)

# УСКОРЕНИЕ: Кешируем юзернейм бота, чтобы не делать лишних запросов
bot_info = bot.get_me()
BOT_USERNAME = f"@{bot_info.username}"

# НАСТРОЙКА Gemini: используем правильный класс и умный алиас gemini-flash-latest
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-flash-latest')


def get_clean_question(message):
    """Извлекает текст из сообщения или подписи, очищая его от тега бота"""
    raw_text = message.text if message.text else message.caption
    if not raw_text:
        return ""
    try:
        return raw_text.replace(BOT_USERNAME, "").strip()
    except Exception:
        return raw_text.strip()


def is_real_reply(message):
    """Фильтр, отсекающий системные привязки тем (форумов) Telegram"""
    if message.reply_to_message is None:
        return False
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

    # Включаем нативный статус "печатает..." вверху чата без отправки сообщений-заглушек
    bot.send_chat_action(message.chat.id, 'typing')

    original_msg = message.reply_to_message
    guide_text = original_msg.text if original_msg.text else original_msg.caption

    if not guide_text:
        bot.reply_to(message, "⚠️ Чтобы я мог ответить, в исходном сообщении должен быть текст или описание!")
        return

    # УМНЫЙ ПРОМПТ ДРУЖБАНА: Без унылых шаблонов, отвечает по ситуации
    prompt = f"""
    Ты — умный ИИ-помощник в Telegram-группе, но общаешься как свой в доску братан.
    Пользователь прислал сообщение в ответ на другое сообщение (реплай).

    ИСХОДНОЕ СООБЩЕНИЕ (Контекст или гайд):
    {guide_text}

    ВОПРОС ПОЛЬЗОВАТЕЛЯ:
    {user_question}

    Твоя задача:
    1. Изучи Исходное сообщение. Если в нём есть ответ на вопрос пользователя (например, это гайд или инструкция) — используй эту информацию, чтобы дать точный ответ.
    2. Если в Исходном сообщении ответа нет или это просто обычная переписка — НЕ ИСПОЛЬЗУЙ никаких шаблонных фраз о том, что информации нет. Просто ответь на вопрос пользователя, опираясь на свои знания, используя исходное сообщение лишь как контекст диалога.
    3. Веди диалог живо, естественно и максимально неформально. Разрешается дружеский стёб, сленг, подколы и умеренный мат (но без реальной токсичности и агрессии).
    4. Главная цель — всегда давать чёткий, правильный и полезный ответ на вопрос пользователя.
    5. Никогда не используй фразы вроде "Я искусственный интеллект" или "Как языковая модель". Сразу переходи к делу в своем стиле.
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

    # Включаем нативный статус "печатает..." вверху чата
    bot.send_chat_action(message.chat.id, 'typing')

    if not user_question:
        bot.reply_to(message, "Привет! Задай мне вопрос или тегни в ответе на гайд, чтобы я помог разобраться! 💡")
        return

    # ЖИВОЙ ПРОМПТ ДРУЖБАНА: Свободный режим
    prompt = f"""
    Ты — умный ИИ-помощник в Telegram-группе, но общаешься как старый друг и свой в доску братан.

    ВОПРОС ПОЛЬЗОВАТЕЛЯ:
    {user_question}

    Твоя задача:
    1. Дать четкий, правильный и полезный ответ на вопрос.
    2. Вести диалог живо и неформально. Разрешается дружеский стёб, подколы, сарказм и умеренный мат (но не скатывайся в откровенное хамство или токсичность).
    3. Разговаривай как обычный человек в чате, используй сленг.
    4. Никогда не отвечай шаблонами вроде "Чем я могу помочь?" или "Как искусственный интеллект...". Сразу херачь по делу в своем стиле.
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
            print(f"Ошибка вебхука: {e}")

        # Гарантированный возврат 200 OK защищает от зацикливания Telegram
        return 'OK', 200
    return 'Forbidden', 403