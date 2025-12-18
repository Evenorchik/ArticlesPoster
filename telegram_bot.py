"""
Telegram бот для уведомлений о постинге статей на Medium и Quora.
Поддерживает множественных подписчиков.
"""
import logging
import json
import os
from typing import Optional, List, Set
import requests
import html

# Импортируем конфигурацию
from config_bot import TELEGRAM_BOT_TOKEN

TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

# Файл для хранения подписчиков
SUBSCRIBERS_FILE = "telegram_subscribers.json"


# ==================== УПРАВЛЕНИЕ ПОДПИСЧИКАМИ ====================

def load_subscribers() -> Set[str]:
    """
    Загружает список chat_id подписчиков из файла.
    
    Returns:
        Множество chat_id подписчиков
    """
    if not os.path.exists(SUBSCRIBERS_FILE):
        # Если файла нет, создаем его с пустым списком
        save_subscribers(set())
        return set()
    
    try:
        with open(SUBSCRIBERS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # Поддерживаем как список, так и множество
            if isinstance(data, list):
                return set(data)
            elif isinstance(data, dict) and 'subscribers' in data:
                return set(data['subscribers'])
            else:
                return set()
    except (json.JSONDecodeError, IOError) as e:
        logging.warning("Failed to load subscribers file: %s. Starting with empty list.", e)
        return set()


def save_subscribers(subscribers: Set[str]) -> None:
    """
    Сохраняет список chat_id подписчиков в файл.
    
    Args:
        subscribers: Множество chat_id подписчиков
    """
    try:
        with open(SUBSCRIBERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(list(subscribers), f, indent=2, ensure_ascii=False)
        logging.debug("Subscribers saved: %d subscriber(s)", len(subscribers))
    except IOError as e:
        logging.error("Failed to save subscribers file: %s", e)


def add_subscriber(chat_id: str) -> bool:
    """
    Добавляет chat_id в список подписчиков.
    
    Args:
        chat_id: Chat ID для добавления
    
    Returns:
        True если успешно добавлен, False если уже существует
    """
    subscribers = load_subscribers()
    if chat_id in subscribers:
        logging.debug("Chat ID %s already subscribed", chat_id)
        return False
    
    subscribers.add(chat_id)
    save_subscribers(subscribers)
    logging.info("Added subscriber: %s (total: %d)", chat_id, len(subscribers))
    return True


def remove_subscriber(chat_id: str) -> bool:
    """
    Удаляет chat_id из списка подписчиков.
    
    Args:
        chat_id: Chat ID для удаления
    
    Returns:
        True если успешно удален, False если не найден
    """
    subscribers = load_subscribers()
    if chat_id not in subscribers:
        logging.debug("Chat ID %s not found in subscribers", chat_id)
        return False
    
    subscribers.remove(chat_id)
    save_subscribers(subscribers)
    logging.info("Removed subscriber: %s (total: %d)", chat_id, len(subscribers))
    return True


def get_subscribers() -> Set[str]:
    """
    Получает текущий список подписчиков.
    
    Returns:
        Множество chat_id подписчиков
    """
    return load_subscribers()


def sync_subscribers_from_updates() -> int:
    """
    Синхронизирует список подписчиков из последних обновлений бота.
    Добавляет всех chat_id, которые писали боту.
    
    Returns:
        Количество добавленных подписчиков
    """
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        logging.warning("Telegram bot token not configured, skipping sync")
        return 0
    
    try:
        # Получаем последние обновления
        url = f"{TELEGRAM_API_URL}/getUpdates"
        params = {"timeout": 1, "limit": 100}  # Получаем до 100 последних обновлений
        response = requests.get(url, params=params, timeout=10)
        
        if response.status_code != 200:
            logging.warning("Failed to get updates: HTTP %d - %s", response.status_code, response.text)
            return 0
        
        data = response.json()
        if not data.get('ok'):
            logging.warning("Telegram API returned error: %s", data.get('description', 'Unknown error'))
            return 0
        
        updates = data.get('result', [])
        subscribers = load_subscribers()
        added_count = 0
        
        for update in updates:
            message = update.get('message', {})
            chat = message.get('chat', {})
            chat_id = str(chat.get('id'))
            
            if chat_id and chat_id not in subscribers:
                subscribers.add(chat_id)
                added_count += 1
                logging.info("Auto-added subscriber from updates: %s", chat_id)
        
        if added_count > 0:
            save_subscribers(subscribers)
            logging.info("Synced %d new subscriber(s) from updates (total: %d)", added_count, len(subscribers))
        
        return added_count
        
    except Exception as e:
        logging.error("Error syncing subscribers from updates: %s", e)
        return 0


# ==================== ОТПРАВКА СООБЩЕНИЙ ====================

def send_message(text: str, chat_id: Optional[str] = None) -> bool:
    """
    Отправляет текстовое сообщение в Telegram.
    Если chat_id не указан, отправляет всем подписчикам.
    
    Args:
        text: Текст сообщения
        chat_id: Конкретный chat_id для отправки (опционально)
        
    Returns:
        True если успешно отправлено хотя бы одному получателю, False при ошибке
    """
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        logging.warning("Telegram bot token not configured, skipping message")
        return False
    
    # Если указан конкретный chat_id, отправляем только ему
    if chat_id:
        return _send_to_chat(text, chat_id)
    
    # Иначе отправляем всем подписчикам
    subscribers = load_subscribers()
    
    # Если подписчиков нет, пытаемся синхронизировать из обновлений
    if not subscribers:
        logging.info("No subscribers found, attempting to sync from bot updates...")
        sync_subscribers_from_updates()
        subscribers = load_subscribers()
    
    # Если все еще нет подписчиков, используем старый способ (из конфига)
    if not subscribers:
        try:
            from config_bot import TELEGRAM_CHAT_ID
            if TELEGRAM_CHAT_ID and TELEGRAM_CHAT_ID != "YOUR_CHAT_ID_HERE":
                logging.info("No subscribers found, using TELEGRAM_CHAT_ID from config: %s", TELEGRAM_CHAT_ID)
                subscribers.add(TELEGRAM_CHAT_ID)
                save_subscribers(subscribers)
        except ImportError:
            pass
    
    if not subscribers:
        logging.warning("No Telegram subscribers found and no chat ID configured, skipping message")
        return False
    
    # Отправляем всем подписчикам
    success_count = 0
    for sub_chat_id in subscribers:
        if _send_to_chat(text, sub_chat_id):
            success_count += 1
    
    if success_count > 0:
        logging.debug("Telegram message sent to %d/%d subscriber(s)", success_count, len(subscribers))
        return True
    else:
        logging.error("Failed to send Telegram message to any subscriber")
        return False


def _send_to_chat(text: str, chat_id: str) -> bool:
    """
    Внутренняя функция для отправки сообщения конкретному chat_id.
    
    Args:
        text: Текст сообщения
        chat_id: Chat ID получателя
        
    Returns:
        True если успешно, False при ошибке
    """
    url = f"{TELEGRAM_API_URL}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML"
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            return True
        else:
            # Если chat_id недействителен, удаляем его из подписчиков
            if response.status_code == 400:
                error_data = response.json()
                if error_data.get('description', '').startswith('Bad Request: chat not found'):
                    logging.warning("Chat ID %s not found, removing from subscribers", chat_id)
                    remove_subscriber(chat_id)
            logging.debug("Failed to send Telegram message to %s: HTTP %d - %s", 
                        chat_id, response.status_code, response.text)
            return False
    except Exception as e:
        logging.debug("Error sending Telegram message to %s: %s", chat_id, e)
        return False


# ==================== УВЕДОМЛЕНИЯ ====================

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
    
    KIEV_TIMEZONE = pytz.timezone('Europe/Kiev')
    
    text = f"<b>🚀 Auto-poster started</b>\n\n"
    text += f"📊 Table: {table_name}\n"
    text += f"📝 Articles: {len(article_assignments)}\n\n"
    text += f"<b>📅 Posting schedule:</b>\n\n"
    
    for profile_id, profile_no, seq_no, posting_time, article in article_assignments:
        article_id = article.get('id') if isinstance(article, dict) else article[0]
        article_topic = article.get('topic', 'N/A')[:50] if isinstance(article, dict) else 'N/A'
        is_link = article.get('is_link', 'no') if isinstance(article, dict) else 'no'
        time_str = posting_time.strftime("%H:%M")
        
        # Определяем, есть ли ссылка в статье
        link_indicator = "🔗" if is_link == 'yes' else "📄"
        
        text += f"{link_indicator} <b>Profile Seq:{seq_no}</b> (No:{profile_no}) → <b>{time_str}</b> (Kiev time)\n"
        text += f"   Article ID: {article_id}\n"
        text += f"   Topic: {html.escape(article_topic)}\n"
        if is_link == 'yes':
            text += f"   ⚠️ <b>This article contains a link</b>\n"
        text += "\n"
    
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


def notify_posting_complete(posted_articles: List[dict]) -> bool:
    """
    Отправляет финальный отчет о запощенных статьях.
    
    Args:
        posted_articles: Список словарей с информацией о запощенных статьях:
            - topic: Тема статьи
            - profile_seq: Sequential номер профиля
            - profile_no: Номер профиля
            - url: URL опубликованной статьи
            - has_link: Есть ли в статье ссылка (is_link='yes')
            - article_link: Ссылка из статьи (для is_link='yes')
        
    Returns:
        True если успешно, False при ошибке
    """
    if not posted_articles:
        text = "<b>📊 Posting Report</b>\n\n"
        text += "❌ No articles were posted."
        return send_message(text)
    
    text = f"<b>📊 Posting Report</b>\n\n"
    text += f"✅ Successfully posted: {len(posted_articles)} article(s)\n\n"
    text += f"<b>📝 Posted articles:</b>\n\n"
    
    for i, article_info in enumerate(posted_articles, 1):
        topic = article_info.get('topic', 'N/A')
        profile_seq = article_info.get('profile_seq', 'N/A')
        profile_no = article_info.get('profile_no', 'N/A')
        url = article_info.get('url', 'N/A')
        has_link = article_info.get('has_link', False)
        article_link = article_info.get('article_link', '')
        platform = article_info.get('platform', 'medium').upper()
        
        # Экранируем HTML
        topic_escaped = html.escape(str(topic)[:60])
        
        text += f"<b>{i}. {topic_escaped}</b>\n"
        text += f"   📱 Platform: {platform}\n"
        text += f"   👤 Profile: Seq {profile_seq} (No {profile_no})\n"
        text += f"   🔗 Article URL: {url}\n"
        
        # Если в статье есть ссылка, показываем её
        if has_link and article_link:
            text += f"   🔗 Link in article: {article_link}\n"
        elif has_link:
            text += f"   ⚠️ Article has link, but link not found in body\n"
        
        text += "\n"
    
    return send_message(text)
