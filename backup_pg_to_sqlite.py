"""
Скрипт для создания резервной копии PostgreSQL базы данных в SQLite.
При каждом запуске создаёт новый файл с временной меткой в названии.
"""
import os
import sqlite3
import logging
from datetime import datetime
from typing import List, Dict, Any
from poster.db.postgres import get_pg_conn

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)


def ensure_backup_directory():
    """Создаёт папку backup_data, если её нет."""
    backup_dir = "./backup_data"
    os.makedirs(backup_dir, exist_ok=True)
    return backup_dir


def get_all_tables(pg_conn) -> List[str]:
    """Получить список всех таблиц в базе данных."""
    query = """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
        AND table_type = 'BASE TABLE'
        ORDER BY table_name
    """
    
    try:
        with pg_conn.cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()
            tables = []
            for row in rows:
                if isinstance(row, dict):
                    tables.append(row['table_name'])
                elif isinstance(row, tuple):
                    tables.append(row[0])
                else:
                    # Для psycopg2 с RealDictCursor
                    tables.append(getattr(row, 'table_name', str(row)))
            return tables
    except Exception as e:
        logging.error("Failed to get tables list: %s", e)
        raise


def get_table_structure(pg_conn, table_name: str) -> List[Dict[str, Any]]:
    """Получить структуру таблицы (колонки и их типы)."""
    query = """
        SELECT 
            column_name,
            data_type,
            character_maximum_length,
            is_nullable,
            column_default
        FROM information_schema.columns
        WHERE table_schema = 'public'
        AND table_name = %s
        ORDER BY ordinal_position
    """
    
    try:
        with pg_conn.cursor() as cur:
            cur.execute(query, (table_name,))
            columns = []
            for row in cur.fetchall():
                if isinstance(row, dict):
                    col_info = row
                elif isinstance(row, tuple):
                    col_info = {
                        'column_name': row[0],
                        'data_type': row[1],
                        'character_maximum_length': row[2],
                        'is_nullable': row[3],
                        'column_default': row[4]
                    }
                else:
                    # Для psycopg2 с RealDictCursor или других типов
                    col_info = {
                        'column_name': getattr(row, 'column_name', None) or (row[0] if hasattr(row, '__getitem__') else None),
                        'data_type': getattr(row, 'data_type', None) or (row[1] if hasattr(row, '__getitem__') else None),
                        'character_maximum_length': getattr(row, 'character_maximum_length', None) or (row[2] if hasattr(row, '__getitem__') else None),
                        'is_nullable': getattr(row, 'is_nullable', None) or (row[3] if hasattr(row, '__getitem__') else None),
                        'column_default': getattr(row, 'column_default', None) or (row[4] if hasattr(row, '__getitem__') else None)
                    }
                columns.append(col_info)
            return columns
    except Exception as e:
        logging.error("Failed to get structure for table %s: %s", table_name, e)
        raise


def pg_type_to_sqlite_type(pg_type: str, max_length: int = None) -> str:
    """Конвертирует тип PostgreSQL в тип SQLite."""
    pg_type_lower = pg_type.lower()
    
    # Числовые типы
    if pg_type_lower in ('smallint', 'integer', 'int', 'int4'):
        return 'INTEGER'
    if pg_type_lower in ('bigint', 'int8', 'bigserial'):
        return 'INTEGER'
    if pg_type_lower in ('real', 'float4', 'double precision', 'float8', 'numeric', 'decimal'):
        return 'REAL'
    
    # Булевы
    if pg_type_lower in ('boolean', 'bool'):
        return 'INTEGER'  # SQLite использует INTEGER для boolean (0/1)
    
    # Текстовые
    if pg_type_lower in ('text', 'varchar', 'char', 'character varying'):
        return 'TEXT'
    
    # Дата и время
    if pg_type_lower in ('timestamp', 'timestamptz', 'timestamp without time zone', 'timestamp with time zone', 'date', 'time'):
        return 'TEXT'  # SQLite хранит даты как TEXT в ISO формате
    
    # JSON
    if pg_type_lower in ('json', 'jsonb'):
        return 'TEXT'
    
    # По умолчанию - TEXT
    return 'TEXT'


def create_sqlite_table(sqlite_conn: sqlite3.Connection, table_name: str, columns: List[Dict[str, Any]]):
    """Создаёт таблицу в SQLite на основе структуры PostgreSQL."""
    column_defs = []
    
    for col in columns:
        col_name = col['column_name']
        col_type = pg_type_to_sqlite_type(col['data_type'], col.get('character_maximum_length'))
        nullable = 'NULL' if col['is_nullable'] == 'YES' else 'NOT NULL'
        
        # Если это PRIMARY KEY (обычно id), добавляем его
        if col_name == 'id' and 'bigserial' in col['data_type'].lower():
            column_defs.append(f"{col_name} INTEGER PRIMARY KEY AUTOINCREMENT")
        else:
            column_defs.append(f"{col_name} {col_type} {nullable}")
    
    columns_str = ',\n    '.join(column_defs)
    create_sql = f"CREATE TABLE IF NOT EXISTS {table_name} (\n    {columns_str}\n)"
    
    try:
        sqlite_conn.execute(create_sql)
        sqlite_conn.commit()
        logging.info("  ✓ Created table: %s", table_name)
    except Exception as e:
        logging.error("  ✗ Failed to create table %s: %s", table_name, e)
        raise


def copy_table_data(pg_conn, sqlite_conn: sqlite3.Connection, table_name: str, columns: List[Dict[str, Any]]):
    """Копирует данные из PostgreSQL таблицы в SQLite."""
    col_names = [col['column_name'] for col in columns]
    col_names_str = ', '.join(col_names)
    placeholders = ', '.join(['?' for _ in col_names])
    
    # Получаем данные из PostgreSQL
    select_query = f"SELECT {col_names_str} FROM {table_name}"
    
    try:
        with pg_conn.cursor() as pg_cur:
            pg_cur.execute(select_query)
            rows = pg_cur.fetchall()
            
            if not rows:
                logging.info("  ⚠ Table %s is empty, skipping data copy", table_name)
                return
            
            # Конвертируем строки в кортежи, если нужно
            if rows:
                first_row = rows[0]
                if isinstance(first_row, dict):
                    rows = [tuple(row[col] for col in col_names) for row in rows]
                elif not isinstance(first_row, tuple):
                    # Для других типов (например, namedtuple)
                    rows = [tuple(getattr(row, col, None) for col in col_names) for row in rows]
            
            # Вставляем данные в SQLite
            insert_query = f"INSERT INTO {table_name} ({col_names_str}) VALUES ({placeholders})"
            sqlite_conn.executemany(insert_query, rows)
            sqlite_conn.commit()
            
            logging.info("  ✓ Copied %d row(s) from %s", len(rows), table_name)
            
    except Exception as e:
        logging.error("  ✗ Failed to copy data from %s: %s", table_name, e)
        raise


def backup_database():
    """Основная функция создания резервной копии."""
    logging.info("="*60)
    logging.info("PostgreSQL to SQLite Backup")
    logging.info("="*60)
    
    # Создаём папку для бэкапов
    backup_dir = ensure_backup_directory()
    logging.info("Backup directory: %s", os.path.abspath(backup_dir))
    
    # Генерируем имя файла с временной меткой
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    db_filename = f"backup_{timestamp}.db"
    db_path = os.path.join(backup_dir, db_filename)
    
    logging.info("Creating backup file: %s", db_filename)
    logging.info("")
    
    # Подключаемся к PostgreSQL
    logging.info("Connecting to PostgreSQL...")
    pg_conn = get_pg_conn()
    
    try:
        # Подключаемся к SQLite
        logging.info("Creating SQLite database...")
        sqlite_conn = sqlite3.connect(db_path)
        sqlite_conn.execute("PRAGMA foreign_keys = OFF")  # Отключаем внешние ключи для быстрой вставки
        
        # Получаем список всех таблиц
        logging.info("Fetching list of tables...")
        tables = get_all_tables(pg_conn)
        logging.info("Found %d table(s): %s", len(tables), ', '.join(tables))
        logging.info("")
        
        # Копируем каждую таблицу
        for table_name in tables:
            logging.info("Processing table: %s", table_name)
            
            try:
                # Получаем структуру таблицы
                columns = get_table_structure(pg_conn, table_name)
                logging.info("  Found %d column(s)", len(columns))
                
                # Создаём таблицу в SQLite
                create_sqlite_table(sqlite_conn, table_name, columns)
                
                # Копируем данные
                copy_table_data(pg_conn, sqlite_conn, table_name, columns)
                
            except Exception as e:
                logging.error("  ✗ Failed to process table %s: %s", table_name, e)
                logging.warning("  Continuing with next table...")
                continue
            
            logging.info("")
        
        sqlite_conn.close()
        
        # Проверяем размер файла
        file_size = os.path.getsize(db_path)
        file_size_mb = file_size / (1024 * 1024)
        
        logging.info("="*60)
        logging.info("✓ Backup completed successfully!")
        logging.info("  File: %s", db_filename)
        logging.info("  Size: %.2f MB", file_size_mb)
        logging.info("  Tables: %d", len(tables))
        logging.info("="*60)
        
    except Exception as e:
        logging.error("="*60)
        logging.error("✗ Backup failed: %s", e)
        logging.error("="*60)
        raise
    finally:
        pg_conn.close()
        logging.info("PostgreSQL connection closed")


if __name__ == "__main__":
    try:
        backup_database()
    except KeyboardInterrupt:
        logging.info("\nBackup interrupted by user")
    except Exception as e:
        logging.error("Fatal error: %s", e, exc_info=True)
        exit(1)

