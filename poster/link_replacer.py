"""
Модуль для замены ссылок Bonza Chat в статьях с is_link='yes'.
"""
import re
import random
import logging
from typing import Optional
from psycopg import sql

# Основная ссылка, которую нужно найти и заменить
BASE_LINK = "https://bonza.chat/ai-girlfriend"

# Список дополнительных ссылок для случайной замены
REPLACEMENT_LINKS = [
    "https://bonza.chat/nsfw-ai-chatbot",
    "https://bonza.chat/spicy-ai-chat",
    "https://bonza.chat/uncensored-ai-chat",
    "https://bonza.chat/dirty-talk",
    "https://bonza.chat/ai-girlfriend-sexting",
    "https://bonza.chat/ai-girlfriend",
    "https://bonza.chat/ai-boyfriend",
    "https://bonza.chat/ai-companions",
    "https://bonza.chat/realistic-ai-chat",
    "https://bonza.chat/flirty-ai-chat",
    "https://bonza.chat/ai-avatar-creator",
    "https://bonza.chat/ai-roleplay-chat",
    "https://bonza.chat/ai-gaming-companion",
]

# Маппинг sequential_no -> реферальный код
REFERRAL_CODES = {
    1: "wcooksey",
    2: "srobin",
    3: "kcheeck",
    4: "hello001",
    5: "haleymarie",
    6: "gailcruz",
    7: "maeprice",
    8: "carolynaC",
    9: "paulineH",
    10: "priscillaH",
}


def get_referral_code(sequential_no: int) -> str:
    """
    Получить реферальный код для sequential_no.
    
    Args:
        sequential_no: Последовательный номер профиля (1-10)
        
    Returns:
        Реферальный код или пустую строку если не найден
    """
    return REFERRAL_CODES.get(sequential_no, "")


def replace_bonza_link_in_text(text: str, sequential_no: int) -> Optional[str]:
    """
    Заменяет ссылку https://bonza.chat/ai-girlfriend на случайную ссылку из списка
    с добавлением реферального параметра.
    
    Args:
        text: Исходный текст статьи
        sequential_no: Последовательный номер профиля для выбора реферального кода
        
    Returns:
        Текст с замененной ссылкой или None если ссылка не найдена
    """
    if not text:
        return None
    
    # Проверяем, есть ли базовая ссылка в тексте
    if BASE_LINK not in text:
        logging.debug("Base link '%s' not found in text", BASE_LINK)
        return None
    
    # Получаем реферальный код
    referral_code = get_referral_code(sequential_no)
    if not referral_code:
        logging.warning("No referral code found for sequential_no %d", sequential_no)
        return None
    
    # Выбираем случайную ссылку из списка
    replacement_link = random.choice(REPLACEMENT_LINKS)
    
    # Добавляем реферальный параметр
    if '?' in replacement_link:
        # Если в ссылке уже есть параметры, добавляем через &
        final_link = f"{replacement_link}&referral={referral_code}"
    else:
        # Если параметров нет, добавляем через ?
        final_link = f"{replacement_link}?referral={referral_code}"
    
    logging.info("Replacing link: '%s' -> '%s' (referral: %s)", BASE_LINK, replacement_link, referral_code)
    
    # Заменяем все вхождения базовой ссылки на новую
    # Используем re.sub для более точной замены (учитываем возможные варианты написания)
    patterns = [
        re.escape(BASE_LINK),  # Точное совпадение
        re.escape(BASE_LINK) + r'/?',  # С возможным слешем в конце
        re.escape(BASE_LINK) + r'\s',  # С пробелом после
    ]
    
    replaced_text = text
    for pattern in patterns:
        replaced_text = re.sub(pattern, final_link, replaced_text, flags=re.IGNORECASE)
    
    # Также делаем простую замену строки на всякий случай
    replaced_text = replaced_text.replace(BASE_LINK, final_link)
    
    # Проверяем, что замена произошла
    if BASE_LINK in replaced_text:
        logging.warning("Base link still found after replacement, trying more aggressive approach")
        # Более агрессивная замена
        replaced_text = re.sub(
            re.escape(BASE_LINK) + r'[^\s<>"]*',
            final_link,
            replaced_text,
            flags=re.IGNORECASE
        )
    
    if BASE_LINK not in replaced_text:
        logging.info("✓ Link replaced successfully")
        return replaced_text
    else:
        logging.error("Failed to replace link, base link still present")
        return None


def update_article_body_with_replaced_link(
    pg_conn,
    table_name: str,
    article_id: int,
    sequential_no: int
) -> bool:
    """
    Обновляет тело статьи в БД, заменяя ссылку Bonza Chat на случайную с реферальным кодом.
    
    Args:
        pg_conn: Подключение к PostgreSQL
        table_name: Имя таблицы
        article_id: ID статьи
        sequential_no: Последовательный номер профиля
        
    Returns:
        True если успешно, False при ошибке
    """
    logging.info("Updating article ID %s with replaced link (sequential_no: %d)", article_id, sequential_no)
    
    # Получаем текущее тело статьи
    select_query = sql.SQL("""
        SELECT body
        FROM {table}
        WHERE id = %s
    """).format(table=sql.Identifier(table_name))
    
    try:
        with pg_conn.cursor() as cur:
            cur.execute(select_query, (article_id,))
            row = cur.fetchone()
            
            if not row:
                logging.error("Article ID %s not found in table %s", article_id, table_name)
                return False
            
            original_body = row['body'] if isinstance(row, dict) else row[0]
            
            if not original_body:
                logging.warning("Article ID %s has empty body", article_id)
                return False
            
            # Заменяем ссылку
            updated_body = replace_bonza_link_in_text(original_body, sequential_no)
            
            if updated_body is None:
                logging.warning("No link replacement needed or failed for article ID %s", article_id)
                return False
            
            # Обновляем в БД
            update_query = sql.SQL("""
                UPDATE {table}
                SET body = %s
                WHERE id = %s
            """).format(table=sql.Identifier(table_name))
            
            cur.execute(update_query, (updated_body, article_id))
            pg_conn.commit()
            
            logging.info("✓ Article ID %s body updated with replaced link", article_id)
            return True
            
    except Exception as e:
        logging.error("Error updating article body: %s", e, exc_info=True)
        pg_conn.rollback()
        return False

