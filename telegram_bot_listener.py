"""
Простой бот-листенер для автоматического добавления подписчиков.
Запускается в фоне и слушает команду /start.
"""
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram_bot import load_subscribers, save_subscribers
from config_bot import TELEGRAM_BOT_TOKEN

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start - автоматически добавляет пользователя в список."""
    try:
        if not update.message:
            logging.warning("Received update without message")
            return
        
        chat_id = str(update.effective_chat.id)
        logging.info(f"Received /start command from chat_id: {chat_id}")
        
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
            logging.info(f"User {chat_id} already subscribed (total: {len(subscribers)})")
            await update.message.reply_text(
                "✅ Вы уже подписаны на уведомления!"
            )
    except Exception as e:
        logging.error(f"Error in start_command: {e}", exc_info=True)
        if update.message:
            try:
                await update.message.reply_text("❌ Произошла ошибка при обработке команды. Попробуйте позже.")
            except:
                pass


def main():
    """Запуск бота-листенера."""
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        logging.error("Telegram bot token not configured!")
        return
    
    logging.info(f"Initializing bot with token: {TELEGRAM_BOT_TOKEN[:10]}...")
    
    try:
        # Создаем приложение
        application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
        
        # Регистрируем обработчик команды /start
        application.add_handler(CommandHandler("start", start_command))
        
        # Запускаем бота
        logging.info("="*60)
        logging.info("Bot listener started successfully!")
        logging.info("Waiting for /start commands...")
        logging.info("="*60)
        application.run_polling(
            allowed_updates=["message"],
            drop_pending_updates=True  # Игнорируем старые обновления
        )
    except Exception as e:
        logging.error(f"Failed to start bot: {e}", exc_info=True)


if __name__ == "__main__":
    main()

