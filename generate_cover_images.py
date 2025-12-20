"""
Скрипт для генерации обложек статей.

Процесс:
1) Получает статьи из БД (id, title, cover_image_name)
2) Если cover_image_name уже заполнен — пропускает статью
3) Для остальных генерирует промпт обложки через OpenAI Chat Completions
4) Генерирует изображение через выбранный backend:
   - OpenAI GPT Image (Images API, b64_json)
   - Google NanoBanana Pro (Gemini API, gemini-3-pro-image-preview)
5) Сохраняет изображение в data/images как cover_image_{id}.jpg (JPEG)
6) Обновляет cover_image_name в БД

Зависимости:
- openai
- requests
- psycopg / psycopg2
- (опционально для Google) google-genai
- (опционально для Google) Pillow
"""

import os
import logging
import time
import base64
import requests
import tempfile
from io import BytesIO
from typing import Optional, List, Tuple, Any, Literal

from openai import OpenAI
from config import (
    OPENAI_API_KEY,
    OPENAI_MODEL_COVER_PROMPT,
    OPENAI_IMAGE_MODEL,
    GOOGLE_API_KEY,
)
from poster.db import get_pg_conn, get_refined_articles_tables

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

# Импортируем sql для работы с запросами
try:
    from psycopg import sql
except ImportError:
    from psycopg2 import sql

# Инициализация OpenAI клиента
OPENAI_CLIENT = OpenAI(api_key=OPENAI_API_KEY)

# Тип выбора бэкенда
ImageBackend = Literal["openai", "google"]

# Промпт для генерации промпта обложки
COVER_PROMPT_TEMPLATE = """Вот тебе заголовок нашей статьи, напиши идеальный промт для обложки для этой статьи.

Заголовок статьи: {title}

Напиши короткий, но детальный промпт на английском языке для генерации обложки. Промпт должен быть визуально привлекательным и отражать суть статьи.
На обложке может быть короткое название статьи из 2-3 слов отражающее её содержание.
Не включай в ответ ничего кроме самого промпта.
"""


def choose_image_backend() -> ImageBackend:
    """На старте предлагает выбрать, через какую модель генерировать изображение."""
    print("\nSelect image generation backend:")
    print("  1) OpenAI GPT Image")
    print("  2) Google NanoBanana Pro (gemini-3-pro-image-preview)")

    while True:
        choice = input("Enter 1 or 2 (default 1): ").strip() or "1"
        if choice == "1":
            logging.info("Selected image backend: OpenAI GPT Image")
            return "openai"
        if choice == "2":
            logging.info("Selected image backend: Google NanoBanana Pro")
            return "google"
        print("Invalid input. Please enter 1 or 2.")


def get_openai_image_generation_params() -> dict:
    """
    Параметры для генерации изображений через OpenAI Images API.
    Всегда сохраняем JPEG.
    """
    return {
        "model": OPENAI_IMAGE_MODEL,
        "size": "1536x1024",
        "quality": "medium",
        "n": 1,
        "output_format": "jpeg",  # ВСЕГДА JPEG
    }


def ensure_images_directory() -> str:
    """Создает папку data/images если её нет и возвращает путь к ней."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    images_dir = os.path.join(base_dir, "data", "images")
    os.makedirs(images_dir, exist_ok=True)
    logging.info("Images directory: %s", images_dir)
    return images_dir


def ensure_cover_image_column(pg_conn, table_name: str) -> None:
    """Гарантирует наличие колонки cover_image_name (чтобы SELECT/UPDATE не падали)."""
    check_query = sql.SQL("""
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = %s
          AND column_name = 'cover_image_name'
        LIMIT 1
    """)

    with pg_conn.cursor() as cur:
        cur.execute(check_query, (table_name,))
        exists = cur.fetchone() is not None

    if exists:
        return

    logging.warning("Column cover_image_name does not exist in %s, creating it...", table_name)
    alter_query = sql.SQL("""
        ALTER TABLE {table}
        ADD COLUMN cover_image_name VARCHAR(255)
    """).format(table=sql.Identifier(table_name))

    with pg_conn.cursor() as cur:
        cur.execute(alter_query)
    pg_conn.commit()
    logging.info("  ✓ Column cover_image_name created")


def generate_cover_prompt(title: str) -> Optional[str]:
    """Генерирует промпт для обложки на основе заголовка статьи (через OpenAI Chat Completions)."""
    logging.info("Generating cover prompt for title: %s", title)

    try:
        prompt = COVER_PROMPT_TEMPLATE.format(title=title)

        response = OPENAI_CLIENT.chat.completions.create(
            model=OPENAI_MODEL_COVER_PROMPT,
            messages=[{"role": "user", "content": prompt}],
            max_completion_tokens=200,
            temperature=0.7,
        )

        cover_prompt = response.choices[0].message.content.strip()
        logging.info(
            "  ✓ Generated cover prompt: %s",
            (cover_prompt[:100] + "...") if len(cover_prompt) > 100 else cover_prompt,
        )
        return cover_prompt

    except Exception as e:
        logging.error("  ✗ Failed to generate cover prompt: %s", e)
        return None


def _init_google_genai_client():
    """
    Инициализирует Google GenAI SDK client для Gemini Developer API.
    Требует:
      pip install google-genai
    """
    if not GOOGLE_API_KEY or not str(GOOGLE_API_KEY).strip():
        raise RuntimeError("GOOGLE_API_KEY is empty. Please set GOOGLE_API_KEY in config.py")

    try:
        from google import genai  # type: ignore
    except Exception as e:
        raise RuntimeError(
            "Google backend выбран, но пакет 'google-genai' не установлен. "
            "Установите: pip install google-genai"
        ) from e

    return genai.Client(api_key=GOOGLE_API_KEY)


def _require_pillow():
    try:
        from PIL import Image  # noqa: F401
    except Exception as e:
        raise RuntimeError(
            "Для Google backend нужна конвертация изображения в JPEG, "
            "но Pillow не установлен. Установите: pip install pillow"
        ) from e


def _pil_to_jpeg_bytes(pil_img, quality: int = 95) -> bytes:
    """PIL.Image.Image -> JPEG bytes (RGB)."""
    _require_pillow()
    # для JPEG нужен RGB
    if getattr(pil_img, "mode", None) != "RGB" and hasattr(pil_img, "convert"):
        pil_img = pil_img.convert("RGB")

    buf = BytesIO()
    pil_img.save(buf, format="JPEG", quality=quality, optimize=True)
    return buf.getvalue()


def _image_object_to_jpeg_bytes(img_obj, quality: int = 95) -> bytes:
    """
    Универсальная конвертация в JPEG bytes.

    Поддерживает:
    - PIL.Image.Image (есть .convert и .save)
    - google.genai.types.Image (обычно есть .show/.save и/или .data/.mime_type)
    - другие wrapper-объекты, если из них можно вытащить байты или сохранить
    """
    _require_pillow()
    from PIL import Image

    # 1) Если это уже PIL-like (есть convert + save)
    if hasattr(img_obj, "convert") and hasattr(img_obj, "save"):
        return _pil_to_jpeg_bytes(img_obj, quality=quality)

    # 2) Если wrapper хранит PIL внутри (частые имена)
    for attr in ("pil_image", "image", "_image", "_pil_image"):
        inner = getattr(img_obj, attr, None)
        if inner is not None and hasattr(inner, "convert") and hasattr(inner, "save"):
            return _pil_to_jpeg_bytes(inner, quality=quality)

    # 3) Если wrapper хранит bytes (частые имена)
    for attr in ("data", "_data", "bytes", "_bytes", "content", "_content"):
        b = getattr(img_obj, attr, None)
        if isinstance(b, (bytes, bytearray)) and b:
            pil = Image.open(BytesIO(bytes(b)))
            return _pil_to_jpeg_bytes(pil, quality=quality)

    # 4) Попытка сохранить в BytesIO через save()
    if hasattr(img_obj, "save"):
        buf = BytesIO()
        try:
            # некоторые реализации принимают file-like
            img_obj.save(buf, format="JPEG")
            data = buf.getvalue()
            if data:
                return data
        except TypeError:
            # возможно, save() принимает только путь
            pass
        except Exception:
            pass

        # 5) Если save() принимает только путь — временный файл
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=True) as tmp:
            try:
                img_obj.save(tmp.name)
                tmp.flush()
                tmp.seek(0)
                return tmp.read()
            except Exception as e:
                raise RuntimeError(f"Could not save Google Image object to temp file: {e}") from e

    raise RuntimeError(f"Unsupported image object type: {type(img_obj)} (no convert/save/data)")


def generate_image_bytes_openai(image_prompt: str) -> Tuple[Optional[bytes], Optional[str]]:
    """
    Генерирует изображение через OpenAI Images API.
    Возвращает (bytes, "jpg").
    """
    logging.info(
        "Generating image (OpenAI) with prompt: %s",
        (image_prompt[:100] + "...") if len(image_prompt) > 100 else image_prompt,
    )

    try:
        params = get_openai_image_generation_params()
        response = OPENAI_CLIENT.images.generate(
            prompt=image_prompt,
            **params,
        )

        data0 = response.data[0]
        ext = "jpg"

        b64 = getattr(data0, "b64_json", None)
        if b64:
            img_bytes = base64.b64decode(b64)
            logging.info("  ✓ OpenAI image generated (b64_json, %d bytes)", len(img_bytes))
            return img_bytes, ext

        # Fallback: url (если вдруг вернется)
        url = getattr(data0, "url", None)
        if url:
            logging.info("  ✓ OpenAI image generated (url): %s", url)
            r = requests.get(url, timeout=60)
            r.raise_for_status()
            return r.content, ext

        logging.error("  ✗ OpenAI Images API returned neither b64_json nor url. data[0]=%r", data0)
        return None, None

    except Exception as e:
        logging.error("  ✗ Failed to generate image (OpenAI): %s", e)
        return None, None


def generate_image_bytes_google(image_prompt: str, google_client) -> Tuple[Optional[bytes], Optional[str]]:
    """
    Генерирует изображение через Google NanoBanana Pro (Gemini 3 Pro Image Preview):
      model="gemini-3-pro-image-preview"
      image_size="2K"
      aspect_ratio="3:2"
    Возвращает (jpeg_bytes, "jpg").
    """
    logging.info(
        "Generating image (Google NanoBanana Pro) with prompt: %s",
        (image_prompt[:100] + "...") if len(image_prompt) > 100 else image_prompt,
    )

    try:
        from google.genai import types  # type: ignore

        aspect_ratio = "16:9"  # близко к 1536x1024
        image_size = "2K"     # как ты хотел

        response = google_client.models.generate_content(
            model="gemini-3-pro-image-preview",
            contents=[image_prompt],
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE"],
                image_config=types.ImageConfig(
                    aspect_ratio=aspect_ratio,
                    image_size=image_size,
                ),
            ),
        )

        # По докам: response.parts, части могут содержать inline_data и as_image()
        for part in getattr(response, "parts", []) or []:
            if getattr(part, "inline_data", None):
                img_obj = part.as_image()
                jpeg_bytes = _image_object_to_jpeg_bytes(img_obj, quality=95)
                logging.info("  ✓ Google image generated and converted to JPEG (%d bytes)", len(jpeg_bytes))
                return jpeg_bytes, "jpg"

        logging.error("  ✗ Google response contained no image parts.")
        return None, None

    except Exception as e:
        logging.error("  ✗ Failed to generate image (Google): %s", e)
        return None, None


def generate_image_bytes(
    image_backend: ImageBackend,
    image_prompt: str,
    google_client=None
) -> Tuple[Optional[bytes], Optional[str]]:
    """Маршрутизатор генерации изображения по выбранному backend."""
    if image_backend == "openai":
        return generate_image_bytes_openai(image_prompt)
    if image_backend == "google":
        return generate_image_bytes_google(image_prompt, google_client)
    logging.error("Unknown image backend: %s", image_backend)
    return None, None


def save_image_bytes(image_bytes: bytes, file_path: str) -> bool:
    """Сохраняет байты изображения в файл."""
    try:
        with open(file_path, "wb") as f:
            f.write(image_bytes)
        logging.info("  ✓ Image saved successfully: %s", file_path)
        return True
    except Exception as e:
        logging.error("  ✗ Failed to save image: %s", e)
        return False


def update_cover_image_name(pg_conn, table_name: str, article_id: int, cover_image_name: str) -> bool:
    """Обновляет cover_image_name для статьи в БД."""
    logging.info("Updating cover_image_name for article ID %d: %s", article_id, cover_image_name)

    try:
        ensure_cover_image_column(pg_conn, table_name)

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

        logging.warning("  No rows updated for article ID %d (article may not exist)", article_id)
        return False

    except Exception as e:
        logging.error("  ✗ Error updating cover_image_name: %s", e)
        pg_conn.rollback()
        return False


def get_articles_with_titles(pg_conn, table_name: str, article_ids: Optional[List[int]] = None) -> List[Any]:
    """Получает статьи с id, title, cover_image_name из таблицы."""
    logging.info("Fetching articles from table %s", table_name)
    ensure_cover_image_column(pg_conn, table_name)

    if article_ids:
        query = sql.SQL("""
            SELECT id, title, cover_image_name
            FROM {table}
            WHERE id = ANY(%s)
            ORDER BY id ASC
        """).format(table=sql.Identifier(table_name))
        params = (article_ids,)
    else:
        query = sql.SQL("""
            SELECT id, title, cover_image_name
            FROM {table}
            ORDER BY id ASC
        """).format(table=sql.Identifier(table_name))
        params = ()

    try:
        with pg_conn.cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()
            logging.info("  ✓ Fetched %d article(s)", len(rows))
            return rows
    except Exception as e:
        logging.error("  ✗ Error fetching articles: %s", e)
        raise


def _extract_article_id_title_cover(row: Any) -> Tuple[int, str, Optional[str]]:
    """Нормализует строку из fetchall к (id, title, cover_image_name)."""
    if isinstance(row, dict):
        return int(row["id"]), str(row["title"]), row.get("cover_image_name")

    try:
        return int(row["id"]), str(row["title"]), row.get("cover_image_name")  # type: ignore
    except Exception:
        cover = row[2] if len(row) >= 3 else None
        return int(row[0]), str(row[1]), cover


def _has_cover(cover_image_name: Optional[str]) -> bool:
    """True если cover_image_name заполнен (не NULL и не пустая строка)."""
    if cover_image_name is None:
        return False
    if isinstance(cover_image_name, str) and cover_image_name.strip() == "":
        return False
    return True


def generate_cover_for_article(
    pg_conn,
    table_name: str,
    article_id: int,
    title: str,
    images_dir: str,
    image_backend: ImageBackend,
    google_client=None,
) -> bool:
    """Генерирует обложку для одной статьи."""
    logging.info("")
    logging.info("=" * 60)
    logging.info("Processing article ID %d: %s", article_id, title)
    logging.info("=" * 60)

    cover_prompt = generate_cover_prompt(title)
    if not cover_prompt:
        logging.error("Failed to generate cover prompt, skipping article")
        return False

    image_bytes, ext = generate_image_bytes(image_backend, cover_prompt, google_client=google_client)
    if not image_bytes or not ext:
        logging.error("Failed to generate image bytes, skipping article")
        return False

    # Всегда сохраняем JPEG -> .jpg
    cover_image_name = f"cover_image_{article_id}.jpg"
    file_path = os.path.join(images_dir, cover_image_name)

    if not save_image_bytes(image_bytes, file_path):
        logging.error("Failed to save image, skipping article")
        return False

    if not update_cover_image_name(pg_conn, table_name, article_id, cover_image_name):
        logging.error("Failed to update database, but image was saved")
        return False

    logging.info("✓ Successfully generated cover for article ID %d", article_id)
    return True


def main():
    logging.info("=" * 60)
    logging.info("Cover Image Generator")
    logging.info("=" * 60)

    image_backend = choose_image_backend()

    google_client = None
    if image_backend == "google":
        try:
            google_client = _init_google_genai_client()
        except Exception as e:
            logging.error("Google backend init failed: %s", e)
            return

    images_dir = ensure_images_directory()

    try:
        pg_conn = get_pg_conn()
    except Exception as e:
        logging.error("Failed to connect to database: %s", e)
        return

    try:
        tables = get_refined_articles_tables(pg_conn)
        if not tables:
            logging.error("No refined_articles tables found!")
            return

        logging.info("")
        logging.info("Available tables:")
        for i, table in enumerate(tables, 1):
            logging.info("  %d. %s", i, table)

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

        logging.info("")
        article_choice = input(
            "Enter article IDs (comma-separated, e.g. '1,2,3' or '1-10' or press Enter for all): "
        ).strip()

        article_ids = None
        if article_choice:
            from poster.db import parse_id_selection
            article_ids = parse_id_selection(article_choice)
            logging.info("Selected article IDs: %s", article_ids)
        else:
            logging.info("Processing all articles")

        rows = get_articles_with_titles(pg_conn, selected_table, article_ids)
        if not rows:
            logging.warning("No articles found!")
            return

        logging.info("")
        logging.info("Found %d article(s) to process", len(rows))
        logging.info("Processing articles sequentially (one by one)...")
        logging.info("")

        success_count = 0
        fail_count = 0
        skipped_count = 0

        for idx, row in enumerate(rows, 1):
            article_id, title, cover_image_name = _extract_article_id_title_cover(row)

            logging.info("")
            logging.info(">>> Processing article %d of %d <<<", idx, len(rows))
            logging.info("")

            if _has_cover(cover_image_name):
                skipped_count += 1
                logging.info("↷ Skipped article ID %d (cover_image_name already set: %s)", article_id, cover_image_name)
            else:
                ok = generate_cover_for_article(
                    pg_conn=pg_conn,
                    table_name=selected_table,
                    article_id=article_id,
                    title=title,
                    images_dir=images_dir,
                    image_backend=image_backend,
                    google_client=google_client,
                )
                if ok:
                    success_count += 1
                    logging.info("✓ Article %d/%d completed successfully", idx, len(rows))
                else:
                    fail_count += 1
                    logging.error("✗ Article %d/%d failed", idx, len(rows))

            if idx < len(rows):
                logging.info("Waiting 2 seconds before next article...")
                time.sleep(2)

        logging.info("")
        logging.info("=" * 60)
        logging.info("Processing completed!")
        logging.info("  Success: %d", success_count)
        logging.info("  Failed: %d", fail_count)
        logging.info("  Skipped (already had cover): %d", skipped_count)
        logging.info("=" * 60)

    except KeyboardInterrupt:
        logging.warning("Interrupted by user")
    except Exception as e:
        logging.error("Fatal error: %s", e, exc_info=True)
    finally:
        try:
            pg_conn.close()
        except Exception:
            pass
        logging.info("Database connection closed")


if __name__ == "__main__":
    main()
