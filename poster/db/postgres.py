"""
Работа с PostgreSQL базой данных.
"""
import logging
from typing import Optional, List
from config import POSTGRES_DSN

# PostgreSQL
try:
    import psycopg
    from psycopg import sql
    from psycopg.rows import dict_row
    _pg_v3 = True
except ImportError:
    import psycopg2 as psycopg
    from psycopg2 import sql
    _pg_v3 = False


def get_pg_conn():
    """Подключение к PostgreSQL."""
    logging.debug("Connecting to PostgreSQL...")
    try:
        if _pg_v3:
            conn = psycopg.connect(POSTGRES_DSN, row_factory=dict_row)
        else:
            conn = psycopg.connect(POSTGRES_DSN)
            from psycopg2.extras import RealDictCursor
            conn.cursor_factory = RealDictCursor
        logging.info("✓ Connected to PostgreSQL")
        return conn
    except Exception as e:
        logging.error("Failed to connect to PostgreSQL: %s", e)
        raise


def get_refined_articles_tables(pg_conn) -> List[str]:
    """Получить список таблиц refined_articles_*."""
    logging.debug("Fetching refined_articles tables...")
    query = sql.SQL("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
        AND table_name LIKE 'refined_articles_%'
        ORDER BY table_name
    """)

    try:
        with pg_conn.cursor() as cur:
            cur.execute(query)
            tables = [row['table_name'] if isinstance(row, dict) else row[0] for row in cur.fetchall()]
        logging.info("Found %d refined_articles table(s): %s", len(tables), tables)
        return tables
    except Exception as e:
        logging.error("Error fetching tables: %s", e)
        raise


def ensure_profile_id_column(pg_conn, table_name: str) -> None:
    """Проверить и создать колонку profile_id если её нет."""
    logging.debug("Checking for profile_id column in table %s...", table_name)
    check_query = sql.SQL("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = %s AND column_name = 'profile_id'
    """)

    with pg_conn.cursor() as cur:
        cur.execute(check_query, (table_name,))
        has_column = cur.fetchone() is not None

    if not has_column:
        logging.info("Adding profile_id column to table %s...", table_name)
        alter_query = sql.SQL("""
            ALTER TABLE {table}
            ADD COLUMN profile_id INTEGER
        """).format(table=sql.Identifier(table_name))

        try:
            with pg_conn.cursor() as cur:
                cur.execute(alter_query)
            pg_conn.commit()
            logging.info("✓ Added profile_id column to table %s", table_name)
        except Exception as e:
            logging.error("Error adding profile_id column: %s", e)
            pg_conn.rollback()
            raise
    else:
        logging.debug("Column profile_id already exists in table %s", table_name)


def parse_id_selection(s: str) -> List[int]:
    """Парсинг строки с ID статей (поддерживает диапазоны и списки)."""
    ids = []
    parts = s.replace(' ', '').split(',')

    for part in parts:
        if '-' in part:
            try:
                start, end = map(int, part.split('-'))
                ids.extend(range(start, end + 1))
            except ValueError:
                logging.warning("Invalid range format: %s", part)
        else:
            try:
                ids.append(int(part))
            except ValueError:
                logging.warning("Invalid ID format: %s", part)

    return sorted(list(dict.fromkeys(ids)))


def get_articles_to_post(pg_conn, table_name: str, article_ids: Optional[List[int]] = None) -> List[dict]:
    """Получить статьи для публикации."""
    logging.debug("Getting articles from table: %s", table_name)

    # Безопасно проверяем наличие колонки hashtag5
    logging.debug("Checking for hashtag5 column...")
    has_hashtag5 = False
    try:
        check_col_query = sql.SQL("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_schema = 'public' 
            AND table_name = %s 
            AND column_name = 'hashtag5'
        """)

        with pg_conn.cursor() as cur:
            cur.execute(check_col_query, (table_name,))
            has_hashtag5 = cur.fetchone() is not None
        logging.info("Table has hashtag5 column: %s", has_hashtag5)
    except Exception as e:
        logging.warning("Could not check for hashtag5 column (assuming it doesn't exist): %s", e)
        has_hashtag5 = False

    # Формируем список колонок в зависимости от наличия hashtag5
    if has_hashtag5:
        select_cols = "id, topic, title, body, hashtag1, hashtag2, hashtag3, hashtag4, hashtag5, url, profile_id"
    else:
        select_cols = "id, topic, title, body, hashtag1, hashtag2, hashtag3, hashtag4, url, profile_id"

    if article_ids:
        logging.info("Fetching articles by IDs: %s", article_ids)
        query = sql.SQL("""
            SELECT {cols}
            FROM {table}
            WHERE id = ANY(%s)
            ORDER BY id ASC
        """).format(
            cols=sql.SQL(select_cols),
            table=sql.Identifier(table_name)
        )
        params = (article_ids,)
    else:
        logging.info("Fetching all unpublished articles (url IS NULL or empty)")
        query = sql.SQL("""
            SELECT {cols}
            FROM {table}
            WHERE url IS NULL OR url = ''
            ORDER BY id ASC
        """).format(
            cols=sql.SQL(select_cols),
            table=sql.Identifier(table_name)
        )
        params = ()

    try:
        with pg_conn.cursor() as cur:
            try:
                query_str = query.as_string(pg_conn) if hasattr(query, 'as_string') else str(query)
                logging.debug("Executing query: %s with params: %s", query_str, params)
            except Exception:
                logging.debug("Executing query with params: %s", params)

            cur.execute(query, params)
            articles = cur.fetchall()
            logging.info("Fetched %d article(s) from database", len(articles))

            if articles:
                logging.debug("Article IDs: %s", [a['id'] if isinstance(a, dict) else a[0] for a in articles[:10]])
            elif article_ids:
                logging.warning("No articles found for IDs: %s. They may not exist in table %s", article_ids, table_name)

            return articles
    except Exception as e:
        logging.error("Error fetching articles: %s", e, exc_info=True)
        try:
            query_str = query.as_string(pg_conn) if hasattr(query, 'as_string') else str(query)
            logging.error("Failed query: %s", query_str)
            logging.error("Query params: %s", params)
        except Exception:
            logging.error("Could not format query string")
        raise


def update_article_url_and_profile(pg_conn, table_name: str, article_id: int, url: str, profile_id: int) -> None:
    """Обновить URL и profile_id для статьи после публикации."""
    logging.debug("Updating URL and profile_id for article ID %s in table %s", article_id, table_name)
    query = sql.SQL("""
        UPDATE {table}
        SET url = %s, profile_id = %s
        WHERE id = %s
    """).format(table=sql.Identifier(table_name))

    try:
        with pg_conn.cursor() as cur:
            cur.execute(query, (url, profile_id, article_id))
            rows_affected = cur.rowcount
        pg_conn.commit()
        if rows_affected > 0:
            logging.info("✓ Updated URL and profile_id for article ID %s: url=%s, profile_id=%s", article_id, url, profile_id)
        else:
            logging.warning("No rows updated for article ID %s (article may not exist)", article_id)
    except Exception as e:
        logging.error("Error updating URL and profile_id for article ID %s: %s", article_id, e)
        raise

