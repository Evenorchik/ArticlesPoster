import os
import time
import logging
import re
import requests
import pyautogui
import pyperclip
import webbrowser
import sqlite3
from openai import OpenAI
from contextlib import closing
from datetime import datetime
from typing import Tuple, Optional, List, Iterable

# ---------- prompts / config ----------
from prompts import prompt_4
from config import OPENAI_API_KEY, OPENAI_MODEL  # для шага структурирования (prompt_4)
# reasoning-модель для лёгкого перефразирования
OPENAI_MODEL_THINKING = os.getenv("OPENAI_MODEL_THINKING", "gpt-5.1-thinking")

# ---------- Postgres DSN ----------
# Пример: POSTGRES_DSN=postgresql://fraxi:Art1clesss@127.0.0.1:5432/articles
POSTGRES_DSN = os.getenv("POSTGRES_DSN", "postgresql://fraxi:Art1clesss@127.0.0.1:5432/articles")

# ---------- логирование ----------
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s")

# ---------- координаты (как у тебя) ----------
SCROLL_COORDS = (1673, 463)
PASTE_COORDS = (446, 216)
HUMANIZE_COORDS = (484, 876)
SCROLL_COORDS_TWO = (1672, 247)
COPY_COORDS = (1357, 840)
HUMANIZER_URL = "https://gpthumanizer.io/"

# ---------- HTTP session (необяз.)
SESSION = requests.Session()
ADAPTER = requests.adapters.HTTPAdapter(max_retries=3)
SESSION.mount("https://", ADAPTER)
SESSION.mount("http://", ADAPTER)

# ---------- OpenAI ----------
OPENAI_CLIENT = OpenAI(api_key=OPENAI_API_KEY)

# ---------- Postgres (psycopg) ----------
try:
    import psycopg
    _pg_v3 = True
except ImportError:
    # на случай, если установлен psycopg2
    import psycopg2 as psycopg
    _pg_v3 = False


# ---------- УТИЛИТЫ И БД-ХЕЛПЕРЫ ----------

def get_db_path() -> str:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, "articles.db")

def quote_ident_sqlite(name: str) -> str:
    # простая безопасная кавычка для SQLite
    return f"\"{name}\""

def normalize_pg_table_name(iteration: int) -> str:
    """
    Для Postgres дефисы в именах — неудобно (нужны кавычки в каждом запросе).
    Делаем snake_case: refined_articles_<N>
    """
    return f"refined_articles_{iteration}"

def create_refined_table_sqlite(conn: sqlite3.Connection, table_name: str) -> None:
    """
    SQLite: создаёт таблицу по имени вида Refined_articles-<N>.
    """
    qname = quote_ident_sqlite(table_name)
    with closing(conn.cursor()) as cur:
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS {qname} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic TEXT,
                title TEXT,
                body TEXT,
                links TEXT,
                keywords TEXT,
                hashtag1 TEXT,
                hashtag2 TEXT,
                hashtag3 TEXT,
                hashtag4 TEXT,
                url TEXT,
                approval TEXT,
                created_at TEXT
            )
        """)
        conn.commit()
    logging.debug("Table %s ensured in SQLite.", table_name)

def get_pg_conn():
    """
    Возвращает подключение к Postgres.
    Поддерживает psycopg v3 (psycopg) и v2 (psycopg2).
    """
    if _pg_v3:
        return psycopg.connect(POSTGRES_DSN)  # psycopg3
    else:
        return psycopg.connect(POSTGRES_DSN)  # psycopg2 совместим по сигнатуре DSN

def create_refined_table_postgres(pg_table: str) -> None:
    """
    Postgres: создаёт таблицу refined_articles_<N>, если её нет.
    """
    ddl = f"""
    CREATE TABLE IF NOT EXISTS {pg_table} (
        id BIGSERIAL PRIMARY KEY,
        topic TEXT,
        title TEXT,
        body TEXT,
        links TEXT,
        keywords TEXT,
        hashtag1 TEXT,
        hashtag2 TEXT,
        hashtag3 TEXT,
        hashtag4 TEXT,
        url TEXT,
        approval TEXT,
        created_at TIMESTAMPTZ
    );
    """
    with get_pg_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(ddl)
        conn.commit()
    logging.debug("Table %s ensured in Postgres.", pg_table)

def list_raw_articles_sqlite(conn: sqlite3.Connection) -> None:
    with closing(conn.cursor()) as cur:
        try:
            cur.execute("SELECT id, title FROM raw_articles ORDER BY id")
        except sqlite3.OperationalError as e:
            logging.error("Could not read raw_articles (table missing?). Error: %s", e)
            return
        rows = cur.fetchall()
        if rows:
            logging.info("Raw articles available:")
            for row in rows:
                logging.info("ID: %s, Title: %s", row[0], row[1])
        else:
            logging.info("No raw articles found.")

def get_raw_article_sqlite(conn: sqlite3.Connection, article_id: int) -> Optional[Tuple[str, str, str]]:
    with closing(conn.cursor()) as cur:
        cur.execute("SELECT topic, title, body FROM raw_articles WHERE id = ?", (article_id,))
        row = cur.fetchone()
    if row:
        logging.debug("Raw article %s retrieved: %s", article_id, row)
        return row
    logging.error("Raw article with ID %s not found.", article_id)
    return None

def insert_refined_article_sqlite(conn: sqlite3.Connection, table_name: str,
                                  topic: str, title: str, body: str,
                                  links: str, keywords: str, hashtags: List[str],
                                  url: str = "", approval: str = "") -> None:
    hashtag1 = hashtags[0] if len(hashtags) > 0 else ""
    hashtag2 = hashtags[1] if len(hashtags) > 1 else ""
    hashtag3 = hashtags[2] if len(hashtags) > 2 else ""
    hashtag4 = hashtags[3] if len(hashtags) > 3 else ""
    qname = quote_ident_sqlite(table_name)
    with closing(conn.cursor()) as cur:
        cur.execute(f"""
            INSERT INTO {qname}
                (topic, title, body, links, keywords, hashtag1, hashtag2, hashtag3, hashtag4, url, approval, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (topic, title, body, links, keywords, hashtag1, hashtag2, hashtag3, hashtag4, url, approval,
              datetime.utcnow().isoformat(timespec="seconds") + "Z"))
        conn.commit()
    logging.info("Refined article inserted into SQLite table %s.", table_name)

def insert_refined_article_postgres(pg_table: str,
                                    topic: str, title: str, body: str,
                                    links: str, keywords: str, hashtags: List[str],
                                    url: str = "", approval: str = "") -> None:
    hashtag1 = hashtags[0] if len(hashtags) > 0 else ""
    hashtag2 = hashtags[1] if len(hashtags) > 1 else ""
    hashtag3 = hashtags[2] if len(hashtags) > 2 else ""
    hashtag4 = hashtags[3] if len(hashtags) > 3 else ""
    with get_pg_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO {pg_table}
                    (topic, title, body, links, keywords, hashtag1, hashtag2, hashtag3, hashtag4, url, approval, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    topic, title, body, links, keywords,
                    hashtag1, hashtag2, hashtag3, hashtag4,
                    url, approval, datetime.utcnow()
                )
            )
        conn.commit()
    logging.info("Refined article inserted into Postgres table %s.", pg_table)


# ---------- OpenAI Responses API wrappers ----------

def _responses_call(model_name: str, messages: List[dict], temperature: float, max_output_tokens: int):
    """
    messages: [{"role": "...", "content": "..."}]
    Конвертация в формат Responses API:
      - assistant → "output_text"
      - иначе → "input_text"
    """
    def _build_input_payload(msgs: Iterable[dict]):
        payload = []
        for m in msgs:
            role = m.get("role", "user")
            text = (m.get("content") or "").strip()
            content_item = {"type": "output_text", "text": text} if role == "assistant" else {"type": "input_text", "text": text}
            payload.append({"role": role, "content": [content_item]})
        return payload

    return OPENAI_CLIENT.responses.create(
        model=model_name,
        input=_build_input_payload(messages),
        temperature=temperature,
        max_output_tokens=max_output_tokens,
    )

def get_openai_response(messages, max_tokens: int = 4000, temperature: float = 0.7):
    """
    Структурирование (prompt_4) — модель из OPENAI_MODEL (обычно gpt-5.1).
    """
    try:
        try:
            resp = _responses_call(OPENAI_MODEL, messages, temperature, max_output_tokens=max_tokens)
        except Exception as e:
            msg = str(e)
            if "model_not_found" in msg or "does not exist" in msg:
                logging.warning("Model %s not available, falling back to gpt-5.1", OPENAI_MODEL)
                resp = _responses_call("gpt-5.1", messages, temperature, max_output_tokens=max_tokens)
            else:
                raise

        text = getattr(resp, "output_text", None)
        if text is None:
            parts = []
            for item in getattr(resp, "output", []) or []:
                for c in getattr(item, "content", []) or []:
                    if getattr(c, "type", "") == "output_text":
                        parts.append(getattr(c, "text", "") or "")
            text = "\n".join(parts).strip()
        return (text or None), []
    except Exception as e:
        logging.error("OpenAI API error (structuring): %s", e)
        return None, []

def rephrase_with_openai(text: str) -> Optional[str]:
    """
    Лёгкое перефразирование через GPT-5.1-thinking,
    без изменения смысла/фактов/упоминаний.
    """
    instruction = (
        "Here's article text that will be used for SEO, please, re-phrase this article, change text a bit, "
        "DO NOT change main bullets and senses, only re-phrase, senses should stay the same, "
        "main takes should stay the same, if mentioned some services, people, anything else, should stay the same."
    )
    messages = [
        {"role": "user", "content": instruction},
        {"role": "user", "content": text},
    ]
    try:
        try:
            resp = _responses_call(os.getenv("OPENAI_MODEL_THINKING", OPENAI_MODEL_THINKING),
                                   messages, temperature=0.3, max_output_tokens=4000)
        except Exception as e:
            msg = str(e)
            if "model_not_found" in msg or "does not exist" in msg:
                logging.warning("Thinking model not available, falling back to gpt-5.1")
                resp = _responses_call("gpt-5.1", messages, temperature=0.3, max_output_tokens=4000)
            else:
                raise

        text_out = getattr(resp, "output_text", None)
        if text_out is None:
            parts = []
            for item in getattr(resp, "output", []) or []:
                for c in getattr(item, "content", []) or []:
                    if getattr(c, "type", "") == "output_text":
                        parts.append(getattr(c, "text", "") or "")
            text_out = "\n".join(parts).strip()
        return text_out or None
    except Exception as e:
        logging.error("OpenAI API error (rephrase): %s", e)
        return None


# ---------- парсинг структурированного ответа ----------

def _extract_section(text: str, label: str, next_labels: Tuple[str, ...]) -> str:
    if not text:
        return ""
    next_union = "|".join([re.escape(lbl) for lbl in next_labels])
    pattern = rf"(?is){label}\s*:\s*(?P<val>.*?)(?=\n+\s*(?:{next_union})\s*:|\Z)"
    m = re.search(pattern, text)
    return (m.group("val").strip() if m else "")

def parse_refined_response(response_text: str):
    try:
        title = _extract_section(response_text, "title", ("body", "links", "hashtags", "keywords"))
        body = _extract_section(response_text, "body", ("links", "hashtags", "keywords"))
        links = _extract_section(response_text, "links", ("hashtags", "keywords"))
        hashtags_str = _extract_section(response_text, "hashtags", ("keywords",))
        keywords = _extract_section(response_text, "keywords", ())

        title = title.strip().strip('"').strip("'").strip("#").strip()
        body = body.strip()
        links = links.strip()
        keywords = keywords.strip()

        hashtags = [h.strip() for h in re.split(r"[,\n]+", hashtags_str) if h.strip()]
        hashtags = (hashtags + ["", "", "", ""])[:4]

        logging.debug("Parsed Title: %s", title)
        logging.debug("Parsed Body (first 100): %s", body[:100])
        logging.debug("Parsed Links: %s", links)
        logging.debug("Parsed Hashtags: %s", hashtags)
        logging.debug("Parsed Keywords: %s", keywords)

        if not title or not body:
            return None, None, None, None, ["", "", "", ""]

        return title, body, links, keywords, hashtags
    except Exception as e:
        logging.error("Error parsing refined response: %s", e)
        return None, None, None, None, ["", "", "", ""]


# ---------- выбор ID ----------

def _expand_token(tok: str) -> List[int]:
    tok = tok.strip()
    if not tok:
        return []
    if "-" in tok:
        a, b = tok.split("-", 1)
        a = a.strip(); b = b.strip()
        if a.isdigit() and b.isdigit():
            a = int(a); b = int(b)
            lo, hi = (a, b) if a <= b else (b, a)
            return list(range(lo, hi + 1))
        return []
    return [int(tok)] if tok.isdigit() else []

def parse_id_selection(s: str) -> List[int]:
    ids: List[int] = []
    for part in s.split(","):
        ids.extend(_expand_token(part))
    return sorted(list(dict.fromkeys(ids)))


# ---------- основной процесс одной статьи: ДВУХФАЗНАЯ ЗАПИСЬ ----------

def process_article(article_id: int,
                    conn_sqlite: sqlite3.Connection,
                    sqlite_table: str,
                    pg_table: str) -> None:
    logging.info("Processing raw article ID: %s", article_id)
    raw_article = get_raw_article_sqlite(conn_sqlite, article_id)
    if not raw_article:
        logging.error("Skipping article ID %s due to retrieval error.", article_id)
        return

    topic, raw_title, raw_body = raw_article

    # (Шаг 0) лёгкое перефразирование
    rephrased_body = rephrase_with_openai(raw_body) or raw_body

    # (Шаг 1) humanizer GUI
    combined_text = f"topic: {topic}\n\nbody: {rephrased_body}"
    logging.debug("Combined text for humanization (first 200 chars): %s", combined_text[:200])

    pyperclip.copy(combined_text)
    time.sleep(1)

    logging.info("Opening humanizer URL: %s", HUMANIZER_URL)
    webbrowser.open_new_tab(HUMANIZER_URL)
    time.sleep(5)

    logging.info("Clicking on input coordinates: %s", SCROLL_COORDS)
    pyautogui.click(*SCROLL_COORDS)
    time.sleep(0.5)

    logging.info("Clicking on input coordinates: %s", PASTE_COORDS)
    pyautogui.click(*PASTE_COORDS)
    time.sleep(0.5)

    logging.info("Pasting combined text (ctrl+v).")
    pyautogui.hotkey('ctrl', 'v')
    time.sleep(1)

    logging.info("Clicking on input coordinates: %s", HUMANIZE_COORDS)
    pyautogui.click(*HUMANIZE_COORDS)
    time.sleep(0.5)

    logging.info("Waiting for humanizer processing...")
    time.sleep(20)

    logging.info("Clicking on input coordinates: %s", SCROLL_COORDS_TWO)
    pyautogui.click(*SCROLL_COORDS_TWO)
    time.sleep(0.5)

    logging.info("Clicking on input coordinates: %s", COPY_COORDS)
    pyautogui.click(*COPY_COORDS)
    time.sleep(0.5)

    logging.info("Closing tab (ctrl+w).")
    pyautogui.hotkey('ctrl', 'w')
    time.sleep(0.5)

    humanized_text = pyperclip.paste()
    logging.debug("Humanized text retrieved (first 200 chars): %s", humanized_text[:200])

    # (Шаг 2) структурирование prompt_4 через OpenAI
    formatted_prompt_4 = prompt_4.replace("{ARTICLE TEXT}", humanized_text)
    conversation = [
        {"role": "assistant", "content": humanized_text},
        {"role": "user", "content": formatted_prompt_4},
    ]

    logging.info("Sending humanized text to OpenAI with prompt_4.")
    response_4, _ = get_openai_response(conversation)
    if not response_4:
        logging.error("Failed to get response for prompt_4 for article ID %s.", article_id)
        return

    logging.debug("Received response from prompt_4 (first 500 chars): %s", response_4[:500])

    refined_title, refined_body, links, keywords, hashtags = parse_refined_response(response_4)
    if not refined_title or not refined_body:
        logging.error("Parsing refined response failed for article ID %s.", article_id)
        return

    # (Шаг 3) ДВЕ записи: SQLite + Postgres
    # 3.1 SQLite
    try:
        insert_refined_article_sqlite(conn_sqlite, sqlite_table, topic, refined_title, refined_body, links, keywords, hashtags)
    except Exception as e:
        logging.error("SQLite insert failed for article ID %s: %s", article_id, e)

    # 3.2 Postgres
    try:
        insert_refined_article_postgres(pg_table, topic, refined_title, refined_body, links, keywords, hashtags)
    except Exception as e:
        logging.error("Postgres insert failed for article ID %s: %s", article_id, e)

    logging.info("Article ID %s processed and saved to tables: SQLite[%s], Postgres[%s].", article_id, sqlite_table, pg_table)


# ---------- main ----------

def main():
    # SQLite
    db_path = get_db_path()
    conn_sqlite = sqlite3.connect(db_path)

    try:
        # показать «сырые» статьи
        list_raw_articles_sqlite(conn_sqlite)

        # выбор ID
        sel = input("Enter raw article IDs (comma-separated, ranges allowed e.g. 5-12,14,18): ").strip()
        if not sel:
            logging.error("No article IDs provided. Exiting.")
            return
        try:
            article_ids = parse_id_selection(sel)
        except Exception:
            logging.error("Invalid selection format. Exiting.")
            return
        if not article_ids:
            logging.error("No valid IDs after parsing. Exiting.")
            return

        # итерация → имя таблицы
        it_str = input("Enter ITERATION number (e.g., 1, 2, 3): ").strip()
        if not it_str.isdigit():
            logging.error("Iteration must be a positive integer. Exiting.")
            return
        iteration = int(it_str)
        if iteration <= 0:
            logging.error("Iteration must be >= 1. Exiting.")
            return

        # SQLite-имя — как ты просил
        sqlite_table = f"Refined_articles-{iteration}"
        create_refined_table_sqlite(conn_sqlite, sqlite_table)

        # Postgres-имя — безопасно для идентификаторов
        pg_table = normalize_pg_table_name(iteration)
        create_refined_table_postgres(pg_table)

        # обработка
        for article_id in article_ids:
            process_article(article_id, conn_sqlite, sqlite_table, pg_table)
            time.sleep(5)  # пауза опционально

    finally:
        conn_sqlite.close()
        logging.debug("SQLite connection closed.")


if __name__ == "__main__":
    main()
