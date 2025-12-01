import os
import sys
import requests
import json
import logging
import re
import sqlite3
from contextlib import closing
from datetime import datetime
from typing import List, Tuple, Optional

# Импорт ваших промптов и конфигурации
from prompts import prompt_1, prompt_2, prompt_3
from config import ANTHROPIC_API_KEY, MODEL_NAME  # <-- MODEL_NAME добавлен вместо жёстко прошитого

# Логирование
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"  # актуальный заголовок по докам на 2025 год

# --- Работа с Anthropic ---

SESSION = requests.Session()
ADAPTER = requests.adapters.HTTPAdapter(max_retries=3)
SESSION.mount("https://", ADAPTER)
SESSION.mount("http://", ADAPTER)

def get_claude_response(messages: List[dict], max_tokens: int = 4000, temperature: float = 0.7) -> Tuple[Optional[str], List[dict]]:
    """
    Отправляет сообщения в Anthropic Messages API и возвращает текстовый ответ.
    Возвращает: (text_response | None, artifacts[])
    """
    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": ANTHROPIC_VERSION,
        "content-type": "application/json",
    }

    payload = {
        "model": MODEL_NAME,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }

    try:
        logging.debug("Sending request to Anthropic with payload: %s", payload)
        resp = SESSION.post(API_URL, headers=headers, json=payload, timeout=60)
    except requests.RequestException as e:
        logging.error("Network error contacting Anthropic: %s", e)
        return None, []

    if resp.status_code != 200:
        logging.error("Anthropic API error: %s", resp.status_code)
        try:
            logging.error(resp.text)
        except Exception:
            pass
        return None, []

    try:
        data = resp.json()
    except Exception as e:
        logging.error("Failed to parse JSON from Anthropic: %s", e)
        return None, []

    # content — это список блоков; нас интересуют текстовые
    content_blocks = data.get("content", [])
    text_parts = []
    artifacts = []
    for block in content_blocks:
        btype = block.get("type")
        if btype == "text":
            text_parts.append(block.get("text", ""))
        # В некоторых продуктах Anthropic встречаются иные типы; аккуратно собираем как «артефакты»
        if btype in {"artifact", "tool_use", "thinking"}:
            artifacts.append(block)

    text_response = "\n".join([t for t in text_parts if t])
    logging.debug("Received text from Anthropic (first 200 chars): %s", text_response[:200])
    return (text_response if text_response else None), artifacts


# --- Файлы/путь ---

def save_to_file(filename: str, content: str) -> None:
    with open(filename, "w", encoding="utf-8") as f:
        f.write(content)
    logging.info("Saved to %s", filename)


# --- База данных (SQLite) ---

def get_db_path() -> str:
    """Формирует путь к файлу articles.db в папке скрипта."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, "articles.db")

def create_db_and_table(db_path: str) -> sqlite3.Connection:
    """Создаёт (если нужно) БД SQLite и таблицу raw_articles."""
    logging.debug("Opening SQLite at %s", db_path)
    conn = sqlite3.connect(db_path)
    with closing(conn.cursor()) as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS raw_articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic TEXT,
                title TEXT,
                body TEXT,
                created_at TEXT
            )
        """)
        conn.commit()
    logging.debug("SQLite table 'raw_articles' is ready.")
    return conn

def insert_article(conn: sqlite3.Connection, topic: str, title: str, body: str) -> None:
    with closing(conn.cursor()) as cur:
        cur.execute("""
            INSERT INTO raw_articles (topic, title, body, created_at)
            VALUES (?, ?, ?, ?)
        """, (topic, title, body, datetime.utcnow().isoformat(timespec="seconds") + "Z"))
        conn.commit()
    logging.info("Article inserted into SQLite.")


# --- Парсинг текста статьи ---

TITLE_RE = re.compile(r"\btitle\s*:\s*(.*)", re.IGNORECASE)
BODY_MARK_RE = re.compile(r"\bbody\s*:\s*", re.IGNORECASE)

def parse_article_text(article_text: str):
    """
    Ищет 'title:' и 'body:' в тексте, независимо от регистра и формата.
    Возвращает (title, body) или (None, None), если не найдены.
    """
    if not article_text:
        return None, None

    # Регулярки с учётом переносов строк и пробелов
    pattern = re.compile(
        r"(?is)title\s*:\s*(?P<title>.*?)\n+body\s*:\s*(?P<body>.*)",
        re.DOTALL,
    )
    match = pattern.search(article_text.strip())
    if not match:
        logging.error("Could not parse title/body structure in article.")
        return None, None

    title = match.group("title").strip().strip('"').strip("'").strip("#").strip()
    body = match.group("body").strip()
    logging.debug("Parsed title: %s", title)
    logging.debug("Body (first 100 chars): %s", body[:100])
    return title, body


# --- Основной сценарий ---

def main():
    topic = input("Enter the article topic: ").strip()
    if not topic:
        logging.error("No topic provided. Exiting.")
        return

    logging.info("Using topic: %s", topic)

    try:
        num_articles = int(input("Enter the number of articles to generate: ").strip())
        if num_articles <= 0:
            raise ValueError
    except ValueError:
        logging.error("Invalid number provided. Exiting.")
        return

    db_path = get_db_path()
    conn = create_db_and_table(db_path)

    try:
        for i in range(num_articles):
            logging.info("Generating article %d of %d...", i + 1, num_articles)

            conversation: List[dict] = []

            # Step 1
            conversation.append({"role": "user", "content": prompt_1})
            response_1, _ = get_claude_response(conversation)
            if not response_1:
                logging.error("Failed to get response for prompt_1. Skipping article %d.", i + 1)
                continue
            conversation.append({"role": "assistant", "content": response_1})

            # Step 2
            conversation.append({"role": "user", "content": prompt_2})
            response_2, _ = get_claude_response(conversation)
            if not response_2:
                logging.error("Failed to get response for prompt_2. Skipping article %d.", i + 1)
                continue
            conversation.append({"role": "assistant", "content": response_2})

            # Step 3
            formatted_prompt_3 = prompt_3.replace("{TOPIC HERE}", topic)
            conversation.append({"role": "user", "content": formatted_prompt_3})
            response_3, _ = get_claude_response(conversation)
            if not response_3:
                logging.error("Failed to get response for prompt_3. Skipping article %d.", i + 1)
                continue

            # Сохраняем «сырую» выдачу
            safe_topic = re.sub(r"[^\w\-]+", "_", topic)
            filename = f"{safe_topic}_{i+1}.txt"
            save_to_file(filename, response_3)

            # Парсим title/body
            title, body = parse_article_text(response_3)
            if not title or not body:
                logging.error("Article parsing failed for article %d. Skipping.", i + 1)
                continue

            # Пишем в SQLite
            insert_article(conn, topic, title, body)
            logging.info("Article %d with title '%s' saved to SQLite successfully.", i + 1, title)

    finally:
        conn.close()
        logging.debug("SQLite connection closed.")


if __name__ == "__main__":
    main()
