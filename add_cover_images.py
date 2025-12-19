"""
Скрипт для добавления колонки cover_image_name и заполнения её тестовыми данными.
"""
import logging
from config import POSTGRES_DSN
from poster.db import get_pg_conn, get_refined_articles_tables

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# PostgreSQL
try:
    import psycopg
    from psycopg import sql
    _pg_v3 = True
except ImportError:
    import psycopg2 as psycopg
    from psycopg2 import sql
    _pg_v3 = False


def ensure_cover_image_column(pg_conn, table_name: str) -> bool:
    """
    Проверяет и создает колонку cover_image_name если её нет.
    
    Returns:
        True если колонка существует или была создана, False при ошибке
    """
    logging.info("Checking for cover_image_name column in table %s...", table_name)
    
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
        
        if has_column:
            logging.info("  ✓ Column cover_image_name already exists in table %s", table_name)
            return True
        
        # Создаем колонку
        logging.info("  Creating cover_image_name column in table %s...", table_name)
        alter_query = sql.SQL("""
            ALTER TABLE {table}
            ADD COLUMN cover_image_name VARCHAR(255)
        """).format(table=sql.Identifier(table_name))
        
        with pg_conn.cursor() as cur:
            cur.execute(alter_query)
        pg_conn.commit()
        
        logging.info("  ✓ Column cover_image_name created successfully in table %s", table_name)
        return True
        
    except Exception as e:
        logging.error("  ✗ Error checking/creating cover_image_name column: %s", e)
        pg_conn.rollback()
        return False


def fill_cover_images(pg_conn, table_name: str, cover_image_name: str = "cover_image_1.jpg") -> int:
    """
    Заполняет колонку cover_image_name для всех статей в таблице.
    
    Args:
        pg_conn: Подключение к PostgreSQL
        table_name: Имя таблицы
        cover_image_name: Имя файла обложки для заполнения
        
    Returns:
        Количество обновленных строк
    """
    logging.info("Filling cover_image_name for all articles in table %s...", table_name)
    
    # Обновляем ВСЕ строки, независимо от текущего значения
    update_query = sql.SQL("""
        UPDATE {table}
        SET cover_image_name = %s
    """).format(table=sql.Identifier(table_name))
    
    try:
        with pg_conn.cursor() as cur:
            cur.execute(update_query, (cover_image_name,))
            rows_affected = cur.rowcount
        pg_conn.commit()
        
        logging.info("  ✓ Updated %d row(s) in table %s", rows_affected, table_name)
        return rows_affected
        
    except Exception as e:
        logging.error("  ✗ Error filling cover_image_name: %s", e)
        pg_conn.rollback()
        return 0


def main():
    """Основная функция"""
    logging.info("="*60)
    logging.info("Adding cover_image_name column and filling with test data")
    logging.info("="*60)
    
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
        logging.info("Found %d table(s):", len(tables))
        for i, table in enumerate(tables, 1):
            logging.info("  %d. %s", i, table)
        
        # Обрабатываем все таблицы автоматически
        tables_to_process = tables
        logging.info("")
        logging.info("Processing all %d tables automatically...", len(tables))
        
        # Обрабатываем каждую таблицу
        total_updated = 0
        for table_name in tables_to_process:
            logging.info("")
            logging.info("-" * 60)
            logging.info("Processing table: %s", table_name)
            logging.info("-" * 60)
            
            # Создаем колонку если нужно
            if not ensure_cover_image_column(pg_conn, table_name):
                logging.warning("  Skipping table %s due to column creation error", table_name)
                continue
            
            # Заполняем данными
            rows_updated = fill_cover_images(pg_conn, table_name)
            total_updated += rows_updated
        
        logging.info("")
        logging.info("="*60)
        logging.info("Completed! Total rows updated: %d", total_updated)
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

