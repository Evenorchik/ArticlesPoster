"""
Простой бот-листенер для автоматического добавления подписчиков.
Запускается в фоне и слушает команду /start.
"""
import logging
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram_bot import load_subscribers, save_subscribers
from config_bot import TELEGRAM_BOT_TOKEN

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start - автоматически добавляет пользователя в список."""
    chat_id = str(update.effective_chat.id)
    
    # Загружаем текущий список подписчиков
    subscribers = load_subscribers()
    
    # Добавляем нового пользователя, если его еще нет
    if chat_id not in subscribers:
        subscribers.add(chat_id)
        save_subscribers(subscribers)
        logging.info(f"✓ New subscriber added: {chat_id} (total: {len(subscribers)})")
        
        await update.message.reply_text(
            "✅ Вы подписаны на уведомления о постинге статей!\n\n"
            "Теперь вы будете получать уведомления о запуске постинга и завершении работы."
        )
    else:
        logging.debug(f"User {chat_id} already subscribed")
        await update.message.reply_text(
            "✅ Вы уже подписаны на уведомления!"
        )


def main():
    """Запуск бота-листенера."""
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        logging.error("Telegram bot token not configured!")
        return
    
    # Создаем приложение
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Регистрируем обработчик команды /start
    application.add_handler(CommandHandler("start", start_command))
    
    # Запускаем бота
    logging.info("Bot listener started. Waiting for /start commands...")
    application.run_polling(allowed_updates=["message"])


if __name__ == "__main__":
    main()

