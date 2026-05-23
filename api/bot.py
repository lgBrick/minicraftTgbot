import os
import telebot
import google.generativeai as genai

# Достаем токены из системы
TG_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Инициализируем бота в классическом режиме непрерывного опроса (Long Polling)
bot = telebot.TeleBot(TG_TOKEN)

# НАСТРОЙКА Gemini: используем самый свежий Flash
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-flash-latest')

# Кешируем юзернейм
bot_info = bot.get_me()
BOT_USERNAME = f"@{bot_info.username}"


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


def true_streaming_to_telegram(message, prompt):
    """
    НАСТОЯЩИЙ СТРИМИНГ ДЛЯ ПОСТОЯННОГО СЕРВЕРА.
    Слова улетают в Телеграм без задержек по мере генерации.
    """
    # Создаем стартовое сообщение-заглушку
    sent_msg = bot.reply_to(message, "⏳ Ща, погодь...")

    current_text = ""
    last_sent_text = ""

    try:
        # Запускаем живой поток от Gemini
        response_stream = model.generate_content(prompt, stream=True)

        for chunk in response_stream:
            if chunk.text:
                current_text += chunk.text

                # Как только текст увеличился хотя бы на 6 символов, сразу обновляем ТГ.
                # На постоянном сервере это происходит мгновенно.
                if len(current_text) - len(last_sent_text) > 6:
                    try:
                        bot.edit_message_text(
                            chat_id=message.chat.id,
                            message_id=sent_msg.message_id,
                            text=current_text + " ✍️"
                        )
                        last_sent_text = current_text
                    except Exception:
                        pass

        # Финальный чистый текст
        bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=sent_msg.message_id,
            text=current_text.strip() if current_text.strip() else "Бля, Gemini промолчал чё-то. 🤷‍♂️"
        )

    except Exception as e:
        bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=sent_msg.message_id,
            text=f"❌ Ошибка стриминга: {e}"
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
    bot.send_chat_action(message.chat.id, 'typing')

    original_msg = message.reply_to_message
    guide_text = original_msg.text if original_msg.text else original_msg.caption

    if not guide_text:
        bot.reply_to(message, "⚠️ Нет текста в исходном сообщении!")
        return

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
    4. Отвечай емко, в пределах 1-4 предложений, чтобы стриминг букв на экране выглядел динамично и быстро.
    5. Никогда не используй фразы вроде "Я искусственный интеллект". Сразу переходи к делу.
    """

    true_streaming_to_telegram(message, prompt)


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
        bot.reply_to(message, "Здорово, бро! Задай мне вопрос или тегни в ответе на гайд, я раскидаю! 💡")
        return

    prompt = f"""
    Ты — умный ИИ-помощник в Telegram-группе, но общаешься как старый друг и свой в доску братан.

    ВОПРОС ПОЛЬЗОВАТЕЛЯ:
    {user_question}

    Твоя задача:
    1. Дать четкий, правильный и полезный ответ на вопрос. Отвечай емко, без лишней воды.
    2. Вести диалог живо и неформально. Разрешается дружеский стёб, подколы, сарказм и умеренный мат (но не скатывайся в откровенное хамство).
    3. Разговаривай как обычный человек в чате, используй сленг.
    4. Никогда не отвечай шаблонами вроде "Чем я могу помочь?". Сразу херачь по делу в своем стиле.
    """

    true_streaming_to_telegram(message, prompt)


# Запуск постоянного прослушивания (Long Polling)
if __name__ == '__main__':
    print("Бот успешно запущен в режиме НАСТОЯЩЕГО стриминга...")
    bot.infinity_polling()