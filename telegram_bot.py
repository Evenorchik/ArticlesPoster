"""
Telegram бот для уведомлений о постинге статей на Medium.
"""
import logging
from typing import Optional, List
import requests
import html

# Импортируем конфигурацию
from config_bot import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

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


def notify_poster_started(table_name: str, article_assignments: List) -> bool:
    """
    Отправляет уведомление о запуске автопостера с расписанием постинга.
    
    Args:
        table_name: Название таблицы
        article_assignments: Список кортежей (profile_id, profile_no, seq_no, posting_time, article)
        
    Returns:
        True если успешно, False при ошибке
    """
    from datetime import datetime
    import pytz
    
    GMT_MINUS_5 = pytz.timezone('America/New_York')
    
    text = f"<b>Auto-poster started</b>\n\n"
    text += f"Table: {table_name}\n"
    text += f"Articles: {len(article_assignments)}\n\n"
    text += f"<b>Posting schedule:</b>\n"
    
    for profile_id, profile_no, seq_no, posting_time, article in article_assignments:
        article_topic = article.get('topic', 'N/A')[:40] if isinstance(article, dict) else 'N/A'
        time_str = posting_time.strftime("%H:%M")
        text += f"Profile Seq:{seq_no} (No:{profile_no}, ID:{profile_id}) → {time_str} GMT-5\n"
        text += f"Article: {article_topic}\n\n"
    
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
    tags_escaped = html.escape(", ".join(hashtags) if hashtags else "none")
    
    # Формируем информацию о ссылке
    link_status = "yes" if has_link else "no"
    
    text = (
        f"<b>Article published</b>\n\n"
        f"<b>Title:</b> {title_escaped}\n\n"
        f"<b>Text (200 characters):</b>\n{body_escaped}\n\n"
        f"<b>Hashtags:</b> {tags_escaped}\n"
        f"<b>Has link:</b> {link_status}\n"
        f"<b>Profile:</b> No {profile_no}, Seq {sequential_no}, ID {profile_id}\n"
        f"<b>URL:</b> {url}"
    )
    
    return send_message(text)

