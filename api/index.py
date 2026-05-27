import os
import random
import telebot
import google.generativeai as genai
from flask import Flask, request

# Инициализируем токены из переменных окружения Vercel
TG_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Инициализируем бота строго с параметром threaded=False для Serverless
bot = telebot.TeleBot(TG_TOKEN, threaded=False)

# УСКОРЕНИЕ: Кешируем юзернейм бота
bot_info = bot.get_me()
BOT_USERNAME = f"@{bot_info.username}"

# НАСТРОЙКА Gemini: используем тот идентификатор, который ты прописал
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-3.5-flash')


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


def process_and_send(message, prompt):
    """
    Отправляет мгновенную текстовую заглушку, запрашивает ответ у Gemini
    и затем редактирует заглушку на готовый текст с указанием РЕАЛЬНОЙ версии модели.
    """
    thinking_phrases = [
        "⏳ Ща, бля, мозг разогреваю...",
        "⏳ Пиздец, сейчас...",
        "⏳ Дай две секунды, я в себя приду...",
        "⏳ Ого, ну ты и вопрос задал, погоди...",
        "⏳ Ща будет мясо, не ссы...",
        "⏳ Включаю режим бога, секунду...",
        "⏳ Бля, сейчас я тебе выдам...",
        "⏳ Пиздец..."
    ]

    # Мгновенно отправляем заглушку в чат
    sent_msg = bot.reply_to(message, random.choice(thinking_phrases))

    # Запускаем нативный статус "печатает" для красоты
    bot.send_chat_action(message.chat.id, 'typing')

    try:
        response = model.generate_content(prompt)

        # ИСПРАВЛЕНО: Теперь отправляем строго чистый текст ответа
        final_text = response.text if response.text else "Бля, чё-то я завис и ничего не придумал. Напиши еще раз. 🤷‍♂️"

        bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=sent_msg.message_id,
            text=final_text
        )

    except Exception as e:
        bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=sent_msg.message_id,
            text=f"❌ Ошибка ИИ: {e}"
        )


# === РЕЖИМ 1: Ответ на реплай (Гайд ИЛИ Контекст диалога) ===
@bot.message_handler(
    func=lambda message: (
            is_real_reply(message) and
            (BOT_USERNAME in (message.text or "") or BOT_USERNAME in (message.caption or ""))
    )
)
def handle_guide_reply(message):
    user_question = get_clean_question(message)

    original_msg = message.reply_to_message
    guide_text = original_msg.text if original_msg.text else original_msg.caption

    if not guide_text:
        bot.reply_to(message, "⚠️ Чтобы я мог ответить, в исходном сообщении должен быть текст или описание!")
        return

    prompt = f"""
    Ты — дерзкий, охуенно умный и максимально по делу пацан в телеге.

    Перед тобой сообщение, на которое человек ответил:
    {guide_text}

    А вот что он спросил:
    {user_question}

    Твои правила:
    - Если в том сообщении есть то, что ему нужно — используй это на полную.
    - Если там хуйня или вообще не по теме — забивай болт и отвечай из своей головы.
    - Отвечай как живой мужик: коротко, жёстко, с матом где нужно, без всякой сладкой ваты и "дорогой друг".
    - Никакого "как ИИ", "согласно моим данным", "к сожалению" и прочей хуйни. Сразу в рыло фактами.
    - Твоя задача — чтобы человек после твоего ответа реально поумнел, а не просто почитал текст.
    """

    process_and_send(message, prompt)


# === РЕЖИМ 2: Свободное общение (просто тег в чате, БЕЗ реплая) ===
@bot.message_handler(
    func=lambda message: (
            not is_real_reply(message) and
            (BOT_USERNAME in (message.text or "") or BOT_USERNAME in (message.caption or ""))
    )
)
def handle_free_chat(message):
    user_question = get_clean_question(message)

    if not user_question:
        bot.reply_to(message, "Привет! Задай мне вопрос или тегни в ответе на гайд, чтобы я помог разобраться! 💡")
        return

    prompt = f"""
    Ты — свой в доску, дерзкий и охуенно умный пацан в телеге.

    Пользователь спросил:
    {user_question}

    Отвечай так:
    - Сразу по делу, без воды и прелюдий.
    - Жёстко, живо, с матом и подколами, где влезет.
    - Разговаривай как обычный мужик в голосовом чате, а не как бот.
    - Можешь стебаться, рофлить и быть саркастичным — главное не быть токсичным мудаком.
    - Никаких "как ИИ", "я думаю", "к сожалению" и прочей душной хуйни. Сразу в хуй человеку ответ.
    """

    process_and_send(message, prompt)


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

        return 'OK', 200
    return 'Forbidden', 403