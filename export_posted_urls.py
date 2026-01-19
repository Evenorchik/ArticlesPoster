"""
Экспорт всех ссылок на опубликованные статьи (Medium + Quora) в TXT файл.
"""
import os
import logging
from datetime import datetime
from typing import List, Set

from poster.db.postgres import get_pg_conn, get_refined_articles_tables


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)


def _normalize_url(url: str) -> str:
    return url.strip()


def _fetch_urls_from_table(pg_conn, table_name: str) -> List[str]:
    query = f"""
        SELECT url
        FROM {table_name}
        WHERE url IS NOT NULL AND url <> ''
        ORDER BY id ASC
    """
    with pg_conn.cursor() as cur:
        cur.execute(query)
        rows = cur.fetchall()
    urls: List[str] = []
    for row in rows:
        if isinstance(row, dict):
            url = row.get("url")
        else:
            url = row[0] if row else None
        if url:
            urls.append(_normalize_url(str(url)))
    return urls


def _write_txt(path: str, medium_urls: List[str], quora_urls: List[str], other_urls: List[str]) -> None:
    lines: List[str] = []
    lines.append("=== Medium ===")
    lines.extend(medium_urls or ["(no urls)"])
    lines.append("")
    lines.append("=== Quora ===")
    lines.extend(quora_urls or ["(no urls)"])
    lines.append("")
    lines.append("=== Other ===")
    lines.extend(other_urls or ["(no urls)"])
    lines.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def main() -> None:
    logging.info("=" * 60)
    logging.info("Exporting posted article URLs to TXT")
    logging.info("=" * 60)

    pg_conn = get_pg_conn()
    try:
        tables = get_refined_articles_tables(pg_conn)
        if not tables:
            logging.error("No refined_articles tables found.")
            return

        all_urls: Set[str] = set()
        for table in tables:
            logging.info("Reading URLs from table: %s", table)
            urls = _fetch_urls_from_table(pg_conn, table)
            all_urls.update(urls)

        medium_urls = sorted([u for u in all_urls if "medium.com" in u])
        quora_urls = sorted([u for u in all_urls if "quora.com" in u])
        other_urls = sorted([u for u in all_urls if u not in medium_urls and u not in quora_urls])

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_name = f"posted_urls_{ts}.txt"
        out_path = os.path.abspath(out_name)
        _write_txt(out_path, medium_urls, quora_urls, other_urls)

        logging.info("✓ Export complete")
        logging.info("File: %s", out_path)
        logging.info("Medium URLs: %d", len(medium_urls))
        logging.info("Quora URLs: %d", len(quora_urls))
        logging.info("Other URLs: %d", len(other_urls))
    finally:
        pg_conn.close()
        logging.info("PostgreSQL connection closed")


if __name__ == "__main__":
    main()

