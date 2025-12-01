import os
import sys
import glob
import logging
import sqlite3
import re
from contextlib import closing
from typing import Optional, Tuple, List

from docx import Document
from openai import OpenAI

# ────────────────────────── НАСТРОЙКИ ──────────────────────────
# Ключ и модель берём из окружения; при желании можно хардкоднуть дефолты.
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL   = os.getenv("OPENAI_MODEL", "gpt-5.1")

# Тот самый промпт (без изменений):
PROMPT = (
    "Here's the DOCX file with article text, this article will be used for SEO, you need to do next things:\n\n"
    'Add markings "title:", "body:" accordingly, where title of the article starts and where body text starts.\n\n'
    "Do not change anythings alse, preserve formatting, your task is to add markings."
)

# Логи
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ──────────────────────── БАЗА ДАННЫХ ─────────────────────
def get_db_path() -> str:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, "articles.db")

def ensure_raw_table(conn: sqlite3.Connection) -> None:
    with closing(conn.cursor()) as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS raw_articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic TEXT,
                title TEXT,
                body TEXT
            )
        """)
        conn.commit()

def insert_article(conn: sqlite3.Connection, topic: str, title: str, body: str) -> None:
    with closing(conn.cursor()) as cur:
        cur.execute(
            "INSERT INTO raw_articles (topic, title, body) VALUES (?, ?, ?)",
            (topic, title, body),
        )
        conn.commit()

# ─────────────────────── ВСПОМОГАТЕЛЬНОЕ ───────────────────
def read_docx_text(path: str) -> str:
    """
    Достаём «чистый» текст (параграфы → строки). Форматирование здесь не требуется,
    т.к. мы просим модель только добавить 'title:'/'body:'.
    """
    try:
        doc = Document(path)
        lines: List[str] = []
        for p in doc.paragraphs:
            lines.append(p.text)
        return "\n".join(lines).strip()
    except Exception as e:
        logging.error("DOCX read error (%s): %s", os.path.basename(path), e)
        return ""

TITLE_BODY_RE = re.compile(r"(?is)title\s*:\s*(?P<title>.*?)\n+body\s*:\s*(?P<body>.*)", re.DOTALL)

def extract_title_body(text_with_marks: str) -> Tuple[Optional[str], Optional[str]]:
    if not text_with_marks:
        return None, None
    m = TITLE_BODY_RE.search(text_with_marks.strip())
    if not m:
        return None, None
    title = m.group("title").strip().strip('"').strip("'").strip("#").strip()
    body = m.group("body").strip()
    return (title or None), (body or None)

def make_client() -> OpenAI:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not set")
    return OpenAI(api_key=OPENAI_API_KEY)

def call_openai_add_marks(client: OpenAI, raw_text: str) -> Optional[str]:
    """
    Отправляем ДВА блока user-контента:
      1) PROMPT (input_text)
      2) Содержимое статьи (input_text)
    Модель: gpt-5.1, Responses API.
    """
    try:
        input_payload = [{
            "role": "user",
            "content": [
                {"type": "input_text", "text": PROMPT},
                {"type": "input_text", "text": raw_text},
            ]
        }]

        resp = client.responses.create(
            model=OPENAI_MODEL,           # по умолчанию gpt-5.1
            input=input_payload,
            temperature=0.0,              # просим не переписывать текст
            max_output_tokens=2000,
        )

        # Берём агрегированный текст, если доступен
        text = getattr(resp, "output_text", None)
        if text is not None:
            return text.strip() or None

        # Фолбэк: ручной сбор (обычно не нужен)
        parts: List[str] = []
        for item in getattr(resp, "output", []) or []:
            for c in getattr(item, "content", []) or []:
                if getattr(c, "type", "") == "output_text":
                    parts.append(getattr(c, "text", "") or "")
        text = "\n".join(parts).strip()
        return text or None

    except Exception as e:
        # если моделька недоступна — пробуем быстрый откат на gpt-5.1
        msg = str(e)
        if "model_not_found" in msg or "does not exist" in msg:
            logging.warning("Model %s not available, fallback to gpt-5.1", OPENAI_MODEL)
            try:
                resp = client.responses.create(
                    model="gpt-5.1",
                    input=[{
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": PROMPT},
                            {"type": "input_text", "text": raw_text},
                        ]
                    }],
                    temperature=0.0,
                    max_output_tokens=2000,
                )
                text = getattr(resp, "output_text", None)
                if text:
                    return text.strip() or None
            except Exception as e2:
                logging.error("OpenAI fallback error: %s", e2)
                return None

        logging.error("OpenAI API error: %s", e)
        return None

# ───────────────────────── ОСНОВНОЙ ЦИКЛ ───────────────────
def process_current_folder(topic: str) -> None:
    client = make_client()

    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    ensure_raw_table(conn)

    try:
        files = sorted(glob.glob("*.docx"))
        if not files:
            logging.warning("No DOCX files found in current folder.")
            return

        logging.info("Topic: %s | Found %d DOCX files.", topic, len(files))

        for i, path in enumerate(files, 1):
            base = os.path.basename(path)
            logging.info("[%d/%d] %s", i, len(files), base)

            raw_text = read_docx_text(path)
            if not raw_text:
                logging.error("Skip %s: empty or unreadable DOCX.", base)
                continue

            marked = call_openai_add_marks(client, raw_text)
            if not marked:
                logging.error("Skip %s: OpenAI returned empty response.", base)
                continue

            title, body = extract_title_body(marked)
            if not title or not body:
                logging.error("Skip %s: could not find 'title:'/'body:' markers.", base)
                continue

            insert_article(conn, topic, title, body)
            logging.info("Saved: %s", base)

    finally:
        conn.close()
        logging.debug("SQLite connection closed.")

# ──────────────────────────── ENTRYPOINT ────────────────────
if __name__ == "__main__":
    try:
        topic = input("Enter TOPIC for this batch: ").strip()
        if not topic:
            raise ValueError("Topic is required.")
        process_current_folder(topic)
        logging.info("Done.")
    except Exception as e:
        logging.error("Fatal error: %s", e)
        sys.exit(1)
