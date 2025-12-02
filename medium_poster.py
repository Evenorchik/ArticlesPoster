"""
Скрипт для автоматического постинга статей на Medium через PyAutoGUI и Ads Power.
Читает статьи из PostgreSQL (таблица refined_articles_*) и публикует их на Medium.
"""
import os
import time
import logging
import random
import requests
import pyautogui
import pyperclip
import webbrowser
from typing import Optional, List
from contextlib import closing

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

# Config
from config import POSTGRES_DSN, LOG_LEVEL

# Логирование
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# Константы
MEDIUM_NEW_STORY_URL = "https://medium.com/new-story"
ADS_POWER_API_URL = "http://local.adspower.net:50325"
ADS_POWER_API_KEY = "856007acdf241361915ed26a00a6d70b"

# Номера профилей Ads Power (циклический перебор) - это profile_no, не profile_id
PROFILE_NOS = [74, 80, 70, 126, 125, 89, 90, 91, 92, 93]

# Координаты для кликов (из алгоритма пользователя)
COORDS_TITLE_INPUT = (516, 215)      # Шаг 3: ввод текста (title)
COORDS_PUBLISH_BUTTON_1 = (1180, 119)  # Шаг 7: первая кнопка Publish
COORDS_HASHTAGS_INPUT = (914, 438)   # Шаг 8: поле ввода хэштегов
COORDS_PUBLISH_BUTTON_2 = (933, 595) # Шаг 10: финальная кнопка Publish
COORDS_URL_BAR = (479, 60)          # Шаг 11: клик на строку браузера

# Задержки (базовые значения, будут рандомизированы)
WAIT_AFTER_OPEN_TAB = 10  # Шаг 2: ждём 10 секунд после открытия вкладки
WAIT_AFTER_TITLE_CLICK = 1  # Шаг 3: ждём 1 секунду после клика на поле title
WAIT_AFTER_TITLE_PASTE = 1  # Шаг 4: ждём 1 секунду после вставки title
WAIT_AFTER_ENTER = 1  # Шаг 5: ждём 1 секунду после Enter
WAIT_AFTER_BODY_PASTE = 1  # Шаг 6: ждём 1 секунду после вставки body
WAIT_AFTER_PUBLISH_1 = 3  # Шаг 7: ждём 3 секунды после первой кнопки Publish
WAIT_AFTER_HASHTAGS_CLICK = 1  # Шаг 8: ждём 1 секунду после клика на поле хэштегов
WAIT_BETWEEN_HASHTAGS = 1  # Шаг 9: ждём 1 секунду между хэштегами
WAIT_AFTER_PUBLISH_2 = 15  # Шаг 10: ждём 15 секунд после финальной кнопки Publish
WAIT_AFTER_URL_BAR_CLICK = 1  # Шаг 11: ждём 1 секунду после клика на адресную строку
WAIT_AFTER_COPY = 1  # Шаг 12: ждём 1 секунду после Ctrl+C

# Настройка PyAutoGUI
pyautogui.PAUSE = 0.1  # минимальная пауза между действиями PyAutoGUI
pyautogui.FAILSAFE = True  # перемещение мыши в угол экрана для остановки


def random_delay(base_seconds: float, variance_percent: float = 10.0) -> float:
    """
    Возвращает случайную задержку с вариацией ±variance_percent%.
    Например: random_delay(10.0, 10.0) вернёт значение от 9.0 до 11.0 секунд.
    """
    variance = base_seconds * (variance_percent / 100.0)
    min_delay = base_seconds - variance
    max_delay = base_seconds + variance
    delay = random.uniform(min_delay, max_delay)
    return delay


def wait_with_log(seconds: float, step_name: str, variance_percent: float = 10.0):
    """
    Ждёт указанное время с рандомизацией и логирует это.
    """
    actual_delay = random_delay(seconds, variance_percent)
    logging.debug("  [%s] Waiting %.2f seconds (base: %.1f ±%.0f%%)", 
                  step_name, actual_delay, seconds, variance_percent)
    time.sleep(actual_delay)


def get_pg_conn():
    """Возвращает подключение к PostgreSQL."""
    logging.debug("Connecting to PostgreSQL...")
    try:
        if _pg_v3:
            conn = psycopg.connect(POSTGRES_DSN, row_factory=dict_row)
        else:
            conn = psycopg.connect(POSTGRES_DSN)
            # Для psycopg2 нужно вручную настроить dict-like доступ
            from psycopg2.extras import RealDictCursor
            conn.cursor_factory = RealDictCursor
        logging.info("✓ Connected to PostgreSQL")
        return conn
    except Exception as e:
        logging.error("Failed to connect to PostgreSQL: %s", e)
        raise


def get_refined_articles_tables(pg_conn) -> List[str]:
    """Получает список таблиц refined_articles из БД."""
    logging.debug("Fetching refined_articles tables...")
    query = sql.SQL("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
        AND (
            table_name LIKE 'Refined_articles-%'
            OR table_name LIKE 'refined_articles_%'
            OR table_name LIKE 'RefinedArticles%'
        )
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
    """Проверяет и создаёт колонку profile_id, если её нет."""
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
    """Парсит строку с ID статей (поддерживает диапазоны и запятые)."""
    ids = []
    parts = s.replace(' ', '').split(',')
    
    for part in parts:
        if '-' in part:
            # Диапазон: "1-5"
            try:
                start, end = map(int, part.split('-'))
                ids.extend(range(start, end + 1))
            except ValueError:
                logging.warning("Invalid range format: %s", part)
        else:
            # Одиночный ID
            try:
                ids.append(int(part))
            except ValueError:
                logging.warning("Invalid ID format: %s", part)
    
    # Убираем дубликаты и сортируем
    return sorted(list(dict.fromkeys(ids)))


def get_articles_to_post(pg_conn, table_name: str, article_ids: Optional[List[int]] = None) -> List[dict]:
    """
    Получает статьи из таблицы для постинга по указанным ID.
    Если article_ids не указан, возвращает все неопубликованные статьи.
    """
    logging.debug("Getting articles from table: %s", table_name)
    
    # Проверяем наличие колонки hashtag5
    logging.debug("Checking for hashtag5 column...")
    check_col_query = sql.SQL("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = %s AND column_name = 'hashtag5'
    """)
    
    with pg_conn.cursor() as cur:
        cur.execute(check_col_query, (table_name,))
        has_hashtag5 = cur.fetchone() is not None
        logging.info("Table has hashtag5 column: %s", has_hashtag5)
    
    # Формируем запрос в зависимости от наличия hashtag5
    if has_hashtag5:
        select_cols = "id, topic, title, body, hashtag1, hashtag2, hashtag3, hashtag4, hashtag5, url, profile_id"
    else:
        select_cols = "id, topic, title, body, hashtag1, hashtag2, hashtag3, hashtag4, url, profile_id"
    
    if article_ids:
        # Получаем статьи по указанным ID
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
        # Берем только неопубликованные (url IS NULL или пустой)
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
            cur.execute(query, params)
            articles = cur.fetchall()
            logging.info("Fetched %d article(s) from database", len(articles))
            if articles:
                logging.debug("Article IDs: %s", [a['id'] if isinstance(a, dict) else a[0] for a in articles[:10]])
            return articles
    except Exception as e:
        logging.error("Error fetching articles: %s", e)
        logging.error("Query: %s", query.as_string(pg_conn) if hasattr(query, 'as_string') else str(query))
        raise


def update_article_url_and_profile(pg_conn, table_name: str, article_id: int, url: str, profile_id: int) -> None:
    """Обновляет URL и profile_id опубликованной статьи в БД."""
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


def check_ads_power_profile_status(profile_no: int) -> Optional[dict]:
    """
    Проверяет статус профиля Ads Power через API v2.
    Использует profile_no (номер профиля), не profile_id.
    Возвращает информацию о профиле или None в случае ошибки.
    """
    logging.debug("Checking status of Ads Power profile No: %s", profile_no)
    
    endpoint = f"{ADS_POWER_API_URL}/api/v2/browser-profile/active"
    
    # Используем GET запрос с параметром profile_no
    params = {
        "profile_no": str(profile_no)
    }
    
    # Формируем заголовки (добавляем API key, если указан)
    headers = {}
    if ADS_POWER_API_KEY:
        headers["Authorization"] = f"Bearer {ADS_POWER_API_KEY}"
        logging.debug("  Using API key for authentication")
    
    try:
        logging.debug("  GET request to: %s with params: %s", endpoint, params)
        response = requests.get(endpoint, params=params, headers=headers, timeout=10)
        logging.debug("  Response status code: %s", response.status_code)
        
        if response.status_code == 200:
            data = response.json()
            logging.debug("  Response data: %s", data)
            
            if data.get("code") == 0:
                profile_data = data.get("data", {})
                status = profile_data.get("status", "Unknown")
                logging.info("Profile No %s status: %s", profile_no, status)
                return profile_data
            else:
                error_msg = data.get("msg", "Unknown error")
                logging.debug("  API returned error: %s", error_msg)
                return None
        else:
            logging.debug("  HTTP error: %s", response.status_code)
            return None
            
    except requests.exceptions.RequestException as e:
        logging.error("✗ Request error checking profile status: %s", e)
        return None
    except Exception as e:
        logging.error("✗ Unexpected error checking profile status: %s", e)
        return None


def activate_ads_power_profile(profile_no: int) -> bool:
    """
    Активирует (разворачивает) уже открытый профиль Ads Power.
    Использует PyAutoGUI для активации окна браузера.
    Возвращает True если успешно, False в противном случае.
    """
    logging.info("Activating Ads Power profile No: %s", profile_no)
    
    # Пробуем через PyAutoGUI найти и активировать окно браузера
    try:
        import pygetwindow as gw
        
        # Ищем окна браузера (Chrome, Edge и т.д.)
        browser_windows = []
        for window in gw.getAllWindows():
            title = window.title.lower()
            if any(browser in title for browser in ['chrome', 'edge', 'brave', 'opera']):
                if window.visible:
                    browser_windows.append(window)
        
        if browser_windows:
            # Активируем первое найденное окно браузера
            window = browser_windows[0]
            window.activate()
            window.maximize()
            logging.info("✓ Profile window activated via PyAutoGUI")
            return True
        else:
            logging.warning("No browser windows found to activate")
            return False
            
    except ImportError:
        logging.warning("pygetwindow not available, cannot activate window")
        logging.info("Please install: pip install pygetwindow")
        return False
    except Exception as e:
        logging.warning("Failed to activate window via PyAutoGUI: %s", e)
        return False


def open_ads_power_profile(profile_no: int) -> Optional[str]:
    """
    Открывает или активирует профиль Ads Power через API v2.
    Использует profile_no (номер профиля), не profile_id.
    Сначала проверяет статус профиля через GET /api/v2/browser-profile/active.
    Если профиль активен - активирует окно и открывает URL.
    Если не активен - открывает профиль через POST /api/v2/browser-profile/start.
    Возвращает profile_no или None в случае ошибки.
    """
    logging.info("Opening/activating Ads Power profile No: %s", profile_no)
    
    # Шаг 1: Проверяем статус профиля
    profile_status = check_ads_power_profile_status(profile_no)
    
    if profile_status:
        status = profile_status.get("status", "Unknown")
        logging.info("Profile No %s status: %s", profile_no, status)
        
        if status == "Active":
            # Профиль уже открыт - активируем окно
            logging.info("Profile No %s is already active, activating window...", profile_no)
            if activate_ads_power_profile(profile_no):
                # Открываем URL в уже открытом профиле через webbrowser
                logging.info("✓ Profile No %s activated, opening URL...", profile_no)
                try:
                    webbrowser.open(MEDIUM_NEW_STORY_URL)
                    time.sleep(2)  # Даём время на открытие URL
                except Exception as e:
                    logging.warning("Failed to open URL via webbrowser: %s", e)
                
                return str(profile_no)
            else:
                logging.warning("Failed to activate window, but profile is active")
                return str(profile_no)
    
    # Шаг 2: Профиль не активен - открываем его через API v2
    logging.info("Profile No %s is not active, opening new instance...", profile_no)
    
    # Используем правильный endpoint для API v2
    endpoint = f"{ADS_POWER_API_URL}/api/v2/browser-profile/start"
    
    # Формируем заголовки
    headers = {
        "Content-Type": "application/json"
    }
    
    # Добавляем API key, если он указан
    if ADS_POWER_API_KEY:
        headers["Authorization"] = f"Bearer {ADS_POWER_API_KEY}"
        logging.debug("  Using API key for authentication")
    
    # Формируем payload с profile_no (в формате строки)
    payload = {
        "profile_no": str(profile_no)
    }
    
    try:
        logging.debug("  POST request to: %s", endpoint)
        logging.debug("  Headers: %s", {k: v if k != "Authorization" else "Bearer ***" for k, v in headers.items()})
        logging.debug("  Payload: %s", payload)
        
        response = requests.post(endpoint, json=payload, headers=headers, timeout=30)
        logging.debug("  Response status code: %s", response.status_code)
        
        if response.status_code == 200:
            data = response.json()
            logging.debug("  Response data: %s", data)
            
            if data.get("code") == 0:
                logging.info("✓ Profile No %s opened successfully", profile_no)
                # Ждём немного, чтобы браузер успел открыться
                time.sleep(3)
                
                # Открываем URL в открытом профиле
                try:
                    webbrowser.open(MEDIUM_NEW_STORY_URL)
                    time.sleep(2)
                except Exception as e:
                    logging.warning("Failed to open URL via webbrowser: %s", e)
                
                return str(profile_no)
            else:
                error_msg = data.get("msg", data.get("message", "Unknown error"))
                error_code = data.get("code", "N/A")
                logging.error("✗ Ads Power API error (code: %s): %s", error_code, error_msg)
                return None
        else:
            logging.error("✗ HTTP error: %s", response.status_code)
            try:
                error_data = response.json()
                logging.error("  Error response: %s", error_data)
            except:
                logging.error("  Error response (text): %s", response.text)
            return None
            
    except requests.exceptions.Timeout:
        logging.error("✗ Timeout while opening profile (request took >30s)")
        return None
    except requests.exceptions.ConnectionError as e:
        logging.error("✗ Connection error: %s", e)
        logging.error("  Make sure Ads Power is running and Local API is enabled")
        logging.error("  Check API URL: %s", ADS_POWER_API_URL)
        return None
    except requests.exceptions.RequestException as e:
        logging.error("✗ Request error: %s", e)
        return None
    except Exception as e:
        logging.error("✗ Unexpected error: %s", e, exc_info=True)
        return None


def close_ads_power_profile(profile_id: int) -> bool:
    """Закрывает профиль Ads Power через API."""
    logging.debug("Closing Ads Power profile ID: %s", profile_id)
    
    url = f"{ADS_POWER_API_URL}/api/v1/user/stop"
    headers = {
        "Content-Type": "application/json"
    }
    payload = {
        "user_ids": [str(profile_id)]
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        if data.get("code") == 0:
            logging.debug("✓ Profile %s closed successfully", profile_id)
            return True
        else:
            logging.warning("Ads Power API warning when closing profile %s: %s", profile_id, data.get("msg"))
            return False
    except Exception as e:
        logging.warning("Failed to close Ads Power profile %s: %s", profile_id, e)
        return False


def post_article_to_medium(article: dict, profile_no: int) -> Optional[str]:
    """
    Публикует статью на Medium через PyAutoGUI.
    Возвращает URL опубликованной статьи или None в случае ошибки.
    """
    article_id = article.get('id') if isinstance(article, dict) else article[0]
    logging.info("="*60)
    logging.info("Posting article ID %s using profile No %s", article_id, profile_no)
    logging.info("="*60)
    
    try:
        # Извлекаем данные статьи
        if isinstance(article, dict):
            title = article.get('title', '').strip()
            body = article.get('body', '').strip()
            hashtags = [
                article.get('hashtag1', '').strip(),
                article.get('hashtag2', '').strip(),
                article.get('hashtag3', '').strip(),
                article.get('hashtag4', '').strip(),
                article.get('hashtag5', '').strip() if article.get('hashtag5') else ''
            ]
        else:
            # Если это tuple (старый формат)
            title = article[2] if len(article) > 2 else ''
            body = article[3] if len(article) > 3 else ''
            hashtags = [
                article[4] if len(article) > 4 else '',
                article[5] if len(article) > 5 else '',
                article[6] if len(article) > 6 else '',
                article[7] if len(article) > 7 else '',
                article[8] if len(article) > 8 else ''
            ]
        
        # Фильтруем пустые хэштеги
        hashtags = [h for h in hashtags if h]
        
        logging.info("Article title: %s", title[:50] + "..." if len(title) > 50 else title)
        logging.info("Article body length: %d characters", len(body))
        logging.info("Hashtags: %s", hashtags)
        logging.info("")
        
        # Шаг 1: Открываем новую вкладку с ссылкой
        logging.info("="*60)
        logging.info("STEP 1: Opening new tab with Medium new story URL...")
        logging.info("  URL: %s", MEDIUM_NEW_STORY_URL)
        try:
            webbrowser.open_new_tab(MEDIUM_NEW_STORY_URL)
            logging.info("  ✓ Tab opened successfully")
        except Exception as e:
            logging.error("  ✗ Failed to open tab: %s", e)
            return None
        
        # Шаг 2: Ждём 10 секунд (рандомизировано)
        logging.info("STEP 2: Waiting for page to load...")
        wait_with_log(WAIT_AFTER_OPEN_TAB, "STEP 2", 10.0)
        logging.info("  ✓ Wait completed")
        
        # Шаг 3: Кликаем на поле ввода текста (title)
        logging.info("STEP 3: Clicking on title input field...")
        logging.info("  Coordinates: %s", COORDS_TITLE_INPUT)
        try:
            pyautogui.click(*COORDS_TITLE_INPUT)
            logging.info("  ✓ Clicked successfully")
        except Exception as e:
            logging.error("  ✗ Failed to click: %s", e)
            return None
        
        wait_with_log(WAIT_AFTER_TITLE_CLICK, "STEP 3", 10.0)
        
        # Шаг 4: Вставляем title
        logging.info("STEP 4: Pasting title...")
        logging.info("  Title length: %d characters", len(title))
        try:
            pyperclip.copy(title)
            time.sleep(0.2)
            pyautogui.hotkey('ctrl', 'v')
            logging.info("  ✓ Title pasted successfully")
        except Exception as e:
            logging.error("  ✗ Failed to paste title: %s", e)
            return None
        
        wait_with_log(WAIT_AFTER_TITLE_PASTE, "STEP 4", 10.0)
        
        # Шаг 5: Нажимаем Enter
        logging.info("STEP 5: Pressing Enter...")
        try:
            pyautogui.press('enter')
            logging.info("  ✓ Enter pressed successfully")
        except Exception as e:
            logging.error("  ✗ Failed to press Enter: %s", e)
            return None
        
        wait_with_log(WAIT_AFTER_ENTER, "STEP 5", 10.0)
        
        # Шаг 6: Вставляем body
        logging.info("STEP 6: Pasting body...")
        logging.info("  Body length: %d characters", len(body))
        try:
            pyperclip.copy(body)
            time.sleep(0.2)
            pyautogui.hotkey('ctrl', 'v')
            logging.info("  ✓ Body pasted successfully")
        except Exception as e:
            logging.error("  ✗ Failed to paste body: %s", e)
            return None
        
        wait_with_log(WAIT_AFTER_BODY_PASTE, "STEP 6", 10.0)
        
        # Шаг 7: Кликаем на первую кнопку Publish
        logging.info("STEP 7: Clicking first Publish button...")
        logging.info("  Coordinates: %s", COORDS_PUBLISH_BUTTON_1)
        try:
            pyautogui.click(*COORDS_PUBLISH_BUTTON_1)
            logging.info("  ✓ Clicked successfully")
        except Exception as e:
            logging.error("  ✗ Failed to click: %s", e)
            return None
        
        wait_with_log(WAIT_AFTER_PUBLISH_1, "STEP 7", 10.0)
        
        # Шаг 8: Кликаем на поле ввода хэштегов
        logging.info("STEP 8: Clicking on hashtags input field...")
        logging.info("  Coordinates: %s", COORDS_HASHTAGS_INPUT)
        try:
            pyautogui.click(*COORDS_HASHTAGS_INPUT)
            logging.info("  ✓ Clicked successfully")
        except Exception as e:
            logging.error("  ✗ Failed to click: %s", e)
            return None
        
        wait_with_log(WAIT_AFTER_HASHTAGS_CLICK, "STEP 8", 10.0)
        
        # Шаг 9: Вставляем хэштеги через запятую (каждый отдельно с запятой)
        logging.info("STEP 9: Pasting hashtags one by one...")
        logging.info("  Hashtags to paste: %s", hashtags[:5])
        try:
            for i, hashtag in enumerate(hashtags[:5]):  # Максимум 5 хэштегов
                if hashtag:
                    logging.debug("  Pasting hashtag %d/%d: %s", i+1, len(hashtags[:5]), hashtag)
                    pyperclip.copy(hashtag)
                    time.sleep(0.2)
                    pyautogui.hotkey('ctrl', 'v')
                    wait_with_log(WAIT_BETWEEN_HASHTAGS, f"STEP 9 hashtag {i+1}", 10.0)
                    
                    if i < len(hashtags[:5]) - 1:  # Не добавляем запятую после последнего
                        logging.debug("  Adding comma after hashtag %d", i+1)
                        pyautogui.write(',', interval=0.1)
                        wait_with_log(WAIT_BETWEEN_HASHTAGS, f"STEP 9 comma {i+1}", 10.0)
            
            logging.info("  ✓ All hashtags pasted successfully")
            logging.info("  Final hashtags: %s", ", ".join(hashtags[:5]))
        except Exception as e:
            logging.error("  ✗ Failed to paste hashtags: %s", e)
            return None
        
        # Шаг 10: Кликаем на финальную кнопку Publish
        logging.info("STEP 10: Clicking final Publish button...")
        logging.info("  Coordinates: %s", COORDS_PUBLISH_BUTTON_2)
        try:
            pyautogui.click(*COORDS_PUBLISH_BUTTON_2)
            logging.info("  ✓ Clicked successfully")
        except Exception as e:
            logging.error("  ✗ Failed to click: %s", e)
            return None
        
        wait_with_log(WAIT_AFTER_PUBLISH_2, "STEP 10", 10.0)
        logging.info("  ✓ Publication should be complete")
        
        # Шаг 11: Кликаем на строку браузера
        logging.info("STEP 11: Clicking on URL bar...")
        logging.info("  Coordinates: %s", COORDS_URL_BAR)
        try:
            pyautogui.click(*COORDS_URL_BAR)
            logging.info("  ✓ Clicked successfully")
        except Exception as e:
            logging.error("  ✗ Failed to click: %s", e)
            return None
        
        wait_with_log(WAIT_AFTER_URL_BAR_CLICK, "STEP 11", 10.0)
        
        # Шаг 12: Копируем URL (Ctrl+C)
        logging.info("STEP 12: Copying URL (Ctrl+C)...")
        try:
            pyautogui.hotkey('ctrl', 'c')
            wait_with_log(WAIT_AFTER_COPY, "STEP 12", 10.0)
            url = pyperclip.paste()
            logging.info("  ✓ URL copied from clipboard")
            logging.info("  Retrieved URL: %s", url)
        except Exception as e:
            logging.error("  ✗ Failed to copy URL: %s", e)
            return None
        
        # Шаг 13: Проверяем и возвращаем URL
        if url and url.startswith('http'):
            logging.info("="*60)
            logging.info("✓ Article published successfully!")
            logging.info("URL: %s", url)
            logging.info("="*60)
            return url
        else:
            logging.warning("="*60)
            logging.warning("⚠ URL not retrieved or invalid")
            logging.warning("  Clipboard content: %s", url)
            logging.warning("  Expected: URL starting with 'http'")
            logging.warning("="*60)
            return None
        
    except Exception as e:
        logging.error("Error posting article ID %s: %s", article_id, e, exc_info=True)
        return None


def main():
    """Основная функция."""
    logging.info("="*60)
    logging.info("Starting Medium Poster Script (PyAutoGUI + Ads Power)")
    logging.info("="*60)
    
    # Подключение к PostgreSQL
    logging.info("Connecting to PostgreSQL...")
    pg_conn = get_pg_conn()
    
    try:
        # Получаем список таблиц
        tables = get_refined_articles_tables(pg_conn)
        if not tables:
            logging.error("No refined_articles tables found in database!")
            return
        
        # Выбор таблицы
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
            # Пользователь ввёл имя таблицы напрямую
            if table_choice in tables:
                selected_table = table_choice
            else:
                logging.error("Table '%s' not found!", table_choice)
                return
        
        logging.info("Selected table: %s", selected_table)
        
        # Проверяем/создаём колонку profile_id
        ensure_profile_id_column(pg_conn, selected_table)
        
        # Выбор статей
        logging.info("")
        article_selection = input("Enter article IDs (e.g., '1,2,3' or '1-5,10' or leave empty for all unpublished): ").strip()
        
        if article_selection:
            article_ids = parse_id_selection(article_selection)
            logging.info("Selected article IDs: %s", article_ids)
        else:
            article_ids = None
            logging.info("Will fetch all unpublished articles")
        
        # Получаем статьи
        articles = get_articles_to_post(pg_conn, selected_table, article_ids)
        
        if not articles:
            logging.warning("No articles to post!")
            return
        
        # Фильтруем уже опубликованные статьи
        unpublished_articles = []
        for article in articles:
            article_id = article.get('id') if isinstance(article, dict) else article[0]
            url = article.get('url') if isinstance(article, dict) else (article[-2] if len(article) > 1 else None)
            if not url or url.strip() == '':
                unpublished_articles.append(article)
            else:
                logging.info("Skipping article ID %s (already published: %s)", article_id, url)
        
        if not unpublished_articles:
            logging.warning("All selected articles are already published!")
            return
        
        logging.info("Articles to post: %d", len(unpublished_articles))
        logging.info("")
        
        # Подтверждение
        response = input(f"Ready to post {len(unpublished_articles)} article(s). Press Enter to start, or 'q' to quit: ").strip().lower()
        if response == 'q':
            logging.info("Aborted by user")
            return
        
        # Циклический перебор профилей
        profile_index = 0
        posted_count = 0
        failed_count = 0
        
        for article in unpublished_articles:
            article_id = article.get('id') if isinstance(article, dict) else article[0]
            
            # Выбираем профиль (циклический перебор)
            profile_no = PROFILE_NOS[profile_index % len(PROFILE_NOS)]
            profile_index += 1
            
            logging.info("")
            logging.info("="*60)
            logging.info("Processing article ID %s with profile No %s", article_id, profile_no)
            logging.info("="*60)
            
            # Открываем профиль Ads Power
            result = open_ads_power_profile(profile_no)
            if not result:
                logging.error("Failed to open profile No %s, skipping article ID %s", profile_no, article_id)
                failed_count += 1
                continue
            
            # Ждём, пока браузер откроется
            time.sleep(5)
            
            try:
                # Публикуем статью
                url = post_article_to_medium(article, profile_no)
                
                if url:
                    # Обновляем БД (сохраняем profile_no как profile_id в БД)
                    update_article_url_and_profile(pg_conn, selected_table, article_id, url, profile_no)
                    posted_count += 1
                    logging.info("✓ Article ID %s posted successfully!", article_id)
                else:
                    failed_count += 1
                    logging.error("✗ Failed to post article ID %s", article_id)
                
            finally:
                # Профиль оставляем открытым (не закрываем)
                pass
            
            # Пауза между статьями (небольшая пауза для стабильности)
            if article != unpublished_articles[-1]:  # Не пауза после последней статьи
                pause_time = random_delay(5.0, 10.0)  # 5 секунд ±10%
                logging.info("Waiting %.2f seconds before next article...", pause_time)
                time.sleep(pause_time)
        
        # Итоги
        logging.info("")
        logging.info("="*60)
        logging.info("Posting completed!")
        logging.info("  Posted: %d", posted_count)
        logging.info("  Failed: %d", failed_count)
        logging.info("="*60)
        
    except KeyboardInterrupt:
        logging.warning("Interrupted by user")
    except Exception as e:
        logging.error("Fatal error: %s", e, exc_info=True)
    finally:
        pg_conn.close()
        logging.info("PostgreSQL connection closed")


if __name__ == "__main__":
    main()
