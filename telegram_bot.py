"""
Telegram bot for article posting notifications on Medium and Quora.
Sends notifications to all users who pressed /start in the bot.
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

# File to store subscribers (those who pressed /start)
SUBSCRIBERS_FILE = "telegram_subscribers.json"


# ==================== SUBSCRIBER MANAGEMENT ====================

def load_subscribers() -> Set[str]:
    """
    Loads the list of subscriber chat_ids from file.
    
    Returns:
        Set of subscriber chat_ids
    """
    if not os.path.exists(SUBSCRIBERS_FILE):
        return set()
    
    try:
        with open(SUBSCRIBERS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if isinstance(data, list):
                return set(str(chat_id) for chat_id in data)
            elif isinstance(data, dict) and 'subscribers' in data:
                return set(str(chat_id) for chat_id in data['subscribers'])
            else:
                return set()
    except (json.JSONDecodeError, IOError) as e:
        logging.warning("Failed to load subscribers file: %s. Starting with empty list.", e)
        return set()


def save_subscribers(subscribers: Set[str]) -> None:
    """
    Saves the list of subscriber chat_ids to file.
    
    Args:
        subscribers: Set of subscriber chat_ids
    """
    try:
        with open(SUBSCRIBERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(list(subscribers), f, indent=2, ensure_ascii=False)
        logging.debug("Subscribers saved: %d subscriber(s)", len(subscribers))
    except IOError as e:
        logging.error("Failed to save subscribers file: %s", e)


def sync_subscribers_from_start_commands() -> int:
    """
    Syncs subscriber list from bot updates.
    Finds all users who sent the /start command.
    
    Returns:
        Number of found subscribers
    """
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        logging.warning("Telegram bot token not configured, skipping sync")
        return 0
    
    try:
        subscribers = load_subscribers()
        initial_count = len(subscribers)
        
        # Get all updates
        url = f"{TELEGRAM_API_URL}/getUpdates"
        offset = 0
        max_updates = 1000  # Safety limit
        
        while True:
            params = {
                "offset": offset,
                "timeout": 1,
                "limit": 100
            }
            
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code != 200:
                logging.warning("Failed to get updates: HTTP %d", response.status_code)
                break
            
            data = response.json()
            if not data.get('ok'):
                logging.warning("Telegram API returned error: %s", data.get('description', 'Unknown error'))
                break
            
            updates = data.get('result', [])
            if not updates:
                break
            
            # Process updates
            for update in updates:
                update_id = update.get('update_id', 0)
                offset = max(offset, update_id + 1)
                
                message = update.get('message', {})
                if not message:
                    continue
                
                # Check if there's a /start command
                text = message.get('text', '').strip()
                if text == '/start' or text.startswith('/start '):
                    chat = message.get('chat', {})
                    chat_id = str(chat.get('id'))
                    
                    if chat_id and chat_id not in subscribers:
                        subscribers.add(chat_id)
                        logging.info("Found new subscriber from /start command: %s", chat_id)
            
            # Safety limit
            if offset > max_updates:
                logging.warning("Reached max updates limit, stopping sync")
                break
        
        # Save updated list
        if len(subscribers) > initial_count:
            save_subscribers(subscribers)
            added_count = len(subscribers) - initial_count
            logging.info("Synced %d new subscriber(s) from /start commands (total: %d)", 
                       added_count, len(subscribers))
            return added_count
        else:
            logging.debug("No new subscribers found (total: %d)", len(subscribers))
            return 0
        
    except Exception as e:
        logging.error("Error syncing subscribers from /start commands: %s", e)
        return 0


# ==================== MESSAGE SENDING ====================

def send_message(text: str, chat_id: Optional[str] = None) -> bool:
    """
    Sends a text message to Telegram.
    If chat_id is not specified, sends to all subscribers (who pressed /start).
    
    Args:
        text: Message text
        chat_id: Specific chat_id to send to (optional)
        
    Returns:
        True if successfully sent to at least one recipient, False on error
    """
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        logging.warning("Telegram bot token not configured, skipping message")
        return False
    
    # If specific chat_id is provided, send only to that one
    if chat_id:
        return _send_to_chat(text, chat_id)
    
    # Get subscriber list
    subscribers = load_subscribers()
    
    # If no subscribers, try to sync
    if not subscribers:
        logging.info("No subscribers found, syncing from /start commands...")
        sync_subscribers_from_start_commands()
        subscribers = load_subscribers()
    
    # If still no subscribers, use old method (from config) for backward compatibility
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
        logging.warning("No Telegram subscribers found, skipping message")
        return False
    
    # Send to all subscribers
    success_count = 0
    failed_chat_ids = []
    
    for sub_chat_id in subscribers:
        if _send_to_chat(text, sub_chat_id):
            success_count += 1
        else:
            failed_chat_ids.append(sub_chat_id)
    
    # Remove invalid chat_ids
    if failed_chat_ids:
        subscribers = load_subscribers()
        for chat_id in failed_chat_ids:
            subscribers.discard(chat_id)
        save_subscribers(subscribers)
        logging.info("Removed %d invalid chat_id(s) from subscribers", len(failed_chat_ids))
    
    if success_count > 0:
        logging.debug("Telegram message sent to %d/%d subscriber(s)", success_count, len(subscribers))
        return True
    else:
        logging.error("Failed to send Telegram message to any subscriber")
        return False


def _send_to_chat(text: str, chat_id: str) -> bool:
    """
    Internal function to send message to a specific chat_id.
    
    Args:
        text: Message text
        chat_id: Recipient chat ID
        
    Returns:
        True if successful, False on error
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
            error_data = response.json() if response.content else {}
            error_desc = error_data.get('description', '')
            
            # Remove invalid chat_ids
            if (response.status_code == 400 and 
                ('chat not found' in error_desc.lower() or 
                 'chat_id is empty' in error_desc.lower())):
                logging.debug("Chat ID %s is invalid, will be removed", chat_id)
            elif response.status_code == 403:
                logging.debug("Bot blocked by user %s", chat_id)
            
            return False
    except Exception as e:
        logging.debug("Error sending Telegram message to %s: %s", chat_id, e)
        return False


# ==================== NOTIFICATIONS ====================

def notify_poster_started(table_name: str, article_assignments: List) -> bool:
    """
    Sends notification about auto-poster start with posting schedule.
    
    Args:
        table_name: Table name
        article_assignments: List of tuples (profile_id, profile_no, seq_no, posting_time, article)
        
    Returns:
        True if successful, False on error
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
        
        # Determine if article has a link
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
    Sends notification about article publication.
    
    Args:
        title: Article title
        body: Article text (will be truncated to 200 characters)
        hashtags: List of hashtags
        url: Published article URL
        has_link: Whether article has a link
        profile_no: Internal profile number
        sequential_no: Sequential profile number (1-10)
        profile_id: Profile ID in Ads Power
        
    Returns:
        True if successful, False on error
    """
    # Truncate body to 200 characters
    body_preview = body[:200] + "..." if len(body) > 200 else body
    
    # Escape HTML characters in text
    title_escaped = html.escape(title)
    body_escaped = html.escape(body_preview)
    tags_escaped = html.escape(", ".join(hashtags) if hashtags else "none")
    
    # Form link information
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
    Sends final report about posted articles.
    
    Args:
        posted_articles: List of dictionaries with information about posted articles:
            - topic: Article topic
            - profile_seq: Sequential profile number
            - profile_no: Profile number
            - url: Published article URL
            - has_link: Whether article has a link (is_link='yes')
            - article_link: Link from article (for is_link='yes')
        
    Returns:
        True if successful, False on error
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
        
        # Escape HTML
        topic_escaped = html.escape(str(topic)[:60])
        
        text += f"<b>{i}. {topic_escaped}</b>\n"
        text += f"   📱 Platform: {platform}\n"
        text += f"   👤 Profile: Seq {profile_seq} (No {profile_no})\n"
        text += f"   🔗 Article URL: {url}\n"
        
        # If article has a link, show it
        if has_link and article_link:
            text += f"   🔗 Link in article: {article_link}\n"
        elif has_link:
            text += f"   ⚠️ Article has link, but link not found in body\n"
        
        text += "\n"
    
    return send_message(text)
