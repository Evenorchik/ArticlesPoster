"""
Telegram бот для уведомлений о постинге статей на Medium.
"""
import logging
from typing import Optional, List
import requests
import html

# ==================== КОНФИГУРАЦИЯ ====================
# Вставьте токен вашего Telegram бота здесь
TELEGRAM_BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"
TELEGRAM_CHAT_ID = "YOUR_CHAT_ID_HERE"  # ID чата или канала для отправки сообщений

TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

# ==================== ФУНКЦИИ ====================

def send_message(text: str) -> bool:
    """
    Отправляет текстовое сообщение в Telegram.
    
    Args:
        text: Текст сообщения
        
    Returns:
        True если успешно, False при ошибке
    """
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        logging.warning("Telegram bot token not configured, skipping message")
        return False
    
    if not TELEGRAM_CHAT_ID or TELEGRAM_CHAT_ID == "YOUR_CHAT_ID_HERE":
        logging.warning("Telegram chat ID not configured, skipping message")
        return False
    
    url = f"{TELEGRAM_API_URL}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML"
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            logging.debug("Telegram message sent successfully")
            return True
        else:
            logging.error("Failed to send Telegram message: HTTP %d - %s", 
                        response.status_code, response.text)
            return False
    except Exception as e:
        logging.error("Error sending Telegram message: %s", e)
        return False


def notify_poster_started(profiles_count: int, articles_count: int, table_name: str) -> bool:
    """
    Отправляет уведомление о запуске автопостера.
    
    Args:
        profiles_count: Количество профилей для постинга
        articles_count: Количество статей для постинга
        table_name: Название таблицы
        
    Returns:
        True если успешно, False при ошибке
    """
    text = (
        f"<b>Автопостер запущен</b>\n\n"
        f"Таблица: {table_name}\n"
        f"Профилей: {profiles_count}\n"
        f"Статей: {articles_count}"
    )
    return send_message(text)


def notify_article_posted(
    title: str,
    body: str,
    hashtags: List[str],
    url: str,
    has_link: bool,
    profile_no: int,
    sequential_no: int,
    profile_id: str
) -> bool:
    """
    Отправляет уведомление о публикации статьи.
    
    Args:
        title: Заголовок статьи
        body: Текст статьи (будет обрезан до 200 символов)
        hashtags: Список хэштегов
        url: URL опубликованной статьи
        has_link: Есть ли в статье ссылка
        profile_no: Внутренний номер профиля
        sequential_no: Порядковый номер профиля (1-10)
        profile_id: ID профиля в Ads Power
        
    Returns:
        True если успешно, False при ошибке
    """
    # Обрезаем body до 200 символов
    body_preview = body[:200] + "..." if len(body) > 200 else body
    
    # Экранируем HTML-символы в тексте
    title_escaped = html.escape(title)
    body_escaped = html.escape(body_preview)
    tags_escaped = html.escape(", ".join(hashtags) if hashtags else "нет")
    
    # Формируем информацию о ссылке
    link_status = "да" if has_link else "нет"
    
    text = (
        f"<b>Статья опубликована</b>\n\n"
        f"<b>Заголовок:</b> {title_escaped}\n\n"
        f"<b>Текст (200 символов):</b>\n{body_escaped}\n\n"
        f"<b>Хэштеги:</b> {tags_escaped}\n"
        f"<b>Есть ссылка:</b> {link_status}\n"
        f"<b>Профиль:</b> No {profile_no}, Seq {sequential_no}, ID {profile_id}\n"
        f"<b>URL:</b> {url}"
    )
    
    return send_message(text)

