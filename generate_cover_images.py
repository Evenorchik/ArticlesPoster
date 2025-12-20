"""
Скрипт для генерации обложек статей с помощью OpenAI GPT-Image 1.5.
Процесс:
1. Получает статьи из БД (id, title)
2. Для каждой статьи генерирует промпт для обложки через GPT
3. Генерирует изображение через GPT-Image 1.5
4. Сохраняет изображение в data/images как cover_image_{id}.jpg
5. Обновляет cover_image_name в БД (после успешной генерации)
"""
import os
import logging
import time
import requests
from typing import Optional, List
from openai import OpenAI
from config import (
    OPENAI_API_KEY,
    OPENAI_MODEL_COVER_PROMPT,
    OPENAI_IMAGE_MODEL
)
from poster.db import get_pg_conn, get_refined_articles_tables

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# PostgreSQL - используем get_pg_conn() из poster.db
# Импортируем sql для работы с запросами
try:
    from psycopg import sql
except ImportError:
    from psycopg2 import sql

# Инициализация OpenAI клиента
OPENAI_CLIENT = OpenAI(api_key=OPENAI_API_KEY)

# Промпт для генерации промпта обложки
COVER_PROMPT_TEMPLATE = """Вот тебе заголовок нашей статьи, напиши идеальный промт для обложки для этой статьи.

Заголовок статьи: {title}

Напиши короткий, но детальный промпт на английском языке для генерации обложки. Промпт должен быть визуально привлекательным и отражать суть статьи. На обложке может быть короткое название статьи из 2-3 слов отражающее её содержание.Не включай в ответ ничего кроме самого промпта."""

# Параметры для генерации изображений GPT-Image 1.5
# Цены на GPT-Image 1.5 API (по состоянию на декабрь 2024):
# - Низкое качество (low): ~$0.01 за квадратное изображение
# - Среднее качество (medium): ~$0.04 за квадратное изображение  
# - Высокое качество (high): ~$0.17 за квадратное изображение
# - Автоматическое качество (auto): выбирается автоматически
# - Текстовые входные токены: $5 за 1 млн токенов
# - Кэшированные входные токены: $1.25 за 1 млн токенов
# - Выходные токены: $10 за 1 млн токенов
def get_image_generation_params():
    """
    Возвращает параметры для генерации изображений через GPT-Image 1.5.
    
    Поддерживаемые параметры:
    - model: "gpt-image-1.5"
    - prompt: текстовое описание (передается отдельно)
    - size: "1024x1024", "1792x1024", "1024x1792"
    - quality: "low" (~$0.01), "medium" (~$0.04), "high" (~$0.17) или "auto"
    - n: количество изображений (обычно 1)
    
    Примечание: response_format не поддерживается GPT-Image 1.5 API
    """
    params = {
        "model": OPENAI_IMAGE_MODEL,
        "size": "1792x1024",  # Размеры: "1024x1024", "1792x1024", "1024x1792"
        "quality": "medium",  # "low" (~$0.01), "medium" (~$0.04), "high" (~$0.17) или "auto"
        "n": 1,  # Количество изображений
    }
    return params


def ensure_images_directory() -> str:
    """Создает папку data/images если её нет и возвращает путь к ней."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    images_dir = os.path.join(base_dir, "data", "images")
    os.makedirs(images_dir, exist_ok=True)
    logging.info("Images directory: %s", images_dir)
    return images_dir


def generate_cover_prompt(title: str) -> Optional[str]:
    """
    Генерирует промпт для обложки на основе заголовка статьи.
    
    Args:
        title: Заголовок статьи
        
    Returns:
        Промпт для генерации изображения или None при ошибке
    """
    logging.info("Generating cover prompt for title: %s", title)
    
    try:
        prompt = COVER_PROMPT_TEMPLATE.format(title=title)
        
        response = OPENAI_CLIENT.chat.completions.create(
            model=OPENAI_MODEL_COVER_PROMPT,
            messages=[
                {"role": "user", "content": prompt}
            ],
            max_completion_tokens=200,
            temperature=0.7
        )
        
        cover_prompt = response.choices[0].message.content.strip()
        logging.info("  ✓ Generated cover prompt: %s", cover_prompt[:100] + "..." if len(cover_prompt) > 100 else cover_prompt)
        return cover_prompt
        
    except Exception as e:
        logging.error("  ✗ Failed to generate cover prompt: %s", e)
        return None


def generate_image(image_prompt: str) -> Optional[str]:
    """
    Генерирует изображение через GPT-Image 1.5 API.
    
    Args:
        image_prompt: Промпт для генерации изображения
        
    Returns:
        URL изображения или None при ошибке
    """
    logging.info("Generating image with prompt: %s", image_prompt[:100] + "..." if len(image_prompt) > 100 else image_prompt)
    
    try:
        params = get_image_generation_params()
        response = OPENAI_CLIENT.images.generate(
            prompt=image_prompt,
            **params
        )
        
        image_url = response.data[0].url
        logging.info("  ✓ Image generated successfully: %s", image_url)
        return image_url
        
    except Exception as e:
        logging.error("  ✗ Failed to generate image: %s", e)
        return None


def download_and_save_image(image_url: str, file_path: str) -> bool:
    """
    Скачивает изображение по URL и сохраняет в файл.
    
    Args:
        image_url: URL изображения
        file_path: Путь для сохранения файла
        
    Returns:
        True если успешно, False при ошибке
    """
    logging.info("Downloading image from %s to %s", image_url, file_path)
    
    try:
        response = requests.get(image_url, timeout=30)
        response.raise_for_status()
        
        with open(file_path, 'wb') as f:
            f.write(response.content)
        
        logging.info("  ✓ Image saved successfully: %s", file_path)
        return True
        
    except Exception as e:
        logging.error("  ✗ Failed to download/save image: %s", e)
        return False


def update_cover_image_name(pg_conn, table_name: str, article_id: int, cover_image_name: str) -> bool:
    """
    Обновляет cover_image_name для статьи в БД.
    
    Args:
        pg_conn: Подключение к PostgreSQL
        table_name: Имя таблицы
        article_id: ID статьи
        cover_image_name: Имя файла обложки
        
    Returns:
        True если успешно, False при ошибке
    """
    logging.info("Updating cover_image_name for article ID %d: %s", article_id, cover_image_name)
    
    # Проверяем наличие колонки cover_image_name
    check_query = sql.SQL("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_schema = 'public' 
        AND table_name = %s 
        AND column_name = 'cover_image_name'
    """)
    
    try:
        with pg_conn.cursor() as cur:
            cur.execute(check_query, (table_name,))
            has_column = cur.fetchone() is not None
        
        if not has_column:
            logging.warning("  Column cover_image_name does not exist, creating it...")
            alter_query = sql.SQL("""
                ALTER TABLE {table}
                ADD COLUMN cover_image_name VARCHAR(255)
            """).format(table=sql.Identifier(table_name))
            
            with pg_conn.cursor() as cur:
                cur.execute(alter_query)
            pg_conn.commit()
            logging.info("  ✓ Column cover_image_name created")
        
        # Обновляем значение
        update_query = sql.SQL("""
            UPDATE {table}
            SET cover_image_name = %s
            WHERE id = %s
        """).format(table=sql.Identifier(table_name))
        
        with pg_conn.cursor() as cur:
            cur.execute(update_query, (cover_image_name, article_id))
            rows_affected = cur.rowcount
        pg_conn.commit()
        
        if rows_affected > 0:
            logging.info("  ✓ Updated cover_image_name for article ID %d", article_id)
            return True
        else:
            logging.warning("  No rows updated for article ID %d (article may not exist)", article_id)
            return False
            
    except Exception as e:
        logging.error("  ✗ Error updating cover_image_name: %s", e)
        pg_conn.rollback()
        return False


def get_articles_with_titles(pg_conn, table_name: str, article_ids: Optional[List[int]] = None) -> List[dict]:
    """
    Получает статьи с id и title из таблицы.
    
    Args:
        pg_conn: Подключение к PostgreSQL
        table_name: Имя таблицы
        article_ids: Список ID статей (если None, берет все статьи)
        
    Returns:
        Список словарей с ключами 'id' и 'title'
    """
    logging.info("Fetching articles from table %s", table_name)
    
    if article_ids:
        query = sql.SQL("""
            SELECT id, title
            FROM {table}
            WHERE id = ANY(%s)
            ORDER BY id ASC
        """).format(table=sql.Identifier(table_name))
        params = (article_ids,)
    else:
        query = sql.SQL("""
            SELECT id, title
            FROM {table}
            ORDER BY id ASC
        """).format(table=sql.Identifier(table_name))
        params = ()
    
    try:
        with pg_conn.cursor() as cur:
            cur.execute(query, params)
            articles = cur.fetchall()
            logging.info("  ✓ Fetched %d article(s)", len(articles))
            return articles
    except Exception as e:
        logging.error("  ✗ Error fetching articles: %s", e)
        raise


def generate_cover_for_article(pg_conn, table_name: str, article_id: int, title: str, images_dir: str) -> bool:
    """
    Генерирует обложку для одной статьи.
    
    Args:
        pg_conn: Подключение к PostgreSQL
        table_name: Имя таблицы
        article_id: ID статьи
        title: Заголовок статьи
        images_dir: Папка для сохранения изображений
        
    Returns:
        True если успешно, False при ошибке
    """
    logging.info("")
    logging.info("="*60)
    logging.info("Processing article ID %d: %s", article_id, title)
    logging.info("="*60)
    
    # Шаг 1: Генерируем промпт для обложки
    cover_prompt = generate_cover_prompt(title)
    if not cover_prompt:
        logging.error("Failed to generate cover prompt, skipping article")
        return False
    
    # Шаг 2: Генерируем изображение
    image_url = generate_image(cover_prompt)
    if not image_url:
        logging.error("Failed to generate image, skipping article")
        return False
    
    # Шаг 3: Сохраняем изображение
    cover_image_name = f"cover_image_{article_id}.jpg"
    file_path = os.path.join(images_dir, cover_image_name)
    
    if not download_and_save_image(image_url, file_path):
        logging.error("Failed to save image, skipping article")
        return False
    
    # Шаг 4: Обновляем БД
    if not update_cover_image_name(pg_conn, table_name, article_id, cover_image_name):
        logging.error("Failed to update database, but image was saved")
        return False
    
    logging.info("✓ Successfully generated cover for article ID %d", article_id)
    return True


def main():
    """Основная функция"""
    logging.info("="*60)
    logging.info("Cover Image Generator")
    logging.info("="*60)
    
    # Создаем папку для изображений
    images_dir = ensure_images_directory()
    
    # Подключение к БД
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
        
        logging.info("")
        logging.info("Available tables:")
        for i, table in enumerate(tables, 1):
            logging.info("  %d. %s", i, table)
        
        # Выбор таблицы
        table_choice = input("\nEnter table number (or table name): ").strip()
        try:
            table_index = int(table_choice) - 1
            if 0 <= table_index < len(tables):
                selected_table = tables[table_index]
            else:
                logging.error("Invalid table number!")
                return
        except ValueError:
            if table_choice in tables:
                selected_table = table_choice
            else:
                logging.error("Table '%s' not found!", table_choice)
                return
        
        logging.info("Selected table: %s", selected_table)
        
        # Выбор статей для обработки
        logging.info("")
        article_choice = input("Enter article IDs (comma-separated, e.g. '1,2,3' or '1-10' or press Enter for all): ").strip()
        
        article_ids = None
        if article_choice:
            from poster.db import parse_id_selection
            article_ids = parse_id_selection(article_choice)
            logging.info("Selected article IDs: %s", article_ids)
        else:
            logging.info("Processing all articles")
        
        # Получаем статьи
        articles = get_articles_with_titles(pg_conn, selected_table, article_ids)
        if not articles:
            logging.warning("No articles found!")
            return
        
        logging.info("")
        logging.info("Found %d article(s) to process", len(articles))
        logging.info("Processing articles sequentially (one by one)...")
        logging.info("")
        
        # Обрабатываем каждую статью последовательно
        success_count = 0
        fail_count = 0
        
        for idx, article in enumerate(articles, 1):
            article_id = article['id'] if isinstance(article, dict) else article[0]
            title = article['title'] if isinstance(article, dict) else article[1]
            
            logging.info("")
            logging.info(">>> Processing article %d of %d <<<", idx, len(articles))
            logging.info("")
            
            # Последовательная обработка: промпт -> изображение -> сохранение -> БД
            if generate_cover_for_article(pg_conn, selected_table, article_id, title, images_dir):
                success_count += 1
                logging.info("✓ Article %d/%d completed successfully", idx, len(articles))
            else:
                fail_count += 1
                logging.error("✗ Article %d/%d failed", idx, len(articles))
            
            # Небольшая пауза между статьями (кроме последней)
            if idx < len(articles):
                logging.info("Waiting 2 seconds before next article...")
                time.sleep(2)
        
        # Итоги
        logging.info("")
        logging.info("="*60)
        logging.info("Processing completed!")
        logging.info("  Success: %d", success_count)
        logging.info("  Failed: %d", fail_count)
        logging.info("="*60)
        
    except KeyboardInterrupt:
        logging.warning("Interrupted by user")
    except Exception as e:
        logging.error("Fatal error: %s", e, exc_info=True)
    finally:
        pg_conn.close()
        logging.info("Database connection closed")


if __name__ == "__main__":
    main()

