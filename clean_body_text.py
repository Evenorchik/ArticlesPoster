"""
Скрипт для очистки колонки body в таблице refined_articles_1 от нежелательных элементов:
- "Topic:" (с большой буквы)
- "topic:" (с маленькой буквы)
- "**" (две звездочки рядом, но не одна звездочка)
"""
import re
import logging
from poster.db import get_pg_conn
from psycopg import sql
from config import LOG_LEVEL

# Настройка логирования
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s - %(levelname)s - %(message)s"
)

TABLE_NAME = "refined_articles_1"


def clean_body_text(text: str) -> str:
    """
    Очищает текст от нежелательных элементов:
    - "Topic:" (с большой буквы, case-sensitive)
    - "topic:" (с маленькой буквы, case-sensitive)
    - "**" (две звездочки рядом, но не одна звездочка)
    
    Args:
        text: Исходный текст
        
    Returns:
        Очищенный текст
    """
    if not text:
        return text
    
    cleaned = text
    
    # Удаляем "Topic:" (с большой буквы, case-sensitive)
    # Ищем "Topic:" как отдельное слово (с границей слова)
    cleaned = re.sub(r'\bTopic:\s*', '', cleaned)
    # Также удаляем если это с пробелами вокруг (для случаев без границы слова)
    cleaned = re.sub(r'\s+Topic:\s+', ' ', cleaned)
    cleaned = re.sub(r'^\s*Topic:\s*', '', cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r'\s+Topic:\s*$', '', cleaned, flags=re.MULTILINE)
    
    # Удаляем "topic:" (с маленькой буквы, case-sensitive)
    cleaned = re.sub(r'\btopic:\s*', '', cleaned)
    cleaned = re.sub(r'\s+topic:\s+', ' ', cleaned)
    cleaned = re.sub(r'^\s*topic:\s*', '', cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r'\s+topic:\s*$', '', cleaned, flags=re.MULTILINE)
    
    # Удаляем "**" (две звездочки рядом)
    # Важно: удаляем только две звездочки рядом, не одну
    # Заменяем "**" на пустую строку (это безопасно, так как не затрагивает одиночные *)
    cleaned = cleaned.replace('**', '')
    
    return cleaned


def process_table(pg_conn, table_name: str, dry_run: bool = False):
    """
    Обрабатывает все записи в таблице, очищая колонку body.
    
    Args:
        pg_conn: Подключение к PostgreSQL
        table_name: Имя таблицы
        dry_run: Если True, только показывает что будет изменено, не обновляет БД
    """
    logging.info("="*60)
    logging.info("Starting body text cleaning for table: %s", table_name)
    if dry_run:
        logging.info("DRY RUN MODE - no changes will be made to database")
    logging.info("="*60)
    
    # Проверяем наличие таблицы и колонки body
    check_query = sql.SQL("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = %s AND column_name = 'body'
    """)
    
    with pg_conn.cursor() as cur:
        cur.execute(check_query, (table_name,))
        has_body = cur.fetchone() is not None
    
    if not has_body:
        logging.error("Table %s does not have 'body' column!", table_name)
        return
    
    # Получаем все записи с body
    select_query = sql.SQL("""
        SELECT id, body
        FROM {table}
        WHERE body IS NOT NULL AND body != ''
    """).format(table=sql.Identifier(table_name))
    
    try:
        with pg_conn.cursor() as cur:
            cur.execute(select_query)
            rows = cur.fetchall()
        
        logging.info("Found %d records with non-empty body", len(rows))
        
        updated_count = 0
        skipped_count = 0
        
        for row in rows:
            article_id = row['id'] if isinstance(row, dict) else row[0]
            original_body = row['body'] if isinstance(row, dict) else row[1]
            
            if not original_body:
                skipped_count += 1
                continue
            
            # Очищаем текст
            cleaned_body = clean_body_text(original_body)
            
            # Проверяем, изменился ли текст
            if cleaned_body == original_body:
                skipped_count += 1
                continue
            
            # Показываем изменения
            logging.info("")
            logging.info("Article ID: %s", article_id)
            logging.debug("Original (first 200 chars): %s", original_body[:200])
            logging.debug("Cleaned (first 200 chars): %s", cleaned_body[:200])
            
            # Подсчитываем удаленные элементы
            removed_topic_upper = len(re.findall(r'\bTopic:\s*', original_body)) - len(re.findall(r'\bTopic:\s*', cleaned_body))
            removed_topic_lower = len(re.findall(r'\btopic:\s*', original_body)) - len(re.findall(r'\btopic:\s*', cleaned_body))
            removed_topic = removed_topic_upper + removed_topic_lower
            removed_stars = original_body.count('**') - cleaned_body.count('**')
            
            if removed_topic > 0 or removed_stars > 0:
                logging.info("  Removed: %d 'Topic:'/'topic:' occurrences, %d '**' pairs", removed_topic, removed_stars)
            
            # Обновляем в БД (если не dry_run)
            if not dry_run:
                update_query = sql.SQL("""
                    UPDATE {table}
                    SET body = %s
                    WHERE id = %s
                """).format(table=sql.Identifier(table_name))
                
                try:
                    with pg_conn.cursor() as update_cur:
                        update_cur.execute(update_query, (cleaned_body, article_id))
                    pg_conn.commit()
                    updated_count += 1
                    logging.info("  ✓ Updated")
                except Exception as e:
                    logging.error("  ✗ Failed to update article ID %s: %s", article_id, e)
                    pg_conn.rollback()
            else:
                updated_count += 1
                logging.info("  [DRY RUN] Would update")
        
        logging.info("")
        logging.info("="*60)
        logging.info("Processing completed!")
        logging.info("  Updated: %d", updated_count)
        logging.info("  Skipped (no changes): %d", skipped_count)
        logging.info("="*60)
        
    except Exception as e:
        logging.error("Error processing table: %s", e, exc_info=True)
        pg_conn.rollback()
        raise


def main():
    """Основная функция."""
    logging.info("="*60)
    logging.info("Body Text Cleaner")
    logging.info("="*60)
    logging.info("This script will clean 'body' column in table '%s'", TABLE_NAME)
    logging.info("Removing: 'Topic:', 'topic:', and '**' (double asterisks)")
    logging.info("")
    
    # Спрашиваем подтверждение
    response = input("Enter 'dry' for dry run (no changes), or 'yes' to proceed: ").strip().lower()
    dry_run = (response == 'dry' or response == 'd')
    
    if not dry_run and response != 'yes':
        logging.info("Aborted by user")
        return
    
    # Подключаемся к БД
    logging.info("Connecting to PostgreSQL...")
    pg_conn = get_pg_conn()
    
    try:
        process_table(pg_conn, TABLE_NAME, dry_run=dry_run)
    except KeyboardInterrupt:
        logging.warning("Interrupted by user")
    except Exception as e:
        logging.error("Fatal error: %s", e, exc_info=True)
    finally:
        pg_conn.close()
        logging.info("PostgreSQL connection closed")


if __name__ == "__main__":
    main()

