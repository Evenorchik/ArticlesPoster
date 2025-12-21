"""
Скрипт для генерации текста для Quora из статей в базе данных.

Функционал:
1. Подключается к базе данных
2. Показывает список таблиц refined_articles_*
3. Позволяет выбрать таблицу
4. Создает колонку quora_text если её нет
5. Позволяет выбрать ID статей для обработки
6. Для каждой статьи: берет title и body, отправляет в OpenAI, записывает ответ в quora_text
"""
import os
import logging
import time
from typing import List, Optional
from openai import OpenAI
from psycopg import sql

from poster.db import get_pg_conn, get_refined_articles_tables, parse_id_selection
from config import OPENAI_API_KEY, OPENAI_MODEL

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# Инициализация OpenAI клиента
client = OpenAI(api_key=OPENAI_API_KEY)


def ensure_quora_text_column(pg_conn, table_name: str) -> None:
    """
    Проверить и создать колонку quora_text если её нет.
    
    Args:
        pg_conn: Подключение к PostgreSQL
        table_name: Имя таблицы
    """
    logging.info("Checking for quora_text column in table %s...", table_name)
    check_query = sql.SQL("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = %s AND column_name = 'quora_text'
    """)
    
    with pg_conn.cursor() as cur:
        cur.execute(check_query, (table_name,))
        has_column = cur.fetchone() is not None
    
    if not has_column:
        logging.info("Adding quora_text column to table %s...", table_name)
        alter_query = sql.SQL("""
            ALTER TABLE {table}
            ADD COLUMN quora_text TEXT
        """).format(table=sql.Identifier(table_name))
        
        try:
            with pg_conn.cursor() as cur:
                cur.execute(alter_query)
            pg_conn.commit()
            logging.info("✓ Added quora_text column to table %s", table_name)
        except Exception as e:
            logging.error("Error adding quora_text column: %s", e)
            pg_conn.rollback()
            raise
    else:
        logging.info("✓ Column quora_text already exists in table %s", table_name)


def load_quora_prompt() -> str:
    """
    Загрузить промпт из файла quora.prompt.
    
    Returns:
        Содержимое файла quora.prompt
    """
    prompt_file = "quora.prompt"
    if not os.path.exists(prompt_file):
        logging.error("Prompt file not found: %s", prompt_file)
        raise FileNotFoundError(f"Prompt file not found: {prompt_file}")
    
    with open(prompt_file, 'r', encoding='utf-8') as f:
        prompt = f.read()
    
    logging.debug("Loaded prompt from %s (%d characters)", prompt_file, len(prompt))
    return prompt


def generate_quora_text(title: str, body: str, prompt: str) -> Optional[str]:
    """
    Сгенерировать текст для Quora через OpenAI API.
    
    Args:
        title: Заголовок статьи
        body: Тело статьи
        prompt: Промпт для OpenAI
    
    Returns:
        Сгенерированный текст для Quora или None при ошибке
    """
    # Объединяем title и body
    combined_text = f"Заголовок: {title}\n\nТело статьи:\n{body}"
    
    # Формируем полный промпт
    full_prompt = f"{prompt}\n\n{combined_text}"
    
    try:
        logging.info("Sending request to OpenAI (model: %s)...", OPENAI_MODEL)
        logging.debug("Title length: %d, Body length: %d", len(title), len(body))
        
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "Ты - эксперт по созданию контента для платформы Quora."},
                {"role": "user", "content": full_prompt}
            ],
            temperature=0.7,
            max_completion_tokens=4000  # Достаточно для длинных статей
        )
        
        quora_text = response.choices[0].message.content.strip()
        logging.info("✓ Generated Quora text (length: %d characters)", len(quora_text))
        return quora_text
        
    except Exception as e:
        logging.error("✗ Failed to generate Quora text: %s", e)
        return None


def get_articles_by_ids(pg_conn, table_name: str, article_ids: List[int]) -> List[dict]:
    """
    Получить статьи по ID.
    
    Args:
        pg_conn: Подключение к PostgreSQL
        table_name: Имя таблицы
        article_ids: Список ID статей
    
    Returns:
        Список статей (словари)
    """
    if not article_ids:
        return []
    
    query = sql.SQL("""
        SELECT id, title, body
        FROM {table}
        WHERE id = ANY(%s)
        ORDER BY id
    """).format(table=sql.Identifier(table_name))
    
    with pg_conn.cursor() as cur:
        cur.execute(query, (article_ids,))
        articles = cur.fetchall()
    
    # Преобразуем в список словарей
    result = []
    for article in articles:
        if isinstance(article, dict):
            result.append(article)
        else:
            result.append({
                'id': article[0],
                'title': article[1] if len(article) > 1 else '',
                'body': article[2] if len(article) > 2 else ''
            })
    
    return result


def update_quora_text(pg_conn, table_name: str, article_id: int, quora_text: str) -> bool:
    """
    Обновить колонку quora_text для статьи.
    
    Args:
        pg_conn: Подключение к PostgreSQL
        table_name: Имя таблицы
        article_id: ID статьи
        quora_text: Текст для Quora
    
    Returns:
        True если успешно, False при ошибке
    """
    update_query = sql.SQL("""
        UPDATE {table}
        SET quora_text = %s
        WHERE id = %s
    """).format(table=sql.Identifier(table_name))
    
    try:
        with pg_conn.cursor() as cur:
            cur.execute(update_query, (quora_text, article_id))
        pg_conn.commit()
        logging.info("✓ Updated quora_text for article ID %d", article_id)
        return True
    except Exception as e:
        logging.error("✗ Failed to update quora_text for article ID %d: %s", article_id, e)
        pg_conn.rollback()
        return False


def main():
    """Основная функция скрипта."""
    logging.info("="*60)
    logging.info("Quora Text Generator")
    logging.info("="*60)
    logging.info("")
    
    # Загружаем промпт
    try:
        prompt = load_quora_prompt()
        logging.info("✓ Prompt loaded successfully")
    except Exception as e:
        logging.error("Failed to load prompt: %s", e)
        return
    
    # Подключаемся к базе данных
    try:
        pg_conn = get_pg_conn()
    except Exception as e:
        logging.error("Failed to connect to database: %s", e)
        return
    
    try:
        # Получаем список таблиц
        tables = get_refined_articles_tables(pg_conn)
        if not tables:
            logging.error("No refined_articles tables found!")
            return
        
        # Выбираем таблицу
        logging.info("")
        logging.info("Available tables:")
        for i, table in enumerate(tables, 1):
            logging.info("  %d. %s", i, table)
        
        while True:
            try:
                choice = input("\nEnter table number or table name: ").strip()
                
                # Попытка как номер
                try:
                    table_index = int(choice) - 1
                    if 0 <= table_index < len(tables):
                        selected_table = tables[table_index]
                        break
                    else:
                        logging.warning("Invalid table number. Please try again.")
                        continue
                except ValueError:
                    pass
                
                # Попытка как имя таблицы
                if choice in tables:
                    selected_table = choice
                    break
                else:
                    logging.warning("Table '%s' not found. Please try again.", choice)
            except KeyboardInterrupt:
                logging.info("\nAborted by user")
                return
        
        logging.info("Selected table: %s", selected_table)
        
        # Создаем колонку quora_text если её нет
        ensure_quora_text_column(pg_conn, selected_table)
        
        # Выбираем ID статей для обработки
        logging.info("")
        logging.info("Enter article IDs to process.")
        logging.info("Format: single ID (e.g., 1), range (e.g., 1-5), or list (e.g., 1,3,5-10)")
        logging.info("Or press Enter to process all articles with empty quora_text")
        
        id_selection = input("\nArticle IDs (or Enter for all empty): ").strip()
        
        if id_selection:
            # Парсим выбранные ID
            article_ids = parse_id_selection(id_selection)
            if not article_ids:
                logging.error("No valid article IDs provided!")
                return
            logging.info("Selected %d article(s) to process", len(article_ids))
        else:
            # Получаем все статьи с пустым quora_text
            query = sql.SQL("""
                SELECT id
                FROM {table}
                WHERE quora_text IS NULL OR quora_text = ''
                ORDER BY id
            """).format(table=sql.Identifier(selected_table))
            
            with pg_conn.cursor() as cur:
                cur.execute(query)
                rows = cur.fetchall()
                article_ids = [row['id'] if isinstance(row, dict) else row[0] for row in rows]
            
            if not article_ids:
                logging.info("No articles with empty quora_text found!")
                return
            logging.info("Found %d article(s) with empty quora_text", len(article_ids))
        
        # Получаем статьи
        articles = get_articles_by_ids(pg_conn, selected_table, article_ids)
        if not articles:
            logging.error("No articles found!")
            return
        
        logging.info("")
        logging.info("="*60)
        logging.info("Processing %d article(s)...", len(articles))
        logging.info("="*60)
        
        # Обрабатываем каждую статью
        success_count = 0
        failed_count = 0
        
        for i, article in enumerate(articles, 1):
            article_id = article['id']
            title = article.get('title', '').strip()
            body = article.get('body', '').strip()
            
            if not title or not body:
                logging.warning("Article ID %d: missing title or body, skipping...", article_id)
                failed_count += 1
                continue
            
            logging.info("")
            logging.info("="*60)
            logging.info("Processing article %d/%d (ID: %d)", i, len(articles), article_id)
            logging.info("Title: %s", title[:80] + "..." if len(title) > 80 else title)
            logging.info("="*60)
            
            # Генерируем текст для Quora
            quora_text = generate_quora_text(title, body, prompt)
            
            if quora_text:
                # Обновляем базу данных
                if update_quora_text(pg_conn, selected_table, article_id, quora_text):
                    success_count += 1
                    logging.info("✓ Article %d/%d processed successfully", i, len(articles))
                else:
                    failed_count += 1
                    logging.error("✗ Article %d/%d failed to update", i, len(articles))
            else:
                failed_count += 1
                logging.error("✗ Article %d/%d failed to generate text", i, len(articles))
            
            # Пауза между запросами (чтобы не превысить rate limit)
            if i < len(articles):
                logging.info("Waiting 2 seconds before next article...")
                time.sleep(2)
        
        # Итоговая статистика
        logging.info("")
        logging.info("="*60)
        logging.info("Processing complete!")
        logging.info("  Success: %d", success_count)
        logging.info("  Failed: %d", failed_count)
        logging.info("="*60)
        
    except KeyboardInterrupt:
        logging.warning("\nInterrupted by user")
    except Exception as e:
        logging.error("Fatal error: %s", e, exc_info=True)
    finally:
        pg_conn.close()
        logging.info("PostgreSQL connection closed")


if __name__ == "__main__":
    main()

