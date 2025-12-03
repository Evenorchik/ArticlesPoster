import os
# === OpenAI ===
# Ключ и модели для шагов:
# - структурирование (prompt_4): OPENAI_MODEL (обычно "gpt-5.1")
# - лёгкое перефразирование: OPENAI_MODEL_THINKING (например "gpt-5.1-thinking"; если нет — можно тоже "gpt-5.1")
OPENAI_API_KEY = "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"           # <-- вставь свой ключ
OPENAI_MODEL = "gpt-5.1"
OPENAI_MODEL_THINKING = "gpt-5.1-thinking"

# === Локальная SQLite ===
# Файл БД лежит рядом со скриптом. Можно задать абсолютный путь.
SQLITE_DB_FILENAME = "articles.db"

# === Postgres (для Directus) ===
# Пример DSN: postgresql://fraxi:Art1clesss@127.0.0.1:5432/articles
POSTGRES_DSN = "postgresql://fraxi:Art1clesss@194.163.130.97:5432/articles?connect_timeout=15"

# === Humanizer (PyAutoGUI) ===
# Если поменяешь сайт/координаты — обнови тут.
HUMANIZER_URL = "https://gpthumanizer.io/"
SCROLL_COORDS = (1673, 463)
PASTE_COORDS = (446, 216)
HUMANIZE_COORDS = (484, 876)
SCROLL_COORDS_TWO = (1672, 247)
COPY_COORDS = (1357, 840)

# === Логи ===
LOG_LEVEL = "DEBUG"  # "INFO" | "DEBUG" и т.д.
LOG_MODE = "SUMMARY"  # "DEBUG" | "SUMMARY" - режим логирования для scheduled_poster
# DEBUG - полное логирование, SUMMARY - сокращенное (тема, профиль, время, ссылка)

# === Поведение ===
# Пауза между обработкой статей (сек)
SLEEP_BETWEEN_ARTICLES_SEC = 5
# Пауза ожидания humanizer (сек)
HUMANIZER_WAIT_SEC = 20

# === Альтернативный промпт для ссылок ===
# Каждая N-я статья будет обрабатываться с альтернативным промптом (prompt_4_links)
# Например, если ALTERNATIVE_PROMPT_FREQUENCY = 5, то каждая 5-я статья будет с альтернативным промптом
ALTERNATIVE_PROMPT_FREQUENCY = 5  # 1 из 5 статей (можно изменить на 4, 3 и т.д.)